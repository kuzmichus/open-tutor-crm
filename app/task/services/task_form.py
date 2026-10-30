"""Разбор и валидация формы задачи: создание и правка.

Сервис не знает про FastAPI: на вход — отображение с полями формы
(`FormData` или обычный `dict`), на выход — очищенные данные и список
ошибок. Так правила проверяются модульными тестами без HTTP-клиента.

Проверка принадлежности учеников репетитору требует БД и живёт в
`task_writer` — здесь только форма: обязательность названия, значения из
закрытых списков, корректность даты срока и отсутствие повторов в списке
учеников.

Ответственного поля в форме нет осознанно: задачи ставит себе сам
педагог, отдельного исполнителя в модели не существует.
"""

from collections.abc import Mapping
from datetime import date

from app.common.services.forms import text_value
from app.task.models.task import TASK_PRIORITIES, TASK_STAGES

# Длина названия — как у колонки модели (`String(200)`).
_TITLE_MAX = 200


def _getlist(form: Mapping, key: str) -> list[str]:
    """Все значения повторяющегося поля (`FormData.getlist` или список)."""
    if hasattr(form, "getlist"):
        values = form.getlist(key)
    else:
        value = form.get(key, "")
        values = value if isinstance(value, list) else [value]
    return [
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    ]


def _parse_due(raw: str, errors: list[str]) -> date | None:
    """Дата поля `type="date"` (YYYY-MM-DD); пусто → None, мусор → ошибка."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors.append("Срок указан некорректно.")
        return None


def parse_task_form(form: Mapping) -> tuple[dict, list[str]]:
    """Поля задачи → очищенные данные и список ошибок.

    Этап и приоритет приходят из селектов; неизвестное значение —
    ошибка, а не тихая замена умолчанием: форма, отправленная криво,
    не должна менять задачу незаметно для пользователя.
    """
    errors: list[str] = []

    title = text_value(form, "title")
    if not title:
        errors.append("Укажите название задачи.")
    elif len(title) > _TITLE_MAX:
        errors.append(f"Название задачи — не длиннее {_TITLE_MAX} символов.")

    priority = text_value(form, "priority") or "medium"
    if priority not in TASK_PRIORITIES:
        errors.append("Неизвестный приоритет задачи.")
        priority = "medium"

    stage = text_value(form, "stage") or "new"
    if stage not in TASK_STAGES:
        errors.append("Неизвестный этап задачи.")
        stage = "new"

    due_date = _parse_due(text_value(form, "due_date"), errors)

    description = text_value(form, "description") or None

    student_ids = _getlist(form, "students")
    # Повтор id в форме — ошибка данных, а не повод молча схлопнуть список:
    # это значит, что разметка формы собрана неверно.
    if len(student_ids) != len(set(student_ids)):
        errors.append("Ученик выбран дважды.")

    data = {
        "title": title,
        "priority": priority,
        "stage": stage,
        "due_date": due_date,
        "description": description,
        "student_ids": list(dict.fromkeys(student_ids)),
    }
    return data, errors
