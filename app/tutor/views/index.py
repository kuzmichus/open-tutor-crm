"""Список репетиторов."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutors", response_class=HTMLResponse)
def tutors_index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Страница со списком репетиторов."""
    tutors = db.scalars(select(Tutor)).all()
    return templates.TemplateResponse(request, "tutor/index.html", {"tutors": tutors})
