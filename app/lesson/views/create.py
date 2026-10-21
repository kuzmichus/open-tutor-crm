"""Создание урока: модальная форма (GET) и сохранение (POST).

GET `/tutor/lessons/new` — фрагмент `lesson/_form.html` в контейнер
`#modal` (кнопка «Создать урок» на странице списка). POST принимает
форму: одиночный урок либо, при включённом «Повторять урок», серия
одним коммитом (`lesson_writer`). Успех — пустое тело закрывает модалку
свопом, а событие `lesson-saved` обновляет таблицу списка.

Цель урока проверяется на принадлежность репетитору (`validate_targets`):
иначе можно было бы «подложить» урок чужому ученику или группе.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.lesson.services.lesson_form import (
    lesson_form_context,
    parse_lesson_form,
    parse_starts_at,
    validate_targets,
)
from app.lesson.services.lesson_writer import create_series, create_single_lesson
from app.templating import templates

router = APIRouter()

LESSONS_URL = "/tutor/lessons"


def _saved_response(request: Request):
    """Успех: пустое тело закрывает модалку, событие обновляет список."""
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=LESSONS_URL, status_code=303)
    return HTMLResponse(content="", headers={"HX-Trigger": "lesson-saved"})


@router.get(f"{LESSONS_URL}/new", response_class=HTMLResponse)
def new_lesson_form(
    request: Request,
    starts_at: str | None = None,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Пустая форма создания для вставки в контейнер `#modal`.

    `?starts_at=` (из календаря) предзаполняет «Начало»; некорректное
    значение просто игнорируется — форма открывается пустой.
    """
    prefill = parse_starts_at(starts_at)
    data = {"starts_at": prefill} if prefill is not None else None
    return templates.TemplateResponse(
        request, "lesson/_form.html", lesson_form_context(db, data=data)
    )


@router.post(LESSONS_URL, response_class=HTMLResponse)
async def create_lesson_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт урок или серию; `tutor_id` берётся только из сессии."""
    form = await request.form()
    data, errors = parse_lesson_form(form)
    errors += validate_targets(db, tutor_id, data)

    if not errors:
        if data["repeat"]:
            _, errors = create_series(db, data)
        else:
            _, errors = create_single_lesson(db, data)

    if errors:
        return templates.TemplateResponse(
            request,
            "lesson/_form.html",
            lesson_form_context(db, data=data, errors=errors),
        )

    return _saved_response(request)
