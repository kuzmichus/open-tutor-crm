"""Сборка роутера модуля finance (по одному эндпоинту на файл).

Порядок регистрации: статические пути (`/payments/new`, `/refund/new`)
объявляются до параметрических (`/tutor/payments/{payment_id}`) — иначе
`/tutor/payments/{payment_id}` перехватил бы `/tutor/payments/new`
(правило AGENTS.md).
"""

from fastapi import APIRouter

from app.finance.views import (
    balance_recalculate,
    card_summary,
    group_panel,
    invoice,
    panel,
    payment_create,
    payment_edit,
    payment_new,
    payment_update,
    refund_create,
    refund_new,
)

router = APIRouter()

router.include_router(panel.router)
router.include_router(payment_new.router)
router.include_router(payment_create.router)
router.include_router(payment_edit.router)
router.include_router(payment_update.router)
router.include_router(refund_new.router)
router.include_router(refund_create.router)
router.include_router(invoice.router)
router.include_router(card_summary.router)
router.include_router(balance_recalculate.router)
# Панель оплат группы: маршрут `/tutor/groups/{group_id}/payments` —
# параметрический, но без статических соседей в этом пространстве,
# конфликтов с роутами модуля group нет.
router.include_router(group_panel.router)
