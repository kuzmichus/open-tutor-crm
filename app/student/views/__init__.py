"""Сборщик роутеров модуля student."""

from fastapi import APIRouter

from app.student.views import (
    archive_student,
    card,
    create_student,
    edit_student,
    index,
    list_partial,
    lookup_contact,
    new_student,
    update_student,
)

router = APIRouter()
router.include_router(index.router)
router.include_router(list_partial.router)
# Статические пути объявляются до `/tutor/students/{student_id}`, иначе
# `/tutor/students/new` и `/tutor/students/list` перехватит карточка.
router.include_router(new_student.router)
router.include_router(create_student.router)
router.include_router(lookup_contact.router)
router.include_router(edit_student.router)
router.include_router(update_student.router)
router.include_router(archive_student.router)
router.include_router(card.router)
