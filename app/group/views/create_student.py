"""Создание ученика из мини-формы группы (решение D9).

Эндпоинт отдельный, а не `POST /tutor/students`: тот возвращает модалку
ученика и целится в `#modal`, здесь же нужен фрагмент состава формы группы.
Ответ несёт строку нового участника и обновлённые опции выбора — Alpine
добавляет ученика в состав формы с датой вступления «сегодня» (D9).
"""

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.group.services.members import addable_students, student_full_name, student_option
from app.group.services.student_mini import create_student, parse_mini_form
from app.templating import templates

router = APIRouter()


def _update_response(
    request: Request,
    *,
    member: dict | None = None,
    options: list[dict] | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """Фрагмент-транспорт для Alpine (см. `_member_update.html`)."""
    return templates.TemplateResponse(
        request,
        "group/_member_update.html",
        {
            "member": member or {},
            "options": options or [],
            "error": error,
        },
    )


@router.post("/tutor/groups/students", response_class=HTMLResponse)
async def create_group_student(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Создаёт ученика и возвращает строку состава для формы группы."""
    form = await request.form()
    data, errors = parse_mini_form(form)

    if errors:
        return _update_response(request, error=errors[0])

    student = create_student(db, tutor_id, data)

    # Созданный ученик уже в составе формы, поэтому в списке выбора его нет.
    options = [
        student_option(item)
        for item in addable_students(db, tutor_id, exclude_ids=[student.id])
    ]
    member = {
        "id": student.id,
        "name": student_full_name(student),
        "grade": student.grade,
        "joined": date.today().isoformat(),
        "price": "",
    }
    return _update_response(request, member=member, options=options)
