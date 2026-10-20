"""Разбор и валидация формы группы: создание и вкладка «Настройки».

Сервис не знает про FastAPI: на вход приходит отображение с полями формы
(`FormData` или обычный dict), на выход — очищенные данные и список ошибок.
Так правила проверяются модульными тестами без поднятия HTTP-клиента.

Именованные поля состава (решение D4): у каждой строки участника —
скрытое `members` со значением id, поле даты `member_joined_<id>` и поле
цены `member_price_<id>`; исключения приходят отдельным полем
`removed_members` (id через запятую), которое заполняет Alpine-состояние
`removed` по кнопке «Убрать».
"""

from collections.abc import Mapping
from datetime import date

from app.group.services.members import MAX_MEMBERS

_NAME_MAX = 100
# Длина постоянной ссылки на встречу (модель: String(500)).
_MEETING_URL_MAX = 500


def _get(form: Mapping, key: str) -> str:
    """Строковое значение поля формы (отсутствие = пустая строка)."""
    value = form.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _getlist(form: Mapping, key: str) -> list[str]:
    """Все значения повторяющегося поля (`FormData.getlist` или список)."""
    if hasattr(form, "getlist"):
        values = form.getlist(key)
    else:
        value = form.get(key, "")
        values = value if isinstance(value, list) else [value]
    return [
        value for value in values if isinstance(value, str) and value.strip()
    ]


def _parse_int(raw: str, *, field: str, errors: list[str]) -> int | None:
    """Целое число из строки поля: пусто → None, мусор → ошибка."""
    if not raw:
        return None
    cleaned = "".join(raw.split())  # «1 200» и «1&nbsp;200» тоже числа
    try:
        value = int(cleaned)
    except ValueError:
        errors.append(f"{field} должна быть целым числом.")
        return None
    if value < 0:
        errors.append(f"{field} не может быть отрицательной.")
        return None
    return value


def _parse_date(raw: str, errors: list[str]) -> date | None:
    """Дата поля `type="date"` (YYYY-MM-DD); пусто → None, мусор → ошибка."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors.append("Дата вступления указана некорректно.")
        return None


def is_membership_submitted(form: Mapping) -> bool:
    """Отправлялся ли блок состава.

    Настоящая форма несёт маркер `members_form=1` (и так же честно
    несёт пустой список, когда состав вычищен). Без маркера и без полей
    состава состав не трогается — например, при упрощённом POST только
    с названием.
    """
    return (
        _get(form, "members_form") == "1"
        or bool(_getlist(form, "members"))
        or bool(_get(form, "removed_members"))
    )


def effective_member_ids(data: dict) -> list[str]:
    """Итоговый состав формы: `members` минус `removed_members`.

    Каждый id встречается один раз: повторные вхождения — ошибка
    валидации (`validate_member_pool`), а не тихое схлопывание здесь.
    """
    removed = set(data.get("removed_ids", ()))
    seen: set[str] = set()
    result: list[str] = []
    for member_id in data.get("member_ids", ()):
        if member_id in removed or member_id in seen:
            continue
        seen.add(member_id)
        result.append(member_id)
    return result


def validate_group_data(data: dict) -> list[str]:
    """Проверки, которым можно доверять без формы: название и состав.

    Дублируется в writer'е (решение D6): форма могла быть отправлена
    криво или устаревшими данными.
    """
    errors: list[str] = []
    if not data["name"]:
        errors.append("Укажите название группы.")
    elif len(data["name"]) > _NAME_MAX:
        errors.append(f"Название группы не длиннее {_NAME_MAX} символов.")
    if data.get("meeting_url") and len(data["meeting_url"]) > _MEETING_URL_MAX:
        errors.append(f"Ссылка на встречу не длиннее {_MEETING_URL_MAX} символов.")
    return errors


def validate_member_pool(data: dict) -> list[str]:
    """Лимит и запрет дублей для итогового состава (D6, повтор в writer'е)."""
    errors: list[str] = []
    if not data.get("membership_submitted"):
        return errors

    member_ids = data["member_ids"]
    if len(set(member_ids)) != len(member_ids):
        errors.append("Один и тот же ученик не может состоять в группе дважды.")

    count = len(effective_member_ids(data))
    if count > MAX_MEMBERS:
        errors.append(f"В группе может быть не более {MAX_MEMBERS} участников.")
    return errors


def parse_group_form(form: Mapping) -> tuple[dict, list[str]]:
    """Разбирает и проверяет форму создания/настроек группы.

    Возвращает `(данные, ошибки)`. Данные содержат только значения,
    которые разрешено сохранять: пустая цена и пустая индивидуальная
    цена — это `None` («по общей цене группы» / «цена не задана»).
    """
    errors: list[str] = []

    data: dict = {
        "name": _get(form, "name"),
        "description": _get(form, "description") or None,
        "price": _parse_int(_get(form, "price"), field="Цена за урок", errors=errors),
        # Поля вкладки «Общее»: постоянная ссылка на встречу и заметки.
        # Заметки видят только репетиторы, ученикам они не показываются.
        # Флаг «поле пришло» отделяет «очистить» от «этот POST его не трогает»:
        # сохранение только настроек не должно стирать заметки.
        "meeting_url": _get(form, "meeting_url") or None,
        "meeting_url_submitted": "meeting_url" in form,
        "notes": _get(form, "notes") or None,
        "notes_submitted": "notes" in form,
        "membership_submitted": is_membership_submitted(form),
        "member_ids": [value.strip() for value in _getlist(form, "members") if value.strip()],
        "removed_ids": [
            value.strip() for value in _get(form, "removed_members").split(",") if value.strip()
        ],
        "joined": {},
        "prices": {},
    }

    errors += validate_group_data(data)
    errors += validate_member_pool(data)

    for member_id in data["member_ids"]:
        joined = _parse_date(_get(form, f"member_joined_{member_id}"), errors)
        if joined is not None:
            data["joined"][member_id] = joined
        price = _parse_int(
            _get(form, f"member_price_{member_id}"),
            field="Индивидуальная цена",
            errors=errors,
        )
        data["prices"][member_id] = price

    # Ошибки могли накопиться до разбора полей состава — не дублируем.
    return data, errors
