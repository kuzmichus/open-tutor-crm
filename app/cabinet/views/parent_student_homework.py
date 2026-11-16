"""Старый адрес ДЗ ребёнка `/parent/students/{id}/homework`: редирект на «Домашние задания».

Страницы ребёнка заменены общей страницей с вкладками по детям (change
parent-cabinet-unified-pages, design D2); адреса сохранены, потому что
ссылки родителям уже разосланы (мессенджер, закладки).

Проверка привязки в редиректе не нужна: страница данных не отдаётся.
Выбор вкладки переносится в параметр адреса `?child={id}` — активный
ребёнок на общей странице совпадает с тем, чью страницу открыли; чужой
или несуществующий id проверит `get_child` уже на странице данных
(404), редирект остаётся честным перенаправлением без проверки.
"""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/parent/students/{student_id}/homework")
def parent_student_homework(student_id: str) -> RedirectResponse:
    """303 на «Домашние задания» с открытой вкладкой этого ребёнка."""
    return RedirectResponse(
        url=f"/parent/homework?child={student_id}", status_code=303
    )
