"""Фрагмент времени для htmx-часов."""

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/time", response_class=HTMLResponse)
def clock_fragment() -> HTMLResponse:
    """Отдаёт текущую дату/время для подстановки в #clock через htmx."""
    return HTMLResponse(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
