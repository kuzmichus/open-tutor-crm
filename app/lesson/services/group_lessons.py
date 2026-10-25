"""Занятия группы: выборка для вкладки «Занятия» модалки управления.

Панель показывает все уроки группы (`group_id`) — новые сверху (порядок
`starts_at` по убыванию, как в референсе вкладки). Изоляция не нужна
отдельным условием: маршрут панели проверяет владельца группы через
`get_owned_group`, дальше выбираются только уроки этой группы.

Индикатор ДЗ («ДЗ: есть/нет») берётся одним запросом: `LEFT JOIN
homework` — связь 1:1 (`lesson_id` UNIQUE), поэтому джойн не размножает
строки. Статус «Не задано» показывается как «нет»: запись ДЗ создаётся
лениво и без задания — для списка это то же «домашнего задания нет».

Фильтр-чипы (Все/Проведённые/Запланированные) — по статусу урока;
неизвестное значение query схлопывается в «Все», как периоды в
`lesson/services/lessons.py`.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.group.models.group import Group
from app.homework.models.homework import Homework
from app.lesson.models.lesson import LESSON_STATUSES, Lesson

# Значения фильтра-чипа статуса; пусто — «Все».
FILTER_STATUSES = ("", *LESSON_STATUSES)


def normalize_status(status: str) -> str:
    """Значение фильтра статуса из query: неизвестное схлопывается в «Все»."""
    return status if status in FILTER_STATUSES else ""


def list_group_lessons(
    db: Session, group: Group, *, status: str = ""
) -> list[dict]:
    """Строки списка занятий группы: урок и статус его ДЗ.

    Строка — `{"lesson": ..., "homework_status": ...}`; ДЗ без записи
    или со статусом «Не задано» приходит как `None` — шаблон покажет
    «ДЗ: нет». Свежие занятия сверху (`starts_at` по убыванию).
    """
    stmt = (
        select(Lesson, Homework.status)
        .join(Homework, Homework.lesson_id == Lesson.id, isouter=True)
        .where(Lesson.group_id == group.id)
        .order_by(Lesson.starts_at.desc(), Lesson.id)
    )
    status = normalize_status(status)
    if status:
        stmt = stmt.where(Lesson.status == status)
    return [
        {"lesson": lesson, "homework_status": homework_status}
        for lesson, homework_status in db.execute(stmt).all()
    ]
