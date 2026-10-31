"""Чтение и валидация полей формы ученика.

Сервис не знает про FastAPI: на вход приходит отображение с полями формы
(`FormData` или обычный dict), на выход — очищенные данные и список ошибок.
Так правила проверяются модульными тестами без поднятия HTTP-клиента.
"""

import re
from collections.abc import Mapping
from datetime import date

from app.common.services.forms import checked, text_value
from app.student.models.student import (
    MAX_GRADE,
    MIN_GRADE,
    STUDENT_KINDS,
    STUDENT_STATUSES,
)
from app.student.services.phone import format_phone

_FIRST_NAME_MAX = 100
_LAST_NAME_MAX = 100
_PHONE_MAX = 32
_EMAIL_MAX = 255
_SCHOOL_MAX = 255
_LEVEL_MAX = 100
_TIMEZONE_MAX = 64

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Поля ученика, которые форма присылает как простые значения.
_TEXT_FIELDS = (
    "first_name",
    "last_name",
    "phone",
    "email",
    "grade",
    "birth_date",
    "school",
    "level",
    "notes",
    "timezone",
)

_REMIND_FIELDS = ("remind_lesson", "remind_homework", "remind_cancel")


def parse_student_form(form: Mapping) -> tuple[dict, list[str]]:
    """Разбирает и проверяет поля карточки ученика.

    Возвращает `(данные, ошибки)`. Данные содержат только те значения,
    которые разрешено сохранять: для взрослого класс и школа принудительно
    очищаются, даже если пришли в форме.
    """
    data: dict = {field: text_value(form, field) for field in _TEXT_FIELDS}
    data["kind"] = text_value(form, "kind") or "child"
    # Пустой статус означает «не передан»: при создании модель подставит
    # `new`, при редактировании текущий статус сохраняется. Менять статус
    # автоматически нельзя — только по явному выбору репетитора.
    data["status"] = text_value(form, "status")
    for field in _REMIND_FIELDS:
        data[field] = checked(form, field)
    data["payer_contact_id"] = text_value(form, "payer_contact_id")

    errors: list[str] = []

    if not data["first_name"]:
        errors.append("Укажите имя ученика.")
    elif len(data["first_name"]) > _FIRST_NAME_MAX:
        errors.append(f"Имя не длиннее {_FIRST_NAME_MAX} символов.")

    if len(data["last_name"]) > _LAST_NAME_MAX:
        errors.append(f"Фамилия не длиннее {_LAST_NAME_MAX} символов.")

    if data["kind"] not in STUDENT_KINDS:
        errors.append("Выберите, кто ученик: ребёнок или взрослый.")

    if data["status"] and data["status"] not in STUDENT_STATUSES:
        errors.append("Выберите корректный статус ученика.")

    # Телефон сохраняется в едином виде `+7 555 555-55-55`.
    data["phone"] = format_phone(data["phone"])

    if len(data["phone"]) > _PHONE_MAX:
        errors.append(f"Телефон не длиннее {_PHONE_MAX} символов.")

    if data["email"] and (
        len(data["email"]) > _EMAIL_MAX or not _EMAIL_RE.match(data["email"])
    ):
        errors.append("Укажите корректный email.")

    if len(data["school"]) > _SCHOOL_MAX:
        errors.append(f"Школа не длиннее {_SCHOOL_MAX} символов.")

    if len(data["level"]) > _LEVEL_MAX:
        errors.append(f"Уровень не длиннее {_LEVEL_MAX} символов.")

    if len(data["timezone"]) > _TIMEZONE_MAX:
        errors.append(f"Часовой пояс не длиннее {_TIMEZONE_MAX} символов.")

    # Класс: пусто или целое 1–11. Нечисловое значение — тоже ошибка.
    grade_raw = data["grade"]
    if grade_raw:
        if not grade_raw.isdigit():
            errors.append("Класс должен быть числом от 1 до 11.")
            data["grade"] = None
        else:
            grade = int(grade_raw)
            if not MIN_GRADE <= grade <= MAX_GRADE:
                errors.append("Класс должен быть числом от 1 до 11.")
                data["grade"] = None
            else:
                data["grade"] = grade
    else:
        data["grade"] = None

    # Дата рождения: пусто или ISO-строка `YYYY-MM-DD` из `input type="date"`.
    # Часовой пояс к дате не применяется — это календарный день, а не момент
    # времени. Поле доступно и ребёнку, и взрослому.
    birth_date_raw = data["birth_date"]
    if birth_date_raw:
        try:
            data["birth_date"] = date.fromisoformat(birth_date_raw)
        except ValueError:
            errors.append("Дата рождения указана некорректно.")
            data["birth_date"] = None
    else:
        data["birth_date"] = None

    # Для взрослого класс и школа не сохраняются.
    if data["kind"] == "adult":
        data["grade"] = None
        data["school"] = ""

    return data, errors


def parse_contact_rows(form: Mapping) -> list[dict]:
    """Собирает строки контактов из проиндексированных полей формы.

    Поля называются `contact_<поле>_<индекс>`; число строк приходит в
    `contact_rows`. Полностью пустая строка (без ФИО, телефона и email)
    пропускается — так «пустая» строка нового контакта не создаёт запись.
    """
    try:
        rows_count = int(text_value(form, "contact_rows") or "0")
    except ValueError:
        rows_count = 0

    rows: list[dict] = []
    for index in range(max(rows_count, 0)):
        row = {
            "contact_id": text_value(form, f"contact_id_{index}"),
            "full_name": text_value(form, f"contact_full_name_{index}"),
            # Телефон контакта хранится в том же виде, что и телефон ученика.
            "phone": format_phone(text_value(form, f"contact_phone_{index}")),
            "email": text_value(form, f"contact_email_{index}"),
            "relation": text_value(form, f"contact_relation_{index}"),
        }
        for field in _REMIND_FIELDS:
            row[field] = checked(form, f"contact_{field}_{index}")

        if not (row["full_name"] or row["phone"] or row["email"]):
            continue
        rows.append(row)
    return rows


def validate_contacts(rows: list[dict]) -> list[str]:
    """Проверяет строки контактов: ФИО обязательно, email корректен."""
    errors: list[str] = []
    for row in rows:
        if not row["full_name"]:
            errors.append("У каждого контакта укажите ФИО.")
        if row["email"] and not _EMAIL_RE.match(row["email"]):
            errors.append(f"Контакт «{row['full_name']}»: некорректный email.")
    return errors


def validate_payer(payer_contact_id: str, allowed_contact_ids: set[str]) -> list[str]:
    """Плательщик обязан быть одним из контактов, привязанных к ученику.

    Пустое значение допустимо и означает «платит сам ученик».
    """
    if not payer_contact_id:
        return []
    if payer_contact_id not in allowed_contact_ids:
        return ["Плательщиком может быть только контакт, привязанный к ученику."]
    return []
