"""Удаление файла домашнего задания (кнопка у файла в панели ДЗ).

Файл удаляется целиком — и объект в хранилище, и строка метаданных: файл
принадлежит одному репетитору и живёт ради ДЗ, «отвязать, но оставить»
означало бы копить объекты, к которым нет ни одного пути в интерфейсе
(спека file-storage, «Удаление файла убирает и объект, и метаданные»).

Доступ — по владению уроком (`get_owned_lesson`): чужой урок и чужой файл
неотличимы от несуществующих (404). Файл, не привязанный к этому ДЗ, тоже
404: иначе через id чужого файла можно было бы удалить его у другого урока.

Ответ — перерендеренная панель ДЗ (`hx-target="#homework-panel"`): удаление
не должно закрывать модалку и терять несохранённые поля вкладки «ДЗ». Без
`HX-Request` — 303 на список уроков, как у сохранения панели.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.responses import is_htmx
from app.database import get_db
from app.files.models.homework_file import HomeworkFile
from app.files.models.stored_file import StoredFile
from app.files.services.removal import delete_file
from app.homework.services.homework_context import homework_panel_context
from app.homework.services.homework_writer import get_homework
from app.lesson.services.access import get_owned_lesson, require_tutor_id
from app.templating import templates
from app.tutor.models.tutor import Tutor

router = APIRouter()

LESSONS_URL = "/tutor/lessons"

def _owned_homework_file(
    db: Session, homework_id: str, file_id: str, tutor_id: str
) -> StoredFile:
    """Файл, привязанный к этому ДЗ и принадлежащий репетитору, либо 404."""
    file = db.scalars(
        select(StoredFile)
        .join(HomeworkFile, HomeworkFile.file_id == StoredFile.id)
        .where(
            StoredFile.id == file_id,
            StoredFile.tutor_id == tutor_id,
            HomeworkFile.homework_id == homework_id,
        )
    ).one_or_none()
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return file

@router.post(
    f"{LESSONS_URL}/{{lesson_id}}/homework/files/{{file_id}}/delete",
    response_class=HTMLResponse,
)
def delete_homework_file_view(
    lesson_id: str,
    file_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tutor_id: str = Depends(require_tutor_id),
):
    """Удаляет файл ДЗ и возвращает панель без него; чужой — 404."""
    lesson = get_owned_lesson(db, lesson_id, tutor_id)
    homework = get_homework(db, lesson.id)
    if homework is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    file = _owned_homework_file(db, homework.id, file_id, tutor_id)
    delete_file(db, file)
    db.commit()

    if not is_htmx(request):
        return RedirectResponse(url=LESSONS_URL, status_code=303)
    return templates.TemplateResponse(
        request,
        "homework/_panel.html",
        homework_panel_context(
            db, lesson, tutor=db.get(Tutor, tutor_id)
        ),
        headers={"HX-Trigger": "homework-saved"},
    )
