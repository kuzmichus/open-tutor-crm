"""Пересчёт сохранённых моментов времени при смене часового пояса педагога.

Настенное время расписания — инвариант: смена зоны во вкладке «Календарь»
не должна менять то, что педагог видит в календаре. Моменты времени при
этом хранятся в UTC (спека tutor-timezone), поэтому при смене зоны
UTC-значения пересчитываются:

```
настенное время = UTC → старая зона
новый UTC       = настенное время → новая зона
```

Обратный порядок («прибавить разницу смещений к UTC») отвергнут: он
ломается на переходе летнего времени, а настенное время каждого значения
переводится по отдельности — так же, как в `tutor_time.to_utc`/`to_local`.

Пересчитываются только моменты расписания и связанные с ними деньги:

- начало урока (`lessons.starts_at`) — и прошедшего, и будущего;
- начало окна для записи (`slots.starts_at`);
- срок сдачи домашнего задания (`homework.due_at`);
- дата списания за проведённый урок (`account_operations.occurred_at`
  у `kind='lesson'`), потому что она равна началу урока
  (`finance/services/charges.py`).

Не сдвигаются технические метки (`created_at`, `updated_at`, `synced_at`,
`decided_at`, `spent_at`) и календарные даты (недоступность, «действует
по» серии, дата вступления в группу): это не настенное время расписания,
и перевод в UTC для них запрещён (спека tutor-timezone, «Календарные даты
остаются датами без времени»).

**Без коммита**: сдвиг и сохранение настроек должны попасть в одну
транзакцию — коммит делает вызывающая сторона (`save_settings`).
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import AccountOperation
from app.group.models.group import Group
from app.homework.models.homework import Homework
from app.lesson.models.lesson import Lesson
from app.slot.models.slot import Slot
from app.student.models.student import Student
from app.tutor.services.clock import as_utc

# База «парковки» значений окон на время двухфазного обновления: год 9000
# заведомо дальше любого реального расписания, поэтому временные значения
# не столкнутся ни с одним окном репетитора.
_PARK_BASE = datetime(9000, 1, 1, tzinfo=UTC)


def shift_moment(
    value: datetime, old_zone: ZoneInfo, new_zone: ZoneInfo
) -> datetime:
    """Тот же момент в UTC после смены зоны, с сохранением настенного времени.

    Значение из БД (наивное UTC или aware) приводится к UTC, переводится в
    старую зону, теряет tzinfo (настенное время) и трактуется как время
    новой зоны. Несуществующие в ночь перевода часов значения `zoneinfo`
    разрешает по `fold=0` — тот же компромисс, что в `to_utc`.
    """
    wall = as_utc(value).astimezone(old_zone).replace(tzinfo=None)
    return wall.replace(tzinfo=new_zone).astimezone(UTC)


def shift_tutor_schedule(
    db: Session, tutor_id: str, old_zone: ZoneInfo, new_zone: ZoneInfo
) -> dict[str, int]:
    """Пересчитывает моменты расписания репетитора под новую зону (без коммита).

    Возвращает счётчики изменённых записей: `lessons`, `slots`, `homework`,
    `charges`. Смена зоны на ту же самую — не ошибка: значения не меняются,
    счётчики нулевые (вызывающая сторона обычно и не зовёт функцию).
    """
    lessons = tutor_lessons(db, tutor_id)
    for lesson in lessons:
        lesson.starts_at = shift_moment(lesson.starts_at, old_zone, new_zone)
    # Уроки сдвигаются до списаний: `occurred_at` списания равен новому
    # началу урока, и значение берётся уже из пересчитанного объекта.
    db.flush()

    counts = {
        "lessons": len(lessons),
        "slots": _shift_slots(db, tutor_id, old_zone, new_zone),
        "homework": _shift_homework(db, lessons, old_zone, new_zone),
        "charges": _shift_charges(db, lessons),
    }
    db.flush()
    return counts


def tutor_lessons(db: Session, tutor_id: str) -> list[Lesson]:
    """Все уроки репетитора — прошедшие и будущие, любого статуса.

    На `lessons` нет `tutor_id`: владелец выводится из цели, поэтому
    выборка джойнит ученика и группу (как `calendar/services/week.py` и
    `gcalendar/services/initial_sync.py`). Фильтров по времени и статусу
    нет: при смене зоны переезжает всё расписание, иначе календарь
    показывал бы разные сдвиги у прошедших и будущих занятий.
    """
    stmt = (
        select(Lesson)
        .outerjoin(Student, Lesson.student_id == Student.id)
        .outerjoin(Group, Lesson.group_id == Group.id)
        .where(or_(Student.tutor_id == tutor_id, Group.tutor_id == tutor_id))
        .order_by(Lesson.starts_at, Lesson.id)
    )
    return list(db.scalars(stmt).all())


def _shift_slots(
    db: Session, tutor_id: str, old_zone: ZoneInfo, new_zone: ZoneInfo
) -> int:
    """Сдвигает окна репетитора двухфазно (уникальность `starts_at`).

    `UNIQUE(tutor_id, starts_at)` не даёт обновить окна построчно: при
    сдвиге +3 часа окно 10:00 занимает место ещё не сдвинутого окна 13:00.
    Поэтому сначала все окна «паркуются» на заведомо свободные значения,
    затем получают финальные — в конце парковки уникальность не нарушена.
    """
    slots = list(
        db.scalars(
            select(Slot)
            .where(Slot.tutor_id == tutor_id)
            .order_by(Slot.starts_at, Slot.id)
        ).all()
    )
    if not slots:
        return 0

    targets = [shift_moment(slot.starts_at, old_zone, new_zone) for slot in slots]
    for index, slot in enumerate(slots):
        slot.starts_at = _PARK_BASE - timedelta(minutes=index + 1)
    db.flush()

    for slot, target in zip(slots, targets, strict=True):
        slot.starts_at = target
    return len(slots)


def _shift_homework(
    db: Session, lessons: list[Lesson], old_zone: ZoneInfo, new_zone: ZoneInfo
) -> int:
    """Сдвигает сроки сдачи ДЗ уроков репетитора; `due_at = NULL` не трогает."""
    lesson_ids = [lesson.id for lesson in lessons]
    if not lesson_ids:
        return 0
    rows = db.scalars(
        select(Homework).where(
            Homework.lesson_id.in_(lesson_ids),
            Homework.due_at.is_not(None),
        )
    ).all()
    for row in rows:
        row.due_at = shift_moment(row.due_at, old_zone, new_zone)
    return len(rows)


def _shift_charges(db: Session, lessons: list[Lesson]) -> int:
    """Ставит дату списания на новое начало урока; суммы не меняются.

    Правило «`occurred_at` списания — начало урока» живёт в
    `finance/services/charges.py`; здесь оно повторяется осознанно: списание
    без урока не существует, а `sync_lesson_charge` звать целиком значило бы
    пересоздавать строки и терять историю.
    """
    starts = {lesson.id: as_utc(lesson.starts_at) for lesson in lessons}
    if not starts:
        return 0
    operations = db.scalars(
        select(AccountOperation).where(
            AccountOperation.kind == "lesson",
            AccountOperation.lesson_id.in_(list(starts)),
        )
    ).all()
    for operation in operations:
        operation.occurred_at = starts[operation.lesson_id]
    return len(operations)
