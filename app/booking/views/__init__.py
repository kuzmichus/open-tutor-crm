"""Сборка роутера модуля booking (по одному эндпоинту на файл).

Маршруты действий с бронью: подтверждение, отклонение, отмена. Все три
имеют одинаковый путь `/{booking_id}/<действие>`, поэтому статических
маршрутов, которые мог бы перехватить параметрический путь, здесь нет —
порядок подключения задаётся только читаемостью.

Публичная страница записи (`public.py`) подключается сюда же, но её
маршруты начинаются с `/s/` и не пересекаются с `/tutor/bookings/...`.
"""

from fastapi import APIRouter

from app.booking.views import cancel, confirm, public, reject

router = APIRouter()

router.include_router(confirm.router)  # POST /tutor/bookings/{id}/confirm
router.include_router(reject.router)  # POST /tutor/bookings/{id}/reject
router.include_router(cancel.router)  # POST /tutor/bookings/{id}/cancel
# Публичная поверхность: свои пути `/s/...`, с остальными не пересекаются.
router.include_router(public.router)  # GET /s/{tutor_id}, POST /s/{tutor_id}/book
