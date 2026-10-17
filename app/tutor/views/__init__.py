"""Сборщик роутеров модуля tutor."""

from fastapi import APIRouter

from app.tutor.views import index

router = APIRouter()
router.include_router(index.router)
