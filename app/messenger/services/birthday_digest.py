"""Список именинников в мессенджеры — задание cron.

Репетитор включает «День рождения» на вкладке «Уведомления»; время
отправки — общее поле «Время отправки» (то же, что у дневной сводки:
`digest_time`). В этот час (и позже, если прогон был пропущен) во все
привязанные каналы уходит список учеников, у которых сегодня день
рождения.

```
есть привязанный чат?          ──нет──> пропустить
«День рождения» включён?       ──нет──> пропустить
местное время >= digest_time?  ──нет──> пропустить
маркер дня уже сегодня?        ──да──> пропустить
именинники есть?               ──нет──> поставить маркер, ничего не отправлять
иначе: текст → каждый привязанный канал → маркер дня
```

Идемпотентность — от маркера `birthday_digest_date` в `tutor_params`: он
хранит локальную дату последней рассылки, поэтому минутные прогоны и их
наложение не отправляют список дважды. Маркер ставится и после пустой
выборки, и после неудачной попытки: иначе сбойный канал ретраился бы
каждую минуту до конца дня. Следствие маркера: день рождения, добавленный
в карточку уже после времени отправки, попадёт в рассылку только в
следующем году.

Пустых рассылок не бывает: нет именинников — нет сообщения (правило
проекта «не показывать нули»).

Сервис не знает про FastAPI: на вход — сессия, на выход — число
доставленных сообщений (для строки лога runner'а).
"""

import logging
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import tutor_zone
from app.messenger.services.binding import chat_id_key
from app.messenger.services.messengers import SUPPORTED
from app.messenger.services.send import send_message
from app.student.models.student import Student
from app.student.services.birthdays import birthday_students
from app.student.services.presentation import birthday_age_label, student_full_name
from app.tutor.models.tutor import Tutor
from app.tutor.models.tutor_settings import (
    DEFAULT_DIGEST_TIME,
    TutorSettings,
    default_values,
)
from app.tutor.services.clock import as_utc, utcnow
from app.tutor.services.params import all_params_by_tutors, save_param

logger = logging.getLogger("cron")

# KV-параметр с датой последней отправленной рассылки (ISO `YYYY-MM-DD`).
# Отдельная строка, а не колонка: миграция не нужна, ключ читается только
# этим заданием.
BIRTHDAY_SENT_KEY = "birthday_digest_date"

# Заголовок сообщения: «Дни рождения сегодня, 1 ноября:».
TITLE = "Дни рождения сегодня, {date}:"

# Полные названия месяцев в родительном падеже. Очередная копия в проекте
# (cabinet, booking, calendar, lesson): приватные константы чужих модулей
# не импортируются, вынос в `app/common/` — отдельная задача.
_MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

def _parse_digest_time(value: str | None) -> time:
    """«ЧЧ:ММ» из настроек → `time`; мусор в строке — дефолтное время.

    Значение пишет форма с валидацией, но строка могла остаться от старой
    версии или правки в обход формы: падать из-за неё cron не должен.
    """
    try:
        hours, minutes = (value or "").split(":")
        return time(int(hours), int(minutes))
    except (AttributeError, TypeError, ValueError):
        logger.warning("дни рождения: некорректное время %r", value)
        return time.fromisoformat(DEFAULT_DIGEST_TIME)

def _date_label(day: date) -> str:
    """«1 ноября» — день и месяц в родительном падеже."""
    return f"{day.day} {_MONTHS_GENITIVE[day.month - 1]}"

def birthday_message(students: list[Student], day: date) -> str:
    """Текст рассылки: заголовок с датой и строки «• Имя Фамилия — N лет».

    Чистая функция форматирования (дата приходит готовой): так текст
    проверяется тестами без базы. Возраст опускается, если он неизвестен;
    при пустом списке функция не вызывается — пустых сообщений не шлём.
    """
    lines = [TITLE.format(date=_date_label(day)), ""]
    for student in students:
        name = student_full_name(student)
        age = birthday_age_label(student.birth_date, day)
        lines.append(f"• {name} — {age}" if age else f"• {name}")
    return "\n".join(lines)

