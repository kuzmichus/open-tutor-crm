"""«Мои уроки» кабинета: ближайшие запланированные занятия ученика.

Те же два SELECT, что в `student_lessons.py` (индивидуальные + групповые
через `GroupMember`), но кабинет показывает только будущее: статус
`planned` и `starts_at >= utcnow()`, по возрастанию, ограниченный список
(D6). Прошедшие и проведённые в кабинете не показываются; грузить всю
историю ученика ради первых N не нужно.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.tutor.services.clock import utcnow

# Сколько ближайших уроков показывает «Мои уроки»: полный календарный
# вид — кандидат в последующие change'и (design, риски).
UPCOMING_LIMIT = 5


def upcoming_lessons(db: Session, student_id: str) -> list[Lesson]:
    """Ближайшие запланированные уроки ученика по возрастанию времени.

    Индивидуальные и групповые уроки ученика собираются двумя SELECT и
    объединяются в Python: у группового урока цель другая, и единый
    запрос потребовал бы UNION с внешними соединениями ради пары полей.
    Сравнение времени — в SQL с aware-utcnow: в БД моменты хранятся
    UTC-строками одного формата (спека tutor-timezone).
    """
    now = utcnow()
    rows: list[Lesson] = []
    rows += db.scalars(
        select(Lesson).where(
            Lesson.student_id == student_id,
            Lesson.status == "planned",
            Lesson.starts_at >= now,
        )
    ).all()
    rows += db.scalars(
        select(Lesson)
        .join(GroupMember, GroupMember.group_id == Lesson.group_id)
        .where(
            GroupMember.student_id == student_id,
            Lesson.status == "planned",
            Lesson.starts_at >= now,
        )
    ).all()
    # Ближайшее занятие первым; вторичный ключ держит порядок одинаковых
    # времён (у `student_lessons.py` сортировка обратная — там новые
    # сверху, здесь будущее снизу вверх).
    rows.sort(key=lambda lesson: (lesson.starts_at, lesson.id))
    return rows[:UPCOMING_LIMIT]
