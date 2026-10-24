"""Пачка окон: предпросмотр (GET) и создание (POST) — один расчёт (D6).

`GET /tutor/slots/plan` — htmx-предпросмотр блока отчёта: он считается тем
же `batch.plan_for_tutor`, что и создание, поэтому разойтись с результатом
не может физически. Запрос приходит на каждое изменение полей
(`hx-trigger="change, input changed delay:400ms"`), ответ — партиал
`slot/_batch_preview.html` в контейнер предпросмотра.

`POST /tutor/slots/batch` — создание: `batch.apply` пишет ровно то, что
посчитал `plan`, и возвращает отчёт о пропусках. Ответ — диалог с блоком
результата (`result=True`), а `HX-Trigger: slot-saved` перерисовывает
неделю: пользователь сразу видит созданные окна в сетке.

Ошибки разбора формы и превышение лимита возвращают диалог с ошибками и
не создают ни одного окна (спека slot-management, «Лимит окон за одно
действие»).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.services.tutor_time import now_utc
from app.database import get_db
from app.slot.services.access import require_tutor_id
from app.slot.services.batch import apply, plan_for_tutor
from app.slot.services.dialog_context import dialog_context, preview_context
from app.slot.services.slot_form import parse_batch_form
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

SLOTS_URL = "/tutor/slots"
CALENDAR_URL = "/tutor/calendar"


def _preview_form(form) -> dict:
    """Присланные значения пачки для повторного показа в форме.

    Разбор мог не удаться (пустая дата, кривой перерыв) — тогда форма
    показывает то, что удалось прочитать, а не сбрасывает поля.
    """
    from app.slot.services.slot_form import batch_form_values

    return batch_form_values(form)


@router.get(f"{SLOTS_URL}/plan", response_class=HTMLResponse)
async def preview_batch(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Предпросмотр пачки: число окон, времена дня и пропуски.

    htmx присылает поля через `hx-include` в query-строке (это GET), а не
    телом запроса, поэтому значения читаются из `query_params`: у них тот
    же интерфейс `get`/`getlist`, что и у `FormData`, и `parse_batch_form`
    работает с ними без изменений.

    Невалидная форма не ошибка для предпросмотра: блок просто пуст —
    пользователь ещё вводит значения, и красная плашка на каждый символ
    была бы шумом. Ошибки появятся при сохранении.
    """
    tutor = db.get(Tutor, tutor_id)
    params, _ = parse_batch_form(request.query_params)

    preview = None
    if params is not None:
        plan = plan_for_tutor(db, tutor, params, now=now_utc())
        preview = preview_context(plan, tutor)

    return templates.TemplateResponse(
        request,
        "slot/_batch_preview.html",
        {"slot_preview": preview},
    )


@router.post(f"{SLOTS_URL}/batch", response_class=HTMLResponse)
async def create_batch(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Создаёт пачку окон; частичное создание, не атомарное (design D6)."""
    tutor = db.get(Tutor, tutor_id)
    form = await request.form()
    params, errors = parse_batch_form(form)

    if errors:
        return templates.TemplateResponse(
            request,
            "slot/_dialog.html",
            dialog_context(
                db,
                tutor,
                data=_preview_form(form),
                errors=errors,
                mode="batch",
            ),
        )

    created, plan = apply(db, tutor, params, now=now_utc())
    preview = preview_context(plan, tutor, created=len(created))

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=CALENDAR_URL, status_code=303)

    response = templates.TemplateResponse(
        request,
        "slot/_dialog.html",
        dialog_context(
            db,
            tutor,
            data=_preview_form(form),
            mode="batch",
            preview=preview,
        ),
    )
    # Неделя перерисовывается с сервера: созданные окна видны сразу
    # (спека calendar, «Сохранение окна обновляет неделю»).
    #
    # Именно `After-Swap`: обычный `HX-Trigger` htmx рассылает ДО подмены
    # содержимого, и подписка `slot-saved` ещё живого диалога закрыла бы его
    # вместе с отчётом о пропусках (проверено в браузере). После подмены в
    # DOM стоит диалог с отчётом, который на это событие уже не подписан.
    response.headers["HX-Trigger-After-Swap"] = "slot-saved"
    return response
