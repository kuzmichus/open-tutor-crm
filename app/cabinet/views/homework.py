"""Вкладка «Домашние задания» кабинета ученика (change cabinet-homework).

Страница и отправка ответа требуют сессию ученика (`require_student_id`):
id ученика только из cookie кабинета. Владение ДЗ проверяет
`get_student_homework` — чужое и несуществующее неразличимы, 404.

Ответы (design D5, по образцу панели ДЗ репетитора):

- и успех, и ошибка — фрагмент той же карточки (`hx-target` — сама
  карточка, `hx-swap="outerHTML"`): ошибка — со списком ошибок и
  введёнными значениями, успех — с сохранённым ответом, чипом «Сдано» и
  пометкой об отправке. Карточка рендерится раскрытой (`open`): отправка
  не должна схлопывать её и прятать результат.

- без `HX-Request` POST отвечает 303-редиректом на страницу — форма
  работает и с отключённым JS (страница после редиректа показывает
  сохранённое состояние с сервера).

ДЗ в статусе «Проверено» закрыто для отправки: ответ репетитора
рассмотрен, перезапись уничтожила бы предмет проверки (design D2) —
фрагмент возвращается с сообщением, ничего не меняя.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.cabinet.services.access import get_student_homework, require_student_id
from app.cabinet.services.homework import homework_card, student_homework
from app.common.responses import is_htmx
from app.database import get_db
from app.homework.services.answer_form import parse_answer_form
from app.homework.services.answer_writer import save_answer
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

HOMEWORK_URL = "/student/homework"

CHECKED_MESSAGE = "Задание уже проверено репетитором — ответ изменить нельзя."


def _card_context(
    card,
    tutor,
    *,
    data: dict | None = None,
    errors: list[str] | None = None,
    saved: bool = False,
) -> dict:
    """Контекст фрагмента карточки: значения ответа и флаги состояния.

    Фрагмент отвечает только на POST отправки — карточка всегда
    раскрытая: отправка не должна схлопывать её и прятать результат
    (design D4).
    """
    return {
        "item": card,
        "tutor": tutor,
        "card_open": True,
        "answer_data": data,
        "answer_errors": errors or [],
        "answer_saved": saved,
    }


@router.get(HOMEWORK_URL, response_class=HTMLResponse)
def homework_page(
    request: Request,
    db: Session = Depends(get_db),
    student_id: str = Depends(require_student_id),
) -> HTMLResponse:
    """Список ДЗ ученика: карточки, раскрытые по клику (D4)."""
    student = db.get(Student, student_id)
    tutor = db.get(Tutor, student.tutor_id)
    return templates.TemplateResponse(
        request,
        "cabinet/homework.html",
        {
            "student": student,
            "tutor": tutor,
            "cards": student_homework(db, student_id),
        },
    )


@router.post(f"{HOMEWORK_URL}/{{homework_id}}/answer", response_class=HTMLResponse)
async def submit_answer(
    homework_id: str,
    request: Request,
    db: Session = Depends(get_db),
    student_id: str = Depends(require_student_id),
):
    """Сохраняет ответ ученика; чужое ДЗ отвечает как несуществующее (404)."""
    homework = get_student_homework(db, homework_id, student_id)
    lesson = db.get(Lesson, homework.lesson_id)
    student = db.get(Student, student_id)
    tutor = db.get(Tutor, student.tutor_id)

    data: dict | None = None
    errors: list[str] = []
    if homework.status == "checked":
        errors = [CHECKED_MESSAGE]
    else:
        form = await request.form()
        data, errors = parse_answer_form(form)
        if not errors:
            errors = save_answer(db, homework, data)

    card = homework_card(db, homework, lesson)
    if errors:
        return templates.TemplateResponse(
            request,
            "cabinet/_homework_card.html",
            _card_context(card, tutor, data=data, errors=errors),
        )

    if not is_htmx(request):
        return RedirectResponse(url=HOMEWORK_URL, status_code=303)
    return templates.TemplateResponse(
        request,
        "cabinet/_homework_card.html",
        _card_context(card, tutor, saved=True),
    )
