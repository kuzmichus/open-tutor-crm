"""Хелпер перевода времени: зона педагога, конвертация UTC, границы.

Тесты не зависят от настройки машины: системная зона подменяется
фикстурой `system_zone` (monkeypatch `system_zone_name`), реальные зоны
IANA берутся из локального tzdata — сеть не нужна.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.common.services import tutor_time
from app.common.services.tutor_time import (
    local_day_bounds,
    local_week_bounds,
    now_local,
    now_utc,
    to_local,
    to_utc,
    today_local,
    tutor_zone,
)

# UTC+04 — та же зона, что в рабочей базе проекта.
TUTOR_UTC_PLUS4 = SimpleNamespace(timezone="Europe/Ulyanovsk")
# Зона с переводом часов: последнее воскресенье марта 2026 — 29.03.
TUTOR_BERLIN = SimpleNamespace(timezone="Europe/Berlin")


@pytest.fixture()
def system_zone(monkeypatch):
    """Подменяет имя системной зоны: тесты детерминированы на любой машине."""

    def _set(name: str | None = "Europe/Moscow"):
        monkeypatch.setattr(tutor_time, "system_zone_name", lambda: name)

    _set()
    return _set


def test_to_utc_interprets_wall_time_in_tutor_zone(system_zone):
    """10:00 местного при UTC+04 — это 06:00 UTC."""
    system_zone("Europe/Ulyanovsk")
    result = to_utc(datetime(2026, 10, 22, 10, 0), TUTOR_UTC_PLUS4)
    assert result == datetime(2026, 10, 22, 6, 0, tzinfo=UTC)


def test_to_local_returns_original_wall_time(system_zone):
    """Обратный перевод возвращает исходные 10:00 в зоне педагога."""
    utc_value = to_utc(datetime(2026, 10, 22, 10, 0), TUTOR_UTC_PLUS4)
    local = to_local(utc_value, TUTOR_UTC_PLUS4)
    assert local.strftime("%Y-%m-%dT%H:%M") == "2026-10-22T10:00"
    assert local.utcoffset() == timedelta(hours=4)


def test_to_local_normalizes_naive_read_from_db(system_zone):
    """Значение из SQLite (наивное) трактуется как UTC, а не как местное."""
    system_zone("Europe/Ulyanovsk")
    local = to_local(datetime(2026, 10, 22, 6, 0), TUTOR_UTC_PLUS4)
    assert local.strftime("%Y-%m-%dT%H:%M") == "2026-10-22T10:00"


def test_local_week_bounds_in_utc_plus4(system_zone):
    """Неделя с понедельника 12.10 при UTC+04 начинается 11.10 20:00 UTC."""
    system_zone("Europe/Ulyanovsk")
    start, end = local_week_bounds(date(2026, 10, 12), TUTOR_UTC_PLUS4)
    assert start == datetime(2026, 10, 11, 20, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 18, 20, 0, tzinfo=UTC)


def test_local_day_bounds_in_utc_plus4(system_zone):
    """Сутки 22.10 при UTC+04: [21.10 20:00, 22.10 20:00) UTC."""
    system_zone("Europe/Ulyanovsk")
    start, end = local_day_bounds(date(2026, 10, 22), TUTOR_UTC_PLUS4)
    assert start == datetime(2026, 10, 21, 20, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 22, 20, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "timezone",
    [None, "", "Europe/Atlantis"],
    ids=["empty-string-none", "empty-string", "unknown-zone"],
)
def test_bad_tutor_timezone_falls_back_to_system_zone(system_zone, timezone):
    """Пустое или неизвестное имя зоны — системная зона, без исключения.

    Карточка репетитора может прийти с пустым полем (форма его не требует)
    или с именем зоны, которой нет в tzdata: страница не должна падать.
    """
    system_zone("Europe/Moscow")

    assert tutor_zone(SimpleNamespace(timezone=timezone)) == ZoneInfo("Europe/Moscow")


def test_unavailable_system_zone_falls_back_to_utc(system_zone):
    """Системная зона недоступна — UTC; страница не падает."""
    system_zone("Europe/Atlantis")
    no_tz_tutor = SimpleNamespace(timezone=None)
    assert tutor_zone(no_tz_tutor) == UTC
    assert to_utc(datetime(2026, 10, 22, 10, 0), no_tz_tutor) == datetime(
        2026, 10, 22, 10, 0, tzinfo=UTC
    )


def test_now_helpers_use_tutor_zone(system_zone):
    """`now_utc` в UTC, `now_local`/`today_local` — в зоне педагога."""
    system_zone("Europe/Moscow")
    utc_value = now_utc()
    local = now_local(TUTOR_UTC_PLUS4)
    assert utc_value.tzinfo == UTC
    assert local.utcoffset() == timedelta(hours=4)
    # `now_utc` и `now_local` зовут часы дважды — сверяем не точное равенство,
    # а совпадение момента с допуском на микросекунды.
    assert abs((local.astimezone(UTC) - utc_value).total_seconds()) < 1
    assert today_local(TUTOR_UTC_PLUS4) == local.date()


def test_dst_keeps_wall_time_and_shifts_utc(system_zone):
    """Перевод часов в Europe/Berlin: настенное 10:00 сохраняется, UTC смещается."""
    system_zone("Europe/Moscow")
    before = to_utc(datetime(2026, 3, 28, 10, 0), TUTOR_BERLIN)
    after = to_utc(datetime(2026, 3, 30, 10, 0), TUTOR_BERLIN)
    # Смещение зоны до и после перехода — разное, настенное время одно.
    assert to_local(before, TUTOR_BERLIN).utcoffset() == timedelta(hours=1)
    assert to_local(after, TUTOR_BERLIN).utcoffset() == timedelta(hours=2)
    assert before == datetime(2026, 3, 28, 9, 0, tzinfo=UTC)
    assert after == datetime(2026, 3, 30, 8, 0, tzinfo=UTC)
    # 48 часов настенного времени между датами, но в UTC — только 47.
    assert after - before == timedelta(hours=47)


def test_week_bounds_across_dst_are_shorter_than_seven_days(system_zone):
    """Неделя с переводом часов в зоне: границы считаются по настенному времени."""
    system_zone("Europe/Moscow")
    start, end = local_week_bounds(date(2026, 3, 23), TUTOR_BERLIN)
    assert start == datetime(2026, 3, 22, 23, 0, tzinfo=UTC)
    # 30.03 00:00 местного — это 29.03 22:00 UTC: неделя короче на час.
    assert end == datetime(2026, 3, 29, 22, 0, tzinfo=UTC)
    assert end - start == timedelta(days=6, hours=23)
