"""Сборка роутеров модуля stats."""

from fastapi import APIRouter

from app.stats.views.index import router as index_router
from app.stats.views.students_csv import router as students_csv_router

router = APIRouter()
router.include_router(students_csv_router)
router.include_router(index_router)
