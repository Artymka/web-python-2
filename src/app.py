import functools
import os
import subprocess
import sys
import xml.etree.ElementTree as et
from flask import Blueprint, Flask, Response, request, send_from_directory

import src.model as model

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
INPUT_DIR = os.path.join(BASE_DIR, "input")
CONVERT_SCRIPT = os.path.join(BASE_DIR, "src", "convert.py")
URL_PREFIX = "/public/api/v3"
XML_MIME = "text/xml"
STATUS_BAD_REQUEST = 400
STATUS_UNSUPPORTED_MEDIA = 415
STATUS_NOT_FOUND = 404
STATUS_SERVER_ERROR = 500


def require_xml(func):
    """Декоратор для проверки заголовка Content-Type: text/xml."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        """Проверяет Content-Type входящего запроса."""
        ctype = request.content_type or ""
        if ctype.split(";")[0].strip().lower() != XML_MIME:
            elem = et.Element("error")
            elem.text = "Content-Type must be text/xml"
            xml_bytes = et.tostring(elem, encoding="utf-8")
            return Response(
                xml_bytes,
                status=STATUS_UNSUPPORTED_MEDIA,
                mimetype=XML_MIME,
            )
        return func(*args, **kwargs)

    return wrapper


def dict_to_xml(tag_name: str, data: dict) -> et.Element:
    """Конвертирует словарь в XML Element."""
    elem = et.Element(tag_name)
    for key, val in data.items():
        child = et.SubElement(elem, str(key))
        if val is not None:
            child.text = str(val)
    return elem


def xml_response(root_elem: et.Element, status: int = 200) -> Response:
    """Формирует Response с телом XML и mime text/xml."""
    xml_bytes = et.tostring(root_elem, encoding="utf-8")
    return Response(xml_bytes, status=status, mimetype=XML_MIME)


def error_response(message: str, status: int) -> Response:
    """Формирует XML-ответ с ошибкой."""
    elem = et.Element("error")
    elem.text = message
    return xml_response(elem, status=status)


def parse_xml_body(data_bytes: bytes) -> dict:
    """Парсит плоский XML запрос в словарь ключ-значение."""
    if not data_bytes:
        return {}
    root = et.fromstring(data_bytes)
    return {child.tag: child.text for child in root}


api = Blueprint("api", __name__, url_prefix=URL_PREFIX)


@api.put("/insert/session/<int:key>")
@require_xml
def insert_session(key: int):
    """Создает сессию по первичному ключу."""
    body = parse_xml_body(request.get_data())
    ip_val = body.get("ip") or request.args.get("ip") or ""
    loc_val = body.get("locale") or request.args.get("locale") or ""
    ua_val = body.get("user_agent") or request.args.get("user_agent") or ""
    try:
        res = model.create_session_with_key(key, ip_val, loc_val, ua_val)
    except ValueError as exc:
        return error_response(str(exc), STATUS_BAD_REQUEST)

    root = et.Element("data")
    root.append(dict_to_xml("session", res))
    return xml_response(root)


@api.post("/delete/session")
@require_xml
def delete_session():
    """Удаляет сессию по переданному XML ключу."""
    body = parse_xml_body(request.get_data())
    key_str = body.get("key")
    if key_str is None:
        return error_response("Missing key in XML body", STATUS_BAD_REQUEST)
    res_list = model.delete_session(int(key_str))
    if not res_list:
        return Response(status=STATUS_NOT_FOUND)

    res_dict = dict(zip(model.sessions_columns, res_list))
    root = et.Element("data")
    root.append(dict_to_xml("session", res_dict))
    return xml_response(root)


@api.get("/query/session")
def query_session():
    """Возвращает список сессий с фильтрацией."""
    ps = request.args
    res = model.query_session(
        ps.get("ip"), ps.get("locale"), ps.get("user_agent")
    )
    root = et.Element("data")
    for row in res:
        row_dict = dict(zip(model.sessions_columns, row))
        root.append(dict_to_xml("session", row_dict))
    return xml_response(root)


@api.get("/single/session")
def single_session():
    """Возвращает сессию по ключу из параметров запроса."""
    ps = request.args
    key = ps.get("key")
    if not key:
        return error_response("No key parameter", STATUS_BAD_REQUEST)

    res = model.get_session(int(key))
    if not res:
        return Response(status=STATUS_NOT_FOUND)
    row_dict = dict(zip(model.sessions_columns, res))
    root = et.Element("data")
    root.append(dict_to_xml("session", row_dict))
    return xml_response(root)


def _run_cli_convert(res_key: int, parameter: str) -> bool:
    """Вызывает CLI утилиту convert.py через subprocess."""
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    inp = os.path.join(INPUT_DIR, f"{res_key}.txt")
    out = os.path.join(OUTPUT_DIR, f"{res_key}.pdf")
    with open(inp, "w", encoding="utf-8") as file:
        file.write(parameter)

    cmd = [sys.executable, CONVERT_SCRIPT, inp, out]
    ret = subprocess.call(cmd)
    return ret == 0


def _extract_task_input() -> tuple[str, int | None, str]:
    """Извлекает и валидирует входные параметры задачи."""
    body = parse_xml_body(request.get_data())
    param = body.get("parameter") or request.args.get("parameter") or ""
    session_raw = body.get("session") or request.args.get("session")
    session_id = int(session_raw) if session_raw is not None else None
    desc = body.get("description") or request.args.get("description") or ""
    return param, session_id, desc


def _save_task_and_complete(
    key: int, param: str, session_id: int, desc: str
) -> tuple[dict | None, str | None, int]:
    """Сохраняет задачу и запускает утилиту конвертации."""
    try:
        res = model.create_task_with_key(key, param, session_id, desc, 0)
    except ValueError as exc:
        return None, str(exc), STATUS_BAD_REQUEST

    if not _run_cli_convert(key, param):
        return None, "CLI conversion failed", STATUS_SERVER_ERROR

    url_response = f"{request.host_url[:-1]}{URL_PREFIX}/file/{key}.pdf"
    model.create_completion(url_response, "file created", "-", key)
    return res, None, 200


@api.put("/insert/task/<int:key>")
@require_xml
def insert_task(key: int):
    """Создает задачу с ключом key и запускает CLI-утилиту."""
    param, session_id, desc = _extract_task_input()
    if session_id is None:
        return error_response("Missing session field", STATUS_BAD_REQUEST)

    res, err_msg, status = _save_task_and_complete(
        key, param, session_id, desc
    )
    if err_msg is not None:
        return error_response(err_msg, status)

    root = et.Element("data")
    root.append(dict_to_xml("task", res))
    return xml_response(root)


@api.post("/delete/task")
@require_xml
def delete_task():
    """Удаляет задачу по переданному XML ключу."""
    body = parse_xml_body(request.get_data())
    key_str = body.get("key")
    if key_str is None:
        return error_response("Missing key in XML body", STATUS_BAD_REQUEST)
    res_list = model.delete_task(int(key_str))
    if not res_list:
        return Response(status=STATUS_NOT_FOUND)

    res_dict = dict(zip(model.tasks_columns, res_list))
    root = et.Element("data")
    root.append(dict_to_xml("task", res_dict))
    return xml_response(root)


@api.get("/query/task/<int:session>")
def query_task(session: int):
    """Возвращает список задач указанной сессии."""
    ps = request.args
    done = None
    if ps.get("done") is not None:
        done = int(ps.get("done"))
    res = model.query_task(
        session, ps.get("parameter"), ps.get("description"), done
    )
    root = et.Element("data")
    for row in res:
        row_dict = dict(zip(model.tasks_columns, row))
        root.append(dict_to_xml("task", row_dict))
    return xml_response(root)


@api.get("/single/task")
def single_task():
    """Возвращает задачу по ключу."""
    ps = request.args
    key = ps.get("key")
    if not key:
        return error_response("No key parameter", STATUS_BAD_REQUEST)

    res = model.get_task(int(key))
    if not res:
        return Response(status=STATUS_NOT_FOUND)
    row_dict = dict(zip(model.tasks_columns, res))
    root = et.Element("data")
    root.append(dict_to_xml("task", row_dict))
    return xml_response(root)


@api.get("/query/completion/<int:task>")
def query_completion(task: int):
    """Возвращает completions по ключу задачи."""
    ps = request.args
    res = model.query_completion(
        task, ps.get("response"), ps.get("stage"), ps.get("error")
    )
    root = et.Element("data")
    for row in res:
        row_dict = dict(zip(model.completions_columns, row))
        root.append(dict_to_xml("completion", row_dict))
    return xml_response(root)


@api.get("/single/completion")
def single_completion():
    """Возвращает completion по ключу."""
    ps = request.args
    key = ps.get("key")
    if not key:
        return error_response("No key parameter", STATUS_BAD_REQUEST)

    res = model.get_completion(int(key))
    if not res:
        return Response(status=STATUS_NOT_FOUND)
    row_dict = dict(zip(model.completions_columns, res))
    root = et.Element("data")
    root.append(dict_to_xml("completion", row_dict))
    return xml_response(root)


@api.get("/file/<path:filename>")
def get_file(filename: str):
    """Отдает статический сгенерированный файл."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return Response(status=STATUS_NOT_FOUND)
    return send_from_directory(OUTPUT_DIR, filename)


@api.get("/query/report")
def query_report():
    """Выполняет реляционную формулу pi(T x sigma) для отчета."""
    rows = model.query_report()
    root = et.Element("data")
    for row in rows:
        row_dict = dict(zip(model.report_columns, row))
        root.append(dict_to_xml("row", row_dict))
    return xml_response(root)


def create_app() -> Flask:
    """Создает и настраивает Flask приложение."""
    application = Flask(__name__)
    application.register_blueprint(api)
    return application


app = create_app()

if __name__ == "__main__":
    app.run("localhost", 8080, debug=True)
