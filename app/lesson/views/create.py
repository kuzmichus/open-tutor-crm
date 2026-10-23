"""Создание урока: модальная форма (GET) и сохранение (POST).

GET `/tutor/lessons/new` — фрагмент `lesson/_form.html` в контейнер
`#modal` (кнопка «Создать урок» на странице списка). POST принимает
форму: одиночный урок либо, при включённом «Повторять урок», серия
одним коммитом (`lesson_writer`). Успех — пустое тело закрывает модалку
свопом, а событие `lesson-saved` обновляет таблицу списка.

Цель урока проверяется на принадлежность репетитору (`validate_targets`):
иначе можно было бы «подложить» урок чужому ученику или группе.

Перед записью проверяется недоступность (design.md D5, D6): если день
(или дни серии) попадает в отметку, форма возвращается с баннером и
присланными значениями, а уроки не создаются — пока пользователь не
подтвердит отправку (`ack_unavailable=1`).
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
from app.lesson.services.unavailability_check import (
    lesson_unavailability_warning,
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


@router.get(f"{LESSONS_URL}/new", response_class=HTMLResponse)
def new_lesson_form(
    request: Request,
    starts_at: str | None = None,
    ack_unavailable: str | None = None,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Пустая форма создания для вставки в контейнер `#modal`.

    `?starts_at=` (из календаря) предзаполняет «Начало»: значение
    трактуется как настенное время в зоне педагога; некорректное
    значение просто игнорируется — форма открывается пустой.
    `?ack_unavailable=1` приходит из календаря после клиентского
    подтверждения и переносится скрытым полем: повторно сервер не
    спрашивает (design.md D5, п. 4), но проверку всё равно выполняет.
    """
    tutor = db.get(Tutor, tutor_id)
    prefill = parse_starts_at(starts_at, tutor)
    data = {"starts_at": prefill} if prefill is not None else None
    return templates.TemplateResponse(
        request,
        "lesson/_form.html",
        lesson_form_context(
            db,
            tutor=tutor,
            data=data,
            ack_unavailable=ack_unavailable in {"1", "on", "true", "yes"},
        ),
    )


@router.post(LESSONS_URL, response_class=HTMLResponse)
async def create_lesson_view(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт урок или серию; `tutor_id` берётся только из сессии.

    Зона педагога берётся из его карточки и передаётся в разбор формы:
    введённое время — настенное время педагога (design D6).
    """
    tutor = db.get(Tutor, tutor_id)
    form = await request.form()
    data, errors = parse_lesson_form(form, tutor)
    errors += validate_targets(db, tutor_id, data)

    # Предупреждение считается до записи: уроки не должны создаваться,
    # пока пользователь не подтвердил постановку в отмеченный день (D5).
    warning = None
    if not errors and not data.get("ack_unavailable"):
        warning = lesson_unavailability_warning(db, tutor_id, data, tutor)

    if not errors and warning is None:
        if data["repeat"]:
            _, errors = create_series(db, data, tutor)
        else:
            _, errors = create_single_lesson(db, data, tutor)

    if errors or warning is not None:
        return templates.TemplateResponse(
            request,
            "lesson/_form.html",
            lesson_form_context(
                db,
                tutor=tutor,
                data=data,
                errors=errors,
                unavailable_warning=warning_context(warning),
            ),
        )

    return _saved_response(request)
