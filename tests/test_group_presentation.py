"""Отображение группы: цена, счётчик и дата вступления (2.5)."""

from datetime import date, datetime

import pytest

from app.group.services.members import MAX_MEMBERS
from app.group.services.presentation import (
    format_joined_at,
    format_price,
    members_label,
)


def test_format_price_uses_thin_space_and_ruble():
    """«1 200 ₽» — неразрывные пробелы, число и знак не разрываются."""
    assert format_price(1200) == "1\u00a0200\u00a0₽"
    assert format_price(1000) == "1\u00a0000\u00a0₽"
    assert format_price(900) == "900\u00a0₽"


def test_format_price_empty_means_no_price_block():
    """Пустая цена — пустая строка: шаблон не рисует блок цены."""
    assert format_price(None) == ""


def test_members_label_matches_reference():
    """Счётчик карточки: «N / 10 учеников»."""
    assert members_label(2) == "2 / 10 учеников"
    assert members_label(0) == "0 / 10 учеников"
    assert members_label(MAX_MEMBERS) == "10 / 10 учеников"


@pytest.mark.parametrize(
    "value",
    [datetime(2026, 10, 14, 9, 30), date(2026, 10, 14)],
)
def test_format_joined_at_uses_day_month_year(value):
    """Подпись «в группе с DD.MM.YYYY» — и для datetime, и для date."""
    assert format_joined_at(value) == "в группе с 14.10.2026"


def test_format_joined_at_empty_value_is_blank():
    assert format_joined_at(None) == ""


def test_helpers_are_registered_in_templates():
    """Хелперы доступны шаблонам без импорта во вьюхах."""
    from app.templating import templates

    assert templates.env.globals["group_price"](1200) == "1\u00a0200\u00a0₽"
    assert templates.env.globals["group_members_label"](3) == "3 / 10 учеников"
    assert (
        templates.env.globals["group_joined_label"](datetime(2026, 10, 14))
        == "в группе с 14.10.2026"
    )
