"""Отправка рассылки (POST `/tutor/mailings/send`).

Успех (хоть одна доставка и/или нет ошибок) — партиал композера с пустым
текстом, сводкой и событием `mailing-sent`: контейнер списка перечитывается
(сброс чекбоксов), Alpine-состояние чистит слушатель. Пустой текст или
пустой выбор — партиал с ошибками и сохранённым текстом, без события.
Без `HX-Request` — 303 на страницу: форма работает и без JS.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import is_htmx
from app.database import get_db
from app.mailing.services.access import require_tutor_id
from app.mailing.services.compose import compose_context
from app.mailing.services.sender import DELIVERED, ERRORS, send_mailing
from app.templating import templates

router = APIRouter()

MAILINGS_URL = "/tutor/mailings"


@router.post("/tutor/mailings/send", response_class=HTMLResponse)
async def send_mailings_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Отправляет рассылку; `tutor_id` — только из сессии."""
    form = await request.form()
    # getlist, а не значение: чекбоксы приходят повторяющимся полем.
    student_ids = form.getlist("student_ids")
    text = form.get("text", "")

    summary = send_mailing(db, tutor_id, student_ids, text)
    delivered = summary[DELIVERED]

    if not is_htmx(request):
        return RedirectResponse(url=MAILINGS_URL, status_code=303)

    context = {
        **compose_context(db, tutor_id, q="", segment=""),
        # Текст показываем пустым только когда хоть что-то ушло: при ошибке
        # формы текст остаётся, чтобы его поправить, а не набрать заново.
        "form_text": "" if delivered > 0 else text,
        "send_summary": summary if delivered > 0 or not summary[ERRORS] else None,
        "send_errors": summary[ERRORS],
    }
    response = templates.TemplateResponse(
        request, "mailing/_composer.html", context
    )
    if delivered > 0:
        response.headers["HX-Trigger"] = "mailing-sent"
    return response
