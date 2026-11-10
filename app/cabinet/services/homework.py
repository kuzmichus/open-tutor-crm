"""«Домашние задания» кабинета: список ДЗ уроков ученика с ответами.

Те же два SELECT, что в `lessons.py` (индивидуальные + групповые через
`GroupMember`), но без ограничения по времени: ДЗ даётся на прошедшем
уроке к следующему и живёт после урока (D3). Показываются записи со
статусом ≠ `not_assigned` — «Не задано» это пустая запись, для ученика
домашнего задания нет. Сортировка по дате урока по убыванию: свежее
задание сверху.

Ответы и ссылки подгружаются двумя массовыми SELECT с `IN` и
группируются в Python — без N+1 на карточку (правило AGENTS.md 9).
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.files.services.presentation import file_size_label
from app.files.services.removal import files_of_homeworks
from app.group.models.group_member import GroupMember
from app.homework.models.answer import HomeworkAnswer
from app.homework.models.answer_link import HomeworkAnswerLink
from app.homework.models.homework import Homework
from app.homework.services.by_lesson import HIDDEN_STATUSES
from app.lesson.models.lesson import Lesson

def _file_rows(files) -> list[dict]:
    """Строки списка файлов: id, имя, подпись размера, адрес скачивания."""
    return [
        {
            "id": file.id,
            "name": file.original_name,
            "size_label": file_size_label(file.size),
            "url": f"/files/{file.id}",
        }
        for file in files
    ]


@dataclass(frozen=True)
class HomeworkCard:
    """Строка списка «Домашних заданий»: ДЗ, его урок, ответ и ссылки.

    `answer` — None, пока ученик не отправлял ответ; `links` — адреса в
    порядке списка (по `position`). `files` — прикреплённые к заданию файлы
    (спека homework-management): строки {id, name, size_label, url},
    собранные здесь, чтобы шаблон не ходил в БД и не считал размеры.
    """

    homework: Homework
    lesson: Lesson
    answer: HomeworkAnswer | None
    links: list[str] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)


def _visible_rows(db: Session, student_id: str) -> list[tuple[Homework, Lesson]]:
    """Пары (ДЗ, урок) ученика: индивидуальные и групповые уроки."""
    filters = (
        Homework.status.not_in(HIDDEN_STATUSES),
    )
    rows = list(
        db.execute(
            select(Homework, Lesson)
            .join(Lesson, Homework.lesson_id == Lesson.id)
            .where(Lesson.student_id == student_id, *filters)
        ).all()
    )
    rows += list(
        db.execute(
            select(Homework, Lesson)
            .join(Lesson, Homework.lesson_id == Lesson.id)
            .join(GroupMember, GroupMember.group_id == Lesson.group_id)
            .where(GroupMember.student_id == student_id, *filters)
        ).all()
    )
    return rows


def _answers_map(
    db: Session, homework_ids: list[str]
) -> dict[str, HomeworkAnswer]:
    """Ответы по id ДЗ: один SELECT на весь список."""
    if not homework_ids:
        return {}
    rows = db.scalars(
        select(HomeworkAnswer).where(HomeworkAnswer.homework_id.in_(homework_ids))
    ).all()
    return {answer.homework_id: answer for answer in rows}


def _links_map(db: Session, answer_ids: list[str]) -> dict[str, list[str]]:
    """Ссылки по id ответа, в порядке `position`: один SELECT на весь список."""
    if not answer_ids:
        return {}
    rows = db.scalars(
        select(HomeworkAnswerLink)
        .where(HomeworkAnswerLink.answer_id.in_(answer_ids))
        .order_by(HomeworkAnswerLink.position, HomeworkAnswerLink.id)
    ).all()
    grouped: dict[str, list[str]] = {}
    for link in rows:
        grouped.setdefault(link.answer_id, []).append(link.url)
    return grouped


def _assemble(
    db: Session,
    rows: list[tuple[Homework, Lesson]],
) -> list[HomeworkCard]:
    """Карточки списка: добирает ответы, ссылки и файлы массовыми SELECT."""
    answers = _answers_map(db, [homework.id for homework, _ in rows])
    links = _links_map(db, [answer.id for answer in answers.values()])
    files = files_of_homeworks(db, [homework.id for homework, _ in rows])
    cards = []
    for homework, lesson in rows:
        answer = answers.get(homework.id)
        cards.append(
            HomeworkCard(
                homework=homework,
                lesson=lesson,
                answer=answer,
                links=links.get(answer.id, []) if answer else [],
                files=_file_rows(files.get(homework.id, [])),
            )
        )
    # Свежее задание сверху; вторичный ключ держит порядок уроков с одним
    # временем (у «Моих уроков» сортировка прямая — там ближайшее первым).
    cards.sort(key=lambda card: (card.lesson.starts_at, card.homework.id), reverse=True)
    return cards


def student_homework(db: Session, student_id: str) -> list[HomeworkCard]:
    """Список «Домашних заданий» ученика — карточки для страницы кабинета."""
    return _assemble(db, _visible_rows(db, student_id))


def homework_card(
    db: Session, homework: Homework, lesson: Lesson
) -> HomeworkCard:
    """Карточка одного ДЗ — контекст фрагмента после отправки ответа."""
    return _assemble(db, [(homework, lesson)])[0]
