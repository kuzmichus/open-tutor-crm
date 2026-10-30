"""Журнал исходящих сообщений бота: запись и чтение.

Журнал пишется в одной точке — диспетчере `send_message` (см. D1 design
change'а mailings): там проходят все реальные попытки доставки, от ручных
рассылок до приветственных при привязке. Ошибки валидации до попытки
журналом не считаются — попытки не было.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.messenger.models.sent_message import (
    SENT_MESSAGE_STATUSES,
    SentMessage,
)
from app.messenger.models.student_invite import StudentMessengerInvite


def log_send(
    db: Session,
    tutor_id: str,
    messenger: str,
    recipient: str,
    text: str,
    errors: list[str],
) -> None:
    """Дописывает попытку доставки в журнал.

    `errors` — результат `send_message`: пустой список — доставлено,
    иначе ошибка после ретраев (первая строка сохраняется как причина).
    Ученик опознаётся по chat_id привязок этого же репетитора; чат вне
    приглашений (например, канал репетитора) пишется без ученика.
    Строку добавляет без commit: транзакцию завершает вызывающий код.
    """
    status = "sent" if not errors else "error"
    if status not in SENT_MESSAGE_STATUSES:  # pragma: no cover — защита инварианта
        raise ValueError(f"Неизвестный статус доставки: {status}")

    student_id = db.scalars(
        select(StudentMessengerInvite.student_id)
        .where(
            StudentMessengerInvite.tutor_id == tutor_id,
            StudentMessengerInvite.messenger == messenger,
            StudentMessengerInvite.chat_id == recipient,
        )
        .limit(1)
    ).first()

    db.add(
        SentMessage(
            tutor_id=tutor_id,
            student_id=student_id,
            messenger=messenger,
            recipient=recipient,
            text=text,
            status=status,
            error=errors[0] if errors else None,
        )
    )


def list_messages(
    db: Session,
    tutor_id: str,
    *,
    limit: int = 100,
) -> list[tuple[SentMessage, str | None]]:
    """Последние `limit` записей журнала репетитора, свежие сверху.

    Возвращает пары «запись — имя ученика»: журнал часто живёт дольше
    учеников, и удаление ученика (SET NULL) не должно прятать его старые
    сообщения — вместо имени тогда выводится пустая подпись.
    """
    from app.student.models.student import Student

    rows = db.execute(
        select(SentMessage, Student.first_name, Student.last_name)
        .outerjoin(Student, Student.id == SentMessage.student_id)
        .where(SentMessage.tutor_id == tutor_id)
        .order_by(SentMessage.created_at.desc(), SentMessage.id.desc())
        .limit(limit)
    ).all()

    result: list[tuple[SentMessage, str | None]] = []
    for message, first_name, last_name in rows:
        name = " ".join(part for part in (first_name, last_name) if part)
        result.append((message, name or None))
    return result
