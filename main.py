"""Точка входа приложения.

Запуск:  uv run uvicorn main:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.common.views import router as common_router
from app.database import init_db
from app.student.views import router as student_router
from app.tutor.views import router as tutor_router

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
    app.include_router(student_router)
    # Статические ассеты (htmx и т.п.) отдаются локально, без CDN.
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    return app


app = create_app()
