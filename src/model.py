import random
import threading
import time

completions = []
completions_lock = threading.Lock()
completions_columns = [
    "key",
    "datetime",
    "response",
    "stage",
    "error",
    "task",
]
tasks = []
tasks_lock = threading.Lock()
tasks_columns = [
    "key",
    "datetime",
    "parameter",
    "session",
    "description",
    "done",
]
sessions = []
sessions_lock = threading.Lock()
sessions_columns = ["key", "datetime", "ip", "locale", "user_agent"]
aggregate_columns = ["response", "description", "parameter"]
report_columns = ["description", "parameter"]


def use_lock(lock: threading.Lock):
    """Декоратор для синхронизации вызовов функций через Lock."""

    def decorator(func):
        """Возвращает обертку с захватом блокировки."""

        def wrapper(*args, **kwargs):
            """Выполняет целевую функцию с захватом блокировки."""
            lock.acquire()
            res = None
            try:
                res = func(*args, **kwargs)
            finally:
                lock.release()
            return res

        return wrapper

    return decorator


def base_create(source: list, *args) -> int:
    """Создает запись со случайным ключом и текущим временем."""
    max_key = 1 << 31
    key = random.randint(0, max_key)
    existing_keys = {item[0] for item in source}
    while key in existing_keys:
        key = random.randint(0, max_key)

    created_at = int(time.time())
    source.append([key, created_at, *args])
    return key


def base_delete(source: list, key: int) -> list | None:
    """Удаляет запись по первичному ключу из списка-источника."""
    for idx, item in enumerate(source):
        if item[0] == key:
            return source.pop(idx)
    return None


def base_get(source: list, key: int) -> list | None:
    """Возвращает запись по первичному ключу."""
    for item in source:
        if item[0] == key:
            return item
    return None


def reset_state() -> None:
    """Очищает состояние всех таблиц в памяти."""
    with sessions_lock:
        sessions.clear()
    with tasks_lock:
        tasks.clear()
    with completions_lock:
        completions.clear()


@use_lock(completions_lock)
def create_completion(response: str, stage: str, error: str, task: int) -> int:
    """Создает запись Completion."""
    return base_create(completions, response, stage, error, task)


@use_lock(completions_lock)
def delete_completion(key: int) -> list | None:
    """Удаляет запись Completion по ключу."""
    return base_delete(completions, key)


@use_lock(completions_lock)
def get_completions() -> list:
    """Возвращает все записи Completion."""
    return list(completions)


@use_lock(completions_lock)
def get_completion(key: int) -> list | None:
    """Возвращает одну запись Completion по ключу."""
    return base_get(completions, key)


@use_lock(completions_lock)
def query_completion(
    task: int,
    response: str | None,
    stage: str | None,
    error: str | None,
) -> list:
    """Выполняет фильтрацию Completion по задаче и атрибутам."""
    res = []
    for item in completions:
        if (
            item[5] == task
            and (response is None or item[2] == response)
            and (stage is None or item[3] == stage)
            and (error is None or item[4] == error)
        ):
            res.append(item)
    return res


@use_lock(tasks_lock)
def create_task(
    parameter: str, session: int, description: str, done: int
) -> int:
    """Создает запись Task со случайным ключом."""
    return base_create(tasks, parameter, session, description, done)


@use_lock(tasks_lock)
def create_task_with_key(
    key: int,
    parameter: str,
    session: int,
    description: str,
    done: int,
) -> dict:
    """Создает запись Task с заданным пользователем ключом."""
    existing = base_get(tasks, key)
    if existing is not None:
        raise ValueError(f"Task with key {key} already exists")
    created_at = int(time.time())
    record = [key, created_at, parameter, session, description, done]
    tasks.append(record)
    return dict(zip(tasks_columns, record))


@use_lock(tasks_lock)
def delete_task(key: int) -> list | None:
    """Удаляет запись Task по ключу."""
    return base_delete(tasks, key)


