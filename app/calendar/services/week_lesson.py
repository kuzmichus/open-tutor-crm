"""Урок недели с разрешённой целью: имя, id, цвет ученика или группы и цена."""

from dataclasses import dataclass

from app.lesson.models.lesson import Lesson


@dataclass(frozen=True)
class WeekLesson:
    """Строка недельной выборки: урок БД и данные его цели для карточки.

    Цель разрешается в `week_lessons` (JOIN по ученику и группе), потому что
    у `lessons` нет ни имени, ни цвета цели, а карточке календаря нужны все
    три значения сразу (design.md D1, D2).

    `price` — цена карточки: у индивидуального урока `lesson.price`, у
    группового — суммарная стоимость группы (сумма цен участников), а не
    цена одного места. Ноль означает «цена не определена»: карточка тогда
    не показывает блок цены вовсе.
    """

    lesson: Lesson
    target_name: str
    target_id: str
    target_color: str
    price: int = 0
