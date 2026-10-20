"""Создание ученика из мини-формы селекта урока (решение D7).

Мини-форма — те же три поля (Имя*, Фамилия, Телефон) и та же валидация,
что в мини-форме группы (`app/group/services/student_mini.py`): статус
нового ученика — «Новый», полное редактирование — на странице учеников.

Ответ — транспортный фрагмент `lesson/_target_update.html` с выбранной
записью (`data-selected`): Alpine закрывает мини-форму и вписывает
ученика в поле селекта. Ошибка валидации возвращается тем же фрагментом
с `data-error` — мини-форма остаётся открытой с сообщением.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.group.services.student_mini import create_student, parse_mini_form
from app.student.services.presentation import student_full_name
from app.templating import templates

router = APIRouter()


def _update_response(
    request: Request,
    *,
    selected: dict | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """Транспортный фрагмент ответа мини-формы (как `_member_update.html`)."""
    return templates.TemplateResponse(
        request,
        "lesson/_target_update.html",
        {
            "kind": "student",
            "selected": selected,
            "error": error,
        },
    )


@router.post("/tutor/lessons/students", response_class=HTMLResponse)
async def create_lesson_student(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Создаёт ученика и возвращает его как выбранную цель урока."""
    form = await request.form()
    data, errors = parse_mini_form(form)

    if errors:
        return _update_response(request, error=errors[0])

    student = create_student(db, tutor_id, data)
    return _update_response(
        request,
        selected={"id": student.id, "name": student_full_name(student)},
    )
