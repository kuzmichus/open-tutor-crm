"""CSV-выгрузка учеников: те же фильтры, что у вкладки, без пагинации.

Файл отдаётся как вложение с BOM (design D9): Excel с кириллицей открывает
его двойным кликом. Роут статический и объявлен рядом со страницей —
параметрических маршрутов в модуле нет, конфликтовать не с чем.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.database import get_db
from app.stats.services.access import LoginRequired, require_tutor_id
from app.stats.services.csv_export import students_csv_text
from app.stats.services.student_rows import apply_filters, collect_rows
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import as_utc, utcnow

router = APIRouter()


@router.get("/tutor/stats/students.csv")
def students_csv(
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
) -> Response:
    """CSV списка учеников вошедшего репетитора с учётом фильтров вкладки."""
    tutor = db.get(Tutor, tutor_id)
    if tutor is None:
        raise LoginRequired()

    rows = collect_rows(db, tutor, now=as_utc(utcnow()))
    filtered = apply_filters(
        rows,
        q=request.query_params.get("q", ""),
        status=request.query_params.get("status", ""),
        activity=request.query_params.get("activity", ""),
        no_future=request.query_params.get("no_future") == "1",
    )
    # BOM в начале файла: Excel распознаёт UTF-8 только по нему.
    content = "\ufeff" + students_csv_text(filtered, tutor)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="students.csv"'},
    )
