"""Блок «Личный кабинет»: создание/перевыпуск приглашения.

Блок — HTMX-фрагмент (`#student-cabinet`): действие возвращает обновлённый
фрагмент целиком, без JS работает 303-редиректом на страницу ученика
(паттерн блока приглашений в мессенджеры). Перевыпуск гасит прежнюю
ссылку сам (D2 change'а student-cabinet-access), отдельных действий
«погасить» не нужно.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.cabinet.services.invites import create_invite, invite_context
from app.common.responses import is_htmx
from app.database import get_db
from app.student.services.access import get_owned_student, require_tutor_id
from app.templating import templates

router = APIRouter()


@router.post(
    "/tutor/students/{student_id}/cabinet/invite", response_class=HTMLResponse
)
def cabinet_invite(
    request: Request,
    student_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Создаёт или перевыпускает приглашение в кабинет; чужой ученик — 404.

    Без htmx возвращается 303-редирект (форма работает и без JS) —
    аннотация `HTMLResponse` нужна FastAPI для схемы ответа, фактический
    ответ выбирает сама вьюха.
    """
    student = get_owned_student(db, student_id, tutor_id)
    create_invite(db, tutor_id, student.id)
    if not is_htmx(request):
        return RedirectResponse(f"/tutor/students/{student.id}", status_code=303)
    return templates.TemplateResponse(
        request,
        "student/_cabinet_block.html",
        {"student": student, "cabinet": invite_context(db, tutor_id, student.id)},
    )
