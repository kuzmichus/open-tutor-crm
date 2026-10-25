"""Разбор и валидация формы домашнего задания (спека homework-management).

Сервис не знает про FastAPI: на вход — отображение с полями формы
(`FormData` или обычный dict), на выход — очищенные значения и список
ошибок (паттерн `lesson_form.py` / `student_form.py`).

Правила (спека «Валидация пустого задания», «Статусы ДЗ»):

- пустое или пробельное «Задание» → ошибка «Укажите задание.»;
- статус вне закрытого `HOMEWORK_STATUSES` → ошибка;
- пустой «Срок сдачи» → `None` без ошибки, кривая строка → ошибка.

Настенное время «Срока сдачи» трактуется как время в зоне педагога и
переводится в UTC (спека tutor-timezone).
"""

from datetime import datetime

from app.common.services.forms import checked, text_value
from app.common.services.tutor_time import to_utc
from app.homework.models.homework import HOMEWORK_STATUSES


def _parse_due_at(raw: str, tutor) -> tuple[datetime | None, bool]:
    """`datetime-local` → aware UTC; пусто — (None, False), кривое — ошибка.

    Настенное время из формы трактуется как время в зоне педагога и сразу
    переводится в UTC (спека tutor-timezone, «Ввод срока сдачи»).
    """
    if raw == "":
        return None, False
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None, True
    return to_utc(parsed, tutor), False


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


def parse_homework_form(form, tutor) -> tuple[dict, list[str]]:
    """Данные формы ДЗ и ошибки разбора полей.

    Возвращает `(данные, ошибки)`; данные содержат только очищенные
    значения полей панели ДЗ (урок не затрагивается — спека «Сохранение
    ДЗ отдельно от урока»). `due_at` переводится из зоны педагога в UTC
    (спека tutor-timezone).
    """
    due_at, due_at_error = _parse_due_at(text_value(form, "due_at"), tutor)

    data = {
        "assignment": text_value(form, "assignment"),
        "due_at": due_at,
        "deadline_enabled": checked(form, "deadline_enabled"),
        "status": text_value(form, "status"),
        "recording_url": text_value(form, "recording_url") or None,
        "teacher_note": text_value(form, "teacher_note") or None,
        "teacher_comment": text_value(form, "teacher_comment") or None,
    }

    errors: list[str] = []
    if due_at_error:
        errors.append("Укажите корректный срок сдачи.")
    errors.extend(validate_homework_data(data))
    return data, errors
