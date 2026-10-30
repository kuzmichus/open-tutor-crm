"""Шаблоны сообщений репетитора: список, создание, правка, удаление.

Шаблон — пара «название ≤ 200, текст». Валидация повторяет соглашение
сервисов проекта: на вход очищенные значения формы, на выход список
ошибок (пустой — запись сохранена и закоммичена).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mailing.models.message_template import TITLE_LENGTH, MessageTemplate


def list_templates(db: Session, tutor_id: str) -> list[MessageTemplate]:
    """Шаблоны репетитора в порядке создания."""
    return list(
        db.scalars(
            select(MessageTemplate)
            .where(MessageTemplate.tutor_id == tutor_id)
            .order_by(MessageTemplate.created_at, MessageTemplate.id)
        ).all()
    )


def template_from_form(form: dict) -> dict:
    """Очищенные значения формы (строки) из сырых данных POST."""
    return {
        "title": (form.get("title") or "").strip(),
        "text": (form.get("text") or "").strip(),
    }


def _validate(data: dict) -> list[str]:
    """Ошибки формы шаблона; длина названия ограничена колонкой БД."""
    errors: list[str] = []
    if not data["title"]:
        errors.append("Укажите название шаблона.")
    elif len(data["title"]) > TITLE_LENGTH:
        errors.append(f"Название шаблона — не длиннее {TITLE_LENGTH} символов.")
    if not data["text"]:
        errors.append("Введите текст шаблона.")
    return errors


def create_template(db: Session, tutor_id: str, form: dict) -> list[str]:
    """Создаёт шаблон репетитора; пустой список — создан."""
    data = template_from_form(form)
    errors = _validate(data)
    if errors:
        return errors
    db.add(MessageTemplate(tutor_id=tutor_id, **data))
    db.commit()
    return []


def update_template(
    db: Session, template: MessageTemplate, form: dict
) -> list[str]:
    """Обновляет шаблон; пустой список — обновлён."""
    data = template_from_form(form)
    errors = _validate(data)
    if errors:
        return errors
    template.title = data["title"]
    template.text = data["text"]
    db.commit()
    return []


def delete_template(db: Session, template: MessageTemplate) -> None:
    """Удаляет шаблон."""
    db.delete(template)
    db.commit()
