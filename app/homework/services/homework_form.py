"""Разбор и валидация формы домашнего задания (спека homework-management).

Сервис не знает про FastAPI: на вход — отображение с полями формы
(`FormData` или обычный dict), на выход — очищенные значения и список
ошибок (паттерн `lesson_form.py` / `student_form.py`).

Правила (спека «Валидация пустого задания», «Статусы ДЗ»):

- пустое или пробельное «Задание» → ошибка «Укажите задание.»;
- статус вне закрытого `HOMEWORK_STATUSES` → ошибка;
- пустой «Срок сдачи» → `None` без ошибки, кривая строка → ошибка.
"""

from datetime import datetime

from app.homework.models.homework import HOMEWORK_STATUSES


def _text(form, name: str) -> str:
    """Значение поля формы как строка (нет значения — пустая строка)."""
    value = form.get(name)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _checked(form, name: str) -> bool:
    """Флаг чекбокса: `on`/`1`/`true` — включён, всё остальное — выключен."""
    value = form.get(name, "")
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"1", "on", "true", "yes"}


def _parse_due_at(raw: str) -> tuple[datetime | None, bool]:
    """`datetime-local` → datetime; пусто — (None, False), кривое — ошибка."""
    if raw == "":
        return None, False
    try:
        return datetime.fromisoformat(raw), False
    except ValueError:
        return None, True


def validate_homework_data(data: dict) -> list[str]:
    """Проверки очищенных значений ДЗ (повторно проверяются и в writer)."""
    errors: list[str] = []

    if not (data.get("assignment") or "").strip():
        errors.append("Укажите задание.")

    # Пустой статус — «не передан»: значение по умолчанию «Не задано».
    status = data.get("status") or "not_assigned"
    if status not in HOMEWORK_STATUSES:
        errors.append("Выберите статус домашнего задания.")

    due_at = data.get("due_at")
    if due_at is not None and not isinstance(due_at, datetime):
        errors.append("Укажите корректный срок сдачи.")

    return errors


def parse_homework_form(form) -> tuple[dict, list[str]]:
    """Данные формы ДЗ и ошибки разбора полей.

    Возвращает `(данные, ошибки)`; данные содержат только очищенные
    значения полей панели ДЗ (урок не затрагивается — спека «Сохранение
    ДЗ отдельно от урока»).
    """
    due_at, due_at_error = _parse_due_at(_text(form, "due_at"))

    data = {
        "assignment": _text(form, "assignment"),
        "due_at": due_at,
        "deadline_enabled": _checked(form, "deadline_enabled"),
        "status": _text(form, "status"),
        "recording_url": _text(form, "recording_url") or None,
        "teacher_note": _text(form, "teacher_note") or None,
        "teacher_comment": _text(form, "teacher_comment") or None,
    }

    errors: list[str] = []
    if due_at_error:
        errors.append("Укажите корректный срок сдачи.")
    errors.extend(validate_homework_data(data))
    return data, errors
