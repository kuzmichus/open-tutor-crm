"""Тесты блока времени на странице финансов (change finance-hours-idle-revenue).

Проверяются три новые вещи страницы: астрономические часы и средняя
стоимость часа (RevPTH), цена простоя («упущенная выручка») и разбивка
дохода по типам занятий. Плюс сценарий бага из задачи: начисленный, но
неоплаченный урок больше не теряется в верхней карточке «Доход».

Тесты идут тем же путём, что у пользователя — HTTP-маршруты страницы
финансов; списания создаются через `sync_lesson_charge`, то есть тем же
правилом, что в путях записи урока (руками собранные строки не проверяли
бы связь «урок → списание»).
"""

import re
from datetime import UTC, datetime, timedelta

import pytest

from app.database import SessionLocal
from app.finance.models.expense import Expense
from app.finance.services.charges import sync_lesson_charge
from app.finance.services.presentation import (
    duration_label,
    free_hours_phrase,
    rate_label,
    ratio_label,
)
from app.finance.services.time_metrics import rev_per_hour, type_insight
from app.lesson.models.lesson import Lesson
from app.tutor.models.tutor import Tutor
from app.tutor.services.clock import utcnow
from app.tutor.services.settings import save_settings

NBSP = "\u00a0"
MINUS = "\u2212"

PASSWORD = "Секретный-Пароль-3"

def _login(client, tutor_factory, email="hours@example.com", name="Часовщик"):
    """Репетитор с зоной UTC и вход под ним; возвращает его id."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id

def _money(value: int) -> str:
    """«1 200 ₽» — как форматирует finance.presentation.money."""
    return f"{value:,}".replace(",", NBSP) + NBSP + "₽"

def _kpi_value(html: str, title: str) -> str:
    """Значение карточки сводки по её заголовку."""
    match = re.search(
        rf'{re.escape(title)}</span>.*?fin-kpi__value[^"]*">\s*([^<]*?)\s*</p>',
        html,
        flags=re.S,
    )
    assert match, f"нет карточки «{title}»"
    return match.group(1)

def _compare_value(html: str, label: str) -> str:
    """Значение строки блока «Заработано и получено» по её подписи."""
    match = re.search(
        rf'{re.escape(label)}</p>.*?fin-compare__value[^"]*">\s*([^<]*?)\s*</p>',
        html,
        flags=re.S,
    )
    assert match, f"нет строки «{label}»"
    return match.group(1)

def _month_start(months_ago: int = 0) -> datetime:
    """Полдень первого числа месяца `months_ago` назад (UTC)."""
    today = utcnow()
    first = today.replace(day=1)
    for _ in range(months_ago):
        first = (first - timedelta(days=1)).replace(day=1)
    return first.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=UTC)

def _lesson(
    tutor_id: str,
    *,
    student_id: str | None = None,
    group_id: str | None = None,
    duration_min: int = 60,
    price: int | None = 1200,
    status: str = "completed",
    starts_at: datetime | None = None,
) -> str:
    """Урок в БД с синхронизированным списанием; возвращает id урока."""
    with SessionLocal() as session:
        lesson = Lesson(
            student_id=student_id,
            group_id=group_id,
            type="group" if group_id else "individual",
            starts_at=starts_at or utcnow(),
            duration_min=duration_min,
            price=price,
            status=status,
        )
        session.add(lesson)
        session.flush()
        sync_lesson_charge(session, lesson)
        session.commit()
        return lesson.id

def _expense(tutor_id: str, amount: int, when: datetime | None = None) -> None:
    """Расход репетитора напрямую в БД."""
    with SessionLocal() as session:
        session.add(
            Expense(
                tutor_id=tutor_id,
                amount=amount,
                category="rent",
                spent_at=when or utcnow(),
            )
        )
        session.commit()

def _settings(db_tutor_id: str, **values) -> None:
    """Настройки репетитора: рабочее время задаётся тестом явно."""
    with SessionLocal() as session:
        save_settings(session, db_tutor_id, values)
        session.commit()

# --------------------------------------------------------------------------
# Форматтеры
# --------------------------------------------------------------------------

def test_duration_label_formats_astronomical_time():
    """45 мин — «45 мин», 90 мин — «1 ч 30 мин», ноль — «0 мин»."""
    assert duration_label(45) == "45 мин"
    assert duration_label(90) == "1 ч 30 мин"
    assert duration_label(60) == "1 ч"
    assert duration_label(0) == "0 мин"
    assert duration_label(150) == "2 ч 30 мин"

def test_rate_label_and_ratio_label():
    """«800 ₽/ч» и «2 раза»; нет базы расчёта — прочерк, а не ноль."""
    assert rate_label(800) == _money(800) + "/ч"
    assert rate_label(None) == "—"
    assert ratio_label(2) == "2 раза"
    assert ratio_label(1.5) == "1,5 раза"

def test_free_hours_phrase_declines():
    """«1 свободный час», «2 свободных часа», «10,5 свободных часа»."""
    assert free_hours_phrase(60) == "1 свободный час"
    assert free_hours_phrase(120) == "2 свободных часа"
    assert free_hours_phrase(300) == "5 свободных часов"
    assert free_hours_phrase(630) == "10,5 свободных часа"

def test_rev_per_hour_is_none_without_hours():
    """Делить не на что — `None`; иначе округление до рубля."""
    assert rev_per_hour(1200, 0) is None
    assert rev_per_hour(1200, 60) == 1200
    assert rev_per_hour(1200, 90) == 800

# --------------------------------------------------------------------------
# Баг «Доход = 0 при заработанных 1 200»
# --------------------------------------------------------------------------

def test_unpaid_completed_lesson_counts_as_income(
    client, tutor_factory, student_factory
):
    """Начислено 1 200, платежей нет: доход 1 200, прибыль −15 000, долг 1 200.

    Сценарий бага из задачи: верхняя карточка «Доход» показывала кассу, и
    проведённый, но неоплаченный урок в ней не появлялся.
    """
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id, first_name="Аня")
    _lesson(tutor_id, student_id=student_id, duration_min=60, price=1200)
    _expense(tutor_id, 15000)

    html = client.get("/tutor/finance").text
    assert _kpi_value(html, "Доход") == _money(1200)
    assert _kpi_value(html, "Чистая прибыль") == f"{MINUS}{_money(15000)}"
    assert _kpi_value(html, "Долги учеников") == f"{MINUS}{_money(1200)}"
    assert _kpi_value(html, "Получено от учеников") == _money(0)
    assert _compare_value(html, "= Осталось репетитору") == f"{MINUS}{_money(15000)}"
    # Проведённое время подписано у «Заработано уроками».
    assert "Проведено: 1 ч" in html

def test_rev_per_hour_in_compare_block(client, tutor_factory, student_factory):
    """Средняя стоимость часа — начисленный доход ÷ проведённые часы."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    # 45 + 90 минут = 2,25 часа; 900 + 1800 = 2 700 ₽ → 1 200 ₽/ч.
    _lesson(tutor_id, student_id=student_id, duration_min=45, price=900)
    _lesson(tutor_id, student_id=student_id, duration_min=90, price=1800)

    html = client.get("/tutor/finance").text
    assert _kpi_value(html, "Проведено часов") == "2 ч 15 мин"
    assert f"Средняя стоимость часа: <strong>{_money(1200)}/ч</strong>" in html

