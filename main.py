"""Точка входа приложения.

Запуск:  uv run uvicorn main:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.booking.views import router as booking_router
from app.calendar.views import router as calendar_router
from app.common.views import router as common_router
from app.common.views.not_found import not_found
from app.database import init_db
from app.finance.views import router as finance_router
from app.group.views import router as group_router
from app.homework.views import router as homework_router
from app.lesson.views import router as lesson_router
from app.slot.views import router as slot_router
from app.stats.views import router as stats_router
from app.student.views import router as student_router
from app.tutor.views import router as tutor_router
from app.unavailability.views import router as unavailability_router

_STATIC_DIR = Path(__file__).resolve().parent / "app" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Удобно для локальной разработки: создаём таблицы, если их ещё нет.
    # Для прод-схемы используйте Alembic:  uv run alembic upgrade head
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Open Tutor CRM", version="0.1.0", lifespan=lifespan)
    app.include_router(common_router)
    app.include_router(tutor_router)
    app.include_router(calendar_router)
    app.include_router(student_router)
    app.include_router(group_router)
    app.include_router(lesson_router)
    app.include_router(homework_router)
    app.include_router(finance_router)
    app.include_router(unavailability_router)
    app.include_router(slot_router)
    app.include_router(booking_router)
    app.include_router(stats_router)
    # Кастомная страница 404 вместо стандартного JSON/Not Found.
    app.add_exception_handler(404, not_found)
    # Статические ассеты (htmx и т.п.) отдаются локально, без CDN.
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    return app


app = create_app()
