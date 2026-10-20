"""Сборщик роутеров модуля group (по одному эндпоинту на файл).

Роуты подключаются по мере реализации вьюх. Статические пути
(`/tutor/groups/new`, `/tutor/groups/list`, `/tutor/groups/students`)
объявляются до `/tutor/groups/{group_id}`, иначе их перехватит маршрут
с параметром id.
"""

from fastapi import APIRouter

from app.group.views import (
    create_group,
    create_student,
    delete_group,
    edit_group,
    index,
    list_partial,
    new_group,
    update_group,
    update_notes,
)

router = APIRouter()
router.include_router(index.router)
router.include_router(list_partial.router)
# Статические пути — до маршрутов с `{group_id}`.
router.include_router(new_group.router)
router.include_router(create_group.router)
router.include_router(create_student.router)
router.include_router(edit_group.router)
router.include_router(update_group.router)
router.include_router(update_notes.router)
router.include_router(delete_group.router)
