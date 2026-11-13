"""Напоминания о начале урока в мессенджеры — задание cron.

Репетитор на вкладке «Уведомления» включает переключатель «Напоминание
об уроке» и интервалы (15 минут / 1 час / 24 часа). В момент, когда до
урока остаётся выбранный интервал, сообщение уходит во все привязанные
каналы репетитора, а ученикам с включённым `remind_lesson` — в их
привязанные каналы.

```
есть урок в окне 24 часов?          ──нет──> пропустить
переключатель включён?              ──нет──> пропустить
интервал дошёл до «сейчас»?         ──нет──> пропустить
канал уже доставлен или захвачен?   ──да──> пропустить
иначе: захват канала (commit) → текст → отправка → delivered_at
```

Идемпотентность — от таблицы `lesson_reminders`: строка «урок + интервал
+ получатель + канал» захватывается и коммитится **до** обращения к
мессенджеру, а после успешной отправки получает `delivered_at`. Поэтому
наложившийся прогон видит захват и дубль не отправляет, а UNIQUE по
каналу — второй рубеж на уровне БД: проигравший гонку INSERT откатывается
ещё до сетевого вызова.

Доставка фиксируется по каналу: сбой одного мессенджера не закрывает
напоминание целиком — успешный канал помечается доставленным, сбойный
отпускает захват и повторяется следующим прогоном (только он). Захват без
подтверждения истекает через `REMINDER_CLAIM_LEASE`, поэтому упавший
посреди отправки прогон не «съедает» напоминание навсегда. Аренда
отсчитывается от фактического момента захвата канала, а не от начала
задания: пока прогон обходит предыдущих получателей, время идёт, и захват,
записанный временем старта, был бы сразу просрочен — наложившийся прогон
перехватил бы его и отправил дубль. Гарантия — «хотя бы один раз»: если
прогон завис дольше аренды и всё-таки доставил, сообщение может прийти
повторно; потеря напоминания хуже редкого дубля.

Пропущенный тик догоняется следующим прогоном, даже если тот наступил уже
после начала урока (`due_at <= now`): в постановке нет ни ограничения «только
до начала», ни предела длительности простоя — напоминание должно уйти
обязательно. Текст строится от интервала, а не от фактического остатка,
поэтому не меняется.

Догон опирается на порядок в реестре cron: задание напоминаний стоит
**раньше** `lesson.auto_complete`. Автозавершение закрывает урок через
24 часа после окончания, а отбор напоминаний берёт только «Запланирован»;
если бы автозавершение отработало первым, неотправленное за время простоя
напоминание потерялось бы навсегда. На первом прогоне после простоя
напоминание уходит, а урок закрывается следом.

Строки не создаются, если у получателя нет ни одного канала: подключение
канала внутри окна ещё успеет получить напоминание. Отменённый урок в
выборку не попадает — напоминание о нём не отправляется.

Сервис не знает про FastAPI: на вход — сессия, на выход — число
доставленных сообщений (для строки лога runner'а).
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.services.tutor_time import tutor_zone
from app.lesson.models.lesson_reminder import REMINDER_CLAIM_LEASE, LessonReminder
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
    REMINDER_OFFSET_LABELS,
    REMINDER_OFFSETS,
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
    """Интервалы, момент отправки которых уже наступил.

    Верхней границы нет намеренно: если cron не сработал в целевой момент
    и восстановился уже после начала урока, напоминание всё равно должно
    уйти следующим прогоном с исходной формулировкой интервала. Постановка
    не ограничивает длительность простоя, поэтому и у отбора уроков нижней
    границы нет: тексты и набор интервалов не зависят от момента прогона.
    """
    moment = as_utc(now)
    start = as_utc(starts_at)
    return [
        offset
        for offset in offsets
        if start - timedelta(minutes=offset) <= moment
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


def _existing_deliveries(
    db: Session, lesson_ids: list[str]
) -> dict[tuple, LessonReminder]:
    """Доставки уроков одним запросом: ключ «урок + интервал + канал» → строка.

    Нужен как быстрый фильтр перед захватом: уже доставленный канал не
    трогаем вовсе, а по `claimed_at` видно, живой ли захват. Решение всё
    равно принимает `_claim_delivery` — эта карта может устареть, если
    параллельный прогон успел раньше.
    """
    if not lesson_ids:
        return {}
    rows = db.scalars(
        select(LessonReminder).where(LessonReminder.lesson_id.in_(lesson_ids))
    ).all()
    return {
        (
            row.lesson_id,
            row.offset_min,
            row.audience,
            row.recipient_id,
            row.channel,
        ): row
        for row in rows
    }


def _claim_expired(row: LessonReminder, now: datetime) -> bool:
    """Захват доставки просрочен — прогон, взявший его, уже не придёт."""
    return as_utc(row.claimed_at) <= as_utc(now) - REMINDER_CLAIM_LEASE


def _claim_delivery(
    db: Session,
    key: tuple[str, int, str, str, str],
    existing: dict[tuple, LessonReminder],
    clock: Callable[[], datetime],
) -> LessonReminder | None:
    """Атомарно захватывает доставку в канал; None — канал уже взят.

    Захват — INSERT строки (или UPDATE `claimed_at` у просроченного
    захвата) с немедленным коммитом **до** сетевого вызова: второй
    прогон, наложившийся на текущий, наткнётся на UNIQUE и отправит не
    больше одного сообщения. Проигравший гонку INSERT откатывается здесь
    же, поэтому его транзакция не отравит следующие уроки.

    Просроченный захват перехватывается условным UPDATE: два прогона
    одновременно увидят истёкшую аренду, но обновит строку только один —
    у второго `rowcount` будет 0.

    Время аренды берётся из `clock()` в момент захвата, а не из начала
    задания: обход предыдущих получателей может занять минуты, и захват
    со временем старта был бы сразу просрочен — наложившийся прогон
    перехватил бы канал и отправил дубль.
    """
    lesson_id, offset_min, audience, recipient_id, channel = key
    now = as_utc(clock())
    row = existing.get(key)
    if row is not None:
        if row.delivered_at is not None:
            return None
        if not _claim_expired(row, now):
            return None
        claimed = db.execute(
            update(LessonReminder)
            .where(
                LessonReminder.id == row.id,
                LessonReminder.delivered_at.is_(None),
                LessonReminder.claimed_at <= now - REMINDER_CLAIM_LEASE,
            )
            .values(claimed_at=now)
            # SQLite отдаёт время без tzinfo, а сравниваем с aware `now`:
            # ORM-синхронизация падает на этом сравнении. Состояние строки
            # выставляем ниже руками.
            .execution_options(synchronize_session=False)
        )
        db.commit()
        if claimed.rowcount != 1:  # перехватил параллельный прогон
            return None
        row.claimed_at = now
        return row

    row = LessonReminder(
        lesson_id=lesson_id,
        offset_min=offset_min,
        audience=audience,
        recipient_id=recipient_id,
        channel=channel,
        claimed_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    existing[key] = row
    return row


def _deliver(
    db: Session,
    *,
    tutor_id: str,
    chats: dict[str, str],
    text: str,
    lesson_id: str,
    offset_min: int,
    audience: str,
    recipient_id: str,
    existing: dict[tuple, LessonReminder],
    clock: Callable[[], datetime],
) -> int:
    """Доставляет текст в каналы получателя; возвращает число доставок.

    Каждый канал проходит три шага: захват (коммит) → отправка →
    `delivered_at` (коммит). Сбой канала не мешает остальным и не
    закрывает напоминание: захват остаётся просроченным, поэтому
    следующий прогон повторит только этот канал, а уже доставленный
    пропустит.
    """
    sent = 0
    for messenger, chat_id in chats.items():
        key = (lesson_id, offset_min, audience, recipient_id, messenger)
        row = _claim_delivery(db, key, existing, clock)
        if row is None:
            continue
        errors = send_message(db, tutor_id, messenger, chat_id, text)
        if errors:
            logger.warning(
                "напоминание об уроке: %s не доставлено (%s)", messenger, errors[0]
            )
            continue
        row.delivered_at = as_utc(clock())
        db.commit()
        sent += 1
    return sent


def _send_reminders(
    db: Session,
    tutor: Tutor,
    now: datetime,
    clock: Callable[[], datetime],
) -> int:
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
    existing = _existing_deliveries(db, [lesson.lesson_id for lesson in lessons])
    sent = 0
    for lesson in lessons:
        for offset in due_offsets(offsets, lesson.starts_at, now):
            if tutor_chats:
                sent += _deliver(
                    db,
                    tutor_id=tutor.id,
                    chats=tutor_chats,
                    text=tutor_reminder_text(offset, lesson, tutor_zone(tutor)),
                    lesson_id=lesson.lesson_id,
                    offset_min=offset,
                    audience="tutor",
                    recipient_id=tutor.id,
                    existing=existing,
                    clock=clock,
                )

            for student in lesson.students:
                chats = _student_chats(db, tutor.id, student.student_id)
                if not chats:
                    continue
                sent += _deliver(
                    db,
                    tutor_id=tutor.id,
                    chats=chats,
                    text=student_reminder_text(
                        offset, lesson, _student_zone(student, tutor)
                    ),
                    lesson_id=lesson.lesson_id,
                    offset_min=offset,
                    audience="student",
                    recipient_id=student.student_id,
                    existing=existing,
                    clock=clock,
                )
    return sent


def run_lesson_reminders(
    db: Session,
    *,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
) -> int:
    """Отправляет напоминания всем, кому пора; число доставленных сообщений.

    `now` — момент отбора интервалов (aware UTC); в тестах подменяется, в
    бою — `utcnow()`. Захват и подтверждение доставки коммитятся внутри
    `_deliver` (до и после сетевого вызова), поэтому открытая транзакция
    SQLite не держится на время отправки и не блокирует запись
    веб-приложению; коммит в конце закрывает остаток работы (журнал
    отправок, чтение настроек). Сбой одного репетитора не роняет рассылку
    остальным.

    `clock` — часы аренды захвата. Аренда отсчитывается от фактического
    момента захвата канала, а не от начала задания: длинный обход
    получателей иначе выдавал бы сразу просроченные захваты, и
    наложившийся прогон перехватил бы канал, отправив дубль. По умолчанию
    это настоящие часы, а при явном `now` (тест, ручной прогон) они
    заморожены на нём, чтобы результат не зависел от реального времени.
    """
    moment = as_utc(now) if now is not None else as_utc(utcnow())
    tick: Callable[[], datetime] = clock or (
        utcnow if now is None else lambda: moment
    )
    sent = 0
    for tutor_id in _tutors_with_channels(db):
        tutor = db.get(Tutor, tutor_id)
        if tutor is None:  # pragma: no cover — FK CASCADE: строка не может пропасть
            continue
        try:
            sent += _send_reminders(db, tutor, moment, tick)
        except Exception:
            db.rollback()
            logger.exception("напоминания об уроке: сбой у репетитора %s", tutor_id)
        else:
            db.commit()
    return sent
