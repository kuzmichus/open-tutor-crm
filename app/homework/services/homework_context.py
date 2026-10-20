"""Контекст панели ДЗ для шаблона `homework/_panel.html`.

Значения полей берутся из записи ДЗ урока; записи ещё нет (ленивое
создание) — дефолты панели: пустые поля, включённый чекбокс дедлайна,
статус «Не задано». При ошибке валидации присланные значения `data`
перекрывают сохранённые — панель показывает введённое пользователем, а
не старое (паттерн `lesson_form_context`).

Сервис не знает про FastAPI: на вход — сессия и очищенные значения
формы, на выход — контекст шаблона.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.homework.models.homework import (
    HOMEWORK_STATUS_LABELS,
    HOMEWORK_STATUSES,
)
from app.homework.services.homework_writer import get_homework
from app.lesson.models.lesson import Lesson


def _input_datetime(value) -> str:
    """Значение для `input[type=datetime-local]`: «YYYY-MM-DDTHH:MM»."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M")
    return str(value or "")


def panel_values(homework) -> dict:
    """Значения полей панели из записи ДЗ; записи нет — дефолты панели."""
    if homework is None:
        return {
            "assignment": "",
            "due_at_value": "",
            # Чекбокс включён по умолчанию (макет, решение D5).
            "deadline_enabled": True,
            "status": "not_assigned",
            "recording_url": "",
            "teacher_note": "",
            "teacher_comment": "",
        }
    return {
        "assignment": homework.assignment,
        "due_at_value": _input_datetime(homework.due_at),
        "deadline_enabled": homework.deadline_enabled,
        "status": homework.status,
        "recording_url": homework.recording_url or "",
        "teacher_note": homework.teacher_note or "",
        "teacher_comment": homework.teacher_comment or "",
    }


def homework_panel_context(
    db: Session,
    lesson: Lesson,
    *,
    data: dict | None = None,
    errors: list[str] | None = None,
    saved: bool = False,
) -> dict:
    """Контекст панели ДЗ: значения из БД, при ошибке — присланные поля.

    Ключи с префиксом `hw_`: панель вставляется в модалку урока через
    include и не должна подменять контекст полей урока (`form`,
    `statuses` — их же использует вкладка «Урок»). Возвращает только
    данные своей панели: вкладка «Урок» и её несохранённые значения
    остаются в форме урока и сюда не попадают (design D3).

    `saved=True` — ответ на успешное сохранение: панель показывает
    кнопку в состоянии успеха («Успешно сохранено»), которую `lessons.js`
    через пару секунд возвращает в обычный вид (design D8).
    """
    values = panel_values(get_homework(db, lesson.id))
    if data is not None:
        values.update(
            {
                "assignment": data.get("assignment") or "",
                "due_at_value": _input_datetime(data.get("due_at")),
                "deadline_enabled": bool(data.get("deadline_enabled")),
                "status": data.get("status") or "not_assigned",
                "recording_url": data.get("recording_url") or "",
                "teacher_note": data.get("teacher_note") or "",
                "teacher_comment": data.get("teacher_comment") or "",
            }
        )

    return {
        "lesson": lesson,
        "hw_form": values,
        "hw_errors": errors or [],
        "hw_saved": saved,
        "hw_statuses": HOMEWORK_STATUSES,
        "hw_status_labels": HOMEWORK_STATUS_LABELS,
    }
