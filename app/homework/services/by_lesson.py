"""Домашние задания по урокам: массовая карта статусов и просрочки.

Одна запись ДЗ на урок (`homework.lesson_id` UNIQUE), поэтому состояние —
это карта «id урока → `LessonHomework`». Карта нужна и календарю
репетитора, и кабинету ученика: оба показывают значок ДЗ в карточке урока
и обязаны догружать данные одним SELECT на всю неделю (правило AGENTS.md 9).

Просрочка — вычисленное состояние, а не колонка БД: срок сдачи прошёл, а
работа всё ещё «Задано». Отдельного статуса «Просрочено» в закрытом списке
нет, и заводить его нельзя — статус ставит педагог вручную, а просрочка
зависит от текущего момента.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.homework.models.homework import Homework
from app.tutor.services.clock import as_utc

# Статус «Не задано» — запись без домашнего задания: значок не показываем
# и в списках кабинета её нет. Один источник правила для всех поверхностей.
HIDDEN_STATUSES = ("not_assigned",)

# Статусы, при которых просроченный срок ещё «висит» на ученике: работа
# не сдана. «Сдано» и «Проверено» — уже не просрочка, «Не выполнено» —
# красное по самому статусу, отдельная просрочка ему не нужна.
OPEN_STATUSES = ("assigned",)


@dataclass(frozen=True)
class LessonHomework:
    """ДЗ урока для значка: статус, срок сдачи и учёт дедлайна."""

    status: str
    due_at: datetime | None = None
    deadline_enabled: bool = True

    def is_overdue(self, now: datetime) -> bool:
        """Срок сдачи прошёл, а работа всё ещё не сдана.

        Флаг «Учитывать дедлайн» выключает автоматику: педагог снял учёт
        срока — просрочку не подсвечиваем (подпись флага в панели ДЗ:
        «напоминания и автоматический статус»). Сравнение — aware UTC:
        SQLite теряет tzinfo, поэтому `due_at` нормализуется `as_utc`.
        """
        if not self.deadline_enabled or self.status not in OPEN_STATUSES:
            return False
        if self.due_at is None:
            return False
        return as_utc(self.due_at) < now


def homework_states(db: Session, lesson_ids: list[str]) -> dict[str, LessonHomework]:
    """Состояние ДЗ по id уроков: один SELECT на всю неделю.

    «Не задано» (`HIDDEN_STATUSES`) не попадает в карту: пустая запись —
    это отсутствие домашнего задания, значка в карточке быть не должно.
    """
    if not lesson_ids:
        return {}
    rows = db.execute(
        select(
            Homework.lesson_id,
            Homework.status,
            Homework.due_at,
            Homework.deadline_enabled,
        ).where(
            Homework.lesson_id.in_(lesson_ids),
            Homework.status.not_in(HIDDEN_STATUSES),
        )
    ).all()
    return {
        lesson_id: LessonHomework(
            status=status,
            due_at=due_at,
            deadline_enabled=bool(deadline_enabled),
        )
        for lesson_id, status, due_at, deadline_enabled in rows
    }


def homework_by_lesson(db: Session, lesson_ids: list[str]) -> dict[str, str]:
    """Статусы ДЗ по id уроков: тот же SELECT, что у `homework_states`.

    Узкая карта нужна кабинету, которому просрочка не важна: там значок
    красится только по статусу.
    """
    return {
        lesson_id: state.status
        for lesson_id, state in homework_states(db, lesson_ids).items()
    }
