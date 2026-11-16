"""Плашка срока домашних заданий кабинета родителя (design D5).

Одна общая плашка для всех детей: считается при рендере `/parent/homework`
по видимым заданиям всех детей — статусы «Задано» и «Не выполнено»,
у которых срок сдачи истекает сегодня или уже истёк. День сравнения —
«сегодня» в зоне репетитора (`today_local`): сроки вводятся и показываются
в настенном времени педагога (спека tutor-timezone), родителю важно
то же «сегодня», что на вкладке ДЗ.

«Сдано» и «Проверено» в подсчёт не попадают: работа сдана — горящий срок
уже не сигнал для родителя. Задания без срока (`due_at IS NULL`) тоже:
сравнивать не с чем.

Состав предупреждения (`homework_ids` + `day`) уходит в ключ клиентского
закрытия: закрытая сегодня плашка с тем же составом не прячет завтрашнюю —
при смене дня или состава заданий ключ другой и плашка возвращается
(design D5, по аналогии с close-keys репетиторских плашек).

Сервис не знает про FastAPI: на вход — сессия, дети контакта и карточка
репетитора; на выход — данные плашки или `None`.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import today_local, to_local
from app.group.models.group_member import GroupMember
from app.homework.models.homework import Homework
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student

# Статусы заданий с горящим сроком: «Задано» и «Не выполнено» —
# закрытые значения `HOMEWORK_STATUSES` (правило AGENTS.md 10).
URGENT_STATUSES = ("assigned", "not_done")


@dataclass(frozen=True)
class HomeworkDeadlineNotice:
    """Состав плашки срока: какие задания горят и на какой день."""

    day: date
    homework_ids: tuple[str, ...]

    @property
    def count(self) -> int:
        """Число заданий с горящим сроком — для подписи плашки."""
        return len(self.homework_ids)

    def close_key(self) -> str:
        """Ключ клиентского закрытия: день и состав заданий.

        День обязателен в ключе: закрытое сегодня напоминание с тем же
        составом заданий иначе молча скрыло бы завтрашнее.
        """
        return (
            "hw-deadline:" + self.day.isoformat() + ":" + "|".join(self.homework_ids)
        )


def homework_deadline_notice(
    db: Session,
    children: list[Student],
    tutor,
    *,
    day: date | None = None,
) -> HomeworkDeadlineNotice | None:
    """Задания детей, у которых срок истекает сегодня или уже истёк.

    Детей нет или горящих сроков нет — `None`: контейнер плашки не
    рендерится вовсе. Выборка — один SELECT по урокам всех детей
    (индивидуальные и групповые через `GroupMember`), день срока
    сравнивается в Python после перевода в зону педагога: сравниваются
    календарные дни, а не моменты времени.
    """
    child_ids = [child.id for child in children]
    if not child_ids:
        return None

    day = day or today_local(tutor)
    rows = db.execute(
        select(Homework.id, Homework.due_at)
        .join(Lesson, Lesson.id == Homework.lesson_id)
        .outerjoin(GroupMember, GroupMember.group_id == Lesson.group_id)
        .where(
            or_(
                Lesson.student_id.in_(child_ids),
                GroupMember.student_id.in_(child_ids),
            ),
            Homework.status.in_(URGENT_STATUSES),
            Homework.due_at.is_not(None),
        )
    ).all()

    urgent = [
        homework_id
        for homework_id, due_at in rows
        if to_local(due_at, tutor).date() <= day
    ]
    if not urgent:
        return None
    return HomeworkDeadlineNotice(day=day, homework_ids=tuple(sorted(urgent)))
