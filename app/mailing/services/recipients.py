"""Получатели рассылки: ученики с балансом, следующим уроком и каналами.

Данные собираются батчами на весь список (правило «без N+1 на карточку»):
поиск — переиспользованный `list_students`, деньги и будущий урок —
`attach_metrics`, каналы — один запрос по привязкам чатов. Своё досчитывает
только «последний завершённый урок», которого в общих метриках нет, а нужен
он сегменту «Были недавно».
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.messenger.services.messengers import SUPPORTED
from app.student.models.student import Student
from app.student.services.list_metrics import (
    BALANCE,
    NEXT_AT,
    attach_metrics,
)
from app.student.services.students import build_cards, list_students
from app.tutor.services.clock import as_utc, utcnow

# Окно сегмента «Были недавно»: завершённый урок за последние N дней.
RECENT_DAYS = 7

# Сегменты-фильтры списка. Пусто нет: ключ «all» — «Все», он же умолчание.
SEGMENTS = ("all", "debtors", "upcoming", "recent", "no_lessons")

SEGMENT_LABELS = {
    "all": "Все",
    "debtors": "Должники",
    "upcoming": "С уроками (будущие)",
    "recent": f"Были недавно ({RECENT_DAYS} дней)",
    "no_lessons": "Без уроков",
}

# Ключи карточки получателя.
LAST_AT = "last_lesson_at"
CHANNELS = "channels"
CAN_MESSAGE = "can_message"


def normalize_segment(segment: str) -> str:
    """Сегмент из query; неизвестное значение — «Все» (не 404)."""
    return segment if segment in SEGMENTS else "all"


def channel_chats(
    db: Session, tutor_id: str, student_ids: list[str]
) -> dict[str, dict[str, str]]:
    """Привязанные chat_id учеников: `{student_id: {messenger: chat_id}}`.

    Только завершённые привязки (`chat_id` непуст): приглашение «в
    процессе» адреса не имеет и получателем быть не может. Порядок
    мессенджеров внутри словаря задаёт `SUPPORTED`.
    """
    if not student_ids:
        return {}

    from app.messenger.models.student_invite import StudentMessengerInvite

    rows = db.execute(
        select(
            StudentMessengerInvite.student_id,
            StudentMessengerInvite.messenger,
            StudentMessengerInvite.chat_id,
        ).where(
            StudentMessengerInvite.tutor_id == tutor_id,
            StudentMessengerInvite.student_id.in_(student_ids),
            StudentMessengerInvite.chat_id.is_not(None),
        )
    ).all()

    result: dict[str, dict[str, str]] = {}
    for student_id, messenger, chat_id in rows:
        if messenger in SUPPORTED:
            result.setdefault(student_id, {})[messenger] = chat_id
    return result


def _last_lessons(
    db: Session, student_ids: list[str], now: datetime
) -> dict[str, datetime]:
    """Последний завершённый урок каждого ученика (UTC, `<= now`).

    Максимум вместо минимума (у «следующего» — минимум): групповые и
    индивидуальные уроки в одной куче, как в `_next_lessons`.
    """
    if not student_ids:
        return {}

    from app.group.models.group_member import GroupMember
    from app.lesson.models.lesson import Lesson

    result: dict[str, datetime] = {}

    individual = db.execute(
        select(Lesson.student_id, Lesson.starts_at)
        .where(
            Lesson.student_id.in_(student_ids),
            Lesson.status == "completed",
            Lesson.starts_at <= now,
        )
    ).all()
    for student_id, starts_at in individual:
        _keep_max(result, student_id, as_utc(starts_at))

    grouped = db.execute(
        select(GroupMember.student_id, Lesson.starts_at)
        .join(Lesson, Lesson.group_id == GroupMember.group_id)
        .where(
            GroupMember.student_id.in_(student_ids),
            Lesson.status == "completed",
            Lesson.starts_at <= now,
        )
    ).all()
    for student_id, starts_at in grouped:
        _keep_max(result, student_id, as_utc(starts_at))
    return result


def _keep_max(target: dict[str, datetime], student_id: str, value: datetime) -> None:
    current = target.get(student_id)
    if current is None or value > current:
        target[student_id] = value


def _matches_segment(card: dict, segment: str, *, now: datetime) -> bool:
    """Предикат сегмента (semantics согласованы в спеке change'а)."""
    if segment == "debtors":
        return card[BALANCE] < 0
    if segment == "upcoming":
        return card[NEXT_AT] is not None
    if segment == "recent":
        last = card[LAST_AT]
        return last is not None and last >= now - timedelta(days=RECENT_DAYS)
    if segment == "no_lessons":
        return card[NEXT_AT] is None
    return True


def list_recipients(
    db: Session,
    tutor_id: str,
    *,
    q: str = "",
    segment: str = "all",
    now: datetime | None = None,
) -> list[dict]:
    """Карточки получателей для списка рассылки.

    Карточка: `student`, `balance`, `next_lesson_at`, `last_lesson_at`,
    `channels` (`{messenger: bool}` по `SUPPORTED`) и `can_message` — есть
    ли хоть один канал, куда сообщение физически уйдёт.
    """
    moment = as_utc(now) if now is not None else as_utc(utcnow())
    chosen = normalize_segment(segment)

    students = list_students(db, tutor_id, q=q)
    cards = attach_metrics(db, build_cards(db, students), now=moment)

    last_lessons = _last_lessons(
        db, [card["student"].id for card in cards], moment
    )
    chats = channel_chats(db, tutor_id, [card["student"].id for card in cards])

    result: list[dict] = []
    for card in cards:
        student_id = card["student"].id
        student_chats = chats.get(student_id, {})
        channels = {messenger: messenger in student_chats for messenger in SUPPORTED}
        card[LAST_AT] = last_lessons.get(student_id)
        card[CHANNELS] = channels
        card[CAN_MESSAGE] = any(channels.values())
        if _matches_segment(card, chosen, now=moment):
            result.append(card)
    return result
