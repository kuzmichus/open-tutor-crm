"""Тесты астрономических часов, загрузки, карты загрузки и сортировки по времени.

Задача tutor-statistics-update: «час» — единица длительности (45 минут =
0,75 часа), а не занятие; загрузка считается от рабочего шаблона за вычетом
отпусков; «Выручка на час» заменяет LTV; у учеников появилась колонка
«Часов/нед» и флаг падения нагрузки.

Даты строятся от «сейчас» и от сегодняшнего дня (зона репетитора в тестах —
UTC), чтобы тесты не зависели от месяца прогона.
"""

import re
from datetime import timedelta

from app.common.services.tutor_time import local_day_bounds, today_local
from app.database import SessionLocal
from app.stats.services.availability import available_minutes
from app.stats.services.heatmap import (
    CELL_BUSY,
    CELL_FREE,
    CELL_UNAVAILABLE,
    heatmap_context,
)
from app.stats.services.hours import (
    completed_minutes,
    student_completed_minutes,
    student_regular_minutes,
)
from app.stats.services.utilization import (
    TONE_DANGER,
    TONE_NONE,
    TONE_OK,
    TONE_WARN,
    tone,
    utilization_context,
)
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import utcnow
from app.tutor.services.settings import save_settings

NBSP = "\u00a0"
PASSWORD = "Секретный-Пароль-1"

# Рабочий день с 09:00 до 18:00 — 540 минут.
WORKDAY_MINUTES = 9 * 60


