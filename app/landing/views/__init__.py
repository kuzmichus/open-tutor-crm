"""Сборка роутера модуля лендинга.

Публичная поверхность — только картинки (`/landing-assets/...`).
Опубликованную страницу с `/` отдаёт общий роутер (`app/common/views/index.py`):
корень принадлежит ему, и лендинг лишь перехватывает ответ, когда страница
опубликована.
"""

from fastapi import APIRouter

from app.landing.views import assets

router = APIRouter()

router.include_router(assets.router)
