"""Сборщик роутеров общего модуля."""

from fastapi import APIRouter

from app.common.views import clock, health, index

router = APIRouter()
router.include_router(health.router)
router.include_router(index.router)
router.include_router(clock.router)
