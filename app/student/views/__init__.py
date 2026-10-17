"""Сборщик роутеров модуля student."""

from fastapi import APIRouter

from app.student.views import index

router = APIRouter()
router.include_router(index.router)
