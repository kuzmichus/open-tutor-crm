"""Автоматическое завершение не отмеченных уроков — задание cron.py.

Репетитор забывает отметить проведённый урок: он остаётся «Запланирован»,
списание не создаётся, статистика врёт. Страховка — задание cron: через
**24 часа** после окончания урока оно ставит статус «Проведён» и синхронизирует
списания штатным `charges.sync_lesson_charge` — деньгами (occurred_at — начало
урока, цена урока), активацией «нового» ученика и возможностью вернуть урок в
«Запланирован» руками автозавершение не отличимо от ручной отметки
(design D4 change'а unmarked-lessons).

Без коммита: коммит делает runner cron (`app/common/services/cron.py`),
задача — только изменения в его транзакции. Условие отбора считается от
«сейчас», поэтому задача идемпотентна: наложение минутных прогонов и повторный
запуск безопасны.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.services.charges import sync_lesson_charge
from app.lesson.models.lesson import Lesson
from app.lesson.services.unmarked import is_unmarked
from app.tutor.services.clock import as_utc, utcnow

# Сколько после окончания урок ждёт ручной отметки, прежде чем автозавершение
# закроет его: ровно окно, которое баннер-напоминание проговаривает на главной.
AUTO_COMPLETE_AFTER = timedelta(hours=24)


def overdue_lessons(
    db: Session,
    *,
    now: datetime | None = None,
    after: timedelta = AUTO_COMPLETE_AFTER,
) -> list[Lesson]:
    """Не отмеченные уроки, «просроченные» дольше `after` после конца.

    Грубый SQL-префильтр: конец урока не раньше начала, значит «начало
    позже отсечки» отсеивается без вычисления длительности; финально
    решает общий предикат `is_unmarked` + порог `after` (design D3).
    """
    cutoff = as_utc(now or utcnow()) - after
    candidates = db.scalars(
        select(Lesson).where(Lesson.status == "planned", Lesson.starts_at <= cutoff)
    ).all()
    return [
        lesson
        for lesson in candidates
        # Отсечка и «сейчас» для предиката — один и тот же момент:
        # просроченность и «не отмеченность» считаются одинаково.
        if is_unmarked(lesson, now=cutoff)
    ]


def auto_complete_finished_lessons(db: Session, *, now: datetime | None = None) -> int:
    """Отмечает «Проведён» просроченные не отмеченные уроки; возвращает их число.

    Списание синхронизируется по каждому уроку до коммита runner'а —
    урок, статус и счёт сохраняются одной транзакцией.
    """
    lessons = overdue_lessons(db, now=now)
    for lesson in lessons:
        lesson.status = "completed"
        sync_lesson_charge(db, lesson)
    return len(lessons)
