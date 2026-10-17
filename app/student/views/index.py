"""Список учеников."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.student.models.student import Student

router = APIRouter()


@router.get("/students", response_class=HTMLResponse)
def students_index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Страница со списком учеников."""
    students = db.scalars(select(Student)).all()
    return templates.TemplateResponse(request, "student/index.html", {"students": students})
