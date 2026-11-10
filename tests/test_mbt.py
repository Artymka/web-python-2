import os
import shutil
import socket
import tempfile
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

TEST_DB_FILE = tempfile.mktemp(suffix="_test.db")
os.environ["APP_DB_PATH"] = TEST_DB_FILE

SERVER_HOST = "127.0.0.1"
KEY_STRATEGY = st.integers(min_value=1, max_value=1 << 20)
SAFE_TEXT = st.text(
    alphabet=st.characters(
        whitelist_categories=(),
        whitelist_characters=(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789 _-"
        ),
    ),
    min_size=1,
    max_size=20,
)
OPTIONAL_TEXT = st.one_of(st.none(), SAFE_TEXT)
STATUS_OK = 200
STATUS_BAD_REQUEST = 400
STATUS_UNSUPPORTED_MEDIA = 415
STATUS_NOT_FOUND = 404
STATUS_SERVER_ERROR = 500


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
        _clean_io_dirs()

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
            assert resp["status_code"] == STATUS_BAD_REQUEST
        else:
            assert resp["status_code"] == STATUS_OK
            self.sessions[key] = {
                "key": key,
                "ip": ip,
                "locale": locale,
                "user_agent": ua,
            }

    @rule(ip=OPTIONAL_TEXT, locale=OPTIONAL_TEXT, ua=OPTIONAL_TEXT)
    def query_session(
        self, ip: str | None, locale: str | None, ua: str | None
    ) -> None:
        """Проверяет эндпоинт GET /query/session."""
        resp = self.client.query_session(ip=ip, locale=locale, user_agent=ua)
        assert resp["status_code"] == STATUS_OK

    @precondition(lambda self: bool(self.sessions))
    @rule(data=st.data())
    def single_session(self, data: Any) -> None:
        """Проверяет эндпоинт GET /single/session для существующего ключа."""
        key = data.draw(st.sampled_from(list(self.sessions.keys())))
        resp = self.client.single_session(key)
        assert resp["status_code"] == STATUS_OK

    @rule(key=KEY_STRATEGY)
    def single_session_missing(self, key: int) -> None:
        """Проверяет эндпоинт GET /single/session для отсутствующего ключа."""
        if key in self.sessions:
            return
        resp = self.client.single_session(key)
        assert resp["status_code"] == STATUS_NOT_FOUND

    @precondition(lambda self: bool(self.sessions))
    @rule(data=st.data())
    def delete_session(self, data: Any) -> None:
        """Проверяет эндпоинт POST /delete/session для существующей сессии."""
        key = data.draw(st.sampled_from(list(self.sessions.keys())))
        resp = self.client.delete_session(key)
        assert resp["status_code"] == STATUS_OK
        self.sessions.pop(key, None)
        dead_tasks = [k for k, v in self.tasks.items() if v["session"] == key]
        for task_k in dead_tasks:
            self.tasks.pop(task_k, None)

    @rule(key=KEY_STRATEGY)
    def delete_session_missing(self, key: int) -> None:
        """Проверяет POST /delete/session для отсутствующей сессии."""
        if key in self.sessions:
            return
        resp = self.client.delete_session(key)
        assert resp["status_code"] == STATUS_NOT_FOUND

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
            assert resp["status_code"] == STATUS_BAD_REQUEST
        else:
            assert resp["status_code"] == STATUS_OK
            self.tasks[key] = {
                "key": key,
                "session": sess_key,
                "parameter": parameter,
                "description": description,
                "done": 0,
            }

    @precondition(lambda self: bool(self.sessions))
    @rule(
        data=st.data(),
        param=OPTIONAL_TEXT,
        desc=OPTIONAL_TEXT,
        done=st.one_of(st.none(), st.sampled_from([0, 1])),
    )
    def query_task(
        self, data: Any, param: str | None, desc: str | None, done: int | None
    ) -> None:
        """Проверяет эндпоинт GET /query/task/:session."""
        sess_key = data.draw(st.sampled_from(list(self.sessions.keys())))
        resp = self.client.query_task(
            sess_key, parameter=param, description=desc, done=done
        )
        assert resp["status_code"] == STATUS_OK

    @precondition(lambda self: bool(self.tasks))
    @rule(data=st.data())
    def single_task(self, data: Any) -> None:
        """Проверяет эндпоинт GET /single/task для существующей задачи."""
        key = data.draw(st.sampled_from(list(self.tasks.keys())))
        resp = self.client.single_task(key)
        assert resp["status_code"] == STATUS_OK

    @rule(key=KEY_STRATEGY)
    def single_task_missing(self, key: int) -> None:
        """Проверяет эндпоинт GET /single/task для отсутствующей задачи."""
        if key in self.tasks:
            return
        resp = self.client.single_task(key)
        assert resp["status_code"] == STATUS_NOT_FOUND

    @precondition(lambda self: bool(self.tasks))
    @rule(data=st.data())
    def delete_task(self, data: Any) -> None:
        """Проверяет POST /delete/task для существующей задачи."""
        key = data.draw(st.sampled_from(list(self.tasks.keys())))
        resp = self.client.delete_task(key)
        assert resp["status_code"] == STATUS_OK
        self.tasks.pop(key, None)

    @rule(key=KEY_STRATEGY)
    def delete_task_missing(self, key: int) -> None:
        """Проверяет POST /delete/task для отсутствующей задачи."""
        if key in self.tasks:
            return
        resp = self.client.delete_task(key)
        assert resp["status_code"] == STATUS_NOT_FOUND

    @precondition(lambda self: bool(self.tasks))
    @rule(
        data=st.data(),
        response=OPTIONAL_TEXT,
        stage=OPTIONAL_TEXT,
        error=OPTIONAL_TEXT,
    )
    def query_completion(
        self,
        data: Any,
        response: str | None,
        stage: str | None,
        error: str | None,
    ) -> None:
        """Проверяет эндпоинт GET /query/completion/:task."""
        task_key = data.draw(st.sampled_from(list(self.tasks.keys())))
        resp = self.client.query_completion(
            task_key, response=response, stage=stage, error=error
        )
        assert resp["status_code"] == STATUS_OK

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
            assert resp["status_code"] == STATUS_OK

    @rule(key=KEY_STRATEGY)
    def single_completion_missing(self, key: int) -> None:
        """Проверяет GET /single/completion для несуществующего ключа."""
        if server_model.get_completion(key) is not None:
            return
        resp = self.client.single_completion(key)
        assert resp["status_code"] == STATUS_NOT_FOUND

    @rule()
    def query_report(self) -> None:
        """Проверяет эндпоинт GET /query/report."""
        resp = self.client.query_report()
        assert resp["status_code"] == STATUS_OK

    @precondition(lambda self: bool(self.tasks))
    @rule(data=st.data())
    def get_file(self, data: Any) -> None:
        """Проверяет отдачу сгенерированного PDF файла."""
        task_key = data.draw(st.sampled_from(list(self.tasks.keys())))
        resp = self.client.get_file(f"{task_key}.pdf")
        assert resp.status_code == STATUS_OK

    @rule(key=KEY_STRATEGY)
    def get_file_missing(self, key: int) -> None:
        """Проверяет отдачу несуществующего файла (404 Not Found)."""
        if key in self.tasks:
            return
        resp = self.client.get_file(f"{key}_missing.pdf")
        assert resp.status_code == STATUS_NOT_FOUND

    @rule(
        target_endpoint=st.sampled_from(["insert_session", "delete_session"])
    )
    def check_unsupported_media_type(self, target_endpoint: str) -> None:
        """Проверяет возврат 415 Unsupported Media Type."""
        base = self.client.base_url
        headers = {"Content-Type": "application/json"}
        if target_endpoint == "insert_session":
            url = f"{base}/insert/session/99999"
            resp = requests.put(url, data="{}", headers=headers)
        else:
            url = f"{base}/delete/session"
            resp = requests.post(url, data="{}", headers=headers)
        assert resp.status_code == STATUS_UNSUPPORTED_MEDIA

    @rule(
        target_endpoint=st.sampled_from(
            ["single_session", "single_task", "single_completion"]
        )
    )
    def check_missing_query_parameters(self, target_endpoint: str) -> None:
        """Проверяет возврат 400 Bad Request при отсутствии key."""
        base = self.client.base_url
        endpoint_map = {
            "single_session": f"{base}/single/session",
            "single_task": f"{base}/single/task",
            "single_completion": f"{base}/single/completion",
        }
        resp = requests.get(endpoint_map[target_endpoint])
        assert resp.status_code == STATUS_BAD_REQUEST

    @rule(target_endpoint=st.sampled_from(["delete_session", "delete_task"]))
    def check_missing_delete_key(self, target_endpoint: str) -> None:
        """Проверяет возврат 400 Bad Request при удалении без key в XML."""
        base = self.client.base_url
        headers = {"Content-Type": "text/xml"}
        sub = "session" if "session" in target_endpoint else "task"
        url = f"{base}/delete/{sub}"
        resp = requests.post(url, data="<req></req>", headers=headers)
        assert resp.status_code == STATUS_BAD_REQUEST

    @rule(key=KEY_STRATEGY)
    def check_insert_task_missing_session(self, key: int) -> None:
        """Проверяет возврат 400 Bad Request при отсутствии session."""
        base = self.client.base_url
        headers = {"Content-Type": "text/xml"}
        xml_data = "<task><parameter>p</parameter></task>"
        resp = requests.put(
            f"{base}/insert/task/{key}", data=xml_data, headers=headers
        )
        assert resp.status_code == STATUS_BAD_REQUEST


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
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


def test_api_state_machine() -> None:
    """Запуск state machine теста на основе hypothesis."""
    run_state_machine_as_test(
        ApiStateMachine,
        settings=settings(
            max_examples=40, stateful_step_count=25, deadline=None
        ),
    )
