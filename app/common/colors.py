"""Палитра цветов целей и назначение цвета при создании (решение D3).

Цвет закрепляется за учеником или группой при создании и далее не меняется.
Одинаковых цветов у объектов одного репетитора стараемся не допускать:
`assign_color` выбирает случайный цвет из тех, что ещё не заняты
учениками и группами этого репетитора.
"""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.group.models.group import Group
from app.student.models.student import Student

# 16 цветов, равномерно распределённых по окружности HSL: шаг 22.5° при
# фиксированных насыщенности 70% и светлоте 55%. Соседние цвета визуально
# не сливаются, а 16 оттенков покрывают круг с запасом для типичного
# числа учеников и групп одного репетитора.
# Цвет карточки, если у цели он не задан: строки до миграции `add target
# color` могли остаться с NULL (design.md D3, `target_color`).
DEFAULT_TARGET_COLOR = "#3b82f6"

PALETTE: tuple[str, ...] = (
    "#dd3c3c",  # 0°
    "#dd783c",  # 22.5°
    "#ddb43c",  # 45°
    "#c8dd3c",  # 67.5°
    "#8cdd3c",  # 90°
    "#50dd3c",  # 112.5°
    "#3cdd64",  # 135°
    "#3cdda0",  # 157.5°
    "#3cdddd",  # 180°
    "#3ca0dd",  # 202.5°
    "#3c64dd",  # 225°
    "#503cdd",  # 247.5°
    "#8c3cdd",  # 270°
    "#c83cdd",  # 292.5°
    "#dd3cb4",  # 315°
    "#dd3c78",  # 337.5°
)


def _occupied_colors(db: Session, tutor_id: str) -> set[str]:
    """Цвета, уже занятые учениками и группами этого репетитора."""
    student_colors = db.scalars(
        select(Student.color).where(
            Student.tutor_id == tutor_id,
            Student.color.is_not(None),
        )
    ).all()
    group_colors = db.scalars(
        select(Group.color).where(
            Group.tutor_id == tutor_id,
            Group.color.is_not(None),
        )
    ).all()
    return set(student_colors) | set(group_colors)


def assign_color(db: Session, tutor_id: str) -> str:
    """Случайный свободный цвет из палитры для объектов этого репетитора.

    Если палитра исчерпана (у репетитора больше 16 объектов), возвращается
    случайный цвет из полной палитры: требование «не путаться» для такого
    объёма уже не выполнимо без расширения палитры.
    """
    occupied = _occupied_colors(db, tutor_id)
    free = [color for color in PALETTE if color not in occupied]
    return secrets.choice(free if free else list(PALETTE))
