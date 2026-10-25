"""Сохранение домашнего задания урока (форма вкладки «ДЗ»).

Отдельный эндпоинт для отдельной формы: сохранение ДЗ меняет только
запись ДЗ и никогда — поля урока (спека «Сохранение ДЗ отдельно от
урока»). Изоляция по репетитору — общая для уроков: `require_tutor_id`
(без сессии — редирект на вход) и `get_owned_lesson` (чужой или
несуществующий урок неразличимы: 404).

Ответы (design D3):

- и успех, и ошибка — фрагмент панели ДЗ (`hx-target` — сама форма,
  `hx-swap="outerHTML"`): успех — переотрендеренный с сохранёнными
  значениями без ошибок, ошибка — со списком ошибок и присланными
  значениями. Пустое тело при успехе невозможно: `outerHTML` по самому
  себя удалил бы панель из DOM. Панель — только своя фрагмент, поэтому
  несохранённые поля вкладки «Урок» остаются в своей форме. Триггера
  `lesson-saved` нет — список уроков ДЗ не отображает.

- успех дополнительно шлёт `HX-Trigger: homework-saved`: индикатор
  «ДЗ: есть/нет» во вкладке «Занятия» группы устарел бы, пока модалка
  урока открыта вторым слоем поверх модалки группы.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.homework.services.homework_context import homework_panel_context
from app.homework.services.homework_form import parse_homework_form
from app.homework.services.homework_writer import save_homework
from app.lesson.services.access import get_owned_lesson, require_tutor_id
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

LESSONS_URL = "/tutor/lessons"


@router.post(f"{LESSONS_URL}/{{lesson_id}}/homework", response_class=HTMLResponse)
async def save_homework_view(
    lesson_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Сохраняет ДЗ урока; чужой урок отвечает как несуществующий (404).

    Зона педагога берётся из его карточки: «Срок сдачи» — настенное время
    педагога, в БД уходит aware UTC (design D6).
    """
    lesson = get_owned_lesson(db, lesson_id, tutor_id)
    tutor = db.get(Tutor, tutor_id)
    form = await request.form()
    data, errors = parse_homework_form(form, tutor)

    if not errors:
        errors = save_homework(db, lesson, data)

    if errors:
        return templates.TemplateResponse(
            request,
            "homework/_panel.html",
            homework_panel_context(db, lesson, tutor=tutor, data=data, errors=errors),
        )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url=LESSONS_URL, status_code=303)
    # Успех: переотрендеренная панель с сохранёнными значениями (design
    # D3) и кнопкой в состоянии успеха (D8); outerHTML подменяет панель
    # на свежую, поля остаются видимыми. `homework-saved` — для списка
    # занятий группы: индикатор ДЗ там мог устареть (см. докстринг).
    return templates.TemplateResponse(
        request,
        "homework/_panel.html",
        homework_panel_context(db, lesson, tutor=tutor, saved=True),
        headers={"HX-Trigger": "homework-saved"},
    )
