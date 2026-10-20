"""Сборка роутера модуля homework (по одному эндпоинту на файл)."""

from fastapi import APIRouter

from app.homework.views import save

router = APIRouter()

router.include_router(save.router)
