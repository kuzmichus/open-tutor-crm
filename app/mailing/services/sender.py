"""Отправка рассылки выбранным ученикам по всем их подключённым каналам.

Транспорт не дублируется: доставка — общий `send_message` (ретрай, журнал,
ошибки списком). Здесь только выбор своих учеников, подстановка значений
под каждого и сбор сводки для ответа формы.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mailing.services.recipients import channel_chats
from app.mailing.services.rendering import render_message
from app.messenger.services.messengers import SUPPORTED
from app.messenger.services.send import send_message
from app.student.models.student import Student
from app.student.services.list_metrics import BALANCE, NEXT_AT, attach_metrics
from app.student.services.students import build_cards
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import as_utc, utcnow

# Ключи сводки, которые читают вьюха и тесты.
RECIPIENTS = "recipients"
DELIVERED = "delivered"
FAILED = "failed"
SKIPPED = "skipped"
ERRORS = "errors"

EMPTY_TEXT_ERROR = "Введите текст сообщения."
EMPTY_SELECTION_ERROR = "Выберите хотя бы одного ученика."


def send_mailing(
    db: Session,
    tutor_id: str,
    student_ids: list[str],
    text: str,
) -> dict:
    """Отправляет текст выбранным ученикам; возвращает сводку доставки.

    Выборка учеников фильтруется по `tutor_id` — чужие id из формы молча
    отсекаются, отправка по ним невозможна в принципе. Ученик без
    подключённых каналов пропускается (в сводке `skipped`): уходит ему
    всё равно некуда. Ошибки каналов не прерывают остальных получателей.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return {RECIPIENTS: 0, DELIVERED: 0, FAILED: 0, SKIPPED: 0,
                ERRORS: [EMPTY_TEXT_ERROR]}

    ids = [value for value in dict.fromkeys(student_ids or []) if value]
    students = list(
        db.scalars(
            select(Student).where(
                Student.tutor_id == tutor_id,
                Student.id.in_(ids),
            )
        ).all()
    ) if ids else []
    if not students:
        return {RECIPIENTS: 0, DELIVERED: 0, FAILED: 0, SKIPPED: 0,
                ERRORS: [EMPTY_SELECTION_ERROR]}

    # Порядок учеников — как в форме, а не как вернул `IN`.
    by_id = {student.id: student for student in students}
    ordered = [by_id[value] for value in ids if value in by_id]

    tutor = db.get(Tutor, tutor_id)
    now = as_utc(utcnow())
    metrics = {
        card["student"].id: card
        for card in attach_metrics(db, build_cards(db, ordered), now=now)
    }
    chats = channel_chats(db, tutor_id, [student.id for student in ordered])

    summary = {RECIPIENTS: 0, DELIVERED: 0, FAILED: 0, SKIPPED: 0, ERRORS: []}
    for student in ordered:
        student_chats = chats.get(student.id, {})
        targets = [m for m in SUPPORTED if m in student_chats]
        if not targets:
            summary[SKIPPED] += 1
            continue
        summary[RECIPIENTS] += 1
        card = metrics[student.id]
        rendered = render_message(
            cleaned,
            student=student,
            balance=card[BALANCE],
            next_lesson_at=card[NEXT_AT],
            tutor=tutor,
        )
        for messenger in targets:
            errors = send_message(db, tutor_id, messenger, student_chats[messenger], rendered)
            if errors:
                summary[FAILED] += 1
                summary[ERRORS].extend(errors)
            else:
                summary[DELIVERED] += 1

    # Журнал (`sent_messages`) пишется `send_message` без commit —
    # вся рассылка фиксируется одной транзакцией.
    db.commit()
    return summary
