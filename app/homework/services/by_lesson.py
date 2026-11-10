"""Домашние задания по урокам: массовая карта статусов.

Одна запись ДЗ на урок (`homework.lesson_id` UNIQUE), поэтому статус —
это просто карта «id урока → статус». Карта нужна и календарю репетитора,
и кабинету ученика: оба показывают значок ДЗ в карточке урока и обязаны
догружать статусы одним SELECT на всю неделю (правило AGENTS.md 9).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.homework.models.homework import Homework

# Статус «Не задано» — запись без домашнего задания: значок не показываем
# и в списках кабинета её нет. Один источник правила для всех поверхностей.
HIDDEN_STATUSES = ("not_assigned",)


def homework_by_lesson(db: Session, lesson_ids: list[str]) -> dict[str, str]:
    """Статусы ДЗ по id уроков: один SELECT на всю неделю.

    «Не задано» (`HIDDEN_STATUSES`) не попадает в карту: пустая запись —
    это отсутствие домашнего задания, значка в карточке быть не должно.
    """
    if not lesson_ids:
        return {}
    rows = db.execute(
        select(Homework.lesson_id, Homework.status).where(
            Homework.lesson_id.in_(lesson_ids),
            Homework.status.not_in(HIDDEN_STATUSES),
        )
    ).all()
    return {lesson_id: status for lesson_id, status in rows}
