"""Тесты внеурочной занятости: подготовка, баланс времени и алерт выгорания.

Задача TOCRM-45: страница статистики учитывает не только уроки, но и
подготовку к ним и проверку домашних заданий. База — коэффициент подготовки
профиля (TOCRM-41): подготовка = фактические минуты × коэффициент.

Проверяется тем же путём, что у пользователя: страница `/tutor/stats` и
сохранённые настройки профиля. Даты строятся от «сейчас», чтобы тесты не
зависели от месяца прогона.
"""

from datetime import timedelta
from decimal import Decimal

from app.common.services.tutor_time import local_day_bounds, today_local
from app.database import SessionLocal
from app.stats.services.preparation import preparation_context
from app.stats.services.workload import (
    COMFORT_WEEKLY_HOURS,
    HIGH_WEEKLY_HOURS,
    LEVEL_BURNOUT,
    LEVEL_COMFORT,
    LEVEL_HIGH,
    level,
    verdict,
)
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import utcnow
from app.tutor.services.settings import save_settings

PASSWORD = "Секретный-Пароль-1"


def _login(client, tutor_factory, email="prep@example.com", name="Готовящийся", **extra):
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


def _context(tutor_id, *, actual_minutes: int, days: int = 7) -> dict:
    """Контекст подготовки для репетитора на `days` дней от сегодня."""
    with SessionLocal() as db:
        tutor = db.get(Tutor, tutor_id)
        return preparation_context(
            db, tutor, actual_minutes=actual_minutes, days=days
        )


# --------------------------------------------------------------------------
# Расчёт: коэффициент, недельный пересчёт, пороги
# --------------------------------------------------------------------------


def test_default_coefficient_is_seventy_percent(tutor_factory):
    """Без сохранённых настроек действует дефолт 0.7: 10 ч уроков → 7 ч подготовки."""
    tutor_id = tutor_factory(timezone="UTC")
    context = _context(tutor_id, actual_minutes=600, days=7)

    assert context["coefficient"] == 0.7
    assert context["coefficient_label"] == "0,7"
    assert context["minutes_per_hour"] == 42
    assert context["lesson_hours"] == 10
    assert context["preparation_hours"] == 7
    assert context["total_hours"] == 17
    # Период ровно неделя — недельные значения совпадают с периодом.
    assert context["weekly_total_hours"] == 17
    assert "42 мин на час урока" in context["insight"]
    assert "17 часов в неделю" in context["insight"]


def test_preparation_uses_saved_coefficient(tutor_factory):
    """Сохранённый коэффициент 2.0: подготовка вдвое больше учебных часов."""
    tutor_id = tutor_factory(timezone="UTC")
    _save(tutor_id, preparation_coefficient=Decimal("2.00"))

    context = _context(tutor_id, actual_minutes=600, days=7)
    assert context["coefficient"] == 2.0
    assert context["preparation_hours"] == 20
    assert context["total_hours"] == 30
    assert context["minutes_per_hour"] == 120


def test_weekly_values_scale_to_period(tutor_factory):
    """Период 14 дней: недельная занятость — половина периода."""
    tutor_id = tutor_factory(timezone="UTC")
    context = _context(tutor_id, actual_minutes=1200, days=14)

    assert context["lesson_hours"] == 20
    assert context["preparation_hours"] == 14
    assert context["total_hours"] == 34
    assert context["weekly_lesson_hours"] == 10
    assert context["weekly_preparation_hours"] == 7
    assert context["weekly_total_hours"] == 17


def test_zero_coefficient_gives_no_preparation(tutor_factory):
    """Коэффициент 0: подготовки нет, кольцо целиком занято уроками."""
    tutor_id = tutor_factory(timezone="UTC")
    _save(tutor_id, preparation_coefficient=Decimal(0))

    context = _context(tutor_id, actual_minutes=600, days=7)
    assert context["preparation_hours"] == 0
    assert context["total_hours"] == 10
    assert context["has_preparation"] is False
    assert context["chart"]["lesson_dash"] == context["chart"]["circumference"]
    assert context["chart"]["prep_dash"] == 0
    assert "Коэффициент подготовки равен 0" in context["insight"]
    assert context["alert"] is None


def test_no_lessons_gives_empty_state(tutor_factory):
    """Уроков нет — пустое состояние, а не кольцо нулевой длины."""
    tutor_id = tutor_factory(timezone="UTC")
    context = _context(tutor_id, actual_minutes=0, days=7)

    assert context["has_lessons"] is False
    assert context["chart"] is None
    assert context["total_hours"] == 0
    assert context["alert"] is None
    assert "нет проведённых уроков" in context["insight"]


