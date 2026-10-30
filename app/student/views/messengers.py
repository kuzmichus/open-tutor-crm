"""Приглашение ученика в мессенджеры: блок на вкладке «Настройки» карточки.

Блок — HTMX-фрагмент (`#student-invites`): «Пригласить», «Сгенерировать
новую» и «Отвязать» возвращают обновлённый фрагмент целиком, без JS
работают 303-редиректом на страницу ученика (точный текст ошибки в URL
не переносится — фрагментный путь основной). Проверка приглашений — GET
того же фрагмента: пока есть непогашенное приглашение, фрагмент
опрашивает сам себя (`every 4s`), и каждый опрос читает апдейты ботов —
ученик подключается сам, когда нажал «Запустить» в чате. GET, который
меняет состояние, оправдан так же, как у каналов репетитора: код
одноразовый и после успеха подтверждение идемпотентно, а htmx-поллинг
умеет только GET.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.common.responses import is_htmx
from app.database import get_db
from app.messenger.services.binding import confirm_binding
from app.messenger.services.messengers import SUPPORTED
from app.messenger.services.student_invites import (
    invites_context,
    start_invite,
    unbind_student,
)
from app.student.services.access import get_owned_student, require_tutor_id
from app.templating import templates

router = APIRouter()


@router.get(
    "/tutor/students/{student_id}/messengers", response_class=HTMLResponse
)
def invites_fragment(
    request: Request,
    student_id: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Фрагмент блока: автоопрос непогашенного приглашения и подтверждение.

    Каждый запрос проверяет апдейты ботов по всем ожидающим кодам
    аккаунта (канал репетитора и приглашения учеников) — один читатель
    потока на всё.
    """
    student = get_owned_student(db, student_id, tutor_id)
    errors = _confirm_pending(db, tutor_id)
    return _invites_response(request, db, tutor_id, student.id, errors)


@router.post(
    "/tutor/students/{student_id}/messengers/{messenger}/invite",
    response_class=HTMLResponse,
)
def invite_student(
    request: Request,
    student_id: str,
    messenger: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Готовит приглашение: одноразовый код и диплинк сохраняются.

    Успешный ответ помечает фрагмент атрибутом `autocopy` — свежеотрисованная
    ссылка копируется в буфер без второго клика.
    """
    student = get_owned_student(db, student_id, tutor_id)
    _require_supported(messenger)
    errors = start_invite(db, tutor_id, student.id, messenger)
    if not is_htmx(request):
        return RedirectResponse(f"/tutor/students/{student.id}", status_code=303)
    return _invites_response(
        request,
        db,
        tutor_id,
        student.id,
        errors,
        autocopy="" if errors else messenger,
    )


@router.post(
    "/tutor/students/{student_id}/messengers/{messenger}/unlink",
    response_class=HTMLResponse,
)
def unlink_student(
    request: Request,
    student_id: str,
    messenger: str,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Удаляет приглашение: привязка чата ученика и незавершённая ссылка."""
    student = get_owned_student(db, student_id, tutor_id)
    _require_supported(messenger)
    unbind_student(db, tutor_id, student.id, messenger)
    if not is_htmx(request):
        return RedirectResponse(f"/tutor/students/{student.id}", status_code=303)
    return _invites_response(request, db, tutor_id, student.id)


def _require_supported(messenger: str) -> None:
    """Неизвестный/неподдерживаемый мессенджер — маршрута нет (404)."""
    if messenger not in SUPPORTED:
        raise HTTPException(status_code=404)


def _confirm_pending(db: Session, tutor_id: str) -> list[str]:
    """Подтверждает все ожидающие коды; ошибки API — списком."""
    errors: list[str] = []
    for messenger in SUPPORTED:
        errors.extend(confirm_binding(db, tutor_id, messenger))
    return errors


def _invites_response(
    request: Request,
    db: Session,
    tutor_id: str,
    student_id: str,
    errors: list[str] | None = None,
    autocopy: str = "",
) -> HTMLResponse:
    """Ответ с обновлённым состоянием приглашений: htmx — фрагмент."""
    context = {
        "student_id": student_id,
        "invites_block": invites_context(db, tutor_id, student_id),
    }
    context["invites_block"]["errors"] = list(errors or [])
    context["invites_block"]["autocopy"] = autocopy
    return templates.TemplateResponse(
        request, "student/_invites_block.html", context
    )