@use_lock(tasks_lock)
def get_tasks() -> list:
    """Возвращает все записи Task."""
    return list(tasks)


@use_lock(tasks_lock)
def get_task(key: int) -> list | None:
    """Возвращает одну запись Task по ключу."""
    return base_get(tasks, key)


@use_lock(tasks_lock)
def query_task(
    session: int,
    parameter: str | None,
    description: str | None,
    done: int | None,
) -> list:
    """Выполняет фильтрацию Task по сессии и атрибутам."""
    res = []
    for item in tasks:
        if (
            item[3] == session
            and (parameter is None or item[2] == parameter)
            and (description is None or item[4] == description)
            and (done is None or item[5] == done)
        ):
            res.append(item)
    return res


@use_lock(sessions_lock)
def create_session(ip: str, locale: str, user_agent: str) -> int:
    """Создает запись Session со случайным ключом."""
    return base_create(sessions, ip, locale, user_agent)


@use_lock(sessions_lock)
def create_session_with_key(
    key: int, ip: str, locale: str, user_agent: str
) -> dict:
    """Создает запись Session с заданным ключом."""
    existing = base_get(sessions, key)
    if existing is not None:
        raise ValueError(f"Session with key {key} already exists")
    created_at = int(time.time())
    record = [key, created_at, ip, locale, user_agent]
    sessions.append(record)
    return dict(zip(sessions_columns, record))


@use_lock(sessions_lock)
def delete_session(key: int) -> list | None:
    """Удаляет запись Session по ключу."""
    return base_delete(sessions, key)


@use_lock(sessions_lock)
def get_sessions() -> list:
    """Возвращает все записи Session."""
    return list(sessions)


@use_lock(sessions_lock)
def get_session(key: int) -> list | None:
    """Возвращает запись Session по ключу."""
    return base_get(sessions, key)


@use_lock(sessions_lock)
def query_session(
    ip: str | None, locale: str | None, user_agent: str | None
) -> list:
    """Выполняет фильтрацию Session по атрибутам."""
    res = []
    for item in sessions:
        if (
            (ip is None or item[2] == ip)
            and (locale is None or item[3] == locale)
            and (user_agent is None or item[4] == user_agent)
        ):
            res.append(item)
    return res


def _filter_recent(recs: list, seconds: int = 7 * 60) -> list:
    """Оставляет записи за последние seconds секунд."""
    threshold = int(time.time()) - seconds
    return [rec for rec in recs if rec[1] >= threshold]


def _tasks_by_id(task_list: list) -> dict:
    """Индексирует задачи по идентификатору."""
    return {task[0]: task for task in task_list}


def _merge(recs: list, tasks_index: dict) -> tuple[list, set]:
    """Выполняет соединение completion с task."""
    join_rows = []
    used_task_ids = set()
    for rec in recs:
        task = tasks_index.get(rec[5])
        if task is None:
            join_rows.append([rec[2], None, None])
            continue
        join_rows.append([rec[2], task[4], task[2]])
        used_task_ids.add(task[0])
    return join_rows, used_task_ids


def _append_unmatched(join_rows: list, task_list: list, used_ids: set) -> list:
    """Добавляет задачи, не вошедшие в выборку completions."""
    for task in task_list:
        if task[0] not in used_ids:
            join_rows.append([None, task[4], task[2]])
    return join_rows


@use_lock(completions_lock)
@use_lock(tasks_lock)
def aggregate() -> list:
    """Выполняет агрегацию связки completion и task."""
    recent = _filter_recent(completions)
    tasks_index = _tasks_by_id(tasks)
    join_rows, used_ids = _merge(recent, tasks_index)
    return _append_unmatched(join_rows, tasks, used_ids)


@use_lock(tasks_lock)
def query_report() -> list:
    """Возвращает проекцию полей description и parameter для Task."""
    return [[task[4], task[2]] for task in tasks]
