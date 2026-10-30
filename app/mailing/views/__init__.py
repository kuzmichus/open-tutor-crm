"""Сборка роутера модуля mailing (по одному эндпоинту на файл).

Статические маршруты (`/tutor/mailings`, `/tutor/mailings/recipients`,
`/tutor/mailings/composer`, `/tutor/mailings/templates`, `/tutor/mailings/templates/new`)
регистрируются до параметрических (`/tutor/mailings/templates/{id}/...`)
— иначе параметрический путь перехватит статический.
"""

from fastapi import APIRouter

from app.mailing.views import (
    composer_partial,
    page,
    recipients_partial,
    send,
    tabs,
    template_create,
    template_delete,
    template_edit,
    template_new,
    template_update,
    templates_dialog,
)

router = APIRouter()

# Статические пути — первыми.
router.include_router(page.router)  # GET /tutor/mailings
router.include_router(tabs.router)  # GET /tutor/mailings/tabs/{tab}
router.include_router(recipients_partial.router)  # GET /tutor/mailings/recipients
router.include_router(composer_partial.router)  # GET /tutor/mailings/composer
router.include_router(templates_dialog.router)  # GET /tutor/mailings/templates
router.include_router(template_new.router)  # GET /tutor/mailings/templates/new
router.include_router(template_create.router)  # POST /tutor/mailings/templates
# Затем действия по id шаблона.
router.include_router(template_edit.router)  # GET /tutor/mailings/templates/{id}/edit
router.include_router(template_update.router)  # POST /tutor/mailings/templates/{id}
router.include_router(
    template_delete.router
)  # POST /tutor/mailings/templates/{id}/delete
router.include_router(send.router)  # POST /tutor/mailings/send
