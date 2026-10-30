"""Ручка содержимого вкладки страницы финансов (GET `/tutor/finance/tabs/{tab}`).

Её запрашивает `hx-get` ссылки вкладки: ответ — та же секция операций
(`finance/_operations.html`), что рендерит страница, поэтому htmx подменяет
`#finance-operations` целиком и перезагрузки страницы не происходит.

Вкладка — часть пути, остальное состояние (период, горизонт «Аналитики»,
месяц «Прогноза») — query-параметры, и разбирает их тот же
`parse_state`, что у страницы: адрес и разметка не могут разойтись.

Ответ несёт `HX-Push-Url` с каноническим адресом страницы (`?period=…&tab=…`):
в истории и в строке браузера остаётся адрес страницы, а не партиала, —
перезагрузка и «назад» открывают ту же вкладку. Значения в адрес попадают
уже разобранными, поэтому мусор в query его не портит.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.finance.services.access import LoginRequired, require_tutor_id
from app.finance.services.operations_section import (
    operations_context,
    parse_state,
)
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/tutor/finance/tabs/{tab}", response_class=HTMLResponse)
def finance_tab(
    request: Request,
    tab: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Секция операций с открытой вкладкой `tab`; без сессии — на вход.

    Неизвестная вкладка в пути — не 404, а умолчание «Все операции»: тот же
    принцип, что у `parse_finance_tab` для query (опечатка не повод ломать
    страницу). Ключ из пути подкладывается в параметры разбора — остальное
    состояние приходит из query как есть.
    """
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    state = parse_state({**request.query_params, "tab": tab}, tutor)
    context = operations_context(db, tutor, oob=True, **state)
    return templates.TemplateResponse(
        request,
        "finance/_operations.html",
        context,
        headers={"HX-Push-Url": context["page_url"]},
    )