def test_planned_lesson_does_not_add_hours(
    client, tutor_factory, student_factory
):
    """Запланированный урок не даёт ни часов, ни начисления."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    _lesson(tutor_id, student_id=student_id, status="planned", price=1200)

    html = client.get("/tutor/finance").text
    assert _kpi_value(html, "Проведено часов") == "0 мин"
    assert _kpi_value(html, "Доход") == _money(0)
    assert "Средняя стоимость часа: <strong>—</strong>" in html

# --------------------------------------------------------------------------
# Типы занятий
# --------------------------------------------------------------------------

def test_group_lesson_counts_once_in_hours_and_fully_in_revenue(
    client, tutor_factory, student_factory, group_factory, group_member_factory
):
    """Группа: часы один раз (время педагога), выручка — сумма участников."""
    tutor_id = _login(client, tutor_factory)
    group_id = group_factory(tutor_id=tutor_id, price_per_lesson=1000)
    first = student_factory(tutor_id=tutor_id, first_name="Первый")
    second = student_factory(tutor_id=tutor_id, first_name="Второй")
    group_member_factory(group_id=group_id, student_id=first)
    group_member_factory(group_id=group_id, student_id=second)

    _lesson(tutor_id, group_id=group_id, duration_min=60)
    # Индивидуальный урок того же репетитора — вторая колонка сравнения.
    individual = student_factory(tutor_id=tutor_id, first_name="Третий")
    _lesson(tutor_id, student_id=individual, duration_min=60, price=1200)

    html = client.get("/tutor/finance").text
    # Сумма колонок равна «Доходу»: 2 000 группы + 1 200 индивидуального.
    assert _kpi_value(html, "Доход") == _money(3200)
    group_block = re.search(
        r'data-type="group".*?</div>\s*</div>', html, re.S
    )
    assert group_block, "нет колонки «Групповые»"
    # Часы группы — 1 ч, а не 2 ч по числу участников.
    assert "1 ч" in group_block.group(0)
    assert _money(2000) in group_block.group(0)

def test_type_insight_when_group_is_more_profitable(
    client, tutor_factory, student_factory, group_factory, group_member_factory
):
    """Группа выгоднее за час — появляется совет набрать ещё одну."""
    tutor_id = _login(client, tutor_factory)
    group_id = group_factory(tutor_id=tutor_id, price_per_lesson=2000)
    member = student_factory(tutor_id=tutor_id, first_name="В группе")
    group_member_factory(group_id=group_id, student_id=member)
    individual = student_factory(tutor_id=tutor_id, first_name="Один")

    _lesson(tutor_id, group_id=group_id, duration_min=60)
    _lesson(tutor_id, student_id=individual, duration_min=60, price=1000)

    html = client.get("/tutor/finance").text
    assert "Групповые занятия приносят вам в 2 раза больше денег за час времени" in html
    assert "Стоит набрать ещё одну группу" in html

def test_no_insight_when_group_is_not_more_profitable(
    client, tutor_factory, student_factory, group_factory, group_member_factory
):
    """Группа не выгоднее — совета нет, колонки остаются."""
    tutor_id = _login(client, tutor_factory)
    group_id = group_factory(tutor_id=tutor_id, price_per_lesson=500)
    member = student_factory(tutor_id=tutor_id, first_name="В группе")
    group_member_factory(group_id=group_id, student_id=member)
    individual = student_factory(tutor_id=tutor_id, first_name="Один")

    _lesson(tutor_id, group_id=group_id, duration_min=60)
    _lesson(tutor_id, student_id=individual, duration_min=60, price=1500)

    html = client.get("/tutor/finance").text
    assert "Доходы по типам занятий" in html
    assert "Стоит набрать ещё одну группу" not in html

def test_type_insight_helpers():
    """Помощник не делит на ноль и не советует при отсутствии преимущества."""
    columns = [
        {"key": "individual", "rate": 1000},
        {"key": "group", "rate": None},
    ]
    assert type_insight(columns) is None
    columns = [
        {"key": "individual", "rate": 1000},
        {"key": "group", "rate": 1000},
    ]
    assert type_insight(columns) is None

# --------------------------------------------------------------------------
# Упущенная выручка
# --------------------------------------------------------------------------

def test_idle_revenue_block_counts_free_hours(
    client, tutor_factory, student_factory
):
    """Свободные часы месяца × RevPTH — сумма потерь, ссылка в календарь."""
    tutor_id = _login(client, tutor_factory)
    # Рабочий день 1 час: доступные часы месяца = число дней до конца месяца.
    _settings(tutor_id, workday_start="09:00", workday_end="10:00")
    student_id = student_factory(tutor_id=tutor_id)
    _lesson(tutor_id, student_id=student_id, duration_min=60, price=1200)

    html = client.get("/tutor/finance").text
    assert "Упущенная выручка" in html
    assert "Вы теряете ~" in html
    assert "из-за" in html and "в этом месяце" in html
    assert f'href="/tutor/calendar"' in html
    assert "Посмотреть свободные окна" in html

def test_idle_block_without_hours(client, tutor_factory):
    """Рабочий день нулевой — свободных часов нет, сумма не выдумывается."""
    tutor_id = _login(client, tutor_factory)
    _settings(tutor_id, workday_start="09:00", workday_end="09:00")

    html = client.get("/tutor/finance").text
    assert "Свободных часов до конца месяца нет" in html
    assert "Вы теряете" not in html

def test_idle_block_without_revenue_base(
    client, tutor_factory, student_factory
):
    """Часы есть, но проведённых часов нет — сумма не считается, часы видны."""
    tutor_id = _login(client, tutor_factory)
    _settings(tutor_id, workday_start="09:00", workday_end="10:00")
    student_factory(tutor_id=tutor_id)

    html = client.get("/tutor/finance").text
    assert "У вас" in html and "в этом месяце" in html
    assert "Сумму потерь пока не посчитать" in html

# --------------------------------------------------------------------------
# Изоляция
# --------------------------------------------------------------------------

def test_time_blocks_are_isolated_between_tutors(
    client, tutor_factory, student_factory
):
    """Часы, простой и типы чужого репетитора не попадают в сводку."""
    _login(client, tutor_factory)
    stranger_tutor = tutor_factory(name="Чужой", email="stranger-hours@example.com")
    stranger_student = student_factory(tutor_id=stranger_tutor, first_name="Чужак")
    _lesson(stranger_tutor, student_id=stranger_student, price=9000)

    html = client.get("/tutor/finance").text
    assert _money(9000) not in html
    assert _kpi_value(html, "Доход") == _money(0)
    assert _kpi_value(html, "Проведено часов") == "0 мин"
