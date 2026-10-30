"""Вкладка ребёнка «Мои уроки» кабинета родителя (design D5, D6).

Доступ — привязка «контакт из сессии ↔ ученик» (`get_child`, один SELECT):
чужой ученик и несуществующий неразличимы — 404. Список уроков строит
общий сервис кабинета `cabinet/services/lessons.py`: родителю нужны те же
ближайшие запланированные занятия, что и ученику, сервиса-двойника нет.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.cabinet.services.access import require_contact_id
from app.cabinet.services.children import children, get_child
from app.cabinet.services.lessons import upcoming_lessons
from app.database import get_db
from app.student.models.contact import Contact
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/parent/students/{student_id}", response_class=HTMLResponse)
def parent_student_lessons(
    request: Request,
    student_id: str,
    db: Session = Depends(get_db),
    contact_id: str = Depends(require_contact_id),
) -> HTMLResponse:
    """Ближайшие запланированные уроки ребёнка; чужой ученик — 404."""
    contact = db.get(Contact, contact_id)
    child = get_child(db, student_id, contact_id)
    tutor = db.get(Tutor, child.tutor_id)
    lessons = upcoming_lessons(db, child.id)
    return templates.TemplateResponse(
        request,
        "cabinet/parent/lessons.html",
        {
            "contact": contact,
            "children": children(db, contact_id),
            "child": child,
            "tutor": tutor,
            "lessons": lessons,
            # Ближайшее занятие — первый элемент списка (D6).
            "nearest": lessons[0] if lessons else None,
        },
    )
