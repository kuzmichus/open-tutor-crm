"""Контекст формы группы: создание (модалка) и вкладка «Настройки».

Общий для `_new_group.html` и `_manage.html`: шаблон получает значения полей,
строки состава, список добавляемых учеников и адрес сохранения. Так форма
не знает, создают группу или меняют, и не дублирует разметку.
"""

from sqlalchemy.orm import Session

from app.group.models.group import Group
from app.group.services.members import (
    MAX_MEMBERS,
    addable_options_json,
    form_member_rows,
    list_members,
    student_full_name,
)

# Заголовок и подзаголовок модалки создания группы (спека group-management).
NEW_GROUP_TITLE = "Новая группа"
NEW_GROUP_SUBTITLE = (
    "Создайте группу для нескольких учеников. "
    "Вы сможете назначать уроки сразу всей группе."
)


def empty_group_form() -> dict:
    """Пустая форма создания группы."""
    return {"name": "", "price": "", "description": ""}


def group_to_form(group: Group) -> dict:
    """Поля группы в виде значений формы (числа — строками)."""
    return {
        "name": group.name,
        "price": "" if group.price_per_lesson is None else str(group.price_per_lesson),
        "description": group.description or "",
        "meeting_url": group.meeting_url or "",
        "notes": group.notes or "",
    }


def form_from_data(data: dict) -> dict:
    """Значения формы из очищенных данных (повторная отрисовка с ошибкой)."""
    return {
        "name": data.get("name", ""),
        "price": "" if data.get("price") is None else str(data["price"]),
        "description": data.get("description") or "",
        "meeting_url": data.get("meeting_url") or "",
        "notes": data.get("notes") or "",
    }


def existing_member_rows(db: Session, group: Group) -> list[dict]:
    """Строки состава группы для вкладки «Настройки» (с датой и ценой)."""
    return [
        {
            "id": row["student"].id,
            "name": student_full_name(row["student"]),
            "grade": row["student"].grade,
            "joined": row["member"].joined_at.strftime("%Y-%m-%d"),
            "price": ""
            if row["member"].price_override is None
            else str(row["member"].price_override),
        }
        for row in list_members(db, group.id)
    ]


def group_form_context(
    db: Session,
    tutor_id: str,
    *,
    form: dict,
    member_rows: list[dict],
    action: str,
    title: str,
    subtitle: str,
    errors: list[str] | None = None,
    group: Group | None = None,
    exclude_ids: list[str] | None = None,
    active_tab: str = "general",
) -> dict:
    """Готовит контекст формы группы.

    `member_rows` — состав, который видит пользователь: при ошибке валидации
    это отправленные строки, при редактировании — текущий состав группы.
    Уже состоящие ученики не предлагаются в списке выбора (`exclude_ids`).
    `active_tab` — вкладка, открытая при отрисовке модалки управления.
    """
    return {
        "form": form,
        "member_rows": member_rows,
        "errors": errors or [],
        "group": group,
        "action": action,
        "title": title,
        "subtitle": subtitle,
        "active_tab": active_tab,
        "max_members": MAX_MEMBERS,
        "options_json": addable_options_json(
            db, tutor_id, exclude_ids=exclude_ids or []
        ),
    }


def submitted_member_rows(db: Session, tutor_id: str, data: dict) -> list[dict]:
    """Состав из отправленной формы — для повторной отрисовки с ошибкой."""
    return form_member_rows(
        db,
        tutor_id,
        data.get("member_ids", []),
        data.get("joined"),
        data.get("prices"),
    )


def manage_context(
    db: Session,
    tutor_id: str,
    group: Group,
    *,
    form: dict | None = None,
    member_rows: list[dict] | None = None,
    errors: list[str] | None = None,
    tab: str = "general",
) -> dict:
    """Контекст модалки управления группой (вкладки «Общее» и «Настройки»).

    Состав по умолчанию — текущий состав группы; при ошибке валидации
    передаются отправленные строки, чтобы введённые даты и цены не терялись.
    Список выбора не содержит уже состоящих участников (спека
    group-membership).
    """
    rows = member_rows if member_rows is not None else existing_member_rows(db, group)
    return group_form_context(
        db,
        tutor_id,
        form=form if form is not None else group_to_form(group),
        member_rows=rows,
        action=f"/tutor/groups/{group.id}",
        title=f"Группа {group.name}",
        subtitle=f"Группа · участников: {len(rows)}",
        errors=errors,
        group=group,
        exclude_ids=[row["id"] for row in rows],
        active_tab=tab,
    )
