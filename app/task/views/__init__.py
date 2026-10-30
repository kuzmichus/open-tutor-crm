"""Сборка роутера модуля task (по одному эндпоинту на файл).

Статические маршруты (`/tutor/tasks`, `/tutor/tasks/list`,
`/tutor/tasks/new`) регистрируются до параметрических
(`/tutor/tasks/{id}/...`) — правило AGENTS.md: иначе `/{task_id}` может
перехватить статический путь.
"""

from fastapi import APIRouter

from app.task.views import (
    count_partial,
    create_task,
    delete_task,
    edit_task,
    list_partial,
    move_task,
    new_task,
    page,
    update_task,
)

router = APIRouter()

# Статические пути — первыми.
router.include_router(page.router)  # GET /tutor/tasks
router.include_router(list_partial.router)  # GET /tutor/tasks/list
router.include_router(new_task.router)  # GET /tutor/tasks/new
router.include_router(count_partial.router)  # GET /tutor/tasks/count
router.include_router(create_task.router)  # POST /tutor/tasks
# Затем действия по id задачи.
router.include_router(edit_task.router)  # GET /tutor/tasks/{id}/edit
router.include_router(update_task.router)  # POST /tutor/tasks/{id}
router.include_router(delete_task.router)  # POST /tutor/tasks/{id}/delete
router.include_router(move_task.router)  # POST /tutor/tasks/{id}/stage