def test_burnout_alert_starts_above_forty_five_hours(tutor_factory):
    """Порог 45 ч: ровно 45 — высокая нагрузка, 45,1 — предупреждение."""
    tutor_id = tutor_factory(timezone="UTC")
    _save(tutor_id, preparation_coefficient=Decimal("1.00"))

    # 22 ч уроков + 22 ч подготовки = 44 ч в неделю — высокая, но без алерта.
    below = _context(tutor_id, actual_minutes=1320, days=7)
    assert below["weekly_total_hours"] == 44
    assert below["level"] == LEVEL_HIGH
    assert below["alert"] is None

    # 22,5 ч уроков + 22,5 ч подготовки = 45 ч в неделю — ровно на пороге.
    at_threshold = _context(tutor_id, actual_minutes=1350, days=7)
    assert at_threshold["weekly_total_hours"] == HIGH_WEEKLY_HOURS
    assert at_threshold["level"] == LEVEL_HIGH
    assert at_threshold["alert"] is None

    # 23 ч уроков + 23 ч подготовки = 46 ч в неделю — выше порога.
    above = _context(tutor_id, actual_minutes=1380, days=7)
    assert above["weekly_total_hours"] == 46
    assert above["level"] == LEVEL_BURNOUT
    assert above["alert"] is not None
    text = above["alert"]["text"]
    assert "Учебная нагрузка 23 часа" in text
    assert "подготовка 23 часа" in text
    assert "46 часов работы в неделю" in text
    assert "Высокий риск выгорания" in text
    assert "повышение цен или сокращение учеников" in text


def test_weekly_load_levels():
    """Уровни недельной нагрузки: до 35 — комфорт, 35–45 — высокая, >45 — риск."""
    assert level(0) == LEVEL_COMFORT
    assert level(COMFORT_WEEKLY_HOURS - 0.1) == LEVEL_COMFORT
    # Ровно 35 — уже высокая нагрузка.
    assert level(COMFORT_WEEKLY_HOURS) == LEVEL_HIGH
    assert level(40) == LEVEL_HIGH
    # Ровно 45 — ещё высокая, а не риск выгорания.
    assert level(HIGH_WEEKLY_HOURS) == LEVEL_HIGH
    assert level(HIGH_WEEKLY_HOURS + 0.1) == LEVEL_BURNOUT

    assert verdict(32.7) == "Это комфортный уровень нагрузки."
    assert verdict(38) == "Это высокий уровень нагрузки."
    assert verdict(47) == "Высокий риск выгорания!"


def test_insight_has_load_verdict(tutor_factory):
    """Инсайт заканчивается вердиктом по абсолютной недельной занятости."""
    tutor_id = tutor_factory(timezone="UTC")

    # 10 ч уроков × 1.7 = 17 ч общей занятости — комфорт.
    comfort = _context(tutor_id, actual_minutes=600, days=7)
    assert comfort["weekly_total_hours"] == 17
    assert "17 часов в неделю" in comfort["insight"]
    assert comfort["insight"].endswith("Это комфортный уровень нагрузки.")

    # 24 ч уроков × 1.7 = 40,8 ч — высокая нагрузка.
    high = _context(tutor_id, actual_minutes=1440, days=7)
    assert high["level"] == LEVEL_HIGH
    assert high["insight"].endswith("Это высокий уровень нагрузки.")

    # 30 ч уроков × 1.7 = 51 ч — риск выгорания.
    burnout = _context(tutor_id, actual_minutes=1800, days=7)
    assert burnout["level"] == LEVEL_BURNOUT
    assert burnout["insight"].endswith("Высокий риск выгорания!")



def test_donut_geometry_is_proportional(tutor_factory):
    """Дуги пончика пропорциональны долям уроков и подготовки."""
    tutor_id = tutor_factory(timezone="UTC")
    context = _context(tutor_id, actual_minutes=600, days=7)
    donut = context["chart"]

    assert donut["size"] == 140
    # 10 ч уроков из 17 ч общей занятости.
    share = 10 / 17
    assert donut["lesson_dash"] == round(donut["circumference"] * share, 1)
    assert donut["prep_dash"] == round(
        donut["circumference"] - donut["lesson_dash"], 1
    )
    assert donut["prep_offset"] == -donut["lesson_dash"]


def test_legend_has_lessons_preparation_and_total(tutor_factory):
    """Легенда: «Уроки», «Подготовка», «Всего» с часами и процентами."""
    tutor_id = tutor_factory(timezone="UTC")
    context = _context(tutor_id, actual_minutes=600, days=7)
    legend = {row["key"]: row for row in context["legend"]}

    assert legend["lesson"]["value"] == "10 ч"
    assert legend["preparation"]["value"] == "7 ч"
    assert legend["total"]["value"] == "17 ч"
    assert legend["lesson"]["percent"] == 59
    assert legend["preparation"]["percent"] == 41


