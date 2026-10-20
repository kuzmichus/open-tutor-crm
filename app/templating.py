"""Общий помощник шаблонов Jinja2.

Собирает все каталоги шаблонов: общий `app/templates` и каталоги модулей
(`app/<module>/templates`). Шаблоны модулей неймспейсятся подкаталогом
(например `tutor/home.html`), чтобы не было коллизий имён.

Чтобы подключить новый модуль — добавьте его каталог в `TEMPLATE_DIRS`.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

_APP_DIR = Path(__file__).resolve().parent

TEMPLATE_DIRS = [
    _APP_DIR / "templates",  # общие шаблоны
    _APP_DIR / "tutor" / "templates",  # модуль tutor
    _APP_DIR / "student" / "templates",  # модуль student
    _APP_DIR / "calendar" / "templates",  # модуль calendar
    _APP_DIR / "group" / "templates",  # модуль group
]

templates = Jinja2Templates(directory=TEMPLATE_DIRS)

# Функции отображения модуля учеников (подписи статусов, инициалы, полное
# имя). Регистрируются здесь, чтобы шаблоны работали и без импорта вьюх.
from app.student.services.presentation import (  # noqa: E402
    register_template_helpers,
)

register_template_helpers()

# Функции отображения модуля групп (цена «1 200 ₽», счётчик участников,
# подпись даты вступления).
from app.group.services.presentation import (  # noqa: E402
    register_template_helpers as register_group_template_helpers,
)

register_group_template_helpers()
