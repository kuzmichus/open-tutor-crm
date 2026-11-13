"""Напоминания о начале урока в мессенджеры — задание cron.

Репетитор на вкладке «Уведомления» включает переключатель «Напоминание
об уроке» и интервалы (15 минут / 1 час / 24 часа). В момент, когда до
урока остаётся выбранный интервал, сообщение уходит во все привязанные
каналы репетитора, а ученикам с включённым `remind_lesson` — в их
привязанные каналы.

```
есть урок в окне 24 часов?     ──нет──> пропустить
переключатель включён?         ──нет──> пропустить
интервал дошёл до «сейчас»?    ──нет──> пропустить
маркер «урок + интервал» есть? ──да──> пропустить
иначе: текст → все каналы получателя → маркер
```

Идемпотентность — от таблицы `lesson_reminders`: строка «урок + интервал
+ получатель» ставится после попытки отправки. Проверка «уже отправлено»
делается по таблице, поэтому повторный прогон и наложение минутных тиков
не дублируют сообщение; UNIQUE-ограничение — второй рубеж на уровне БД.

Пропущенный тик догоняется следующим прогоном: интервал считается
наступившим, пока урок не начался (`due_at <= now < starts_at`), а текст
строится от интервала, а не от фактического остатка, поэтому не меняется.

Маркер не ставится, если у получателя нет ни одного канала: подключение
канала внутри окна ещё успеет получить напоминание. Отменённый урок в
выборку не попадает — напоминание о нём не отправляется.

Сервис не знает про FastAPI: на вход — сессия, на выход — число
доставленных сообщений (для строки лога runner'а).
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import tutor_zone
from app.lesson.models.lesson_reminder import LessonReminder
from app.lesson.services.reminder_lesson import ReminderLesson
from app.lesson.services.reminder_lessons import upcoming_lessons
from app.lesson.services.reminder_student import ReminderStudent
from app.messenger.models.student_invite import StudentMessengerInvite
from app.messenger.services.binding import bound_chats, chat_id_key
from app.messenger.services.messengers import SUPPORTED
from app.messenger.services.send import send_message
from app.tutor.models.tutor import Tutor
from app.tutor.models.tutor_param import TutorParam
from app.tutor.models.tutor_settings import (
    REMINDER_OFFSETS,
    REMINDER_OFFSET_LABELS,
)
from app.tutor.services.clock import as_utc, utcnow
from app.tutor.services.settings import get_settings

logger = logging.getLogger("cron")

# Полные названия месяцев в родительном падеже: «13 ноября». Очередная
# копия в проекте (cabinet, booking, calendar, lesson): приватные
# константы чужих модулей не импортируются, вынос в `app/common/` —
# отдельная задача.
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

# Интервал, который в тексте называется «Завтра», а не «Через N часов».
TOMORROW_OFFSET_MIN = 1440


def reminder_headline(offset_min: int) -> str:
    """Формулировка интервала: «Через 15 минут», «Через 1 час», «Завтра»."""
    if offset_min == TOMORROW_OFFSET_MIN:
        return "Завтра"
    return f"Через {REMINDER_OFFSET_LABELS[offset_min]}"


def reminder_when(starts_at: datetime, zone: ZoneInfo) -> str:
    """«13 ноября в 09:30» — время урока в зоне получателя."""
    local = as_utc(starts_at).astimezone(zone)
    return f"{local.day} {_MONTHS_GENITIVE[local.month - 1]} в {local:%H:%M}"


def tutor_reminder_text(
    offset_min: int, lesson: ReminderLesson, zone: ZoneInfo
) -> str:
    """Текст напоминания репетитору: имя ученика или название группы.

    Для группового урока вместо имени ученика подставляется «группой
    <название>»: по первой строке должно быть понятно, о каком занятии речь.
    """
    target = f"группой {lesson.target_name}" if lesson.is_group else lesson.target_name
    return (
        f"{reminder_headline(offset_min)} урок с {target} — \n"
        f"Время: {reminder_when(lesson.starts_at, zone)}"
    )


def student_reminder_text(
    offset_min: int, lesson: ReminderLesson, zone: ZoneInfo
) -> str:
    """Текст напоминания ученику: только время, без имени ученика."""
    return (
        f"{reminder_headline(offset_min)} урок — \n"
        f"Время: {reminder_when(lesson.starts_at, zone)}"
    )


def due_offsets(
    offsets: list[int], starts_at: datetime, now: datetime
) -> list[int]:
    """Интервалы, момент отправки которых уже наступил, а урок не начался.

    Проверка «до начала» не даёт догонять напоминание после урока, а
    отсутствие нижней границы — догонять пропущенный тик: если cron не
    сработал вовремя, сообщение уйдёт следующим прогоном с тем же текстом.
    """
    moment = as_utc(now)
    start = as_utc(starts_at)
    return [
        offset
        for offset in offsets
        if start - timedelta(minutes=offset) <= moment < start
    ]


def _tutors_with_channels(db: Session) -> list[str]:
    """Id репетиторов, у которых есть хотя бы один канал доставки.

    Это канал самого репетитора (`<мессенджер>_chat_id` в параметрах) или
    привязанный чат ученика: ученику сообщение отправляет тот же бот
    репетитора. Отбор до чтения уроков и настроек: у остальных отправлять
    некуда, и минутный прогон не должен обходить всю базу.
    """
    keys = [chat_id_key(messenger) for messenger in SUPPORTED]
    tutor_ids = set(
        db.scalars(
            select(TutorParam.tutor_id).where(TutorParam.key.in_(keys)).distinct()
        ).all()
    )
    tutor_ids.update(
        db.scalars(
            select(StudentMessengerInvite.tutor_id)
            .where(StudentMessengerInvite.chat_id.is_not(None))
            .distinct()
        ).all()
    )
    return sorted(tutor_ids)


def _student_chats(db: Session, tutor_id: str, student_id: str) -> dict[str, str]:
    """Привязанные каналы ученика: «мессенджер → chat_id»."""
    rows = db.scalars(
        select(StudentMessengerInvite).where(
            StudentMessengerInvite.tutor_id == tutor_id,
            StudentMessengerInvite.student_id == student_id,
            StudentMessengerInvite.chat_id.is_not(None),
        )
    ).all()
    by_messenger = {row.messenger: row.chat_id for row in rows}
    return {
        messenger: by_messenger[messenger]
        for messenger in SUPPORTED
        if by_messenger.get(messenger)
    }


def _student_zone(student: ReminderStudent, tutor: Tutor) -> ZoneInfo:
    """Зона получателя-ученика; пустая или неизвестная — зона педагога."""
    if student.timezone:
        try:
            return ZoneInfo(student.timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            pass  # неизвестное имя — не 500, а зона педагога
    return tutor_zone(tutor)


def _sent_markers(db: Session, lesson_ids: list[str]) -> set[tuple]:
    """Уже отправленные напоминания уроков: набор ключей маркеров."""
    if not lesson_ids:
        return set()
    rows = db.scalars(
        select(LessonReminder).where(LessonReminder.lesson_id.in_(lesson_ids))
    ).all()
    return {
        (row.lesson_id, row.offset_min, row.audience, row.recipient_id)
        for row in rows
    }


def _mark_sent(
    db: Session,
    markers: set[tuple],
    lesson_id: str,
    offset_min: int,
    audience: str,
    recipient_id: str,
) -> None:
    """Ставит маркер в текущей транзакции (коммит — у runner'а)."""
    db.add(
        LessonReminder(
            lesson_id=lesson_id,
            offset_min=offset_min,
            audience=audience,
            recipient_id=recipient_id,
        )
    )
    markers.add((lesson_id, offset_min, audience, recipient_id))


def _send_to_channels(
    db: Session, tutor_id: str, chats: dict[str, str], text: str
) -> int:
    """Отправляет текст во все каналы; возвращает число доставок.

    Ошибка одного канала не мешает остальным: она уже в журнале
    `sent_messages`, а второй мессенджер сообщение всё равно получит.
    """
    sent = 0
    for messenger, chat_id in chats.items():
        errors = send_message(db, tutor_id, messenger, chat_id, text)
        if errors:
            logger.warning(
                "напоминание об уроке: %s не доставлено (%s)", messenger, errors[0]
            )
        else:
            sent += 1
    return sent


def _send_reminders(db: Session, tutor: Tutor, now: datetime) -> int:
    """Отправляет напоминания одному репетитору; число доставок."""
    settings = get_settings(db, tutor.id)
    if not settings.notify_lesson_reminder:
        return 0
    # Порядок и состав — из закрытого списка: мусор в JSON (ручная правка
    # базы) не должен порождать отправку «за 7 минут».
    offsets = [
        offset for offset in REMINDER_OFFSETS if offset in (settings.reminder_offsets or [])
    ]
    if not offsets:
        return 0

    lessons = upcoming_lessons(db, tutor.id, now)
    if not lessons:
        return 0

    tutor_chats = bound_chats(db, tutor.id)
    markers = _sent_markers(db, [lesson.lesson_id for lesson in lessons])
    sent = 0
    for lesson in lessons:
        for offset in due_offsets(offsets, lesson.starts_at, now):
            tutor_key = (lesson.lesson_id, offset, "tutor", tutor.id)
            if tutor_chats and tutor_key not in markers:
                text = tutor_reminder_text(offset, lesson, tutor_zone(tutor))
                sent += _send_to_channels(db, tutor.id, tutor_chats, text)
                _mark_sent(db, markers, lesson.lesson_id, offset, "tutor", tutor.id)

            for student in lesson.students:
                student_key = (lesson.lesson_id, offset, "student", student.student_id)
                if student_key in markers:
                    continue
                chats = _student_chats(db, tutor.id, student.student_id)
                if not chats:
                    continue
                text = student_reminder_text(offset, lesson, _student_zone(student, tutor))
                sent += _send_to_channels(db, tutor.id, chats, text)
                _mark_sent(
                    db, markers, lesson.lesson_id, offset, "student", student.student_id
                )
    return sent


def run_lesson_reminders(db: Session, *, now: datetime | None = None) -> int:
    """Отправляет напоминания всем, кому пора; число доставленных сообщений.

    `now` — момент проверки (aware UTC); в тестах подменяется, в бою —
    `utcnow()`. Коммит после каждого репетитора: сетевые вызовы не должны
    держать открытую транзакцию SQLite и блокировать запись веб-приложению.
    Сбой одного репетитора не роняет рассылку остальным.
    """
    moment = as_utc(now or utcnow())
    sent = 0
    for tutor_id in _tutors_with_channels(db):
        tutor = db.get(Tutor, tutor_id)
        if tutor is None:  # pragma: no cover — FK CASCADE: строка не может пропасть
            continue
        try:
            sent += _send_reminders(db, tutor, moment)
        except Exception:
            db.rollback()
            logger.exception("напоминания об уроке: сбой у репетитора %s", tutor_id)
        else:
            db.commit()
    return sent