"""Сохранение ответа ученика на ДЗ (change cabinet-homework, решение D2).

Ответ создаётся при первой отправке и обновляется при повторных — UNIQUE
на `homework_id` гарантирует ровно один ответ на ДЗ. Ссылки заменяются
целиком (delete + insert): правка списка по одной строке не нужна,
порядок восстанавливается по `position`. Отправка переводит ДЗ в статус
«Сдано» — иначе этот статус не наступал бы никогда (репетитор ставит
остальные статусы вручную). Статус «Проверено» блокируется вьюхой, а не
здесь: writer отвечает за запись, вьюха — за то, кому можно.

Сервис не знает про FastAPI: на вход — словарь очищенных значений
`parse_answer_form`, на выход — список ошибок (пустой при успехе).
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.homework.models.answer import HomeworkAnswer
from app.homework.models.answer_link import HomeworkAnswerLink
from app.homework.models.homework import Homework
from app.homework.services.answer_form import validate_answer_data
from app.tutor.services.clock import utcnow


def get_answer(db: Session, homework_id: str) -> HomeworkAnswer | None:
    """Ответ на ДЗ или None (ученик ещё не отправлял ответ)."""
    return db.scalars(
        select(HomeworkAnswer).where(HomeworkAnswer.homework_id == homework_id)
    ).one_or_none()


def save_answer(db: Session, homework: Homework, data: dict) -> list[str]:
    """Создаёт (лениво) или обновляет ответ; при ошибке — rollback.

    Явный `flush` перед вставкой ссылок обязателен: `SessionLocal` создан
    с `autoflush=False`, и у нового ответа ещё нет `id` для FK ссылок
    (ловушка change'а group-lesson-attendance).
    """
    errors = validate_answer_data(data)
    if errors:
        db.rollback()
        return errors

    text = (data.get("text") or "").strip() or None
    links = data.get("links") or []

    answer = get_answer(db, homework.id)
    if answer is None:
        answer = HomeworkAnswer(
            homework_id=homework.id,
            text=text,
            submitted_at=utcnow(),
        )
        db.add(answer)
    else:
        answer.text = text
        answer.submitted_at = utcnow()
    db.flush()

    db.execute(
        delete(HomeworkAnswerLink).where(HomeworkAnswerLink.answer_id == answer.id)
    )
    for position, url in enumerate(links):
        db.add(
            HomeworkAnswerLink(
                answer_id=answer.id,
                url=url,
                position=position,
            )
        )

    homework.status = "submitted"
    db.commit()
    return []
