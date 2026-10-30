"""Модалка «Доступ ученика»: форма логина и пароля (GET)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import get_owned_student, require_tutor_id
from app.student.services.credentials import get_access, suggest_login
from app.templating import templates

router = APIRouter()


@router.get("/tutor/students/{student_id}/access", response_class=HTMLResponse)
def student_access_form(
    request: Request,
    student_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Форма входа ученика; чужой ученик — 404.

    Существующий вход показывается только логином: пароль хранится хешем и
    показан быть не может — правило «данные показываются один раз» держится
    устройством хранения, а не дисциплиной шаблона. У ученика без входа
    логин предзаполняется подсказкой из имени (D7 change'а
    student-cabinet-access): уникальность знает только сервер, поэтому
    подсказка считается здесь, а не в JS.
    """
    student = get_owned_student(db, student_id, tutor_id)
    access = get_access(db, student.id)
    return templates.TemplateResponse(
        request,
        "student/_access_modal.html",
        {
            "student": student,
            "access": access,
            "errors": [],
            "login_value": "" if access else suggest_login(db, student),
        },
    )
