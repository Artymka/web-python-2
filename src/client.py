import xml.etree.ElementTree as et
import requests


def _dict_to_xml_bytes(root_tag: str, data: dict) -> bytes:
    """Сериализует словарь в байтовую строку XML."""
    elem = et.Element(root_tag)
    for key, val in data.items():
        child = et.SubElement(elem, str(key))
        if val is not None:
            child.text = str(val)
    return et.tostring(elem, encoding="utf-8")


def _xml_to_dict(elem: et.Element) -> dict | list | str:
    """Рекурсивно преобразует XML Element в словарь или список."""
    children = list(elem)
    if not children:
        return elem.text or ""

    child_tags = [c.tag for c in children]
    if len(set(child_tags)) == 1 and len(child_tags) > 1:
        return [_xml_to_dict(c) for c in children]

    result: dict = {}
    for child in children:
        val = _xml_to_dict(child)
        if child.tag in result:
            prev = result[child.tag]
            if isinstance(prev, list):
                prev.append(val)
            else:
                result[child.tag] = [prev, val]
        else:
            result[child.tag] = val
    return result


def _parse_response(resp: requests.Response) -> dict:
    """Парсит ответ сервера из XML в dict с сохранением статуса."""
    parsed: dict = {"status_code": resp.status_code, "data": None}
    if not resp.content:
        return parsed

    try:
        root = et.fromstring(resp.content)
        parsed["root_tag"] = root.tag
        parsed["data"] = _xml_to_dict(root)
    except et.ParseError:
        parsed["data"] = resp.text
    return parsed


class ApiClient:
    """HTTP-клиент для вызова маршрутов Flask API."""

    def __init__(self, base_url: str):
        """Инициализирует базовый URL клиента."""
        self.base_url = base_url.rstrip("/")
        self.headers = {"Content-Type": "text/xml"}

    def insert_session(
        self, key: int, ip: str, locale: str, user_agent: str
    ) -> dict:
        """Вызывает PUT /insert/session/:key для создания сессии."""
        payload = {"ip": ip, "locale": locale, "user_agent": user_agent}
        body = _dict_to_xml_bytes("session", payload)
        url = f"{self.base_url}/insert/session/{key}"
        resp = requests.put(url, data=body, headers=self.headers)
        return _parse_response(resp)

    def delete_session(self, key: int) -> dict:
        """Вызывает POST /delete/session для удаления сессии."""
        body = _dict_to_xml_bytes("request", {"key": key})
        url = f"{self.base_url}/delete/session"
        resp = requests.post(url, data=body, headers=self.headers)
        return _parse_response(resp)

    def query_session(
        self,
        ip: str | None = None,
        locale: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        """Вызывает GET /query/session для фильтрации списка сессий."""
        params = {}
        if ip is not None:
            params["ip"] = ip
        if locale is not None:
            params["locale"] = locale
        if user_agent is not None:
            params["user_agent"] = user_agent

        url = f"{self.base_url}/query/session"
        resp = requests.get(url, params=params)
        return _parse_response(resp)

    def single_session(self, key: int) -> dict:
        """Вызывает GET /single/session для получения одной сессии."""
        url = f"{self.base_url}/single/session"
        resp = requests.get(url, params={"key": key})
        return _parse_response(resp)

    def insert_task(
        self, key: int, session: int, parameter: str, description: str
    ) -> dict:
        """Вызывает PUT /insert/task/:key для создания задачи."""
        payload = {
            "session": session,
            "parameter": parameter,
            "description": description,
        }
        body = _dict_to_xml_bytes("task", payload)
        url = f"{self.base_url}/insert/task/{key}"
        resp = requests.put(url, data=body, headers=self.headers)
        return _parse_response(resp)

    def delete_task(self, key: int) -> dict:
        """Вызывает POST /delete/task для удаления задачи."""
        body = _dict_to_xml_bytes("request", {"key": key})
        url = f"{self.base_url}/delete/task"
        resp = requests.post(url, data=body, headers=self.headers)
        return _parse_response(resp)

    def query_task(
        self,
        session: int,
        parameter: str | None = None,
        description: str | None = None,
        done: int | None = None,
    ) -> dict:
        """Вызывает GET /query/task/:session для выборки задач."""
        params = {}
        if parameter is not None:
            params["parameter"] = parameter
        if description is not None:
            params["description"] = description
        if done is not None:
            params["done"] = done

        url = f"{self.base_url}/query/task/{session}"
        resp = requests.get(url, params=params)
        return _parse_response(resp)

    def single_task(self, key: int) -> dict:
        """Вызывает GET /single/task для получения одной задачи."""
        url = f"{self.base_url}/single/task"
        resp = requests.get(url, params={"key": key})
        return _parse_response(resp)

    def query_completion(
        self,
        task: int,
        response: str | None = None,
        stage: str | None = None,
        error: str | None = None,
    ) -> dict:
        """Вызывает GET /query/completion/:task для выборки completions."""
        params = {}
        if response is not None:
            params["response"] = response
        if stage is not None:
            params["stage"] = stage
        if error is not None:
            params["error"] = error

        url = f"{self.base_url}/query/completion/{task}"
        resp = requests.get(url, params=params)
        return _parse_response(resp)

    def single_completion(self, key: int) -> dict:
        """Вызывает GET /single/completion для получения одного completion."""
        url = f"{self.base_url}/single/completion"
        resp = requests.get(url, params={"key": key})
        return _parse_response(resp)

    def query_report(self) -> dict:
        """Вызывает GET /query/report для формирования отчета."""
        url = f"{self.base_url}/query/report"
        resp = requests.get(url)
        return _parse_response(resp)

    def get_file(self, filename: str) -> requests.Response:
        """Вызывает GET /file/:filename для скачивания файла."""
        url = f"{self.base_url}/file/{filename}"
        return requests.get(url)
