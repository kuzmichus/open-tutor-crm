"""Сборка роутера модуля booking (по одному эндпоинту на файл).

Маршруты действий с бронью: подтверждение, отклонение, отмена. Все три
имеют одинаковый путь `/{booking_id}/<действие>`. Статические маршруты
страницы (`/tutor/bookings`, `/tutor/bookings/list`, `/tutor/bookings/count`)
подключаются до них: параметрический `/tutor/bookings/{id}/...` — другой
метод и глубина, но порядок «статические первыми» держим единообразно
(AGENTS.md, п. 4).

Публичная страница записи (`public.py`) подключается сюда же, но её
маршруты начинаются с `/s/` и не пересекаются с `/tutor/bookings/...`.
"""

from fastapi import APIRouter

from app.booking.views import (
    cancel,
    confirm,
    count_partial,
    list_partial,
    page,
    public,
    reject,
)

router = APIRouter()

# Статические пути — первыми.
router.include_router(page.router)  # GET /tutor/bookings
router.include_router(list_partial.router)  # GET /tutor/bookings/list
router.include_router(count_partial.router)  # GET /tutor/bookings/count
# Затем действия по id брони.
router.include_router(confirm.router)  # POST /tutor/bookings/{id}/confirm
router.include_router(reject.router)  # POST /tutor/bookings/{id}/reject
router.include_router(cancel.router)  # POST /tutor/bookings/{id}/cancel
# Публичная поверхность: свои пути `/s/...`, с остальными не пересекаются.
router.include_router(public.router)  # GET /s/{tutor_id}, POST /s/{tutor_id}/book
