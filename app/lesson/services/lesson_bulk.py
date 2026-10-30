"""Массовая отметка уроков проведёнными (change lessons-table-scale).

Ежедневный сценарий репетитора — «отметить прошедшие уроки проведёнными».
Поштучно это одна модалка на урок: пять уроков — пять модалок и пять
перезапросов списка. Здесь тот же результат одним POST.

Правила:
- меняются только уроки вошедшего репетитора (выборка идёт через JOIN по
  цели, как `get_owned_lesson`): чужой id в форме не даёт ни ошибки, ни
  доступа — он просто не попадает в выборку;
- уже проведённые уроки не трогаются: повторная отметка не должна
  пересчитывать списания и сдвигать историю денег;
- списания синхронизируются по каждому изменённому уроку до коммита —
  уроки и счёт сохраняются одной транзакцией (design D6 спеки finance).

Сервис не знает про FastAPI: на вход — `Session`, `tutor_id` и список id,
на выход — число изменённых уроков.
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.finance.services.charges import sync_lesson_charge
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student

COMPLETED = "completed"
PLANNED = "planned"


def complete_lessons(db: Session, tutor_id: str, lesson_ids: list[str]) -> int:
    """Переводит выбранные уроки в «Проведён»; возвращает число изменённых.

    Без коммита: вызывающая вьюха коммитит сама, вместе с ответом. Пустой
    список id — ноль изменений (нажали кнопку, ничего не выбрав).
    """
    if not lesson_ids:
        return 0

    stmt = (
        select(Lesson)
        .outerjoin(Student, Lesson.student_id == Student.id)
        .outerjoin(Group, Lesson.group_id == Group.id)
        .where(
            Lesson.id.in_(lesson_ids),
            # Только запланированные: проведённый урок уже отмечен, а его
            # цена и списание заморожены (спека «Цена проведённого урока
            # только для чтения»).
            Lesson.status == PLANNED,
            or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
        )
    )

    lessons = db.scalars(stmt).all()
    for lesson in lessons:
        lesson.status = COMPLETED
        # Списание — производная от статуса: без синхронизации урок стал бы
        # «Проведён», а счёт ученика не изменился бы.
        sync_lesson_charge(db, lesson)
    return len(lessons)
