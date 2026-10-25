"""Страница статистики: три вкладки одним GET-роутом.

Вкладка — query-параметр (`tab`), а не htmx-партиал: страницы только читают
данные, и обычные ссылки/GET-формы работают без JS (design D1). Неизвестное
значение `tab` — «Обзор»: мусор в query не должен ломать страницу.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.stats.services.access import LoginRequired, require_tutor_id
from app.stats.services.new_and_trials import new_students_stats, trial_conversion
from app.stats.services.overview import overview_context
from app.stats.services.periods import parse_period
from app.stats.services.student_rows import (
    apply_filters,
    collect_rows,
    paginate,
)
from app.student.models.student import Student
from app.templating import templates
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import as_utc, utcnow

router = APIRouter()

# Вкладки страницы; порядок — порядок чипов в шапке.
TABS = ("overview", "students", "new")


def _students_total(db: Session, tutor_id: str) -> int:
    """Всего учеников репетитора — для счётчика в чипе вкладки."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(Student)
            .where(Student.tutor_id == tutor_id)
        )
        or 0
    )


def _students_context(db: Session, request: Request, tutor, *, now) -> dict:
    """Контекст вкладки «Ученики»: строки, фильтры, пагинация, ссылка на CSV."""
    rows = collect_rows(db, tutor, now=now)
    filters = {
        "q": request.query_params.get("q", ""),
        "status": request.query_params.get("status", ""),
        "activity": request.query_params.get("activity", ""),
        "no_future": request.query_params.get("no_future") == "1",
    }
    filtered = apply_filters(rows, **filters)
    page_rows, paging = paginate(filtered, request.query_params.get("page", ""))

    # Ссылки пагинации сохраняют фильтры; включить/выключить страницу можно
    # только если соседняя существует — иначе мёртвых кнопок нет.
    base_url = request.url.include_query_params()
    prev_url = (
        str(base_url.include_query_params(page=paging["page"] - 1))
        if paging["page"] > 1
        else None
    )
    next_url = (
        str(base_url.include_query_params(page=paging["page"] + 1))
        if paging["page"] < paging["pages"]
        else None
    )
    csv_url = str(
        request.url.replace(path="/tutor/stats/students.csv")
    )

    return {
        "rows": page_rows,
        "filters": filters,
        "paging": {**paging, "prev_url": prev_url, "next_url": next_url},
        "csv_url": csv_url,
        "students_total": len(rows),
    }


@router.get("/tutor/stats", response_class=HTMLResponse)
def stats_index(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> HTMLResponse:
    """Статистика вошедшего репетитора; без сессии — редирект на вход."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        # Сессия указывает на удалённого репетитора — считаем входа нет.
        raise LoginRequired()

    now = as_utc(utcnow())
    tab = request.query_params.get("tab", "overview")
    if tab not in TABS:
        tab = "overview"

    context = {
        "active_page": "stats",
        "user_name": tutor.name,
        "user_role": "Владелец",
        "tutor": tutor,
        "tab": tab,
    }

    if tab == "students":
        context.update(_students_context(db, request, tutor, now=now))
    elif tab == "new":
        period = parse_period(request.query_params, tutor)
        context.update(
            period=period,
            new_stats=new_students_stats(
                db, tutor, start=period["start"], end=period["end"]
            ),
            trials=trial_conversion(
                db, tutor, start=period["start"], end=period["end"], now=now
            ),
            students_total=_students_total(db, tutor.id),
        )
    else:
        rows = collect_rows(db, tutor, now=now)
        context.update(
            overview=overview_context(
                db,
                tutor,
                rows=rows,
                now=now,
                forecast=request.query_params.get("forecast") == "1",
            ),
            students_total=len(rows),
        )

    return templates.TemplateResponse(request, "stats/index.html", context)
