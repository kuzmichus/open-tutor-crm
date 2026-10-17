"""Кастомная страница 404: рендерит свой HTML вместо стандартного Not Found."""

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.templating import templates


async def not_found(request: Request, exc: Exception) -> HTMLResponse:
    """Обработчик 404 для всего приложения (регистрируется в main.py)."""
    return templates.TemplateResponse(
        request,
        "404.html",
        {"status_code": 404},
        status_code=404,
    )
