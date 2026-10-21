"""Перенос урока перетаскиванием на календаре (design.md D8).

Отдельный endpoint, а не `POST /tutor/lessons/{id}`: полная форма требует
цель, тип, длительность и прочее, а drag меняет только начало. Принимает
`date` + `time` (снап к четверти часа уже сделан на клиенте) и трогает
исключительно `starts_at` — остальные поля урока остаются как были.

Валидация:
- `get_owned_lesson` — чужой или несуществующий урок отвечает 404, как в
  `update.py` (существование чужой записи не раскрывается);
- проведённый урок переносить нельзя: 409 и понятное сообщение;
- `date`/`time` разбираются строго, кривое значение — 400.

Успех — `HX-Trigger: lesson-saved`: неделю перерисовывает тот же механизм,
что и после формы (design.md D6).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.lesson.services.access import get_owned_lesson, require_tutor_id

router = APIRouter()

LESSONS_URL = "/tutor/lessons"
CALENDAR_URL = "/tutor/calendar"

# Форматы, которые присылает calendar.js: дата и время карточки после снапа.
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"


def _parse_starts_at(date_value: str, time_value: str) -> datetime:
    """`date` + `time` из drag → начало урока; кривое значение — 400."""
    try:
        return datetime.strptime(
            f"{date_value} {time_value}", f"{DATE_FORMAT} {TIME_FORMAT}"
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректные дата или время переноса.",
        )


def _moved_response(request: Request):
    """Успех: пустое тело, событие перерисовывает неделю календаря."""
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=CALENDAR_URL, status_code=303)
    return HTMLResponse(content="", headers={"HX-Trigger": "lesson-saved"})


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
    starts_at = _parse_starts_at(
        str(form.get("date") or ""), str(form.get("time") or "")
    )

    lesson.starts_at = starts_at
    db.commit()

    return _moved_response(request)
