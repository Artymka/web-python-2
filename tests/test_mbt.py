import os
import shutil
import socket
import threading
import time
from typing import Any
import hypothesis.strategies as st
import pytest
import requests
from hypothesis import settings
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    precondition,
    rule,
    run_state_machine_as_test,
)
from werkzeug.serving import make_server

import src.model as server_model
from src.app import app
from src.client import ApiClient

SERVER_HOST = "127.0.0.1"
KEY_STRATEGY = st.integers(min_value=1, max_value=1 << 20)
SAFE_TEXT = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters=" _-",
    ),
    min_size=1,
    max_size=20,
)


class ServerThread(threading.Thread):
    """Фоновый поток с WSGI сервером для тестирования API."""

    def __init__(self, flask_app, host: str, port: int):
        """Инициализация потока тестового сервера."""
        super().__init__(daemon=True)
        self.server = make_server(host, port, flask_app)

    def run(self) -> None:
        """Запуск обслуживания запросов."""
        self.server.serve_forever()

    def shutdown(self) -> None:
        """Остановка обслуживания запросов."""
        self.server.shutdown()


def _find_free_port() -> int:
    """Находит свободный порт для запуска сервера."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


def _clean_io_dirs() -> None:
    """Очищает директории input и output."""
    for folder in ("input", "output"):
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder, exist_ok=True)


class ApiStateMachine(RuleBasedStateMachine):
    """Стейт-машина для тестирования API всех эндпоинтов."""

    server_thread: ServerThread | None = None
    client: ApiClient

    def __init__(self):
        """Инициализация состояния теста."""
        super().__init__()
        server_model.reset_state()

        self.sessions: dict[int, dict] = {}
        self.tasks: dict[int, dict] = {}
        self.completions: dict[int, dict] = {}

    @initialize()
    def setup_seed(self) -> None:
        """Начальное заполнение связанными данными."""
        sess_key = 1001
        self.client.insert_session(sess_key, "127.0.0.1", "ru", "seed_ua")
        self.sessions[sess_key] = {
            "key": sess_key,
            "ip": "127.0.0.1",
            "locale": "ru",
            "user_agent": "seed_ua",
        }

        task_key = 2001
        self.client.insert_task(task_key, sess_key, "seed_param", "seed_desc")
        self.tasks[task_key] = {
            "key": task_key,
            "session": sess_key,
            "parameter": "seed_param",
            "description": "seed_desc",
            "done": 0,
        }

    @rule(key=KEY_STRATEGY, ip=SAFE_TEXT, locale=SAFE_TEXT, ua=SAFE_TEXT)
    def insert_session(self, key: int, ip: str, locale: str, ua: str) -> None:
        """Проверяет эндпоинт создания сессии PUT /insert/session/:key."""
        resp = self.client.insert_session(key, ip, locale, ua)
        if key in self.sessions:
            assert resp["status_code"] == 400
        else:
            assert resp["status_code"] == 200
            self.sessions[key] = {
                "key": key,
                "ip": ip,
                "locale": locale,
                "user_agent": ua,
            }

    @rule()
    def query_session(self) -> None:
        """Проверяет эндпоинт GET /query/session."""
        resp = self.client.query_session()
        assert resp["status_code"] == 200

    @precondition(lambda self: bool(self.sessions))
    @rule(data=st.data())
    def single_session(self, data: Any) -> None:
        """Проверяет эндпоинт GET /single/session для существующего ключа."""
        key = data.draw(st.sampled_from(list(self.sessions.keys())))
        resp = self.client.single_session(key)
        assert resp["status_code"] == 200

    @rule(key=KEY_STRATEGY)
    def single_session_missing(self, key: int) -> None:
        """Проверяет эндпоинт GET /single/session для отсутствующего ключа."""
        if key in self.sessions:
            return
        resp = self.client.single_session(key)
        assert resp["status_code"] == 404

    @precondition(lambda self: bool(self.sessions))
    @rule(data=st.data())
    def delete_session(self, data: Any) -> None:
        """Проверяет эндпоинт POST /delete/session для существующей сессии."""
        key = data.draw(st.sampled_from(list(self.sessions.keys())))
        resp = self.client.delete_session(key)
        assert resp["status_code"] == 200
        self.sessions.pop(key, None)

    @rule(key=KEY_STRATEGY)
    def delete_session_missing(self, key: int) -> None:
        """Проверяет POST /delete/session для отсутствующей сессии."""
        if key in self.sessions:
            return
        resp = self.client.delete_session(key)
        assert resp["status_code"] == 404

    @precondition(lambda self: bool(self.sessions))
    @rule(
        data=st.data(),
        key=KEY_STRATEGY,
        parameter=SAFE_TEXT,
        description=SAFE_TEXT,
    )
    def insert_task(
        self, data: Any, key: int, parameter: str, description: str
    ) -> None:
        """Проверяет создание задачи через PUT /insert/task/:key."""
        sess_key = data.draw(st.sampled_from(list(self.sessions.keys())))
        resp = self.client.insert_task(key, sess_key, parameter, description)
        if key in self.tasks:
            assert resp["status_code"] == 400
        else:
            assert resp["status_code"] == 200
            self.tasks[key] = {
                "key": key,
                "session": sess_key,
                "parameter": parameter,
                "description": description,
                "done": 0,
            }

    @precondition(lambda self: bool(self.sessions))
    @rule(data=st.data())
    def query_task(self, data: Any) -> None:
        """Проверяет эндпоинт GET /query/task/:session."""
        sess_key = data.draw(st.sampled_from(list(self.sessions.keys())))
        resp = self.client.query_task(sess_key)
        assert resp["status_code"] == 200

    @precondition(lambda self: bool(self.tasks))
    @rule(data=st.data())
    def single_task(self, data: Any) -> None:
        """Проверяет эндпоинт GET /single/task для существующей задачи."""
        key = data.draw(st.sampled_from(list(self.tasks.keys())))
        resp = self.client.single_task(key)
        assert resp["status_code"] == 200

    @rule(key=KEY_STRATEGY)
    def single_task_missing(self, key: int) -> None:
        """Проверяет эндпоинт GET /single/task для отсутствующей задачи."""
        if key in self.tasks:
            return
        resp = self.client.single_task(key)
        assert resp["status_code"] == 404

    @precondition(lambda self: bool(self.tasks))
    @rule(data=st.data())
    def delete_task(self, data: Any) -> None:
        """Проверяет POST /delete/task для существующей задачи."""
        key = data.draw(st.sampled_from(list(self.tasks.keys())))
        resp = self.client.delete_task(key)
        assert resp["status_code"] == 200
        self.tasks.pop(key, None)

    @rule(key=KEY_STRATEGY)
    def delete_task_missing(self, key: int) -> None:
        """Проверяет POST /delete/task для отсутствующей задачи."""
        if key in self.tasks:
            return
        resp = self.client.delete_task(key)
        assert resp["status_code"] == 404

    @precondition(lambda self: bool(self.tasks))
    @rule(data=st.data())
    def query_completion(self, data: Any) -> None:
        """Проверяет эндпоинт GET /query/completion/:task."""
        task_key = data.draw(st.sampled_from(list(self.tasks.keys())))
        resp = self.client.query_completion(task_key)
        assert resp["status_code"] == 200

    @precondition(lambda self: bool(self.tasks))
    @rule(data=st.data())
    def single_completion(self, data: Any) -> None:
        """Проверяет получение completion созданной задачи."""
        task_key = data.draw(st.sampled_from(list(self.tasks.keys())))
        comp_records = server_model.query_completion(
            task_key, None, None, None
        )
        if comp_records:
            comp_key = comp_records[0][0]
            resp = self.client.single_completion(comp_key)
            assert resp["status_code"] == 200

    @rule()
    def query_report(self) -> None:
        """Проверяет эндпоинт GET /query/report."""
        resp = self.client.query_report()
        assert resp["status_code"] == 200

    @precondition(lambda self: bool(self.tasks))
    @rule(data=st.data())
    def get_file(self, data: Any) -> None:
        """Проверяет отдачу сгенерированного PDF файла."""
        task_key = data.draw(st.sampled_from(list(self.tasks.keys())))
        resp = self.client.get_file(f"{task_key}.pdf")
        assert resp.status_code == 200


@pytest.fixture(scope="module", autouse=True)
def setup_server():
    """Фикстура для запуска и остановки тестового HTTP сервера."""
    port = _find_free_port()
    server = ServerThread(app, SERVER_HOST, port)
    server.start()
    base_url = f"http://{SERVER_HOST}:{port}/public/api/v3"
    ApiStateMachine.client = ApiClient(base_url)

    time.sleep(0.1)
    yield
    server.shutdown()


def test_api_state_machine() -> None:
    """Запуск state machine теста на основе hypothesis."""
    run_state_machine_as_test(
        ApiStateMachine,
        settings=settings(
            max_examples=35, stateful_step_count=20, deadline=None
        ),
    )


def test_unsupported_media_type() -> None:
    """Тестирование валидации Content-Type (ожидается 415)."""
    base_url = ApiStateMachine.client.base_url
    bad_headers = {"Content-Type": "application/json"}
    put_resp = requests.put(
        f"{base_url}/insert/session/999",
        data="{}",
        headers=bad_headers,
    )
    assert put_resp.status_code == 415

    post_resp = requests.post(
        f"{base_url}/delete/session",
        data="{}",
        headers=bad_headers,
    )
    assert post_resp.status_code == 415


def test_missing_query_parameters() -> None:
    """Тестирование ошибочных параметров запроса (400 Bad Request)."""
    base_url = ApiStateMachine.client.base_url
    resp = requests.get(f"{base_url}/single/session")
    assert resp.status_code == 400

    resp = requests.get(f"{base_url}/single/task")
    assert resp.status_code == 400

    resp = requests.get(f"{base_url}/single/completion")
    assert resp.status_code == 400
