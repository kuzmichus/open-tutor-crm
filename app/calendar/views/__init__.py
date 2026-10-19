"""Сборщик роутеров модуля calendar."""

from fastapi import APIRouter

from app.calendar.views import index

router = APIRouter()
router.include_router(index.router)
