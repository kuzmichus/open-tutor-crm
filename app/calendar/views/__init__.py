"""Сборщик роутеров модуля calendar."""

from fastapi import APIRouter

from app.calendar.views import index, show_price

router = APIRouter()
router.include_router(index.router)
router.include_router(show_price.router)
