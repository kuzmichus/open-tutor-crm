"""Модалка «Отчёт» ученика: итоги занятий и расчёт за месяц.

Один маршрут отвечает двумя шаблонами: без `HX-Target` — вся модалка
(открытие по кнопке карточки), с `HX-Target: report-content` — только
содержимое (стрелки месяцев перезапрашивают маршрут, и модалка не должна
вложиться сама в себя; тот же приём определения слоя, что в
`lesson/views/update.py::_modal_target`).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.student.services.access import get_owned_student, require_tutor_id
from app.student.services.report import parse_month, report_context
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

# Цель стрелок месяцев: по этому заголовку htmx отличает перезапрос
# содержимого от открытия окна.
CONTENT_TARGET = "report-content"


@router.get("/tutor/students/{student_id}/report", response_class=HTMLResponse)
def student_report_modal(
    request: Request,
    student_id: str,
    month: str = "",
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Карточки-итоги месяца; мусорный `month` — текущий месяц педагога."""
    student = get_owned_student(db, student_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    month_date = parse_month(month or None, tutor)

    context = {
        **report_context(db, student, tutor, month=month_date),
        "tutor": tutor,
    }
    # Перезапрос стрелками: отдаём содержимое без оболочки окна, иначе ответ
    # вложил бы модалку в её же body (двойной оверлей, сломанный крестик).
    if request.headers.get("HX-Target") == CONTENT_TARGET:
        return templates.TemplateResponse(
            request, "student/_report_content.html", context
        )
    return templates.TemplateResponse(
        request, "student/_report_modal.html", context
    )
