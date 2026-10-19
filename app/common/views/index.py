"""Корень приложения: редирект на личный кабинет репетитора."""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/", response_class=RedirectResponse)
def index() -> RedirectResponse:
    """Главная страница: 303 на `/tutor/`."""
    return RedirectResponse(url="/tutor/", status_code=303)
