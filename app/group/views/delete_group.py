"""Удаление группы: членство уходит каскадом, ученики остаются.

Подтверждение — на клиенте (двухшаговое, решение D7): второй клик по
«Точно удалить?» отправляет POST. Ответ — свежая сетка карточек, поэтому
страница не перезагружается, а модалка закрывается событием.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.common.responses import is_htmx
from app.database import get_db
from app.group.services.access import get_owned_group
from app.group.services.group_writer import delete_group
from app.group.services.groups import group_options
from app.templating import templates

router = APIRouter()


@router.post("/tutor/groups/{group_id}/delete", response_class=HTMLResponse)
def delete_group_view(
    request: Request,
    group_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Удаляет группу; чужая группа отвечает как отсутствующая (404)."""
    group = get_owned_group(db, group_id, tutor_id)
    delete_group(db, group)

    if not is_htmx(request):
        return RedirectResponse(url="/tutor/groups", status_code=303)

    options = group_options(db, tutor_id)
    response = templates.TemplateResponse(
        request,
        "group/_grid.html",
        {"options": options, "total": len(options)},
    )
    # Сетка уже пришла в ответе; модалка управления закрывается событием.
    response.headers["HX-Trigger"] = "group-deleted"
    return response
