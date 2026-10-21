"""Тесты палитры и назначения цвета цели (1.1)."""

from app.common.colors import PALETTE, assign_color
from app.database import SessionLocal


def test_palette_has_16_distinct_hex_colors():
    """Палитра — 16 визуально разнесённых hex-цветов."""
    assert len(PALETTE) == 16
    assert len(set(PALETTE)) == 16
    for color in PALETTE:
        assert len(color) == 7 and color.startswith("#")


def test_assign_color_avoids_occupied(tutor_factory, student_factory, group_factory):
    """Цвет не совпадает с уже занятыми учениками и группами репетитора."""
    owner = tutor_factory(email="colors-owner@example.com")
    foreign = tutor_factory(email="colors-foreign@example.com")
    occupied = [PALETTE[0], PALETTE[1], PALETTE[2]]
    for index, color in enumerate(occupied):
        student_factory(tutor_id=owner, first_name=f"Занятый{index}", color=color)
    group_factory(tutor_id=owner, name="Занятая группа", color=PALETTE[3])
    # Цвета чужого репетитора не мешают: его объекты занимают остальные цвета.
    for index, color in enumerate(PALETTE[4:]):
        student_factory(tutor_id=foreign, first_name=f"Чужой{index}", color=color)

    with SessionLocal() as db:
        color = assign_color(db, owner)

    assert color in PALETTE
    assert color not in occupied
    assert color != PALETTE[3]


def test_assign_color_falls_back_to_full_palette(
    tutor_factory, student_factory, group_factory
):
    """При исчерпании палитры возвращается цвет из полной палитры."""
    owner = tutor_factory(email="colors-exhausted@example.com")
    for index, color in enumerate(PALETTE[:15]):
        student_factory(tutor_id=owner, first_name=f"Ученик{index}", color=color)
    group_factory(tutor_id=owner, name="Последняя группа", color=PALETTE[15])

    with SessionLocal() as db:
        color = assign_color(db, owner)

    assert color in PALETTE
