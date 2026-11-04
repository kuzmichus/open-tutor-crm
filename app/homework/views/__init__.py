"""Сборка роутера модуля homework (по одному эндпоинту на файл)."""

from fastapi import APIRouter

from app.homework.views import delete_file, save

router = APIRouter()

router.include_router(save.router)
router.include_router(delete_file.router)
