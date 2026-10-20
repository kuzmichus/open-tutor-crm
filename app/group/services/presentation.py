"""Отображение группы: цена, счётчик участников, подпись даты вступления.

Чистые функции без БД и HTTP (как `app/student/services/presentation.py`):
принимают значения модели, возвращают строки для шаблона. Бизнес-правила
живут в других сервисах модуля.

Пустая цена (`None`) — это «цена не задана»: возвращается пустая строка,
и шаблон не рисует блок цены вовсе (спека group-management).
"""

from datetime import date, datetime

from app.group.services.members import MAX_MEMBERS


def format_price(price: int | None) -> str:
    """«1 200 ₽»; пустая цена — пустая строка (блока цены нет).

    Разделитель разрядов — неразрывный пробел, как в календаре: число
    не переносится отдельно от знака рубля.
    """
    if price is None:
        return ""
    return f"{price:,}".replace(",", "\u00a0") + "\u00a0₽"


def members_label(count: int) -> str:
    """Счётчик участников карточки: «2 / 10 учеников»."""
    return f"{count} / {MAX_MEMBERS} учеников"


def format_joined_at(value: datetime | date | str | None) -> str:
    """Подпись даты вступления: «в группе с 19.10.2026».

    Принимает и модель (`datetime`/`date`), и строку ISO `YYYY-MM-DD`
    (строки состава формы несут дату именно в этом виде).
    """
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return ""
    return f"в группе с {value.strftime('%d.%m.%Y')}"


def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        group_price=format_price,
        group_members_label=members_label,
        group_joined_label=format_joined_at,
    )
