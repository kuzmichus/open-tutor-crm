"""Сборщик роутеров общего модуля."""

from fastapi import APIRouter

from app.common.views import auth_status, clock, favicon, health, index

router = APIRouter()
router.include_router(health.router)
router.include_router(auth_status.router)
router.include_router(index.router)
router.include_router(clock.router)
router.include_router(favicon.router)
