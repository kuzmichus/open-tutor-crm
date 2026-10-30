"""Перенос урока перетаскиванием на календаре (design.md D8).

Отдельный endpoint, а не `POST /tutor/lessons/{id}`: полная форма требует
цель, тип, длительность и прочее, а drag меняет только начало. Принимает
`date` + `time` (снап к четверти часа уже сделан на клиенте) и трогает
исключительно `starts_at` — остальные поля урока остаются как были.

Валидация:
- `get_owned_lesson` — чужой или несуществующий урок отвечает 404, как в
  `update.py` (существование чужой записи не раскрывается);
- проведённый урок переносить нельзя: 409 и понятное сообщение;
- `date`/`time` разбираются строго, кривое значение — 400; переданные
  дата и время — настенное время в зоне педагога, в БД уходит aware UTC
  (спека lesson-management, «Перенос урока на новое время»);
- перенос в отмеченный день без `ack_unavailable` отклоняется (409) с
  предупреждением и причиной: новое время ещё не сохранено (design.md D5);
  день недоступности проверяется по локальной дате в зоне педагога.

Успех — `HX-Trigger: lesson-saved`: неделю перерисовывает тот же механизм,
что и после формы (design.md D6).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.responses import saved_response
from app.common.services.tutor_time import to_utc
from app.database import get_db
from app.lesson.services.access import get_owned_lesson, require_tutor_id
from app.lesson.services.unavailability_check import (
    start_unavailability_warning,
    warning_context,
)
from app.tutor.models.tutor import Tutor

router = APIRouter()

LESSONS_URL = "/tutor/lessons"
CALENDAR_URL = "/tutor/calendar"

# Форматы, которые присылает calendar.js: дата и время карточки после снапа.
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"


def _parse_starts_at(date_value: str, time_value: str, tutor) -> datetime:
    """`date` + `time` из drag → начало урока (aware UTC); кривое — 400.

    Значение трактуется как настенное время в зоне педагога: клиент
    присылает локальные дату/время карточки (design D6).
    """
    try:
        naive = datetime.strptime(
            f"{date_value} {time_value}", f"{DATE_FORMAT} {TIME_FORMAT}"
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректные дата или время переноса.",
        )
    return to_utc(naive, tutor)


def _acknowledged(form) -> bool:
    """Признак подтверждения из запроса: `1`/`on`/`true`/`yes`."""
    value = form.get("ack_unavailable", "")
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"1", "on", "true", "yes"}


@router.post(f"{LESSONS_URL}/{{lesson_id}}/move", response_class=HTMLResponse)
async def move_lesson(
    lesson_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Меняет только начало урока; проведённый урок не переносится."""
    lesson = get_owned_lesson(db, lesson_id, tutor_id)
    if lesson.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Проведённый урок нельзя перенести.",
        )

    form = await request.form()
    tutor = db.get(Tutor, tutor_id)
    starts_at = _parse_starts_at(
        str(form.get("date") or ""), str(form.get("time") or ""), tutor
    )

    # Отмеченный день: без подтверждения перенос отклоняется, время урока
    # остаётся прежним (спека lesson-management, «Предупреждение при
    # переносе урока»). Причина возвращается в detail — клиент показывает
    # её в confirm() и повторяет запрос с ack_unavailable=1.
    if not _acknowledged(form):
        warning = start_unavailability_warning(db, tutor_id, starts_at, tutor)
        if warning is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=warning_context(warning)["message"],
            )

    lesson.starts_at = starts_at
    db.commit()

    return saved_response(request, "lesson-saved", CALENDAR_URL)
