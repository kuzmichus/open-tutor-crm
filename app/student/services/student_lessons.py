"""Уроки ученика для модалки «Уроки» (по образцу `group_lessons.py`).

Уроки ученика — не только его индивидуальные: ученик участвует и в
групповых занятиях, и для него они такие же уроки, как личные (списания
и «Проведено» считают их тем же способом — `list_metrics.py`). Два
`SELECT` объединяются в Python: у группового урока цель другая, и
единый запрос потребовал бы UNION с внешними соединениями ради пары
полей.

Строки newest-first (`starts_at` по убыванию): модалку открывают ради
последних занятий — в референсе сверху более свежий урок.

Фильтр-чипы «Все / Прошедшие / Запланированные» — по статусу урока:
«Прошедшие» — это «Проведён» (статус модели), значения query — значения
`LESSON_STATUSES`, неизвестное схлопывается в «Все».
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import LESSON_STATUSES, LESSON_TYPE_LABELS, Lesson

# Значения фильтра-чипа; пусто — «Все».
FILTER_STATUSES = ("", *LESSON_STATUSES)


def normalize_status(status: str) -> str:
    """Значение чипа из query: неизвестное схлопывается в «Все»."""
    return status if status in FILTER_STATUSES else ""


def list_student_lessons(
    db: Session,
    student_id: str,
    *,
    status: str = "",
    subject: str = "",
) -> list[Lesson]:
    """Уроки ученика от новых к старым; пустой статус — все.

    `subject` — предмет педагога: подстрока строки, когда свой предмет у
    урока не назван (тот же fallback, что у расписания главной).
    """
    status = normalize_status(status)

    rows: list[Lesson] = []
    rows += list(
        db.scalars(
            select(Lesson).where(
                Lesson.student_id == student_id,
            )
        ).all()
    )
    rows += list(
        db.scalars(
            select(Lesson)
            .join(GroupMember, GroupMember.group_id == Lesson.group_id)
            .where(GroupMember.student_id == student_id)
        ).all()
    )

    if status:
        rows = [lesson for lesson in rows if lesson.status == status]
    # Новые сверху; вторичный ключ держит порядок одинаковых времён.
    rows.sort(key=lambda lesson: (lesson.starts_at, lesson.id), reverse=True)
    return rows


def lesson_subject(lesson: Lesson, group_name: str | None, subject: str) -> str:
    """Подпись предмета строки: предмет педагога или тип урока.

    У группового урока вместо предмета — имя группы: репетитору важнее
    видеть, какая группа занималась (предмет у всех групп один).
    """
    if lesson.group_id:
        return group_name or LESSON_TYPE_LABELS.get(lesson.type, lesson.type)
    return subject or LESSON_TYPE_LABELS.get(lesson.type, lesson.type)


def group_names(db: Session, lessons: list[Lesson]) -> dict[str, str]:
    """Имена групп для строк модалки одним запросом (без N+1)."""
    group_ids = {lesson.group_id for lesson in lessons if lesson.group_id}
    if not group_ids:
        return {}
    rows = db.execute(
        select(Group.id, Group.name).where(Group.id.in_(group_ids))
    ).all()
    return {group_id: name for group_id, name in rows}
