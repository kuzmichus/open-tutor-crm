"""Сборщик роутеров модуля student."""

from fastapi import APIRouter

from app.student.views import (
    access_form,
    access_save,
    archive_student,
    card,
    create_student,
    edit_student,
    index,
    lessons_modal,
    list_partial,
    lookup_contact,
    new_student,
    report_modal,
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
# Модалки списка (уроки, отчёт, доступ): пути `/tutor/students/{id}/...`
# длиннее маршрутов карточки и с ними не конфликтуют, но держатся рядом
# с остальными параметрическими.
router.include_router(lessons_modal.router)
router.include_router(report_modal.router)
router.include_router(access_form.router)
router.include_router(access_save.router)
router.include_router(edit_student.router)
router.include_router(update_student.router)
router.include_router(archive_student.router)
router.include_router(card.router)
