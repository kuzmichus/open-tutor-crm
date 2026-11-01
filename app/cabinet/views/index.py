"""Кабинет ученика: вкладка «Мои уроки» — недельный календарь.

Таблица ближайших занятий заменена сеткой недели (change
student-lessons-calendar): ученик видит уроки своей недели в том же
визуальном компоненте, что репетитор в `/tutor/calendar`, но только для
чтения — без переноса, открытия и редактирования занятий.

Карточка «Ближайшее занятие» осталась (замечание администратора к плану):
это короткий ответ на вопрос «когда у меня следующий урок», календарь
отвечает на другой — «как выглядит моя неделя».
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.cabinet.services.access import require_student_id
from app.cabinet.services.calendar import student_calendar_context
from app.cabinet.services.lessons import upcoming_lessons
from app.calendar.services.week import week_start
from app.common.responses import is_htmx
from app.common.services.tutor_time import today_local
from app.database import get_db
from app.student.models.student import Student
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()


@router.get("/student", response_class=HTMLResponse)
def cabinet_index(
    request: Request,
    start: str | None = None,
    db: Session = Depends(get_db),
    student_id: str = Depends(require_student_id),
) -> HTMLResponse:
    """«Мои уроки»: ближайшее занятие и неделя в режиме только чтения.

    Без сессии ученика запрос прерван редиректом на `/student/login`
    (зависимость `require_student_id`). Время выводится в зоне репетитора:
    зона самого ученика появится вместе с вкладкой «Профиль».

    `?start=` — любая дата недели, нормализуется к понедельнику;
    некорректное значение не ошибка, а текущая неделя (тот же приём, что
    у календаря репетитора). При заголовке `HX-Request` рендерится только
    область `#student-calendar` — листание недель не перезагружает
    страницу целиком и не трогает карточку ближайшего занятия.
    """
    student = db.get(Student, student_id)
    tutor = db.get(Tutor, student.tutor_id)

    try:
        monday = week_start(start) if start else week_start(today_local(tutor))
    except ValueError:
        monday = week_start(today_local(tutor))

    context = {
        "student": student,
        "tutor": tutor,
        **student_calendar_context(db, student, tutor, monday),
    }
    if is_htmx(request):
        return templates.TemplateResponse(
            request, "cabinet/_lessons_calendar.html", context
        )

    lessons = upcoming_lessons(db, student_id)
    context.update(
        lessons=lessons,
        # Ближайшее занятие — первый элемент списка (D6).
        nearest=lessons[0] if lessons else None,
    )
    return templates.TemplateResponse(request, "cabinet/lessons.html", context)
