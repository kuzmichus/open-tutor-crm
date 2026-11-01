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
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.common.responses import saved_response
from app.database import get_db
from app.gcalendar.services.sync import sync_lessons
from app.lesson.services.lesson_form import (
    lesson_form_context,
    parse_duration_min,
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


@router.get(f"{LESSONS_URL}/new", response_class=HTMLResponse)
def new_lesson_form(
    request: Request,
    starts_at: str | None = None,
    duration_min: str | None = None,
    ack_unavailable: str | None = None,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Пустая форма создания для вставки в контейнер `#modal`.

    `?starts_at=` (из календаря) предзаполняет «Начало»: значение
    трактуется как настенное время в зоне педагога; некорректное
    значение просто игнорируется — форма открывается пустой.
    `?duration_min=` (из окна для записи) предзаполняет «Длительность»:
    урок из окна должен совпасть с окном по времени, иначе окно останется
    «Свободно» рядом с созданным уроком (спека calendar, «Префилл из
    окна»). Значение вне `LESSON_DURATIONS` игнорируется.
    `?ack_unavailable=1` приходит из календаря после клиентского
    подтверждения и переносится скрытым полем: повторно сервер не
    спрашивает (design.md D5, п. 4), но проверку всё равно выполняет.
    """
    tutor = db.get(Tutor, tutor_id)
    prefill = parse_starts_at(starts_at, tutor)
    duration = parse_duration_min(duration_min)
    data = {
        key: value
        for key, value in (("starts_at", prefill), ("duration_min", duration))
        if value is not None
    } or None
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
    # Создание всегда даёт «Запланирован» (спека lesson-management): поля
    # «Проведение» в форме создания нет, и присланный статус — мусор от
    # устаревшей страницы. Сервис записи статус принимает (им пользуются
    # тесты и будущие импорты), поэтому гасим его здесь, а не в writer'е.
    data["status"] = None

    # Предупреждение считается до записи: уроки не должны создаваться,
    # пока пользователь не подтвердил постановку в отмеченный день (D5).
    warning = None
    if not errors and not data.get("ack_unavailable"):
        warning = lesson_unavailability_warning(db, tutor_id, data, tutor)

    if not errors and warning is None:
        if data["repeat"]:
            lessons, errors = create_series(db, data, tutor)
        else:
            lesson, errors = create_single_lesson(db, data, tutor)
            lessons = [lesson] if lesson is not None else []
        if not errors:
            # Уроки уже сохранены своей транзакцией: синхронизация с Google
            # best-effort и не ломает создание (design D2, D10).
            sync_lessons(db, tutor, lessons)

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

    return saved_response(request, "lesson-saved", LESSONS_URL)
