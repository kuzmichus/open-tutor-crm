"""Главная страница: «Hello world» и часы, обновляемые каждую секунду через htmx."""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Главная страница приложения."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return templates.TemplateResponse(request, "index.html", {"now": now})
