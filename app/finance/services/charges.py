"""Списания за проведённые уроки (design D6).

Списание — функция от урока, а не отдельная запись, которую кто-то ведёт
руками: `sync_lesson_charge(db, lesson)` приводит строки `account_operations`
с `kind='lesson'` в соответствие с текущим состоянием урока.

```
цели = []                                   если урок не «Проведён»
     = участники группы                     если урок групповой
     = [ученик]                             иначе
для каждой цели с определимой ценой:
    upsert строки (lesson_id, student_id): amount = цена
удалить строки по lesson_id, которых больше нет в целях
```

Цена цели: `lesson.price` для индивидуального урока; для участника группы —
`price_override ?? group.price_per_lesson`. Цена не определима — строки
нет вовсе (не «0 ₽», а именно отсутствие строки): списание нуля было бы
операцией, влияющей на баланс, и попало бы в историю.

`occurred_at` списания — `lesson.starts_at` (design D15): история читается
как хронология занятий, а не как хронология правок.

**Без коммита**: функция вызывается из путей записи урока до их `commit`,
поэтому урок и его списания сохраняются одной транзакцией. Тесты, которые
создают уроки фабрикой напрямую, списаний не получают — это осознанно
(design D6): неявных подписок на ORM-события в проекте нет.

`upsert`, а не «удалить и создать»: удаление меняло бы `id` строки и
сбрасывало `occurred_at`, а история должна переживать правку цены.

Сервис не знает про FastAPI: на вход — сессия и урок, на выход — ничего
(или число строк, если это удобно вызывающему).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import AccountOperation
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.tutor.services.clock import as_utc

# Статус урока, при котором занятие считается состоявшимся.
COMPLETED_STATUS = "completed"


def group_targets(db: Session, group_id: str) -> list[tuple[str, int | None]]:
    """Цели группового урока: пары «ученик, цена» по текущему составу.

    Цена участника — его индивидуальная (`price_override`), иначе общая
    цена группы. Пары с неопределимой ценой тоже возвращаются (`None`):
    вызывающий решает, создавать ли строку, — так `sync` и `recalculate`
    используют одно правило.

    Состав берётся текущий: истории членства в модели нет (design D7), и
    это осознанное ограничение — исключённый участник просто перестаёт
    получать новые списания, а прошлые строки остаются в истории.
    """
    group = db.get(Group, group_id)
    group_price = group.price_per_lesson if group is not None else None
    rows = db.execute(
        select(GroupMember.student_id, GroupMember.price_override).where(
            GroupMember.group_id == group_id
        )
    ).all()
    return [
        (student_id, price_override if price_override is not None else group_price)
        for student_id, price_override in rows
    ]


def lesson_targets(db: Session, lesson: Lesson) -> list[tuple[str, int | None]]:
    """Цели урока с ценами: пусто у непроведённого урока.

    Непроведённый урок не списывает ничего: «Запланирован» — это ещё не
    состоявшееся занятие, а возврат в «Запланирован» должен снять списание
    (спека student-finance, «Возврат урока в „Запланирован“»).
    """
    if lesson.status != COMPLETED_STATUS:
        return []
    if lesson.group_id:
        return group_targets(db, lesson.group_id)
    if lesson.student_id:
        return [(lesson.student_id, lesson.price)]
    return []


def sync_lesson_charge(db: Session, lesson: Lesson) -> int:
    """Приводит списания урока в соответствие с ним; без коммита.

    Возвращает число списаний, которые остались у урока после синхронизации
    (ноль — урок ничего не списывает).
    """
    occurred_at = as_utc(lesson.starts_at)
    targets = lesson_targets(db, lesson)
    # Цена не определима — строки быть не должно: «0 ₽» в истории
    # выглядел бы как списание, а не как отсутствие цены.
    priced = {student_id: price for student_id, price in targets if price is not None}

    existing = {
        operation.student_id: operation
        for operation in db.scalars(
            select(AccountOperation).where(
                AccountOperation.lesson_id == lesson.id,
                AccountOperation.kind == "lesson",
            )
        ).all()
    }

    for student_id, price in priced.items():
        operation = existing.pop(student_id, None)
        if operation is None:
            db.add(
                AccountOperation(
                    student_id=student_id,
                    kind="lesson",
                    amount=price,
                    occurred_at=occurred_at,
                    lesson_id=lesson.id,
                )
            )
            continue
        # Сумма следует за ценой урока (спека «Изменение оплаты проведённого
        # урока пересчитывает списание»); `occurred_at` — за началом урока,
        # чтобы перенос занятия не оставлял списание на старом месте.
        operation.amount = price
        operation.occurred_at = occurred_at

    # Строки, которых больше нет в целях: ученик вышел из группы, цена
    # исчезла, урок вернулся в «Запланирован».
    for operation in existing.values():
        db.delete(operation)

    return len(priced)


def series_lessons(db: Session, series_id: str) -> list[Lesson]:
    """Уроки серии — для массового пересчёта списаний.

    Отдельная функция, а не `select` в вьюхе: правило «что такое серия»
    должно жить в одном месте, рядом с синхронизацией.
    """
    return list(db.scalars(select(Lesson).where(Lesson.series_id == series_id)).all())


def sync_lesson_charges(
    db: Session, lesson: Lesson, *, series_applied: bool = False
) -> None:
    """Синхронизирует списания урока и, при массовой правке, всей серии.

    Без коммита: вызывается из `views/update.py` перед `db.commit()`, чтобы
    урок, серия и счёт сохранялись одной транзакцией.

    `series_applied` — в форме было включено «Применить ко всей серии»:
    общие поля (в том числе цена) уже применены к каждому уроку серии
    (`mass_update.apply_to_series`), поэтому и списания пересчитываются у
    всех — иначе уроки обновились бы, а история денег осталась старой.

    Сам урок синхронизируется всегда: он мог быть передан другой цели,
    переведён в «Проведён» или обратно и без массовой правки.
    """
    targets = [lesson]
    if series_applied and lesson.series_id:
        targets = series_lessons(db, lesson.series_id)
    for item in targets:
        sync_lesson_charge(db, item)
