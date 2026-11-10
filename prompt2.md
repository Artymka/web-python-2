Роль: Ты — Senior Python-разработчик, эксперт по Flask, тестированию и архитектуре.

Контекст:
Мы выполняем 2-й этап практической работы. Проект — это система управления вычислительными задачами (Session, Task, Completion). У нас уже есть частично написанный код для HTTP API, но в нем есть баги, и он не полностью соответствует требованиям. Тебе нужно дополнить существующий код и исправить ошибки, строго соблюдая ограничения из agents.md (PEP8, docstrings, максимум 80 символов в строке, Conventional Commits и т.д.).

Твоя задача — реализовать/исправить следующее:

    HTTP API на Flask (XML формат):

        Обработчики должны возвращать ответы в формате XML (используй xml.etree.ElementTree или Flask-XML).

        Реализуй все маршруты из таблицы 21:

        Session: PUT /public/api/v3/insert/session/:key, POST /public/api/v3/delete/session, GET /public/api/v3/query/session, GET /public/api/v3/single/session.

        Task: PUT /public/api/v3/insert/task/:key, POST /public/api/v3/delete/task, GET /public/api/v3/query/task/:session, GET /public/api/v3/single/task.

        Completion: GET /public/api/v3/query/completion/:task, GET /public/api/v3/single/completion.

        Report: GET /public/api/v3/query/report (должен выполнять формулу π(T×σ)π(T×σ) из задания, возвращая описание и параметры из Task).

    Валидация заголовков (Middleware/Decorator):

        Для методов POST, PUT, PATCH обязательно наличие заголовка Content-Type: text/xml.

        Если заголовка нет или он неверный — возвращать 415 Unsupported Media Type. (Напиши декоратор для проверки).

    Интеграция с CLI (метод 2.1 PUT .../insert/task/:key):

        При создании задачи API должен вызывать внешнюю утилиту (из 1-го этапа) через модуль subprocess.

    
    HTTP-клиент:

        Напиши Python-класс (например, ApiClient), методы которого называются так же, как функции в моделях (например, insert_task, query_completion).

        Клиент должен отправлять запросы и парсить XML-ответы.

    Тестирование на основе моделей (MBT) с hypothesis:

        Напиши тесты с использованием RuleBasedStateMachine из библиотеки hypothesis.

        Тесты должны использовать твой ApiClient и покрывать все эндпоинты API (из Табл. 21).

        Обязательно: Настрой генерацию отчета о покрытии (coverage). Убедись, что все обработчики покрыты тестами, сгенерированными hypothesis.

Ограничения и ожидаемый результат:

    Код должен быть разбит на модули (например, src/api.py, src/client.py, tests/test_mbt.py).

    Все функции и классы должны иметь docstrings на русском или английском. Обычных комментариев # быть не должно.

    В ответе я ожидаю увидеть готовую структуру файлов с кодом, инструкции по запуску тестов. Коммит совершать НЕ НУЖНО.

    Пожалуйста, укажи, какие именно баги в текущей версии (если они видны из логики) ты исправляешь.

Чек-лист перед сдачей:

    Код в папке src/

    Тесты в папке tests/

    Нет файлов __pycache__ и .venv в коммите

    Длина строк < 80 символов

    Запуск тестов через run.sh или pytest

