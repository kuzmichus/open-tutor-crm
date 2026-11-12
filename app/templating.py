"""Общий помощник шаблонов Jinja2.

Собирает все каталоги шаблонов: общий `app/templates` и каталоги модулей
(`app/<module>/templates`). Шаблоны модулей неймспейсятся подкаталогом
(например `tutor/home.html`), чтобы не было коллизий имён.

Чтобы подключить новый модуль — добавьте его каталог в `TEMPLATE_DIRS`.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app import __repository_url__, __version__

_APP_DIR = Path(__file__).resolve().parent

TEMPLATE_DIRS = [
    _APP_DIR / "templates",  # общие шаблоны
    _APP_DIR / "tutor" / "templates",  # модуль tutor
    _APP_DIR / "student" / "templates",  # модуль student
    _APP_DIR / "calendar" / "templates",  # модуль calendar
    _APP_DIR / "group" / "templates",  # модуль group
    _APP_DIR / "lesson" / "templates",  # модуль lesson
    _APP_DIR / "homework" / "templates",  # модуль homework
    _APP_DIR / "unavailability" / "templates",  # модуль unavailability
    _APP_DIR / "slot" / "templates",  # модуль slot
    _APP_DIR / "booking" / "templates",  # модуль booking
    _APP_DIR / "finance" / "templates",  # модуль finance
    _APP_DIR / "stats" / "templates",  # модуль stats
    _APP_DIR / "task" / "templates",  # модуль task
    _APP_DIR / "mailing" / "templates",  # модуль mailing
    _APP_DIR / "cabinet" / "templates",  # модуль cabinet (личный кабинет ученика)
    _APP_DIR / "landing" / "templates",  # модуль лендинга
]

templates = Jinja2Templates(directory=TEMPLATE_DIRS)

# Подпись сервиса в подвале (`_footer_signature.html`): версия и адрес
# исходников. Версия берётся из манифеста (`app.__version__`), адрес — из
# `app.__repository_url__`, поэтому в шаблонах нет литералов, которые
# пришлось бы править при смене версии или переезде репозитория.
templates.env.globals.update(
    app_version=__version__,
    app_repository_url=__repository_url__,
)

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

# Функции отображения модуля уроков (стоимость «1 200 ₽ (Оплачено)»,
# цель урока, чип типа, оценка-звёзды).
from app.lesson.services.presentation import (  # noqa: E402
    register_template_helpers as register_lesson_template_helpers,
)

register_lesson_template_helpers()

# Функции отображения модуля недоступности (подписи причин «Отпуск»/
# «Больничный»/«Выходной» и форматы срока «26.10 – 30.10», «с 26.10 —
# бессрочно», «сб, бессрочно»).
from app.unavailability.services.presentation import (  # noqa: E402
    register_template_helpers as register_unavailability_template_helpers,
)

register_unavailability_template_helpers()

# Функции отображения модуля окон (подписи состояний «Свободно»/«Занято
# уроком», причин пропуска пачки, интервал «10:00 – 10:40»).
from app.slot.services.presentation import (  # noqa: E402
    register_template_helpers as register_slot_template_helpers,
)

register_slot_template_helpers()

# Функции отображения модуля финансов (деньги «1 200 ₽» и знак суммы,
# подписи вида операции и статуса платежа, дата «22 окт. 2026, 01:31»).
from app.finance.services.presentation import (  # noqa: E402
    register_template_helpers as register_finance_template_helpers,
)

register_finance_template_helpers()

# Функции отображения модуля репетитора (интервал урока «23:30 - 00:30»,
# дата платежа «21 окт.», подпись месяца «За октябрь» дашборда главной).
from app.tutor.services.presentation import (  # noqa: E402
    register_template_helpers as register_tutor_template_helpers,
)

register_tutor_template_helpers()

# Функции отображения модуля статистики («Занятий/нед» «0,5», проценты,
# конверсия «мало данных», причины в раскрытии пробных).
from app.stats.services.presentation import (  # noqa: E402
    register_template_helpers as register_stats_template_helpers,
)

register_stats_template_helpers()

# Функции отображения модуля задач (подписи этапа и приоритета, короткая
# дата срока «26 окт.»).
from app.task.services.presentation import (  # noqa: E402
    register_template_helpers as register_task_template_helpers,
)

register_task_template_helpers()

# Функции отображения модуля рассылок (метка мессенджера, счётчик
# получателей, сводка доставки).
from app.mailing.services.presentation import (  # noqa: E402
    register_template_helpers as register_mailing_template_helpers,
)

register_mailing_template_helpers()

# Функции отображения кабинета ученика (заголовок карточки ДЗ «урок
# 30 октября 2026», срок сдачи, подпись и чип статуса ДЗ).
from app.cabinet.services.presentation import (  # noqa: E402
    register_template_helpers as register_cabinet_template_helpers,
)

register_cabinet_template_helpers()

# Функции отображения модуля файлов (размер «12,4 КБ» в списке файлов ДЗ).
from app.files.services.presentation import (  # noqa: E402
    register_template_helpers as register_files_template_helpers,
)

register_files_template_helpers()

# Флаг лендинга (`landing_enabled`) — сайдбар показывает пункт «Лендинг»
# только в сингл-режиме, а флаг читается в момент отрисовки.
from app.landing.services.template import (  # noqa: E402
    register_template_helpers as register_landing_template_helpers,
)

register_landing_template_helpers()
