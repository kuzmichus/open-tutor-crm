"""Личный кабинет репетитора: карточка вошедшего."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.sessions import COOKIE_NAME, SessionService

router = APIRouter()

_sessions = SessionService()


@router.get("/tutor/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    """Карточка вошедшего репетитора; без сессии — редирект на вход."""
    tutor_id = _sessions.get_tutor_id_from_request(db, request)
    if tutor_id is None:
        return RedirectResponse(url="/tutor/login", status_code=303)

    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        # Сессия указывает на удалённого репетитора — считаем входа нет.
        _sessions.delete(db, request.cookies.get(COOKIE_NAME))
        return RedirectResponse(url="/tutor/login", status_code=303)

    return templates.TemplateResponse(
        request, "tutor/home.html", {"tutor": tutor}
    )
