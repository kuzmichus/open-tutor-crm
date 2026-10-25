"""Сохранение доступа ученика: создание входа или смена пароля (POST).

Успех отдаёт `_access_saved.html` — логин и пароль открытым текстом один
раз, для передачи ученику (по референсу «данные показаны один раз»).
Пароль приходит в ответ ровно из формы: нигде не сохраняется открытым
текстом и не попадает в другие ответы, поэтому повторное открытие
модалки показывает только логин.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import get_owned_student, require_tutor_id
from app.student.services.credentials import get_access, save_access
from app.templating import templates

router = APIRouter()


@router.post("/tutor/students/{student_id}/access", response_class=HTMLResponse)
async def student_access_save(
    request: Request,
    student_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт/обновляет вход; ошибки возвращают форму с сообщениями."""
    student = get_owned_student(db, student_id, tutor_id)
    form = await request.form()
    login = str(form.get("login", ""))
    password = str(form.get("password", ""))

    errors = save_access(db, student.id, login, password)
    if errors:
        if request.headers.get("HX-Request") != "true":
            return RedirectResponse(
                url=f"/tutor/students/{student_id}", status_code=303
            )
        return templates.TemplateResponse(
            request,
            "student/_access_modal.html",
            {
                "student": student,
                "access": get_access(db, student.id),
                "errors": errors,
                "login_value": login.strip(),
            },
            status_code=200,
        )

    db.commit()

    if request.headers.get("HX-Request") != "true":
        # Без JS — на страницу списка: показать пароль один раз там нечем.
        return RedirectResponse(url="/tutor/students", status_code=303)

    return templates.TemplateResponse(
        request,
        "student/_access_saved.html",
        {
            "student": student,
            "login_value": login.strip(),
            # Ровно один показ: дальше пароль существует только хешем.
            "password_once": password,
        },
    )