def _login(client, tutor_factory, email="hours@example.com", name="Часовик", **extra):
    """Репетитор с заводской карточкой (зона UTC) и вход под ним."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD, **extra)
    client.post("/tutor/login", data={"email": email, "password": PASSWORD})
    return tutor_id


def _save(tutor_id, **values):
    """Сохраняет настройки репетитора отдельной сессией (как страница профиля)."""
    with SessionLocal() as db:
        save_settings(db, tutor_id, values)


def _day_bounds(tutor, days: int = 1):
    """Границы `days` локальных суток начиная с сегодняшнего дня."""
    today = today_local(tutor)
    start, _ = local_day_bounds(today, tutor)
    _, end = local_day_bounds(today + timedelta(days=days - 1), tutor)
    return start, end


def _kpi_value(html: str, title: str) -> str:
    """Значение KPI-карточки по её заголовку (как в test_stats.py)."""
    match = re.search(
        rf'{re.escape(title)}</span>.*?stats-kpi__value">\s*([^<]*?)\s*</p>',
        html,
        flags=re.S,
    )
    assert match, f"нет KPI-карточки «{title}»"
    return match.group(1).strip()


# --------------------------------------------------------------------------
# Часы: длительность, а не количество занятий
# --------------------------------------------------------------------------


def test_group_lesson_counts_once_in_hours(
    tutor_factory,
    group_factory,
    student_factory,
    group_member_factory,
    lesson_factory,
):
    """Групповой урок 90 минут — 1,5 часа, а не 3 часа по числу участников."""
    tutor_id = tutor_factory(timezone="UTC")
    group_id = group_factory(tutor_id=tutor_id)
    anna = student_factory(tutor_id=tutor_id)
    boris = student_factory(tutor_id=tutor_id)
    group_member_factory(group_id=group_id, student_id=anna)
    group_member_factory(group_id=group_id, student_id=boris)
    lesson_factory(
        group_id=group_id,
        starts_at=utcnow() - timedelta(days=1),
        duration_min=90,
    )

    with SessionLocal() as db:
        assert completed_minutes(db, tutor_id) == 90
        per_student = student_completed_minutes(db, tutor_id)
    # Каждому участнику — полная длительность: это его время с педагогом.
    assert per_student[anna] == 90
    assert per_student[boris] == 90


def test_trial_counts_in_actual_hours_but_not_in_week_hours(
    tutor_factory, student_factory, lesson_factory
):
    """Пробное — реально потраченное время, но не «часы на ученика в неделю»."""
    tutor_id = tutor_factory(timezone="UTC")
    dasha = student_factory(tutor_id=tutor_id)
    lesson_factory(
        student_id=dasha,
        type="trial",
        starts_at=utcnow() - timedelta(days=1),
        duration_min=45,
    )

    with SessionLocal() as db:
        assert completed_minutes(db, tutor_id) == 45
        assert student_regular_minutes(db, tutor_id) == {}
        assert student_completed_minutes(db, tutor_id)[dasha] == 45


# --------------------------------------------------------------------------
# Доступные часы: рабочий шаблон минус отметки недоступности
# --------------------------------------------------------------------------


def test_available_minutes_subtract_marks(tutor_factory, unavailability_factory):
    """Доступные часы = рабочий день × дни, отпуск и выходной день дают ноль."""
    tutor_id = tutor_factory(timezone="UTC")
    _save(tutor_id, workday_start="09:00", workday_end="18:00")

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        start, end = _day_bounds(tutor, 1)
        assert available_minutes(db, tutor, start=start, end=end) == WORKDAY_MINUTES

    today = today_local(tutor)
    unavailability_factory(
        tutor_id=tutor_id,
        mode="period",
        start_date=today,
        end_date=today,
    )
    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        start, end = _day_bounds(tutor, 1)
        assert available_minutes(db, tutor, start=start, end=end) == 0
        # Неделя: отпуск только на один день — остальные шесть рабочих.
        start, end = _day_bounds(tutor, 7)
        assert available_minutes(db, tutor, start=start, end=end) == WORKDAY_MINUTES * 6


def test_available_minutes_subtract_weekday_dayoff(tutor_factory, unavailability_factory):
    """Постоянный выходной вычитается в каждой неделе периода."""
    tutor_id = tutor_factory(timezone="UTC")
    _save(tutor_id, workday_start="09:00", workday_end="18:00")
    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        start, end = _day_bounds(tutor, 7)
        weekday = (today_local(tutor) + timedelta(days=1)).weekday()

    unavailability_factory(tutor_id=tutor_id, mode="weekday", weekday=weekday)

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        start, end = _day_bounds(tutor, 7)
        assert available_minutes(db, tutor, start=start, end=end) == WORKDAY_MINUTES * 6


def test_broken_workday_gives_zero_available(client, tutor_factory):
    """Битые границы рабочего дня (конец раньше начала) — ноль, а не 500."""
    tutor_id = _login(client, tutor_factory)
    _save(tutor_id, workday_start="18:00", workday_end="09:00")

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        start, end = _day_bounds(tutor, 1)
        assert available_minutes(db, tutor, start=start, end=end) == 0

    assert client.get("/tutor/stats").status_code == 200


# --------------------------------------------------------------------------
# Загрузка: пороги и масштабирование цели
# --------------------------------------------------------------------------


def test_utilization_tones():
    """Пороги «факта к цели»: <70 недогруз, 70–100 норма, >100 перегруз."""
    assert tone(None) == TONE_NONE
    assert tone(0) == TONE_WARN
    assert tone(69) == TONE_WARN
    assert tone(70) == TONE_OK
    assert tone(85) == TONE_OK
    assert tone(100) == TONE_OK
    assert tone(101) == TONE_DANGER


def test_utilization_scales_target_to_period(tutor_factory):
    """Недельная цель масштабируется на длину периода: 10 ч/нед × 7 дней."""
    tutor_id = tutor_factory(timezone="UTC")
    _save(
        tutor_id,
        workday_start="09:00",
        workday_end="18:00",
        weekly_load_hours=10,
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        start, end = _day_bounds(tutor, 7)
        context = utilization_context(
            db,
            tutor,
            start=start,
            end=end,
            actual_minutes=480,
            available_minutes=WORKDAY_MINUTES * 7,
        )
    assert context["target_hours"] == 10
    # 8 часов из 10 комфортных — 80%, «норма».
    assert context["fact_to_target"] == 80
    # Без подготовки «Загрузка ресурса» — те же 8 ч из 63 доступных.
    assert context["resource_hours"] == 8
    assert context["resource_percent"] == 13
    assert context["weekly_resource_hours"] == 8
    assert context["target_tone"] == TONE_OK
    # Цвет второй шкалы — по часам: 8 ч в неделю — комфорт.
    assert context["resource_tone"] == TONE_OK
    assert context["target_missing"] is False
    assert "рабочему шаблону" in context["hint"]


def test_resource_scale_counts_preparation(tutor_factory):
    """Вторая шкала считает общую занятость: уроки плюс подготовка."""
    tutor_id = tutor_factory(timezone="UTC")
    _save(tutor_id, workday_start="09:00", workday_end="18:00")

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        start, end = _day_bounds(tutor, 7)
        context = utilization_context(
            db,
            tutor,
            start=start,
            end=end,
            actual_minutes=600,
            available_minutes=WORKDAY_MINUTES * 7,
            preparation_minutes=420,
        )

    # 10 ч уроков + 7 ч подготовки = 17 ч общей занятости.
    assert context["actual_hours"] == 10
    assert context["preparation_hours"] == 7
    assert context["resource_hours"] == 17
    assert context["resource_percent"] == 27
    assert context["weekly_resource_hours"] == 17
    assert context["resource_tone"] == TONE_OK


def test_resource_tone_depends_on_hours_not_percent(tutor_factory):
    """90% от большого календаря — красный, 90% от малого — зелёный."""
    tutor_id = tutor_factory(timezone="UTC")
    _save(tutor_id, workday_start="09:00", workday_end="18:00")

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        start, end = _day_bounds(tutor, 7)

        # 40 ч работы при 90 доступных — 44% полосы, но высокая нагрузка.
        wide = utilization_context(
            db,
            tutor,
            start=start,
            end=end,
            actual_minutes=2400,
            available_minutes=90 * 60,
            preparation_minutes=0,
        )
        assert wide["resource_percent"] == 44
        assert wide["resource_tone"] == TONE_WARN

        # 46 ч работы — красный, даже если календарь огромный.
        burnout = utilization_context(
            db,
            tutor,
            start=start,
            end=end,
            actual_minutes=2760,
            available_minutes=200 * 60,
            preparation_minutes=0,
        )
        assert burnout["resource_percent"] == 23
        assert burnout["resource_tone"] == TONE_DANGER

        # 20 ч работы при 21 доступном — 95% полосы, но нагрузка комфортная.
        narrow = utilization_context(
            db,
            tutor,
            start=start,
            end=end,
            actual_minutes=1200,
            available_minutes=21 * 60,
            preparation_minutes=0,
        )
        assert narrow["resource_percent"] == 95
        assert narrow["resource_tone"] == TONE_OK


def test_utilization_without_target(tutor_factory):
    """Цель не задана — процента нет, шаблон покажет «Цель не задана»."""
    tutor_id = tutor_factory(timezone="UTC")
    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        start, end = _day_bounds(tutor, 7)
        context = utilization_context(
            db,
            tutor,
            start=start,
            end=end,
            actual_minutes=60,
            available_minutes=0,
        )
    assert context["target_missing"] is True
    assert context["fact_to_target"] is None
    # Доступных часов нет — процента тоже нет, а не деление на ноль.
    assert context["resource_percent"] is None
    assert context["target_tone"] == TONE_NONE
    # Часы при этом считаются: цвет шкалы не зависит от процента.
    assert context["resource_tone"] == TONE_OK


def test_overview_shows_utilization_and_heatmap(client, tutor_factory):
    """Блок «Загрузка» и «Карта загрузки» есть на «Обзоре»."""
    tutor_id = _login(client, tutor_factory)
    html = client.get("/tutor/stats").text
    assert "Загрузка" in html
    assert "Факт к цели" in html
    assert "Загрузка ресурса" in html
    # Цели нет — вместо процента подсказка со ссылкой на настройки.
    assert "Цель не задана" in html
    assert "/tutor/profile?tab=calendar" in html
    assert "Карта загрузки" in html
    assert "Доступные часы рассчитаны по вашему рабочему шаблону" in html


# --------------------------------------------------------------------------
# Карта загрузки
# --------------------------------------------------------------------------


def test_heatmap_states_and_insight(
    client, tutor_factory, student_factory, lesson_factory, unavailability_factory
):
    """Ячейки: занято / свободно / недоступно, инсайт с самым большим окном."""
    tutor_id = _login(client, tutor_factory)
    _save(tutor_id, workday_start="09:00", workday_end="12:00")

    now = utcnow()
    anna = student_factory(tutor_id=tutor_id)
    lesson_factory(
        student_id=anna,
        starts_at=now.replace(hour=10, minute=0, second=0, microsecond=0),
        duration_min=60,
    )
    # Постоянный выходной на завтрашний день недели: ровно один день недели.
    tomorrow_weekday = (now + timedelta(days=1)).weekday()
    unavailability_factory(
        tutor_id=tutor_id, mode="weekday", weekday=tomorrow_weekday
    )

    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        context = heatmap_context(db, tutor, now=now)

    states = [cell["state"] for row in context["rows"] for cell in row["cells"]]
    # Три часа в день × семь дней = 21 ячейка; один час занят, один день
    # (три часа) недоступен.
    assert len(states) == 21
    assert states.count(CELL_BUSY) == 1
    assert states.count(CELL_UNAVAILABLE) == 3
    assert states.count(CELL_FREE) == 17
    assert context["total_free_hours"] == 17
    assert "17 свободных астрономических часов" in context["insight"]
    assert "Самое большое окно — " in context["insight"]


def test_heatmap_without_workday(client, tutor_factory):
    """Без рабочего времени карта не рисуется, а просит задать шаблон."""
    tutor_id = _login(client, tutor_factory)
    _save(tutor_id, workday_start="12:00", workday_end="12:00")
    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        context = heatmap_context(db, tutor, now=utcnow())
    assert context["has_workday"] is False
    assert context["rows"] == []
    assert "Рабочее время не задано" in context["insight"]


# --------------------------------------------------------------------------
# Выручка на час
# --------------------------------------------------------------------------


def test_revenue_per_hour(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    """Карточка «Выручка на час»: 2000 ₽ за 2 фактических часа = 1000 ₽."""
    now = utcnow()
    tutor_id = _login(client, tutor_factory)
    anna = student_factory(tutor_id=tutor_id, first_name="Аня", status="active")
    lesson_factory(student_id=anna, starts_at=now - timedelta(days=1), duration_min=60)
    lesson_factory(student_id=anna, starts_at=now - timedelta(days=2), duration_min=60)
    operation_factory(student_id=anna, amount=2000, occurred_at=now)

    html = client.get("/tutor/stats").text
    # LTV остался в ряду карточек и стоит до «Выручки на час»: сначала
    # «сколько приносит ученик», потом «сколько стоит час».
    assert "LTV (Сред. чек)" in html
    assert html.index("LTV (Сред. чек)") < html.index("Выручка на час")
    assert _kpi_value(html, "Выручка на час") == f"1{NBSP}000{NBSP}₽"


# --------------------------------------------------------------------------
# Таблица учеников: «Часов/нед» и сортировка по времени
# --------------------------------------------------------------------------


def test_students_hours_column_and_sorting(
    client, tutor_factory, student_factory, lesson_factory
):
    """Колонка «Часов/нед» и сортировка по часам: тяжёлые сверху."""
    now = utcnow()
    tutor_id = _login(client, tutor_factory)

    heavy = student_factory(tutor_id=tutor_id, first_name="Тяжёлая", status="active")
    for days in (5, 7, 9, 11):
        lesson_factory(
            student_id=heavy, starts_at=now - timedelta(days=days), duration_min=90
        )
    light = student_factory(tutor_id=tutor_id, first_name="Лёгкая", status="active")
    lesson_factory(
        student_id=light, starts_at=now - timedelta(days=1), duration_min=45
    )

    by_date = client.get("/tutor/stats?tab=students&activity=active").text
    assert "Часов/нед" in by_date
    # По дате: свежая «Лёгкая» выше «Тяжёлой».
    assert by_date.index("Лёгкая") < by_date.index("Тяжёлая")
    # 4 урока по 90 минут за 4 недели — 1,5 часа в неделю.
    assert "1,5 ч" in by_date

    by_hours = client.get(
        "/tutor/stats?tab=students&activity=active&sort=hours"
    ).text
    assert by_hours.index("Тяжёлая") < by_hours.index("Лёгкая")
    assert "name=\"sort\"" in by_hours

    # Мусорный режим сортировки — обычный порядок по дате, без ошибки.
    garbage = client.get("/tutor/stats?tab=students&sort=bogus")
    assert garbage.status_code == 200
    assert garbage.text.index("Лёгкая") < garbage.text.index("Тяжёлая")


def test_students_csv_has_hours_column(
    client, tutor_factory, student_factory, lesson_factory
):
    """В CSV есть колонка «Часов/нед» — та же, что в таблице."""
    now = utcnow()
    tutor_id = _login(client, tutor_factory)
    anna = student_factory(tutor_id=tutor_id, first_name="Аня", status="active")
    lesson_factory(student_id=anna, starts_at=now - timedelta(days=1), duration_min=90)

    body = client.get("/tutor/stats/students.csv").content.decode("utf-8-sig")
    assert body.splitlines()[0].startswith("Имя;Педагог;Статус")
    assert "Часов/нед" in body.splitlines()[0]
    # 90 минут за 4 недели = 0,375 → «0,4 ч».
    assert "0,4 ч" in body


# --------------------------------------------------------------------------
# Флаг падения нагрузки в «Риске потери»
# --------------------------------------------------------------------------


def test_decline_flag_for_falling_load(
    client, tutor_factory, student_factory, lesson_factory
):
    """Было 2×60 мин за 2 недели, стало 1×45 — флаг «нагрузка −62%»."""
    now = utcnow()
    tutor_id = _login(client, tutor_factory)
    falling = student_factory(
        tutor_id=tutor_id, first_name="Падающий", status="active"
    )
    lesson_factory(
        student_id=falling, starts_at=now - timedelta(days=16), duration_min=60
    )
    lesson_factory(
        student_id=falling, starts_at=now - timedelta(days=20), duration_min=60
    )
    lesson_factory(
        student_id=falling, starts_at=now - timedelta(days=3), duration_min=45
    )

    html = client.get("/tutor/stats").text
    assert "нагрузка −62%" in html
    assert "Риск потери: 1" in html
    assert "Падающий" in html[html.index("Риск потери:") :]


def test_decline_flag_absent_for_small_drop_or_small_base(
    client, tutor_factory, student_factory, lesson_factory
):
    """Падение меньше 50% и база меньше 2 часов флаг не ставят."""
    now = utcnow()
    tutor_id = _login(client, tutor_factory)

    # Было 120 минут, стало 90 — падение всего на четверть.
    soft = student_factory(tutor_id=tutor_id, first_name="Мягкий", status="active")
    lesson_factory(
        student_id=soft, starts_at=now - timedelta(days=16), duration_min=60
    )
    lesson_factory(
        student_id=soft, starts_at=now - timedelta(days=20), duration_min=60
    )
    lesson_factory(
        student_id=soft, starts_at=now - timedelta(days=3), duration_min=90
    )

    # База 60 минут: даже «падение вдвое» — это шум, а не тенденция.
    small = student_factory(tutor_id=tutor_id, first_name="Мелкий", status="active")
    lesson_factory(
        student_id=small, starts_at=now - timedelta(days=16), duration_min=60
    )
    lesson_factory(
        student_id=small, starts_at=now - timedelta(days=3), duration_min=30
    )

    html = client.get("/tutor/stats").text
    risk_block = html[html.index("Риск потери:") :]
    assert 'class="stats-flag"' not in risk_block
    assert "Мягкий" not in risk_block
    assert "Мелкий" not in risk_block
    assert "Все активные ученики посещают занятия регулярно!" in html


# --------------------------------------------------------------------------
# Период «Обзора»
# --------------------------------------------------------------------------


def test_overview_period_defaults_to_30_days(client, tutor_factory):
    """На «Обзоре» чипы периода и умолчание 30 дней; мусор — тоже 30 дней."""
    _login(client, tutor_factory)
    pattern = re.compile(
        r'tab--active"\s+href="/tutor/stats\?tab=overview&period=30d"'
    )
    assert pattern.search(client.get("/tutor/stats").text)

    garbage = client.get("/tutor/stats?tab=overview&period=bogus")
    assert garbage.status_code == 200
    assert pattern.search(garbage.text)


def test_period_chips_order(client, tutor_factory):
    """Чипы периода идут от короткого окна к длинному, последнее — «Весь период»."""
    _login(client, tutor_factory)
    html = client.get("/tutor/stats").text
    labels = ["Сегодня", "7 дней", "30 дней", "Весь период"]
    assert [html.index(label) for label in labels] == sorted(
        html.index(label) for label in labels
    )


def test_forecast_block_under_its_button(client, tutor_factory):
    """Прогноз раскрывается сразу под кнопкой, до блока «Загрузка»."""
    _login(client, tutor_factory)
    html = client.get("/tutor/stats?tab=overview&forecast=1").text
    toolbar = html.index('class="stats-toolbar"')
    forecast = html.index('class="card stats-forecast"')
    utilization = html.index('class="card stats-util"')
    assert toolbar < forecast < utilization