def _chats(params: dict[str, str]) -> dict[str, str]:
    """Привязанные каналы репетитора из уже прочитанных параметров."""
    chats: dict[str, str] = {}
    for messenger in SUPPORTED:
        chat_id = params.get(chat_id_key(messenger))
        if chat_id:
            chats[messenger] = chat_id
    return chats

def _settings_map(db: Session, tutor_ids: list[str]) -> dict[str, TutorSettings]:
    """Настройки пачки репетиторов одним запросом; строки нет — дефолты."""
    rows = db.scalars(
        select(TutorSettings).where(TutorSettings.tutor_id.in_(tutor_ids))
    ).all()
    result: dict[str, TutorSettings] = {row.tutor_id: row for row in rows}
    for tutor_id in tutor_ids:
        if tutor_id not in result:
            result[tutor_id] = TutorSettings(tutor_id=tutor_id, **default_values())
    return result

def _send_birthdays(
    db: Session,
    tutor: Tutor,
    settings: TutorSettings,
    params: dict[str, str],
    now_local: datetime,
) -> int:
    """Отправляет список именинников одному репетитору; число доставок.

    Решение «слать или нет» принимается здесь целиком: флаг настроек,
    время, маркер дня. Маркер ставится при любом исходе после проверки
    времени — день считается обработанным, даже если именинников нет.
    """
    if not settings.notify_birthday:
        return 0
    if now_local.time() < _parse_digest_time(settings.digest_time):
        return 0

    today = now_local.date()
    if params.get(BIRTHDAY_SENT_KEY) == today.isoformat():
        return 0

    chats = _chats(params)
    if not chats:
        # Канал не привязан — отправлять некуда; маркер не ставим, чтобы
        # привязка канала в течение дня ещё успела дать рассылку.
        logger.warning("дни рождения: у репетитора %s нет привязанных каналов", tutor.id)
        return 0

    students = birthday_students(db, tutor.id, today)
    sent = 0
    if students:
        text = birthday_message(students, today)
        for messenger, chat_id in chats.items():
            # Ошибка одного канала не мешает остальным: она уже в журнале
            # `sent_messages`, а список всё равно получит второй мессенджер.
            errors = send_message(db, tutor.id, messenger, chat_id, text)
            if errors:
                logger.warning(
                    "дни рождения: %s не доставлены (%s)", messenger, errors[0]
                )
            else:
                sent += 1

    save_param(db, tutor.id, BIRTHDAY_SENT_KEY, today.isoformat())
    return sent

def notify_birthday_digest(db: Session, *, now: datetime | None = None) -> int:
    """Рассылает списки именинников всем, кому пора; число доставок.

    `now` — момент проверки (aware UTC); в тестах подменяется, в бою —
    `utcnow()`. Коммит после каждого репетитора: сетевые вызовы не должны
    держать открытую транзакцию SQLite и блокировать запись веб-приложению.
    """
    moment = as_utc(now or utcnow())
    tutor_ids = list(db.scalars(select(Tutor.id).order_by(Tutor.id)).all())
    if not tutor_ids:
        return 0
    settings = _settings_map(db, tutor_ids)
    params = all_params_by_tutors(db, tutor_ids)

    sent = 0
    for tutor_id in tutor_ids:
        tutor = db.get(Tutor, tutor_id)
        if tutor is None:  # pragma: no cover — FK CASCADE: строка не может пропасть
            continue
        try:
            sent += _send_birthdays(
                db,
                tutor,
                settings[tutor_id],
                params.get(tutor_id, {}),
                moment.astimezone(tutor_zone(tutor)),
            )
        except Exception:
            # Сбой одного репетитора не должен ронять рассылку остальным.
            db.rollback()
            logger.exception("дни рождения: сбой у репетитора %s", tutor_id)
        else:
            db.commit()
    return sent
