"""Сборка роутера модуля lesson (по одному эндпоинту на файл).

Статические маршруты (`/list`, `/lookup/...`, `/students`, `/groups`)
регистрируются до будущих маршрутов с параметром `/{lesson_id}`, чтобы
поиск по пути не перехватывал их.
"""

from fastapi import APIRouter

from app.lesson.views import (
    complete_selected,
    create,
    create_group,
    create_student,
    delete,
    delete_series,
    group_lessons,
    index,
    list_partial,
    lookup_group,
    lookup_student,
    move,
    notices,
    update,
)

router = APIRouter()

router.include_router(index.router)
router.include_router(list_partial.router)
# Массовая отметка — статический путь `/complete-selected`, обязательно до
# `POST /{lesson_id}`, иначе параметрический маршрут принял бы его за id.
router.include_router(complete_selected.router)
router.include_router(lookup_student.router)
router.include_router(lookup_group.router)
router.include_router(create_student.router)
router.include_router(create_group.router)
# Модалки создания/редактирования и удаление — после статических маршрутов:
# POST `/tutor/lessons/{lesson_id}` не должен перехватывать `/students` и др.
router.include_router(create.router)
router.include_router(update.router)
router.include_router(delete.router)
router.include_router(delete_series.router)
# Перенос перетаскиванием — свой путь `/{lesson_id}/move`, поэтому
# статические маршруты выше он не перехватывает (design.md D8).
router.include_router(move.router)
# Панель «Занятия» группы: маршрут `/tutor/groups/{group_id}/lessons` —
# чужое пространство имён, с маршрутами `/{lesson_id}` не пересекается.
router.include_router(group_lessons.router)
# Баннер-напоминание `/tutor/notices`: собственный префикс, с маршрутами
# `/tutor/lessons/{lesson_id}` не пересекается.
router.include_router(notices.router)
