"""Срок сдачи нового ДЗ — начало следующего занятия (TOCRM-62).

Педагог задаёт ДЗ на уроке, а сдаётся оно к следующей встрече, поэтому
поле «Срок сдачи» подставляется автоматически: вручную вводить те же дату
и время, что уже есть в календаре, — лишняя работа и источник ошибок.

«Следующее занятие» выбирается так же, как «ближайший урок ученика» в
`student/services/list_metrics.py` и `cabinet/services/lessons.py`:
индивидуальные уроки ученика плюс групповые через `GroupMember`. У
группового урока цели-ученика нет, поэтому для него берутся уроки той же
группы.

Учитываются только запланированные занятия, которые начинаются позже
текущего урока и не раньше текущего момента: проведённый урок или занятие
в прошлом сроком сдачи быть не может. Значения из БД нормализуются через
`as_utc` — SQLite теряет tzinfo (спека tutor-timezone).

Сервис не знает про FastAPI: на вход — сессия и урок, на выход — aware UTC
или None.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.tutor.services.clock import as_utc, utcnow


def _planned_after(lesson: Lesson, moment: datetime):
    """Условия «следующего занятия»: запланировано, позже урока и не в прошлом."""
    return (
        Lesson.status == "planned",
        Lesson.starts_at > as_utc(lesson.starts_at),
        Lesson.starts_at >= moment,
        # Сам урок отсекает уже `starts_at >`; фильтр по id — страховка от
        # строки с тем же временем (например, при ручной правке в БД).
        Lesson.id != lesson.id,
    )


def _student_starts(db: Session, lesson: Lesson, moment: datetime) -> list[datetime]:
    """Начала следующих занятий ученика: индивидуальные и групповые."""
    individual = db.scalars(
        select(Lesson.starts_at).where(
            Lesson.student_id == lesson.student_id,
            *_planned_after(lesson, moment),
        )
    ).all()
    # Групповые занятия ученика: своей строки в `lessons` у него нет, но
    # занятие группы для него такое же занятие (как в `_next_lessons`).
    grouped = db.scalars(
        select(Lesson.starts_at)
        .join(GroupMember, GroupMember.group_id == Lesson.group_id)
        .where(
            GroupMember.student_id == lesson.student_id,
            *_planned_after(lesson, moment),
        )
    ).all()
    return [*individual, *grouped]


def _group_starts(db: Session, lesson: Lesson, moment: datetime) -> list[datetime]:
    """Начала следующих занятий группы (у группового урока нет ученика)."""
    return db.scalars(
        select(Lesson.starts_at).where(
            Lesson.group_id == lesson.group_id,
            *_planned_after(lesson, moment),
        )
    ).all()


def next_lesson_start(
    db: Session,
    lesson: Lesson,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Начало ближайшего следующего занятия урока в UTC; нет — None.

    `now` передаётся снаружи (тесты и вызовы из одного запроса), чтобы
    «сейчас» не расходилось внутри одной страницы.
    """
    moment = now or utcnow()
    if lesson.student_id:
        starts = _student_starts(db, lesson, moment)
    elif lesson.group_id:
        starts = _group_starts(db, lesson, moment)
    else:
        # XOR-ограничение не даёт такого урока; защита от битой строки.
        return None
    if not starts:
        return None
    return min(as_utc(value) for value in starts)
