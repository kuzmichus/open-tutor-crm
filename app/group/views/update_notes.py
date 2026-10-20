"""Сохранение заметок к группе с подменой панели «Общее».

Заметки видят только репетиторы (спека group-management): поле живёт на
вкладке «Общее», сохраняется отдельным запросом, чтобы не отправлять всю
форму настроек.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.common.access import require_tutor_id
from app.database import get_db
from app.group.services.access import get_owned_group
from app.group.services.form_context import existing_member_rows, manage_context
from app.group.services.group_writer import update_notes
from app.templating import templates

router = APIRouter()


@router.post("/tutor/groups/{group_id}/notes", response_class=HTMLResponse)
async def update_notes_view(
    request: Request,
    group_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Сохраняет заметки и возвращает обновлённую панель «Общее»."""
    group = get_owned_group(db, group_id, tutor_id)
    form = await request.form()
    notes = form.get("notes", "")
    update_notes(db, group, notes if isinstance(notes, str) else "")

    context = manage_context(db, tutor_id, group)
    # Панель отдаётся вне модалки: шаблон ждёт те же переменные.
    context.update(
        {
            "notes_saved": True,
            "member_rows": existing_member_rows(db, group),
        }
    )
    return templates.TemplateResponse(
        request, "group/_general_panel.html", context
    )
