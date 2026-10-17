# AGENTS.md — правила разработки open-tutor-crm

Этот файл — свод правил для работы с кодовой базой (и для AI-ассистентов, и для людей).
Соблюдай их при любом изменении проекта.

## Технологии

Python 3.14 · FastAPI · Uvicorn · SQLAlchemy 2.0 · Alembic · SQLite · Jinja2 · HTMX · pytest.
Все команды выполняются через менеджер окружений **uv** (см. README.md).

## Структура проекта

Приложение разбито на **доменные модули** и **общий** модуль:

```
main.py                     # точка входа, сборка app (include_router)
app/
├── config.py               # настройки (Settings, pydantic-settings)
├── database.py             # engine, SessionLocal, Base, init_db, get_db
├── models.py               # АГРЕГАТОР моделей (только импорты, ни одного класса)
├── templating.py           # общий Jinja2Templates со всеми каталогами шаблонов
├── templates/              # ОБЩИЕ шаблоны (base.html, index.html)
├── static/                 # ОБЩИЕ статические ассеты (htmx.min.js)
├── common/                 # общие фичи, не привязанные к домену (health, главная, часы)
│   └── views/
├── tutor/                  # доменный модуль «Репетитор»
│   ├── models/tutor.py
│   ├── views/index.py
│   └── templates/tutor/
└── student/                # доменный модуль «Ученик»
    ├── models/student.py
    ├── views/index.py
    └── templates/student/
alembic/                    # миграции БД
tests/                      # pytest-тесты
```

## Правила

1. **Один класс — один файл.** Каждый класс (модель, сервис и т.д.) живёт в своём файле.
2. **Модели** — в `<модуль>/models/<имя_модели>.py, по одному классу на файл.
   Пример: `app/tutor/models/tutor.py` содержит `class Tutor`.
3. **Views (роуты)** — в `<модуль>/views/<имя_вью.py, по одному эндпоинту на файл.
   Пример: `app/tutor/views/index.py`. Каждый файл создаёт `router = APIRouter()`.
4. **Шаблоны.** Общие — в `app/templates/`, шаблоны модуля — в `app/<модуль>/templates/`.
   Шаблон модуля неймспейсится подкаталогом (`tutor/index.html`, `student/index.html`),
   чтобы не было коллизий имён. Все шаблоны наследуют `base.html`.
5. **Общий код**, который нельзя отнести к конкретному домену (health, базовые страницы,
   утилиты), — в `app/common/`.
6. **`app/models.py`** — только агрегатор: импортирует модели всех модулей, чтобы они
   зарегистрировались на `Base.metadata`. Там не должно быть ни одного класса.
7. **Статические ассеты** (JS/CSS/картинки) кладутся в `app/static/` и отдаются
   локально через `app.mount("/static", ...)` в `main.py` — **без CDN и без SRI-хешей**
   в шаблонах (иначе несовпадение хеша молча блокирует скрипт).

## Как добавить новый доменный модуль

1. Создай каталог `app/<module>/` с `__init__.py`, `models/`, `views/`, `templates/`.
2. Добавь модель в `app/<module>/models/<name>.py` (один класс — один файл)
   и `from app.<module>.models.<name> import <Name>  # noqa: F401` в `app/models.py`.
3. Добавь view в `app/<module>/views/<name>.py` (создаёт `router`) и собери
   роутеры модуля в `app/<module>/views/__init__.py`.
4. Зарегистрируй каталог шаблонов: допиши `_APP_DIR / "<module>" / "templates"`
   в `TEMPLATE_DIRS` (`app/templating.py`).
5. Подключи роутер модуля в `main.py` (`app.include_router(...)`).
6. Создай миграцию: `uv run alembic revision --autogenerate -m "add <module>"`.
7. Напиши тесты в `tests/`.

## Команды

```bash
uv sync                                   # установить зависимости
uv run pytest                             # прогнать тесты
uv run alembic upgrade head               # применить миграции
uv run alembic revision --autogenerate -m "..."   # новая миграция
uv run uvicorn main:app --host 0.0.0.0 --port 8000  # запуск сервера
```

## Требования к изменениям

- Тесты в `tests/` должны оставаться зелёными (`uv run pytest`).
- Новый домен/поведение — с тестами.
- Миграции создаются через autogenerate и применяются штатно (`alembic upgrade head`).
