"""Первичная выгрузка: все будущие занятия репетитора в Google.

Выполняется сразу после подключения календаря (ответ пользователя на
вопрос №2): репетитор не должен вручную пересохранять каждый урок,
чтобы увидеть своё расписание в Google. Прошедшие занятия не выгружаются:
календарь нужен на будущее, а не как архив.

Порядок — по времени начала: события создаются «сверху вниз», и при
обрыве на ошибке уже выгруженное остаётся осмысленным. Ошибка одного
урока не останавливает выгрузку (best-effort): счётчик ошибок
возвращается для текста на карточке, а сверка cron догонит пропущенное.
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import now_utc
from app.gcalendar.services.sync import (
    OUTCOME_CREATED,
    OUTCOME_FAILED,
    OUTCOME_UPDATED,
    enabled,
    sync_lesson,
)
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student

def sync_upcoming(db: Session, tutor) -> tuple[int, int, int]:
    """Выгружает будущие занятия. Возвращает `(создано, обновлено, ошибок)`.

    «Будущее» — `starts_at >= сейчас` (UTC): урок, который идёт прямо
    сейчас, тоже попадает в календарь. Статус не фильтруется: проведённый
    урок с будущей датой — редкость, но скрывать его незачем.

    Без подключённого календаря — `(0, 0, 0)` и ни одного запроса к API.
    """
    if not enabled(db, tutor.id):
        return 0, 0, 0

    created = updated = failed = 0
    for lesson in _upcoming_lessons(db, tutor.id):
        outcome = sync_lesson(db, tutor, lesson)
        if outcome == OUTCOME_CREATED:
            created += 1
        elif outcome == OUTCOME_UPDATED:
            updated += 1
        elif outcome == OUTCOME_FAILED:
            failed += 1
    return created, updated, failed

def _upcoming_lessons(db: Session, tutor_id: str) -> list[Lesson]:
    """Занятия репетитора со `starts_at >= сейчас`, по возрастанию времени.

    Пачки по `limit/offset` не листаются: выгрузка идёт один раз при
    подключении, а сдвиг окна пришлось бы отслеживать с риском пропустить
    урок. У одного репетитора занятий тысячи, не миллионы — список
    помещается в память.
    """
    stmt = (
        select(Lesson)
        .outerjoin(Student, Lesson.student_id == Student.id)
        .outerjoin(Group, Lesson.group_id == Group.id)
        .where(
            Lesson.starts_at >= now_utc(),
            or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
        )
        .order_by(Lesson.starts_at)
    )
    return list(db.scalars(stmt).all())
