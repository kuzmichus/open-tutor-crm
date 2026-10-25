"""Создание ученика из мини-формы группы (решение D9).

Мини-форма живёт внутри формы группы, поэтому у неё свой эндпоинт: ответ —
фрагмент состава, а не модалка ученика. Правила полей совпадают с карточкой
ученика (`app/student/services/student_form.py`), но берутся только три поля:
имя, фамилия и телефон. Статус и подтип — «Новый» и «Ребёнок»: полное
редактирование доступно на странице учеников.
"""

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.common.colors import assign_color
from app.common.services.forms import text_value
from app.student.models.student import Student
from app.student.services.phone import format_phone, is_phone_like

_FIRST_NAME_MAX = 100
_LAST_NAME_MAX = 100
_PHONE_MAX = 32


def parse_mini_form(form: Mapping) -> tuple[dict, list[str]]:
    """Разбирает и проверяет мини-форму: имя обязательно, телефон — телефон.

    Возвращает `(данные, ошибки)`. Телефон нормализуется тем же правилом,
    что и в карточке ученика, поэтому значение сохраняется в едином виде.
    """
    errors: list[str] = []
    data = {
        "first_name": text_value(form, "first_name"),
        "last_name": text_value(form, "last_name"),
        "phone": text_value(form, "phone"),
    }

    if not data["first_name"]:
        errors.append("Укажите имя ученика.")
    elif len(data["first_name"]) > _FIRST_NAME_MAX:
        errors.append(f"Имя не длиннее {_FIRST_NAME_MAX} символов.")

    if len(data["last_name"]) > _LAST_NAME_MAX:
        errors.append(f"Фамилия не длиннее {_LAST_NAME_MAX} символов.")

    if not is_phone_like(data["phone"]):
        errors.append("Укажите корректный телефон.")
    else:
        data["phone"] = format_phone(data["phone"])
        if len(data["phone"]) > _PHONE_MAX:
            errors.append(f"Телефон не длиннее {_PHONE_MAX} символов.")

    return data, errors


def create_student(db: Session, tutor_id: str, data: dict) -> Student:
    """Создаёт ученика репетитора со статусом «Новый» и типом «Ребёнок»."""
    student = Student(
        tutor_id=tutor_id,
        first_name=data["first_name"],
        last_name=data["last_name"] or None,
        phone=data["phone"] or None,
        kind="child",
        status="new",
        color=assign_color(db, tutor_id),
    )
    db.add(student)
    db.commit()
    return student
