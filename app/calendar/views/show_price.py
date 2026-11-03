"""Переключатель «Показывать цену» на странице «Календарь» (POST).

Флаг живёт в настройках репетитора (`tutor_settings.show_calendar_price`):
это выбор отображения, а не свойство занятия, поэтому отдельной таблицы и
миграции урока не нужно. Ответ — событие `price-saved` для htmx (неделя
перерисовывается с сервера) либо 303 на ту же неделю, если JS выключен.
"""

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.calendar.services.week import week_start
from app.common.access import LoginRequired, require_tutor_id
from app.common.responses import saved_response
from app.common.services.tutor_time import today_local
from app.database import get_db
from app.tutor.models.tutor import Tutor
from app.tutor.services.settings import save_settings

router = APIRouter()


def _redirect_url(tutor: Tutor, start: str | None) -> str:
    """Адрес календаря на той неделе, где переключили флаг.

    `start` приходит из разметки (`hx-vals`) — это понедельник видимой
    недели. Кривое значение не ошибка: открывается текущая неделя, как и
    при листании.
    """
    try:
        monday = week_start(start) if start else week_start(today_local(tutor))
    except ValueError:
        monday = week_start(today_local(tutor))
    return f"/tutor/calendar?start={monday.isoformat()}"


@router.post("/tutor/calendar/show-price")
def calendar_show_price(
    request: Request,
    show_price: str = Form(""),
    start: str = Form(""),
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет флаг «Показывать цену» и возвращает событие обновления.

    Отсутствие поля в форме означает выключенный чекбокс — тот же приём,
    что у переключателей уведомлений: браузер не отправляет снятые
    галочки, поэтому значение читается как «истина/пусто».
    """
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    save_settings(db, tutor_id, {"show_calendar_price": bool(show_price)})
    return saved_response(request, "price-saved", _redirect_url(tutor, start))
