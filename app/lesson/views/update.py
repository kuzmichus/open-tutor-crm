"""Редактирование урока: модальная форма (GET) и сохранение (POST).

Заголовок модалки — «Цель · дата, время», подзаголовок — интервал урока
(спека «Редактирование урока»). Помимо полей создания форма содержит
статус и блок «Для семьи» (оценка 1–5 звёзд и комментарий) — это
пер-уточные поля: с включённым «Применить ко всей серии» они меняют
только этот урок, общие поля уходят в `mass_update.apply_to_series`.

Серийные поля («Повторять урок», слоты) в редактировании отсутствуют:
генерация серии — только при создании (design: Non-Goals).

Смена «Начала» на день, попадающий в отметку недоступности, предупреждает
так же, как создание урока (design.md D5): без подтверждения урок не
изменяется, форма возвращается с баннером и присланными значениями.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.services.tutor_time import to_local
from app.database import get_db
from app.finance.services.charges import sync_lesson_charges
from app.lesson.services.access import get_owned_lesson, require_tutor_id
from app.lesson.services.lesson_form import (
    lesson_form_context,
    parse_lesson_form,
    validate_edit_fields,
    validate_targets,
)
from app.lesson.services.mass_update import apply_to_series
from app.lesson.services.lesson_writer import update_lesson
from app.lesson.services.unavailability_check import (
    start_unavailability_warning,
    warning_context,
)
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

LESSONS_URL = "/tutor/lessons"


def _saved_response(request: Request):
    """Успех: пустое тело закрывает модалку, событие обновляет список."""
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=LESSONS_URL, status_code=303)
    return HTMLResponse(content="", headers={"HX-Trigger": "lesson-saved"})


def _start_day_changed(lesson, data: dict, tutor) -> bool:
    """«Начало» переехало на другой день (время внутри дня не считается).

    Дни сравниваются в зоне педагога: `starts_at` в `data` — aware UTC,
    значение в БД — UTC (возможно, наивный формат SQLite), а день
    недоступности — локальная дата.

    Проверять отметку при правке прочих полей урока, уже стоящего в
    отмеченном дне, не нужно: пользователь не переносит занятие, а
    предупреждение на каждое сохранение было бы шумом (design.md D5).
    """
    new_start = data.get("starts_at")
    if new_start is None or lesson.starts_at is None:
        return False
    return to_local(new_start, tutor).date() != to_local(
        lesson.starts_at, tutor
    ).date()


@router.get(f"{LESSONS_URL}/{{lesson_id}}/edit", response_class=HTMLResponse)
def edit_lesson_form(
    lesson_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Форма редактирования; чужой или несуществующий урок — 404."""
    lesson = get_owned_lesson(db, lesson_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    return templates.TemplateResponse(
        request,
        "lesson/_form.html",
        lesson_form_context(db, tutor=tutor, lesson=lesson),
    )


@router.post(f"{LESSONS_URL}/{{lesson_id}}", response_class=HTMLResponse)
async def update_lesson_view(
    lesson_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет урок; чужой урок отвечает как несуществующий (404).

    Зона педагога берётся из его карточки: введённое время — настенное
    время педагога, в БД уходит aware UTC (design D6).
    """
    lesson = get_owned_lesson(db, lesson_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    form = await request.form()
    data, errors = parse_lesson_form(form, tutor)
    errors += validate_targets(db, tutor_id, data)
    errors += validate_edit_fields(data)

    # Предупреждение только при переезде «Начала» на отмеченный день и без
    # подтверждения (design.md D5): урок ещё не изменён.
    warning = None
    if (
        not errors
        and not data.get("ack_unavailable")
        and _start_day_changed(lesson, data, tutor)
    ):
        warning = start_unavailability_warning(
            db, tutor_id, data["starts_at"], tutor
        )

    if not errors and warning is None:
        errors = update_lesson(db, lesson, data, tutor)

    if errors or warning is not None:
        return templates.TemplateResponse(
            request,
            "lesson/_form.html",
            lesson_form_context(
                db,
                tutor=tutor,
                lesson=lesson,
                data=data,
                errors=errors,
                unavailable_warning=warning_context(warning),
            ),
        )

    # Общие поля — на всю серию, пер-уточные уже применены к уроку выше
    # и в массовое обновление не попадают (whitelist MASS_UPDATE_FIELDS).
    if form.get("series_all") == "1" and lesson.series_id:
        apply_to_series(db, lesson.series_id, data)
    # Списания пересчитываются после всех правок урока и серии, до коммита
    # (design D6): одной транзакцией сохраняются и уроки, и счёт. Массовая
    # правка цены меняет все уроки серии, поэтому списания синхронизируются
    # по каждому — иначе «Применить ко всей серии» обновило бы уроки, а
    # история денег осталась бы старой.
    sync_lesson_charges(db, lesson, series_applied=form.get("series_all") == "1")
    db.commit()

    return _saved_response(request)