# --------------------------------------------------------------------------
# Страница «Обзор»
# --------------------------------------------------------------------------


def test_overview_shows_preparation_insight(
    client, tutor_factory, student_factory, lesson_factory
):
    """Под блоком «Загрузка» — инсайт об общей занятости с подготовкой."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    lesson_factory(
        student_id=student_id,
        starts_at=utcnow() - timedelta(hours=1),
        duration_min=60,
    )

    html = client.get("/tutor/stats?period=7d").text

    assert "С учётом подготовки" in html
    assert "42 мин на час урока" in html
    assert "ваша общая занятость составляет" in html


def test_overview_shows_balance_widget(
    client, tutor_factory, student_factory, lesson_factory
):
    """Виджет «Баланс времени»: пончик, легенда и подпись коэффициента."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    now = utcnow()
    # Два урока по 60 минут за последние сутки — 2 фактические часа.
    for days_ago in (0, 1):
        lesson_factory(
            student_id=student_id,
            starts_at=now - timedelta(days=days_ago),
            duration_min=60,
        )

    html = client.get("/tutor/stats?period=7d").text

    assert "Баланс времени (Уроки vs Подготовка)" in html
    assert "stats-balance__donut" in html
    assert "Уроки" in html
    assert "Подготовка" in html
    assert "Всего" in html
    assert "2 ч" in html
    # 2 ч уроков × 0.7 = 1,4 ч подготовки, итого 3,4 ч.
    assert "1,4 ч" in html
    assert "3,4 ч" in html


def test_overview_balance_empty_state(client, tutor_factory):
    """Уроков нет — вместо пустого кольца пояснение."""
    _login(client, tutor_factory)
    html = client.get("/tutor/stats").text

    assert "Баланс времени (Уроки vs Подготовка)" in html
    assert "нет проведённых уроков" in html
    assert "stats-balance__donut" not in html
    assert "Риск выгорания" not in html


def test_overview_burnout_alert_above_threshold(
    client, tutor_factory, student_factory, lesson_factory
):
    """Много часов за неделю + подготовка выше 45 ч — алерт выгорания."""
    tutor_id = _login(client, tutor_factory)
    _save(tutor_id, preparation_coefficient=Decimal("1.00"))
    student_id = student_factory(tutor_id=tutor_id)
    now = utcnow()
    # 28 уроков по 60 минут за 7 дней = 28 ч + 28 ч подготовки = 56 ч.
    for day in range(7):
        for hour in range(4):
            lesson_factory(
                student_id=student_id,
                starts_at=now - timedelta(days=day, hours=hour * 2),
                duration_min=60,
            )

    html = client.get("/tutor/stats?period=7d").text

    assert "Риск выгорания" in html
    assert "Высокий риск выгорания" in html
    assert "повышение цен или сокращение учеников" in html


def test_overview_no_burnout_alert_below_threshold(
    client, tutor_factory, student_factory, lesson_factory
):
    """Умеренная нагрузка — алерта нет."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    now = utcnow()
    # 4 урока по 60 минут за 7 дней = 4 ч + 2,8 ч подготовки — далеко от порога.
    for day in range(4):
        lesson_factory(
            student_id=student_id,
            starts_at=now - timedelta(days=day),
            duration_min=60,
        )

    html = client.get("/tutor/stats?period=7d").text

    assert "Баланс времени (Уроки vs Подготовка)" in html
    assert "Риск выгорания" not in html


def test_saved_coefficient_changes_page_numbers(
    client, tutor_factory, student_factory, lesson_factory
):
    """Смена коэффициента в профиле меняет часы подготовки на странице."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    now = utcnow()
    for day in range(2):
        lesson_factory(
            student_id=student_id,
            starts_at=now - timedelta(days=day),
            duration_min=60,
        )

    html = client.get("/tutor/stats?period=7d").text
    # Дефолт 0.7: 2 ч уроков + 1,4 ч подготовки.
    assert "1,4 ч" in html

    _save(tutor_id, preparation_coefficient=Decimal("0.50"))
    html = client.get("/tutor/stats?period=7d").text
    # Коэффициент 0.5: 2 ч уроков + 1 ч подготовки, итого 3 ч.
    assert "1 ч" in html
    assert "3 ч" in html


# --------------------------------------------------------------------------
# «Загрузка ресурса»: общая занятость против календаря, цвет по часам
# --------------------------------------------------------------------------


