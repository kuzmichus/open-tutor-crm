"""Модалка «Уроки» ученика: список занятий с фильтром-чипами.

Фрагмент по образцу вкладки «Занятия» группы (`lesson/views/group_lessons.py`):
контейнер страницы вставляет ответ в `#modal`, строки открывают модалку урока
во втором слое `#modal-lesson` — он объявлен на странице списка учеников.
Чужой ученик и несуществующий неразличимы — 404.

Один маршрут отвечает двумя шаблонами: без `HX-Target` — вся модалка
(открытие по кнопке карточки), с `HX-Target: student-lessons-content` —
только содержимое (чипы фильтра перезапрашивают маршрут, и модалка не
должна вложиться сама в себя; тот же приём определения слоя, что в
`lesson/views/update.py::_modal_target`).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import get_owned_student, require_tutor_id
from app.student.services.student_lessons import (
    group_names,
    lesson_subject,
    list_student_lessons,
    normalize_status,
)
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

# Цель чипов фильтра: по этому заголовку htmx отличает перезапрос
# содержимого от открытия окна.
CONTENT_TARGET = "student-lessons-content"


@router.get("/tutor/students/{student_id}/lessons", response_class=HTMLResponse)
def student_lessons_modal(
    request: Request,
    student_id: str,
    status: str = "",
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Список уроков ученика; неизвестный статус чипа — «Все»."""
    student = get_owned_student(db, student_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    status = normalize_status(status)
    lessons = list_student_lessons(db, student.id, status=status)
    names = group_names(db, lessons)

    context = {
        "student": student,
        "tutor": tutor,
        "status": status,
        "rows": [
            {
                "lesson": lesson,
                "subject": lesson_subject(lesson, names.get(lesson.group_id), tutor.subject or ""),
            }
            for lesson in lessons
        ],
    }
    # Перезапрос чипами: отдаём содержимое без оболочки окна, иначе ответ
    # вложил бы модалку в её же body (двойной оверлей, сломанный крестик).
    if request.headers.get("HX-Target") == CONTENT_TARGET:
        return templates.TemplateResponse(
            request, "student/_lessons_content.html", context
        )
    return templates.TemplateResponse(
        request, "student/_lessons_modal.html", context
    )
