"""Контекст диалога платежа со страницы финансов (design D5).

Тот же шаблон `finance/_payment_dialog.html`, что у диалога из карточки
ученика, но `payment_student is None`: ученик — поле выбора, исходно
пустое. Варианты выбора приходят сервером в `data-options` (общий виджет
`_person_picker.html`), поле ввода не имеет `name` — в POST уходит только
скрытый `student_id`, который заполняет Alpine.

При ошибке валидации присланные значения перекрывают умолчания (паттерн
`payment_dialog_context`), а выбранный ученик возвращается в контексте:
ошибка в сумме не должна сбрасывать выбор.

Сервис не знает про FastAPI: на вход — сессия, репетитор и значения
формы, на выход — контекст шаблона.
"""

from json import dumps

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import today_local
from app.finance.models.account_operation import (
    PAYMENT_METHODS,
    PAYMENT_METHOD_LABELS,
    PAYMENT_STATUSES,
    PAYMENT_STATUS_LABELS,
)
from app.finance.services.payment_dialog import (
    PAYMENT_DIALOG_TITLES,
    _form_values,
)
from app.finance.services.payment_form import empty_payment_form
from app.student.models.student import Student
from app.student.services.presentation import student_full_name

# Варианты выбора — ученики, с которыми продолжаются деньги: «архивные»
# в список не попадают, платёж им внесут из карточки ученика.
INCOME_STUDENT_STATUSES = ("new", "active")


def payment_students_json(db: Session, tutor_id: str) -> str:
    """JSON-варианты выбора ученика для `data-options` поля диалога.

    Вариант — id, имя и подпись-класс: пикер ищет по ним, шаблон списка
    показывает имя слева и класс справа (как поле «Добавить ученика»
    в форме группы).
    """
    students = db.scalars(
        select(Student)
        .where(
            Student.tutor_id == tutor_id,
            Student.status.in_(INCOME_STUDENT_STATUSES),
        )
        .order_by(Student.first_name, Student.last_name)
    ).all()
    return dumps(
        [
            {
                "id": student.id,
                "name": student_full_name(student),
                "meta": f"{student.grade} класс" if student.grade else "",
            }
            for student in students
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def income_dialog_context(
    db: Session,
    tutor,
    *,
    data: dict | None = None,
    errors: list[str] | None = None,
    selected_student=None,
) -> dict:
    """Контекст `finance/_payment_dialog.html` в режиме выбора ученика.

    `data` — значения, введённые при ошибке; `selected_student` — ученик,
    выбранный до ошибки (свой, уже проверенный).
    """
    values = empty_payment_form(today_local(tutor))
    if data is not None:
        values = _form_values(data)

    return {
        "payment_student": None,
        "payment": None,
        "payment_form": values,
        "payment_errors": errors or [],
        "payment_action": "/tutor/payments",
        "payment_title": PAYMENT_DIALOG_TITLES["create"],
        "payment_methods": PAYMENT_METHODS,
        "payment_method_labels": PAYMENT_METHOD_LABELS,
        "payment_statuses": PAYMENT_STATUSES,
        "payment_status_labels": PAYMENT_STATUS_LABELS,
        "payment_students_json": payment_students_json(db, tutor.id),
        "income_student_id": selected_student.id if selected_student else "",
        "income_student_name": (
            student_full_name(selected_student) if selected_student else ""
        ),
    }
