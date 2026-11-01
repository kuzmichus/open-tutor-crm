"""Сверка с Google: страховка от пропущенных вызовов и сбоев сети.

Задание cron обходит всех репетиторов с подключённым календарём и
приводит события окна к состоянию БД: создаёт отсутствующие, обновляет
изменившиеся по хешу, удаляет события занятий, которых в БД уже нет.

Зачем нужна, если каждый путь уже синхронизирует (design D12):

- сеть моргнула в момент сохранения — хук записал ошибку, но событие
  не создалось; следующий прогон догонит;
- урок удалён в обход хука (каскад, восстановление из бэкапа, прямой
  SQL) — событие осталось бы в календаре навсегда;
- урок перенесён правкой в БД, а не через интерфейс.

Идемпотентность: состояние считается от БД, повторный прогон ничего не
меняет. Окно ограничено (`RECONCILE_PAST_DAYS`/`RECONCILE_FUTURE_DAYS`):
календарь репетитора может содержать годы личных событий, и сверять
всё незачем — синхронизируются только занятия.

Ошибка одного репетитора не мешает остальным: транзакция и коммит —
на репетитора, падение пишется в лог и в карточку.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import now_utc
from app.gcalendar.services import api, connection, mapping
from app.gcalendar.services.errors import (
    GoogleApiError,
    GoogleReauthRequired,
)
from app.gcalendar.services.sync import (
    OUTCOME_CREATED,
    OUTCOME_FAILED,
    OUTCOME_UPDATED,
    log_failure,
    enabled,
    sync_lesson,
)
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.tutor.models.tutor import Tutor

logger = logging.getLogger("gcalendar")

# Окно сверки: день назад (урок, который только что прошёл, ещё может
# быть нужен в календаре) и 90 дней вперёд (расписание на квартал).
RECONCILE_PAST_DAYS = 1
RECONCILE_FUTURE_DAYS = 90

def reconcile_all(db: Session, *, now: datetime | None = None) -> int:
    """Сверяет календари всех подключённых репетиторов; число изменений.

    Возвращает число созданных, обновлённых и удалённых событий — это
    значение cron пишет в лог. Коммит — на репетитора: упавшая сверка
    одного не откатывает уже сделанное другим.
    """
    moment = now or now_utc()
    changed = 0
    for tutor in _connected_tutors(db):
        try:
            changed += reconcile_tutor(db, tutor, now=moment)
            db.commit()
        except Exception:  # noqa: BLE001 — изоляция репетитора (design D12)
            db.rollback()
            logger.exception("Google Календарь: сверка упала (tutor=%s)", tutor.id)
    return changed

def reconcile_tutor(db: Session, tutor, *, now: datetime | None = None) -> int:
    """Сверяет окно одного репетитора. Без коммита — его делает вызывающий."""
    if not enabled(db, tutor.id):
        return 0

    moment = now or now_utc()
    time_min = moment - timedelta(days=RECONCILE_PAST_DAYS)
    time_max = moment + timedelta(days=RECONCILE_FUTURE_DAYS)
    changed = 0

    for lesson in _window_lessons(db, tutor.id, time_min, time_max):
        outcome = sync_lesson(db, tutor, lesson)
        if outcome in (OUTCOME_CREATED, OUTCOME_UPDATED):
            changed += 1
        elif outcome == OUTCOME_FAILED:
            # Ошибка уже в логе и в карточке: остальные уроки не трогаем,
            # следующий прогон попробует снова.
            continue

    changed += _delete_orphans(db, tutor, time_min, time_max)
    return changed

def _delete_orphans(
    db: Session, tutor, time_min: datetime, time_max: datetime
) -> int:
    """Удаляет события, чьих занятий в БД уже нет (или они вне окна).

    Сверка опирается на два источника: строки `calendar_events` (что мы
    создавали) и список событий календаря в окне. Событие считается
    сиротой, если строка соответствия есть, а урока нет — каскад должен
    был удалить строку, но восстановление из бэкапа или прямой SQL этого
    не гарантируют.
    """
    known = mapping.event_ids_of_tutor(db, tutor.id)
    if not known:
        return 0

    existing_lessons = set(
        db.scalars(
            select(Lesson.id).where(Lesson.id.in_(
                [row.lesson_id for row in known.values()]
            ))
        ).all()
    )
    orphans = [
        row for row in known.values() if row.lesson_id not in existing_lessons
    ]
    if not orphans:
        return 0

    calendar_id = connection.calendar_id(db, tutor.id)
    try:
        remote = api.list_event_ids(
            connection.access_token(db, tutor.id) or "",
            calendar_id,
            time_min=time_min.isoformat(),
            time_max=time_max.isoformat(),
        )
    except GoogleReauthRequired:
        connection.clear(db, tutor.id)
        return 0
    except GoogleApiError as exc:
        log_failure(db, tutor.id, exc)
        return 0

    removed = 0
    for row in orphans:
        # Удаляем только то, что реально существует в Google: иначе
        # каждый прогон повторял бы безнадёжный DELETE.
        if row.event_id in remote:
            try:
                api.delete_event(
                    connection.access_token(db, tutor.id) or "",
                    row.calendar_id or calendar_id,
                    row.event_id,
                )
            except GoogleApiError as exc:
                log_failure(db, tutor.id, exc)
                continue
        mapping.forget(db, row.lesson_id)
        removed += 1
    return removed

def _connected_tutors(db: Session) -> list[Tutor]:
    """Репетиторы с сохранённым refresh_token — одной выборкой, без N+1."""
    from app.tutor.models.tutor_param import TutorParam

    return list(
        db.scalars(
            select(Tutor)
            .join(
                TutorParam,
                (TutorParam.tutor_id == Tutor.id)
                & (TutorParam.key == connection.REFRESH_TOKEN_KEY),
            )
            .order_by(Tutor.id)
        ).all()
    )

def _window_lessons(
    db: Session, tutor_id: str, time_min: datetime, time_max: datetime
) -> list[Lesson]:
    """Занятия репетитора в окне сверки, по возрастанию времени."""
    stmt = (
        select(Lesson)
        .outerjoin(Student, Lesson.student_id == Student.id)
        .outerjoin(Group, Lesson.group_id == Group.id)
        .where(
            Lesson.starts_at >= time_min,
            Lesson.starts_at < time_max,
            or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id),
        )
        .order_by(Lesson.starts_at)
    )
    return list(db.scalars(stmt).all())
