"""Пересчёт баланса: ремонт счёта, а не переписывание истории (design D7).

Кнопка «Пересчитать баланс» и баннер «Баланс не пересчитан» — две стороны
одной задачи: таблица `account_operations` появилась позже уроков, и у
уже проведённых занятий списаний нет. Бэкфилл миграцией отвергнут (design
D8), поэтому историю догоняет явное действие репетитора.

Правило ремонта:

```
для каждого проведённого урока ученика с определимой ценой:
    строки (lesson_id, student_id) нет — создать
    строка есть — не трогать (сумму не переписываем)
для каждой строки списания урока, который больше не проведён:
    удалить
```

**Почему не «удалить всё и построить заново»**: `group_members` хранит
только текущий состав, исключённый участник удаляется физически (design
D7). Полный rebuild молча стёр бы исторические списания вышедших из
группы и создал бы их заново только у нынешних участников — то есть
переписал бы прошлое по сегодняшнему составу.

**Почему не переписываем существующие суммы**: изменение цены группы
задним числом — настройка на будущее, а не документ прошлого. Списание
меняется только вместе с самим уроком (`charges.sync_lesson_charge`).

Сервис не знает про FastAPI: на вход — сессия, репетитор и ученик,
на выход — число добавленных строк.
"""

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import AccountOperation
from app.finance.services.charges import (
    COMPLETED_STATUS,
    lesson_targets,
)
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.student.services.activation import activate_on_first_charge

# SQL-выражение цены участника группы: индивидуальная цена перекрывает
# общую (design D6). `coalesce` повторяет правило `charges.group_targets`
# на стороне БД — без него детектор расхождения считал бы иначе, чем
# пересчёт, и баннер мог бы не исчезать после ремонта.
_GROUP_PRICE = func.coalesce(GroupMember.price_override, Group.price_per_lesson)

# Списания ученика по уроку уже существует — условие для NOT EXISTS.
_CHARGE_EXISTS = exists(
    select(AccountOperation.id).where(
        AccountOperation.kind == "lesson",
        AccountOperation.lesson_id == Lesson.id,
        AccountOperation.student_id == Student.id,
    )
)


def student_completed_lessons(db: Session, student_id: str) -> list[Lesson]:
    """Проведённые уроки ученика: индивидуальные и групповые, где он участник.

    Групповое участие берётся по текущему составу — истории членства в
    модели нет (design D7). Для уже существующих списаний это безопасно:
    `recalculate` их не удаляет, пока урок остаётся проведённым.
    """
    member_groups = select(GroupMember.group_id).where(
        GroupMember.student_id == student_id
    )
    return list(
        db.scalars(
            select(Lesson).where(
                Lesson.status == COMPLETED_STATUS,
                or_(
                    Lesson.student_id == student_id,
                    Lesson.group_id.in_(member_groups),
                ),
            )
        ).all()
    )


def student_charges(db: Session, student_id: str) -> dict[str, AccountOperation]:
    """Списания ученика по `lesson_id` — для проверки «строка уже есть»."""
    rows = db.scalars(
        select(AccountOperation).where(
            AccountOperation.student_id == student_id,
            AccountOperation.kind == "lesson",
        )
    ).all()
    return {operation.lesson_id: operation for operation in rows}


def recalculate(db: Session, tutor_id: str, student_id: str) -> int:
    """Добавляет недостающие списания ученика; возвращает их число.

    Ученик чужого репетитора не ремонтируется: вьюха отвечает 404 раньше
    (`get_owned_student`), а сервис не должен доверять вызывающему.
    Существующие строки не изменяются — ни сумма, ни дата: история должна
    переживать повторное нажатие кнопки.
    """
    student = db.get(Student, student_id)
    if student is None or student.tutor_id != tutor_id:
        return 0

    lessons = student_completed_lessons(db, student_id)
    completed_ids = {lesson.id for lesson in lessons}
    charges = student_charges(db, student_id)

    added = 0
    for lesson in lessons:
        price = dict(lesson_targets(db, lesson)).get(student_id)
        # Цена не определима — списания быть не должно (design D6).
        if price is None or lesson.id in charges:
            continue
        db.add(
            AccountOperation(
                student_id=student_id,
                kind="lesson",
                amount=price,
                occurred_at=lesson.starts_at,
                lesson_id=lesson.id,
            )
        )
        # Backfill-списание — тоже «первый платный урок» для «нового»
        # ученика: без хука кнопка «Пересчитать баланс» не активировала бы
        # тех, чьи занятия прошли до появления счёта.
        activate_on_first_charge(db, student_id)
        added += 1

    # Урок перестал быть проведённым — его списание больше не имеет смысла.
    # Такие строки остались только у «осиротевших» данных: обычный путь
    # снимает их в `sync_lesson_charge`.
    for lesson_id, operation in charges.items():
        if lesson_id not in completed_ids:
            db.delete(operation)

    db.commit()
    return added


def has_missing_charges(db: Session, tutor_id: str, student_id: str) -> bool:
    """Есть ли проведённый урок с ценой, по которому нет списания (design D8).

    Один запрос с двумя `EXISTS`: индивидуальная ветка (урок ученика) и
    групповая (ученик — участник группы). Проверка на каждой отрисовке
    панели, поэтому N+1 здесь недопустим — в отличие от редкого пересчёта.

    Условия совпадают с `recalculate`: статус «Проведён», цена определима,
    строка `(lesson_id, student_id)` отсутствует. Иначе баннер мог бы
    висеть после ремонта или не появиться перед ним.
    """
    student = db.get(Student, student_id)
    if student is None or student.tutor_id != tutor_id:
        return False

    individual_lesson = (
        select(Lesson.id)
        .join(Student, Student.id == Lesson.student_id)
        .where(
            Student.id == student_id,
            Student.tutor_id == tutor_id,
            Lesson.status == COMPLETED_STATUS,
            Lesson.price.is_not(None),
            ~_CHARGE_EXISTS,
        )
        .exists()
    )
    group_lesson = (
        select(Lesson.id)
        .join(GroupMember, GroupMember.group_id == Lesson.group_id)
        .join(Group, Group.id == Lesson.group_id)
        .join(Student, Student.id == GroupMember.student_id)
        .where(
            GroupMember.student_id == student_id,
            Group.tutor_id == tutor_id,
            Student.tutor_id == tutor_id,
            Lesson.status == COMPLETED_STATUS,
            _GROUP_PRICE.is_not(None),
            ~_CHARGE_EXISTS,
        )
        .exists()
    )
    return bool(db.scalar(select(or_(individual_lesson, group_lesson))))
