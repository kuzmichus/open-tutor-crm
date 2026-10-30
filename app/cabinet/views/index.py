"""Кабинет ученика: вкладка «Мои уроки»."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.cabinet.services.access import require_student_id
from app.cabinet.services.lessons import upcoming_lessons
from app.database import get_db
from app.student.models.student import Student
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/student", response_class=HTMLResponse)
def cabinet_index(
    request: Request,
    db: Session = Depends(get_db),
    student_id: str = Depends(require_student_id),
) -> HTMLResponse:
    """«Мои уроки»: ближайшее занятие и список ближайших уроков.

    Без сессии ученика запрос прерван редиректом на `/student/login`
    (зависимость `require_student_id`). Время выводится в зоне репетитора:
    зона самого ученика появится вместе с вкладкой «Профиль».
    """
    student = db.get(Student, student_id)
    tutor = db.get(Tutor, student.tutor_id)
    lessons = upcoming_lessons(db, student_id)
    return templates.TemplateResponse(
        request,
        "cabinet/lessons.html",
        {
            "student": student,
            "tutor": tutor,
            "lessons": lessons,
            # Ближайшее занятие — первый элемент списка (D6).
            "nearest": lessons[0] if lessons else None,
        },
    )
