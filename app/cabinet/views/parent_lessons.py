"""Страница «Уроки» кабинета родителя: сетка недели всех детей (design D3).

Единая страница вместо вкладок ребёнка: уроки всех детей контакта в
одной сетке «только чтение». Доступ — сессия контакта
(`require_contact_id`): без неё запрос прерван редиректом на
`/parent/login`. Дети в архиве учится наравне с активными — фильтра по
статусу ученика нет (спека parent-cabinet, «Дети в архиве»).

`?start=` — любая дата недели, нормализуется к понедельнику; некорректное
значение не ошибка, а текущая неделя (тот же приём, что у календаря
репетитора и кабинета ученика). При заголовке `HX-Request` рендерится
только область `#parent-calendar` — листание недель не перезагружает
страницу целиком и не пересчитывает плашку ближайшего занятия.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.calendar.services.week import week_start
from app.cabinet.services.access import require_contact_id
from app.cabinet.services.children import children
from app.cabinet.services.parent_calendar import (
    display_zone_owner,
    nearest_lesson,
    parent_calendar_context,
)
from app.common.responses import is_htmx
from app.common.services.tutor_time import today_local
from app.database import get_db
from app.student.models.contact import Contact
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/parent/lessons", response_class=HTMLResponse)
def parent_lessons(
    request: Request,
    start: str | None = None,
    db: Session = Depends(get_db),
    contact_id: str = Depends(require_contact_id),
) -> HTMLResponse:
    """Неделя занятий всех детей; без сессии контакта — редирект на вход."""
    contact = db.get(Contact, contact_id)
    kids = children(db, contact_id)
    tutor = db.get(Tutor, contact.tutor_id)

    try:
        monday = week_start(start) if start else week_start(today_local(tutor))
    except ValueError:
        monday = week_start(today_local(tutor))

    context = {
        "contact": contact,
        "children": kids,
        "tutor": tutor,
        **parent_calendar_context(db, kids, tutor, monday),
    }
    if is_htmx(request):
        return templates.TemplateResponse(
            request, "cabinet/parent/_lessons_calendar.html", context
        )

    nearest, nearest_names = nearest_lesson(db, kids, tutor)
    context.update(
        nearest=nearest,
        # Имена детей ближайшего занятия («Аня» или «Аня, Боря»): плашка
        # отвечает не только на «когда», но и на «кого».
        nearest_names=nearest_names,
        # Плашка «Ближайшее занятие» показывает время в той же зоне, что и
        # сетка ниже: зона первого ребёнка (display_zone_owner).
        display_zone=display_zone_owner(kids, tutor),
    )
    return templates.TemplateResponse(request, "cabinet/parent/lessons.html", context)
