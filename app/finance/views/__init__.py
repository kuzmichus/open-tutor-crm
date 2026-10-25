"""Сборка роутера модуля finance (по одному эндпоинту на файл).

Порядок регистрации: статические пути (`/tutor/finance/summary`,
`/tutor/payments/new`, `/payments/new`, `/refund/new`) объявляются до
параметрических (`/tutor/payments/{payment_id}`) — иначе параметрический
маршрут перехватил бы статический (правило AGENTS.md).
"""

from fastapi import APIRouter

from app.finance.views import (
    balance_recalculate,
    card_summary,
    expense_create,
    expense_new,
    group_panel,
    income_create,
    income_new,
    index,
    invoice,
    operations,
    panel,
    payment_create,
    payment_edit,
    payment_new,
    payment_update,
    refund_create,
    refund_new,
    summary,
)

router = APIRouter()

router.include_router(panel.router)
# Страница финансов: сводка за период, партиалы её перезапроса и секции
# операций (табы, список, балансы учеников).
router.include_router(index.router)
router.include_router(summary.router)
router.include_router(operations.router)
# Диалог «Доход» со страницы финансов: `/tutor/payments/new` — статический
# путь, он обязан идти до `/tutor/payments/{payment_id}`.
router.include_router(income_new.router)
router.include_router(income_create.router)
# Диалог «Расход» страницы финансов.
router.include_router(expense_new.router)
router.include_router(expense_create.router)
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
