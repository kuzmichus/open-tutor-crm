"""Бейдж «Личный кабинет» на миникарточке контакта: приглашение родителя.

Действие живёт в диалоге ученика (прецедент `cabinet_invite.py` ученика),
сервис приглашения — в `cabinet/services/` (design D3). Ответ —
HTMX-фрагмент бейджa (`hx-target` на бейдж, `outerHTML`), не строка
контакта: замена строки затёрла бы несохранённые правки раскрытой формы.
Перевыпуск гасит прежнюю ссылку сам (D2), отдельного действия «погасить»
не нужно. Кнопка действия — `type="button"` без no-JS-фолбэка: не-hx
браузер до этого маршрута не доберётся, а редирект-фолбэк при нём означал
бы отправку всей формы ученика.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.cabinet.services.contact_invites import badge_contexts, create_invite
from app.common.responses import is_htmx
from app.database import get_db
from app.student.services.access import get_owned_contact, require_tutor_id
from app.templating import templates

router = APIRouter()


@router.post(
    "/tutor/contacts/{contact_id}/cabinet/invite", response_class=HTMLResponse
)
def contact_cabinet_invite(
    request: Request,
    contact_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Создаёт или перевыпускает приглашение контакта; чужой контакт — 404.

    Чужой контакт и несуществующий неразличимы (`get_owned_contact`) —
    404, существование чужой записи не раскрывается. Ответ — обновлённый
    бейдж: тот же партиал, что в строке контакта, с состоянием после
    действия (сетенезависимый рендер через `badge_contexts`).
    """
    contact = get_owned_contact(db, contact_id, tutor_id)
    create_invite(db, tutor_id, contact.id)
    if not is_htmx(request):
        # Страховка для запроса без htmx: кнопка в форме — type="button",
        # поэтому сюда попадают только прямые вызовы.
        return RedirectResponse("/tutor/students", status_code=303)
    context = badge_contexts(db, tutor_id, [contact.id])[contact.id]
    return templates.TemplateResponse(
        request,
        "student/_cabinet_badge.html",
        {"badge_contact_id": contact.id, "badge": context},
    )
