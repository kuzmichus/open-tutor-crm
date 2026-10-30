"""Вкладка ребёнка «Домашние задания» кабинета родителя (design D7).

Только просмотр: роутов записи у кабинета родителя нет. Контекст строит
`cabinet/services/child_homework.py` — тот же состав данных, что виден
ученику (задание, срок, статус, комментарий педагога, запись урока);
заметка педагога в выборку не попадает вовсе.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.cabinet.services.access import require_contact_id
from app.cabinet.services.child_homework import child_homework
from app.cabinet.services.children import children, get_child
from app.database import get_db
from app.student.models.contact import Contact
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/parent/students/{student_id}/homework", response_class=HTMLResponse)
def parent_student_homework(
    request: Request,
    student_id: str,
    db: Session = Depends(get_db),
    contact_id: str = Depends(require_contact_id),
) -> HTMLResponse:
    """Домашние задания ребёнка без возможностей изменить; чужой — 404."""
    contact = db.get(Contact, contact_id)
    child = get_child(db, student_id, contact_id)
    tutor = db.get(Tutor, child.tutor_id)
    return templates.TemplateResponse(
        request,
        "cabinet/parent/homework.html",
        {
            "contact": contact,
            "children": children(db, contact_id),
            "child": child,
            "tutor": tutor,
            "cards": child_homework(db, child.id),
        },
    )
