"""Сборка роутера модуля файлов."""

from fastapi import APIRouter

from app.files.views import download

router = APIRouter()

router.include_router(download.router)
