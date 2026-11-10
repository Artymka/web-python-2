import os
import time
from pony import orm

DEFAULT_DB_FILE = "app.db"
SECONDS_IN_SEVEN_MIN = 7 * 60

completions_columns = [
    "key",
    "datetime",
    "response",
    "stage",
    "error",
    "task",
]
tasks_columns = [
    "key",
    "datetime",
    "parameter",
    "session",
    "description",
    "done",
]
sessions_columns = ["key", "datetime", "ip", "locale", "user_agent"]
aggregate_columns = ["response", "description", "parameter"]
report_columns = ["description", "parameter"]

db = orm.Database()


class Session(db.Entity):
    """Сущность сессии в базе данных SQLite."""

    _table_ = "sessions"
    key = orm.PrimaryKey(int)
    datetime = orm.Required(int)
    ip = orm.Optional(str, nullable=False, default="")
    locale = orm.Optional(str, nullable=False, default="")
    user_agent = orm.Optional(str, nullable=False, default="")
    tasks = orm.Set("Task", cascade_delete=True)


class Task(db.Entity):
    """Сущность вычислительной задачи в базе данных SQLite."""

    _table_ = "tasks"
    key = orm.PrimaryKey(int)
    datetime = orm.Required(int)
    parameter = orm.Optional(str, nullable=False, default="")
    session = orm.Required(Session)
    description = orm.Optional(str, nullable=False, default="")
    done = orm.Required(int)
    completions = orm.Set("Completion", cascade_delete=True)


class Completion(db.Entity):
    """Сущность результата выполнения задачи в базе данных SQLite."""

    _table_ = "completions"
    key = orm.PrimaryKey(int, auto=True)
    datetime = orm.Required(int)
    response = orm.Optional(str, nullable=False, default="")
    stage = orm.Optional(str, nullable=False, default="")
    error = orm.Optional(str, nullable=False, default="")
    task = orm.Required(Task)


