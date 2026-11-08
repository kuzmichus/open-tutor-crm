"""Сборка роутера модуля лендинга.

Публичная поверхность — только картинки (`/landing-assets/...`).
Опубликованную страницу с `/` отдаёт общий роутер (`app/common/views/index.py`):
корень принадлежит ему, и лендинг лишь перехватывает ответ, когда страница
опубликована. Остальное — поверхность репетитора: управление
(`/tutor/landing`), предпросмотр и редактор (`/tutor/landing/editor`).
"""

from fastapi import APIRouter

from app.landing.views import assets, editor, page

router = APIRouter()

router.include_router(assets.router)
router.include_router(page.router)
router.include_router(editor.router)