def test_resource_scale_uses_lessons_plus_preparation(
    client, tutor_factory, student_factory, lesson_factory
):
    """«Загрузка ресурса» сравнивает с календарём уроки вместе с подготовкой."""
    tutor_id = _login(client, tutor_factory)
    # Рабочий день 09:00–18:00 = 9 ч × 7 дней = 63 доступных часа.
    _save(tutor_id, workday_start="09:00", workday_end="18:00")
    student_id = student_factory(tutor_id=tutor_id)
    now = utcnow()
    # 10 уроков по 60 минут за 7 дней: 10 ч уроков + 7 ч подготовки = 17 ч.
    for day in range(7):
        lesson_factory(
            student_id=student_id,
            starts_at=now - timedelta(days=day),
            duration_min=60,
        )
    for hour in range(3):
        lesson_factory(
            student_id=student_id,
            starts_at=now - timedelta(days=1, hours=hour + 2),
            duration_min=60,
        )

    html = client.get("/tutor/stats?period=7d").text

    assert "Загрузка ресурса" in html
    # «Факт к максимуму» больше не выводится.
    assert "Факт к максимуму" not in html
    # 17 ч общей занятости из 63 доступных — 27%, цвет при этом зелёный.
    assert "17 ч из" in html
    assert "63 ч доступных" in html
    assert "27%" in html
    assert "stats-util__bar--ok" in html


def test_resource_scale_is_green_despite_high_percent(
    client, tutor_factory, student_factory, lesson_factory
):
    """Цвет шкалы — по часам, а не по проценту: 81% полосы ещё комфорт."""
    tutor_id = _login(client, tutor_factory)
    # Узкий календарь: 6 ч в день × 7 = 42 доступных часа.
    _save(tutor_id, workday_start="09:00", workday_end="15:00")
    student_id = student_factory(tutor_id=tutor_id)
    now = utcnow()
    # 20 уроков по 60 минут = 20 ч уроков + 14 ч подготовки = 34 ч — комфорт.
    for day in range(7):
        for hour in range(2):
            lesson_factory(
                student_id=student_id,
                starts_at=now - timedelta(days=day, hours=hour * 2),
                duration_min=60,
            )
    for day in range(6):
        lesson_factory(
            student_id=student_id,
            starts_at=now - timedelta(days=day, hours=6),
            duration_min=60,
        )

    html = client.get("/tutor/stats?period=7d").text

    # 34 ч из 42 доступных — 81% полосы, но нагрузка комфортная: зелёный.
    assert "34 ч из" in html
    assert "81%" in html
    assert "stats-util__bar--ok" in html
    assert "stats-util__bar--danger" not in html
    assert "Это комфортный уровень нагрузки." in html


def test_resource_scale_turns_red_above_forty_five_hours(
    client, tutor_factory, student_factory, lesson_factory
):
    """Больше 45 ч недельной занятости — красная шкала и вердикт выгорания."""
    tutor_id = _login(client, tutor_factory)
    _save(
        tutor_id,
        workday_start="09:00",
        workday_end="18:00",
        preparation_coefficient=Decimal("1.00"),
    )
    student_id = student_factory(tutor_id=tutor_id)
    now = utcnow()
    # 24 урока по 60 минут = 24 ч уроков + 24 ч подготовки = 48 ч в неделю.
    for day in range(7):
        for hour in range(3):
            lesson_factory(
                student_id=student_id,
                starts_at=now - timedelta(days=day, hours=hour * 2),
                duration_min=60,
            )
    for hour in range(3):
        lesson_factory(
            student_id=student_id,
            starts_at=now - timedelta(days=1, hours=hour + 7),
            duration_min=60,
        )

    html = client.get("/tutor/stats?period=7d").text

    assert "stats-util__bar--danger" in html
    assert "Высокий риск выгорания!" in html
    assert "Риск выгорания" in html


def test_resource_scale_high_load_is_yellow(
    client, tutor_factory, student_factory, lesson_factory
):
    """Недельная занятость 35–45 ч — жёлтая шкала и вердикт высокой нагрузки."""
    tutor_id = _login(client, tutor_factory)
    _save(
        tutor_id,
        workday_start="09:00",
        workday_end="18:00",
        preparation_coefficient=Decimal("1.00"),
    )
    student_id = student_factory(tutor_id=tutor_id)
    now = utcnow()
    # 19 уроков по 60 минут = 19 ч уроков + 19 ч подготовки = 38 ч в неделю.
    for day in range(7):
        for hour in range(2):
            lesson_factory(
                student_id=student_id,
                starts_at=now - timedelta(days=day, hours=hour * 2),
                duration_min=60,
            )
    for day in range(5):
        lesson_factory(
            student_id=student_id,
            starts_at=now - timedelta(days=day, hours=6),
            duration_min=60,
        )

    html = client.get("/tutor/stats?period=7d").text

    assert "stats-util__bar--warn" in html
    assert "Это высокий уровень нагрузки." in html
    assert "Риск выгорания" not in html

