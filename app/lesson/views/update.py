"""Редактирование урока: модальная форма (GET) и сохранение (POST).

Заголовок модалки — «Цель · дата, время», подзаголовок — интервал урока
(спека «Редактирование урока»). Помимо полей создания форма содержит
статус и блок «Для семьи» (оценка 1–5 звёзд и комментарий) — это
пер-уточные поля: с включённым «Применить ко всей серии» они меняют
только этот урок, общие поля уходят в `mass_update.apply_to_series`.

Серийные поля («Повторять урок», слоты) в редактировании отсутствуют:
генерация серии — только при создании (design: Non-Goals).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.lesson.services.access import get_owned_lesson, require_tutor_id
from app.lesson.services.lesson_form import (
    lesson_form_context,
    parse_lesson_form,
    validate_edit_fields,
    validate_targets,
)
from app.lesson.services.mass_update import apply_to_series
from app.lesson.services.lesson_writer import update_lesson
from app.templating import templates

router = APIRouter()

LESSONS_URL = "/tutor/lessons"


def _saved_response(request: Request):
    """Успех: пустое тело закрывает модалку, событие обновляет список."""
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=LESSONS_URL, status_code=303)
    return HTMLResponse(content="", headers={"HX-Trigger": "lesson-saved"})


@router.get(f"{LESSONS_URL}/{{lesson_id}}/edit", response_class=HTMLResponse)
def edit_lesson_form(
    lesson_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Форма редактирования; чужой или несуществующий урок — 404."""
    lesson = get_owned_lesson(db, lesson_id, tutor_id)
    return templates.TemplateResponse(
        request, "lesson/_form.html", lesson_form_context(db, lesson=lesson)
    )


@router.post(f"{LESSONS_URL}/{{lesson_id}}", response_class=HTMLResponse)
async def update_lesson_view(
    lesson_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет урок; чужой урок отвечает как несуществующий (404)."""
    lesson = get_owned_lesson(db, lesson_id, tutor_id)
    form = await request.form()
    data, errors = parse_lesson_form(form)
    errors += validate_targets(db, tutor_id, data)
    errors += validate_edit_fields(data)

    if not errors:
        errors = update_lesson(db, lesson, data)

    if errors:
        return templates.TemplateResponse(
            request,
            "lesson/_form.html",
            lesson_form_context(db, lesson=lesson, data=data, errors=errors),
        )

    # Общие поля — на всю серию, пер-уточные уже применены к уроку выше
    # и в массовое обновление не попадают (whitelist MASS_UPDATE_FIELDS).
    if form.get("series_all") == "1" and lesson.series_id:
        apply_to_series(db, lesson.series_id, data)
    db.commit()

    return _saved_response(request)
