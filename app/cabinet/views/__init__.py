"""Вьюхи кабинетов: ученика и родителя.

Маршруты ученика — публичные поверхности (`/invite/<token>`,
`/student/login`) и страницы с сессией ученика (`/student`,
`/student/homework`, `/student/logout`); доступ к последним —
зависимостью `require_student_id` из `app/cabinet/services/access.py`.

Маршруты родителя (`cabinet/views/parent_*.py`, change parent-cabinet) —
те же две группы: публичные `/parent/invite/<token>` и `/parent/login`,
страницы с сессией контакта (`/parent`, вкладки, `/parent/logout`) за
`require_contact_id`. Роутеры ученика и родителя не пересекаются путями:
`/student*` и `/parent*` — разные префиксы.
"""

from fastapi import APIRouter

from app.cabinet.views import homework, index, login, logout, register
from app.cabinet.views import (
    parent_finance,
    parent_index,
    parent_login,
    parent_logout,
    parent_profile,
    parent_register,
    parent_student_homework,
    parent_student_lessons,
)

router = APIRouter()
router.include_router(login.router)
router.include_router(logout.router)
router.include_router(register.router)
router.include_router(index.router)
router.include_router(homework.router)
# Кабинет родителя: публичные страницы первыми, затем страницы с сессией.
router.include_router(parent_register.router)
router.include_router(parent_login.router)
router.include_router(parent_logout.router)
router.include_router(parent_index.router)
router.include_router(parent_student_lessons.router)
router.include_router(parent_student_homework.router)
router.include_router(parent_finance.router)
router.include_router(parent_profile.router)
