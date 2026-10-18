"""Представление ученика и контактов для шаблонов.

Здесь только чистые функции отображения: подписи статусов, инициалы,
преобразование модели в данные формы. Бизнес-правила живут в других
сервисах модуля.
"""

from app.student.models.contact import Contact
from app.student.models.student import Student
from app.student.models.student_contact import StudentContact

_STATUS_LABELS = {
    "new": "Новый",
    "active": "Активный",
    "archived": "В архиве",
}

_KIND_LABELS = {
    "child": "Ребёнок",
    "adult": "Взрослый",
}


def status_label(status: str | None) -> str:
    """Человекочитаемая подпись статуса (неизвестное значение — как есть)."""
    return _STATUS_LABELS.get(status or "", status or "")


def kind_label(kind: str | None) -> str:
    """Человекочитаемая подпись подтипа ученика."""
    return _KIND_LABELS.get(kind or "", kind or "")


def student_full_name(student: Student) -> str:
    """Имя и фамилия одной строкой."""
    return " ".join(
        part for part in (student.first_name, student.last_name) if part
    )


def student_initials(student: Student) -> str:
    """Инициалы для аватара: первые буквы имени и фамилии."""
    letters = [student.first_name[:1] if student.first_name else ""]
    if student.last_name:
        letters.append(student.last_name[:1])
    return "".join(letters).upper()


def receives_reminders(link: StudentContact) -> bool:
    """True, если привязка включена хотя бы в одну настройку напоминаний."""
    return bool(link.remind_lesson or link.remind_homework or link.remind_cancel)


def contact_row(link: StudentContact, contact: Contact) -> dict:
    """Строка контакта для формы редактирования."""
    return {
        "contact_id": contact.id,
        "full_name": contact.full_name,
        "phone": contact.phone or "",
        "email": contact.email or "",
        "relation": link.relation or "",
        "remind_lesson": bool(link.remind_lesson),
        "remind_homework": bool(link.remind_homework),
        "remind_cancel": bool(link.remind_cancel),
    }


def student_to_form(student: Student) -> dict:
    """Поля карточки ученика в виде значений формы (строки и флаги)."""
    return {
        "first_name": student.first_name,
        "last_name": student.last_name or "",
        "phone": student.phone or "",
        "email": student.email or "",
        "kind": student.kind,
        "status": student.status,
        "grade": "" if student.grade is None else str(student.grade),
        "school": student.school or "",
        "level": student.level or "",
        "notes": student.notes or "",
        "timezone": student.timezone or "",
        "remind_lesson": bool(student.remind_lesson),
        "remind_homework": bool(student.remind_homework),
        "remind_cancel": bool(student.remind_cancel),
        "payer_contact_id": student.payer_contact_id or "",
    }


def form_from_data(data: dict) -> dict:
    """Значения формы из очищенных данных (для повторной отрисовки с ошибкой)."""
    form = {key: data.get(key, "") for key in empty_student_form()}
    form["grade"] = "" if data.get("grade") is None else str(data["grade"])
    for field in ("remind_lesson", "remind_homework", "remind_cancel"):
        form[field] = bool(data.get(field))
    return form


def empty_student_form() -> dict:
    """Пустая форма создания: обязательный подтип по умолчанию — ребёнок."""
    return {
        "first_name": "",
        "last_name": "",
        "phone": "",
        "email": "",
        "kind": "child",
        "status": "new",
        "grade": "",
        "school": "",
        "level": "",
        "notes": "",
        "timezone": "",
        "remind_lesson": False,
        "remind_homework": False,
        "remind_cancel": False,
        "payer_contact_id": "",
    }


def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        status_label=status_label,
        kind_label=kind_label,
        student_full_name=student_full_name,
        student_initials=student_initials,
        receives_reminders=receives_reminders,
    )



