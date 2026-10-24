"""Сборка роутера модуля slot (по одному эндпоинту на файл).

Статические маршруты (`/new`, `/plan`, `/batch`) регистрируются до
маршрутов с параметром `/{slot_id}`: иначе параметрический путь перехватил
бы их (правило AGENTS.md, п. 4).
"""

from fastapi import APIRouter

from app.slot.views import batch, create, delete, dialog, update

router = APIRouter()

# Статические пути — первыми.
router.include_router(create.router)  # GET /tutor/slots/new, POST /tutor/slots
router.include_router(batch.router)  # GET /tutor/slots/plan, POST /tutor/slots/batch
# Затем окно по id.
router.include_router(dialog.router)  # GET /tutor/slots/{slot_id}
router.include_router(update.router)  # POST /tutor/slots/{slot_id}
router.include_router(delete.router)  # POST /tutor/slots/{slot_id}/delete
