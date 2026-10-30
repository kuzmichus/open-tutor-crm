"""Домашние задания ребёнка для кабинета родителя (design D7).

Домашка живёт на уроке, поэтому ДЗ ребёнка — это домашки уроков, где
ученик — цель: те же два SELECT, что в `lessons.py` (индивидуальные +
групповые через `GroupMember`), с JOIN `homework`. Показываются записи со
статусом ≠ `not_assigned` — «Не задано» это пустая запись, домашнего
задания нет.

«Секретность через выборку»: контекст родителя собирается явным списком
колонок — только то, что видит ученик (задание, срок, статус, комментарий
педагога, запись урока). Колонки `teacher_note` в выборе нет, и попасть
в шаблон она не может — скрытие гарантируется составом запроса, а не
условием в шаблоне. Роутов записи из кабинета родителя нет (спека).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.group.models.group_member import GroupMember
from app.homework.models.homework import Homework
from app.lesson.models.lesson import Lesson

# Статус «Не задано» — записи без домашнего задания: в кабинете её нет.
HIDDEN_STATUSES = ("not_assigned",)

# Сколько последних заданий показывает вкладка: пагинации нет, страница
# открывают ради актуальной домашки, а не ради архива (список ограничен —
# design, риски).
HOMEWORK_LIMIT = 20

# Явный список колонок контекста: `teacher_note` здесь отсутствует —
# состав выдачи родителю фиксируется одним местом.
_CONTEXT_COLUMNS = (
    Lesson.starts_at,
    Lesson.type,
    Homework.id,
    Homework.assignment,
    Homework.due_at,
    Homework.status,
    Homework.teacher_comment,
    Homework.recording_url,
)


@dataclass(frozen=True)
class ChildHomeworkCard:
    """Строка списка «Домашних заданий» ребёнка: ДЗ и его урок.

    Полей ровно столько, сколько видит ученик; заметки педагога в контексте
    нет в принципе (D7).
    """

    lesson_starts_at: datetime
    lesson_type: str
    assignment: str
    due_at: datetime | None
    status: str
    teacher_comment: str | None
    recording_url: str | None


def child_homework(db: Session, student_id: str) -> list[ChildHomeworkCard]:
    """Домашние задания ребёнка, свежие сверху, не больше `HOMEWORK_LIMIT`.

    Индивидуальные и групповые уроки ученика собираются двумя SELECT и
    объединяются в Python: у группового урока цель другая, и единый
    запрос потребовал бы UNION с внешними соединениями ради пары полей.
    """
    rows = list(
        db.execute(
            select(*_CONTEXT_COLUMNS)
            .join(Homework, Homework.lesson_id == Lesson.id)
            .where(Lesson.student_id == student_id, Homework.status.not_in(HIDDEN_STATUSES))
        ).all()
    )
    rows += list(
        db.execute(
            select(*_CONTEXT_COLUMNS)
            .join(Homework, Homework.lesson_id == Lesson.id)
            .join(GroupMember, GroupMember.group_id == Lesson.group_id)
            .where(
                GroupMember.student_id == student_id,
                Homework.status.not_in(HIDDEN_STATUSES),
            )
        ).all()
    )
    # Свежее задание сверху; вторичный ключ держит порядок уроков с одним
    # временем (id в сортировке участвует, в контекст не попадает).
    rows.sort(key=lambda row: (row.starts_at, row[2]), reverse=True)
    return [
        ChildHomeworkCard(
            lesson_starts_at=row.starts_at,
            lesson_type=row.type,
            assignment=row.assignment,
            due_at=row.due_at,
            status=row.status,
            teacher_comment=row.teacher_comment,
            recording_url=row.recording_url,
        )
        for row in rows[:HOMEWORK_LIMIT]
    ]
