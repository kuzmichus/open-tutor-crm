"""Страница «Домашние задания» кабинета родителя: вкладки по детям (design D4/D5).

Единая страница вместо вкладок ребёнка: активный ребёнок — параметр
адреса `?child=<id>`, по умолчанию первый из `children()` (в порядке
навигации). Чужой или несуществующий ученик неразличим с несуществующей
страницей — 404 (`get_child`, один SELECT): изоляция по контакту
сохраняется и на общих страницах.

Только просмотр: роутов записи у кабинета родителя нет. Контекст карточек
строит `cabinet/services/child_homework.py` — заметки педагога в выборке
нет в принципе, скрытие гарантируется составом запроса (D7).

Плашка срока считается по всем детям (`homework_deadline_notice`) и
рендерится над вкладками: её закрытие — клиентское, по составу заданий
и дню.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.cabinet.services.access import require_contact_id
from app.cabinet.services.child_homework import child_homework
from app.cabinet.services.children import children, get_child
from app.cabinet.services.homework_deadline import homework_deadline_notice
from app.database import get_db
from app.student.models.contact import Contact
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/parent/homework", response_class=HTMLResponse)
def parent_homework(
    request: Request,
    child: str | None = None,
    db: Session = Depends(get_db),
    contact_id: str = Depends(require_contact_id),
) -> HTMLResponse:
    """Задания активного ребёнка; чужой `child` — 404, без параметра — первый."""
    contact = db.get(Contact, contact_id)
    kids = children(db, contact_id)
    tutor = db.get(Tutor, contact.tutor_id)

    # Активная вкладка — параметр адреса; дефолт — первый ребёнок в
    # порядке навигации (design D4). Проверка привязки — тем же
    # `get_child`: 404 у чужого и несуществующего неразличим.
    active = get_child(db, child, contact_id) if child else (kids[0] if kids else None)

    deadline = homework_deadline_notice(db, kids, tutor)
    return templates.TemplateResponse(
        request,
        "cabinet/parent/homework.html",
        {
            "contact": contact,
            "children": kids,
            "tutor": tutor,
            # Тот же ключ, что ждёт `parent/_child_tabs.html` и страница
            # «Финансы»: активная вкладка — `active_child`.
            "active_child": active,
            "cards": child_homework(db, active.id) if active else [],
            "deadline": deadline,
            "deadline_key": deadline.close_key() if deadline else "",
        },
    )
