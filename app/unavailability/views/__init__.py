"""Сборка роутера модуля unavailability (по одному эндпоинту на файл).

Статический маршрут панели (`GET/POST /tutor/unavailability`) регистрируется
до маршрутов с `/{mark_id}`, иначе параметрический путь перехватил бы его
(правило AGENTS.md).
"""

from fastapi import APIRouter

from app.unavailability.views import create, delete, panel, update_end

router = APIRouter()

router.include_router(panel.router)
router.include_router(create.router)
# Маршруты с `/{mark_id}` — после статических.
router.include_router(update_end.router)
router.include_router(delete.router)
