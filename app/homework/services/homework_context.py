"""Контекст панели ДЗ для шаблона `homework/_panel.html`.

Значения полей берутся из записи ДЗ урока; записи ещё нет (ленивое
создание) — дефолты панели: пустые поля, включённый чекбокс дедлайна,
статус «Не задано». При ошибке валидации присланные значения `data`
перекрывают сохранённые — панель показывает введённое пользователем, а
не старое (паттерн `lesson_form_context`).

Сервис не знает про FastAPI: на вход — сессия и очищенные значения
формы, на выход — контекст шаблона.

Список файлов (`hw_files`) читается одним SELECT по ДЗ (без N+1) и
передаётся готовыми строками: шаблон не должен ходить в БД и не должен
считать размеры сам.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.common.services.tutor_time import to_local
from app.config import settings
from app.files.services.presentation import file_size_label
from app.files.services.removal import files_of_homework
from app.homework.models.homework import (
    HOMEWORK_STATUS_LABELS,
    HOMEWORK_STATUSES,
)
from app.homework.services.homework_writer import get_homework
from app.lesson.models.lesson import Lesson


def _input_datetime(value, tutor) -> str:
    """Значение для `input[type=datetime-local]`: «YYYY-MM-DDTHH:MM».

    `due_at` хранится в UTC, значение поля — в зоне педагога (спека
    tutor-timezone, «Показ срока сдачи»).
    """
    if isinstance(value, datetime):
        return to_local(value, tutor).strftime("%Y-%m-%dT%H:%M")
    return str(value or "")


def panel_values(homework, tutor) -> dict:
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
        "due_at_value": _input_datetime(homework.due_at, tutor),
        "deadline_enabled": homework.deadline_enabled,
        "status": homework.status,
        "recording_url": homework.recording_url or "",
        "teacher_note": homework.teacher_note or "",
        "teacher_comment": homework.teacher_comment or "",
    }


def _file_rows(db: Session, homework) -> list[dict]:
    """Строки списка файлов ДЗ: id, имя, размер, ссылка на скачивание.

    Размер форматируется здесь, а не в шаблоне: подпись «12,4 КБ» —
    правило отображения (`file_size_label`), и Jinja-фильтр не должен
    дублировать форматирование по месту.
    """
    if homework is None:
        return []
    return [
        {
            "id": file.id,
            "name": file.original_name,
            "size_label": file_size_label(file.size),
            "url": f"/files/{file.id}",
        }
        for file in files_of_homework(db, homework.id)
    ]

def homework_panel_context(
    db: Session,
    lesson: Lesson,
    *,
    tutor,
    data: dict | None = None,
    errors: list[str] | None = None,
    saved: bool = False,
) -> dict:
    """Контекст панели ДЗ: значения из БД, при ошибке — присланные поля.

    `tutor` — карточка репетитора: её зона задаёт значение поля «Срок
    сдачи» — хранится срок в UTC, а поле показывает настенное время
    (спека tutor-timezone).

    Ключи с префиксом `hw_`: панель вставляется в модалку урока через
    include и не должна подменять контекст полей урока (`form`,
    `statuses` — их же использует вкладка «Урок»). Возвращает только
    данные своей панели: вкладка «Урок» и её несохранённые значения
    остаются в форме урока и сюда не попадают (design D3).

    `saved=True` — ответ на успешное сохранение: панель показывает
    кнопку в состоянии успеха («Успешно сохранено»), которую `lessons.js`
    через пару секунд возвращает в обычный вид (design D8).
    """
    homework = get_homework(db, lesson.id)
    values = panel_values(homework, tutor)
    if data is not None:
        values.update(
            {
                "assignment": data.get("assignment") or "",
                "due_at_value": _input_datetime(data.get("due_at"), tutor),
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
        "hw_files": _file_rows(db, homework),
        "hw_errors": errors or [],
        "hw_saved": saved,
        "hw_statuses": HOMEWORK_STATUSES,
        "hw_status_labels": HOMEWORK_STATUS_LABELS,
        "files_max_size_mb": settings.files_max_size_mb,
        "files_allowed_extensions": ", ".join(settings.allowed_extensions),
    }
