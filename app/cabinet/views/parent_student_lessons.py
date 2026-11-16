"""Старый адрес страницы ребёнка `/parent/students/{id}`: редирект на «Уроки».

Страницы ребёнка заменены общей сеткой недели всех детей (change
parent-cabinet-unified-pages, design D2); адреса сохранены, потому что
ссылки родителям уже разосланы (мессенджер, закладки).

Проверка привязки в редиректе не нужна: страница данных не отдаётся,
и чужой/несуществующий id ученика ведёт туда же, куда свой, —
перенаправление на `/parent/lessons`, а не 404.
"""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/parent/students/{student_id}")
def parent_student_lessons(student_id: str) -> RedirectResponse:
    """303 на «Уроки» — общую страницу всех детей."""
    return RedirectResponse(url="/parent/lessons", status_code=303)