def init_db(db_path: str | None = None) -> orm.Database:
    """Инициализирует подключение к SQLite и генерирует маппинг таблиц."""
    if db.provider is not None:
        return db

    path = db_path or os.environ.get("APP_DB_PATH", DEFAULT_DB_FILE)
    if path == ":memory:":
        db.bind(provider="sqlite", filename=":memory:")
    else:
        abs_path = os.path.abspath(path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        db.bind(provider="sqlite", filename=abs_path, create_db=True)

    db.generate_mapping(create_tables=True)
    return db


init_db()


def session_to_list(sess: Session) -> list:
    """Преобразует сущность Session в список значений."""
    return [sess.key, sess.datetime, sess.ip, sess.locale, sess.user_agent]


def task_to_list(task: Task) -> list:
    """Преобразует сущность Task в список значений."""
    return [
        task.key,
        task.datetime,
        task.parameter,
        task.session.key,
        task.description,
        task.done,
    ]


def completion_to_list(comp: Completion) -> list:
    """Преобразует сущность Completion в список значений."""
    return [
        comp.key,
        comp.datetime,
        comp.response,
        comp.stage,
        comp.error,
        comp.task.key,
    ]


@orm.db_session
def reset_state() -> None:
    """Очищает состояние всех таблиц базы данных."""
    Completion.select().delete()
    Task.select().delete()
    Session.select().delete()
    orm.commit()


@orm.db_session
def create_session_with_key(
    key: int, ip: str, locale: str, user_agent: str
) -> dict:
    """Создает запись Session с заданным пользователем ключом."""
    existing = Session.get(key=key)
    if existing is not None:
        raise ValueError(f"Session with key {key} already exists")
    created_at = int(time.time())
    sess = Session(
        key=key,
        datetime=created_at,
        ip=ip or "",
        locale=locale or "",
        user_agent=user_agent or "",
    )
    orm.commit()
    return dict(zip(sessions_columns, session_to_list(sess)))


@orm.db_session
def create_session(ip: str, locale: str, user_agent: str) -> int:
    """Создает запись Session с автогенерацией ключа."""
    max_key = 1 << 31
    key = int(time.time_ns()) % max_key
    while Session.get(key=key) is not None:
        key = (key + 1) % max_key
    create_session_with_key(key, ip, locale, user_agent)
    return key


@orm.db_session
def delete_session(key: int) -> list | None:
    """Удаляет запись Session по первичному ключу."""
    sess = Session.get(key=key)
    if sess is None:
        return None
    res = session_to_list(sess)
    sess.delete()
    orm.commit()
    return res


@orm.db_session
def get_session(key: int) -> list | None:
    """Возвращает запись Session по первичному ключу."""
    sess = Session.get(key=key)
    if sess is None:
        return None
    return session_to_list(sess)


@orm.db_session
def get_sessions() -> list:
    """Возвращает все записи Session."""
    return [session_to_list(s) for s in Session.select()]


@orm.db_session
def query_session(
    ip: str | None, locale: str | None, user_agent: str | None
) -> list:
    """Выполняет фильтрацию Session по заданным атрибутам."""
    query = Session.select()
    if ip is not None:
        query = query.filter(lambda s: s.ip == ip)
    if locale is not None:
        query = query.filter(lambda s: s.locale == locale)
    if user_agent is not None:
        query = query.filter(lambda s: s.user_agent == user_agent)
    return [session_to_list(s) for s in query]


@orm.db_session
def create_task_with_key(
    key: int,
    parameter: str,
    session: int,
    description: str,
    done: int,
) -> dict:
    """Создает запись Task с заданным пользователем ключом."""
    existing = Task.get(key=key)
    if existing is not None:
        raise ValueError(f"Task with key {key} already exists")
    sess = Session.get(key=session)
    if sess is None:
        raise ValueError(f"Session with key {session} does not exist")
    created_at = int(time.time())
    task = Task(
        key=key,
        datetime=created_at,
        parameter=parameter or "",
        session=sess,
        description=description or "",
        done=done,
    )
    orm.commit()
    return dict(zip(tasks_columns, task_to_list(task)))


@orm.db_session
def create_task(
    parameter: str, session: int, description: str, done: int
) -> int:
    """Создает запись Task с автогенерацией ключа."""
    max_key = 1 << 31
    key = int(time.time_ns()) % max_key
    while Task.get(key=key) is not None:
        key = (key + 1) % max_key
    create_task_with_key(key, parameter, session, description, done)
    return key


@orm.db_session
def delete_task(key: int) -> list | None:
    """Удаляет запись Task по первичному ключу."""
    task = Task.get(key=key)
    if task is None:
        return None
    res = task_to_list(task)
    task.delete()
    orm.commit()
    return res


@orm.db_session
def get_task(key: int) -> list | None:
    """Возвращает одну запись Task по первичному ключу."""
    task = Task.get(key=key)
    if task is None:
        return None
    return task_to_list(task)


@orm.db_session
def get_tasks() -> list:
    """Возвращает все записи Task."""
    return [task_to_list(t) for t in Task.select()]


@orm.db_session
def query_task(
    session: int,
    parameter: str | None,
    description: str | None,
    done: int | None,
) -> list:
    """Выполняет фильтрацию Task по сессии и атрибутам."""
    query = Task.select(lambda t: t.session.key == session)
    if parameter is not None:
        query = query.filter(lambda t: t.parameter == parameter)
    if description is not None:
        query = query.filter(lambda t: t.description == description)
    if done is not None:
        query = query.filter(lambda t: t.done == done)
    return [task_to_list(t) for t in query]


@orm.db_session
def create_completion(response: str, stage: str, error: str, task: int) -> int:
    """Создает запись Completion."""
    task_obj = Task.get(key=task)
    if task_obj is None:
        raise ValueError(f"Task with key {task} does not exist")
    created_at = int(time.time())
    comp = Completion(
        datetime=created_at,
        response=response or "",
        stage=stage or "",
        error=error or "",
        task=task_obj,
    )
    orm.commit()
    return comp.key


@orm.db_session
def delete_completion(key: int) -> list | None:
    """Удаляет запись Completion по первичному ключу."""
    comp = Completion.get(key=key)
    if comp is None:
        return None
    res = completion_to_list(comp)
    comp.delete()
    orm.commit()
    return res


@orm.db_session
def get_completion(key: int) -> list | None:
    """Возвращает одну запись Completion по первичному ключу."""
    comp = Completion.get(key=key)
    if comp is None:
        return None
    return completion_to_list(comp)


@orm.db_session
def get_completions() -> list:
    """Возвращает все записи Completion."""
    return [completion_to_list(c) for c in Completion.select()]


@orm.db_session
def query_completion(
    task: int,
    response: str | None,
    stage: str | None,
    error: str | None,
) -> list:
    """Выполняет фильтрацию Completion по задаче и атрибутам."""
    query = Completion.select(lambda c: c.task.key == task)
    if response is not None:
        query = query.filter(lambda c: c.response == response)
    if stage is not None:
        query = query.filter(lambda c: c.stage == stage)
    if error is not None:
        query = query.filter(lambda c: c.error == error)
    return [completion_to_list(c) for c in query]


def _filter_recent(recs: list, seconds: int = SECONDS_IN_SEVEN_MIN) -> list:
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


@orm.db_session
def aggregate() -> list:
    """Выполняет агрегацию связки completion и task."""
    comps = get_completions()
    tasks_list = get_tasks()
    recent = _filter_recent(comps)
    tasks_index = _tasks_by_id(tasks_list)
    join_rows, used_ids = _merge(recent, tasks_index)
    return _append_unmatched(join_rows, tasks_list, used_ids)


@orm.db_session
def query_report() -> list:
    """Возвращает проекцию полей description и parameter для Task."""
    return [[t.description, t.parameter] for t in Task.select()]
