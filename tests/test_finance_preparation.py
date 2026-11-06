"""Тесты учёта внеурочной занятости на странице финансов (TOCRM-46).

Задача: страница «Финансы» учитывает не только уроки, но и подготовку к
ним и проверку домашних заданий. Объём подготовки задаёт «Коэффициент
подготовки» профиля (TOCRM-41), а формула — та же, что у «Статистики»
(TOCRM-45): `preparation_minutes` из `stats/services/preparation`.

Проверяется три вещи:

- часы подготовки мелкой строкой рядом с «Проведено» (значение карточки
  остаётся только по урокам);
- «Реальная стоимость часа» = начисленный доход ÷ (уроки + подготовка);
- совет «поднять цену до …» и его отсутствие, когда считать нечего
  (коэффициент 0, нет проведённых уроков).

Тесты идут тем же путём, что у пользователя — HTTP-маршруты страницы
финансов; списания создаются через `sync_lesson_charge`, настройки — через
`save_settings`, как это делает страница профиля.
"""

import re
from datetime import datetime
from decimal import Decimal

from app.database import SessionLocal
from app.finance.services.charges import sync_lesson_charge
from app.finance.services.time_metrics import real_rate_insight
from app.lesson.models.lesson import Lesson
from app.stats.services.preparation import coefficient_label, preparation_minutes
from app.tutor.models.tutor_settings import TutorSettings, default_values
from app.tutor.services.clock import utcnow
from app.tutor.services.settings import save_settings

NBSP = "\u00a0"

PASSWORD = "Секретный-Пароль-1"


def _login(client, tutor_factory, email="prep-finance@example.com", name="Готовящийся"):
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


def _compare_block(html: str) -> str:
    """Разметка блока «Заработано и получено»."""
    match = re.search(
        r'<section class="card fin-compare.*?</section>', html, flags=re.S
    )
    assert match, "нет блока сравнения"
    return match.group(0)


def _lesson(
    tutor_id: str,
    *,
    student_id: str | None = None,
    duration_min: int = 60,
    price: int | None = 1200,
    status: str = "completed",
    starts_at: datetime | None = None,
) -> str:
    """Урок в БД с синхронизированным списанием; возвращает id урока."""
    with SessionLocal() as session:
        lesson = Lesson(
            student_id=student_id,
            type="individual",
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


def _settings(tutor_id: str, **values) -> None:
    """Настройки репетитора отдельной сессией, как страница профиля."""
    with SessionLocal() as session:
        save_settings(session, tutor_id, values)


def _enable_npd(tutor_id: str) -> None:
    """Включает флаг НПД: нужен для проверки совместимости блоков."""
    with SessionLocal() as session:
        row = session.get(TutorSettings, tutor_id)
        if row is None:
            row = TutorSettings(tutor_id=tutor_id, **default_values())
            session.add(row)
        row.npd_enabled = True
        session.commit()


# --------------------------------------------------------------------------
# Формула: та же, что у «Статистики»
# --------------------------------------------------------------------------


def test_preparation_minutes_uses_coefficient():
    """60 мин × 0.7 → 42, × 1.2 → 72; нет уроков или коэффициент 0 → 0."""
    assert preparation_minutes(60, 0.7) == 42
    assert preparation_minutes(60, 1.2) == 72
    assert preparation_minutes(0, 0.7) == 0
    assert preparation_minutes(60, 0) == 0
    assert preparation_minutes(60, -1) == 0


def test_coefficient_label_formats_decimal():
    """Коэффициент для подписи — «0,7» и «1,25», без хвостовых нулей."""
    assert coefficient_label(Decimal("0.70")) == "0,7"
    assert coefficient_label(Decimal("1.25")) == "1,25"
    assert coefficient_label(Decimal("2.00")) == "2"


def test_real_rate_insight_is_none_without_base():
    """Нет подготовки, ставки или реальной ставки — совета нет."""
    assert real_rate_insight(nominal=1200, real=1200, coefficient=0) is None
    assert real_rate_insight(nominal=None, real=None, coefficient=0.7) is None
    assert real_rate_insight(nominal=1200, real=None, coefficient=0.7) is None


def test_real_rate_insight_names_target_price():
    """Совет называет реальную ставку и цену, при которой ставка вернётся."""
    text = real_rate_insight(nominal=1500, real=1000, coefficient=0.5)
    assert text is not None
    assert f"{_money(1000)}/ч" in text
    assert "поднять цену до" in text
    # 1 500 × (1 + 0.5) = 2 250 — пример из ТЗ.
    assert f"{_money(2250)}/ч" in text
    assert "сократить время подготовки" in text


# --------------------------------------------------------------------------
# Страница: коэффициент по умолчанию (0.7)
# --------------------------------------------------------------------------


def test_default_coefficient_shows_preparation_and_real_rate(
    client, tutor_factory, student_factory
):
    """Час урока за 1 200 ₽: + 42 мин подготовки и реальная ставка 706 ₽/ч."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id, first_name="Аня")
    _lesson(tutor_id, student_id=student_id, duration_min=60, price=1200)

    html = client.get("/tutor/finance").text
    compare = _compare_block(html)

    # Карточка «Проведено часов» остаётся по урокам, подготовка — ниже.
    assert _kpi_value(html, "Проведено часов") == "1 ч"
    assert "+ 42 мин на подготовку" in html
    # Номинальная ставка на месте, рядом — реальная: 1 200 / 1.7 ч.
    assert f"Средняя стоимость часа: <strong>{_money(1200)}/ч</strong>" in compare
    assert f"Реальная стоимость часа: <strong>{_money(706)}/ч</strong>" in compare
    assert "Проведено: 1 ч" in compare
    # Подсказка о коэффициенте и совет по цене.
    assert "коэффициенту 0,7" in compare
    assert "поднять цену до" in compare
    assert f"{_money(2040)}/ч" in compare


def test_saved_coefficient_changes_preparation_and_rate(
    client, tutor_factory, student_factory
):
    """Коэффициент 1.2: + 1 ч 12 мин подготовки, реальная ставка 545 ₽/ч."""
    tutor_id = _login(client, tutor_factory)
    _settings(tutor_id, preparation_coefficient=Decimal("1.20"))
    student_id = student_factory(tutor_id=tutor_id)
    _lesson(tutor_id, student_id=student_id, duration_min=60, price=1200)

    html = client.get("/tutor/finance").text
    compare = _compare_block(html)

    assert "+ 1 ч 12 мин на подготовку" in compare
    assert f"Реальная стоимость часа: <strong>{_money(545)}/ч</strong>" in compare
    assert "коэффициенту 1,2" in compare
    # 1 200 × (1 + 1.2) = 2 640.
    assert f"{_money(2640)}/ч" in compare


# --------------------------------------------------------------------------
# Пустые состояния: страница выглядит как до изменения
# --------------------------------------------------------------------------


def test_zero_coefficient_keeps_page_as_before(client, tutor_factory, student_factory):
    """Коэффициент 0: ни строк подготовки, ни реальной ставки, ни совета."""
    tutor_id = _login(client, tutor_factory)
    _settings(tutor_id, preparation_coefficient=Decimal(0))
    student_id = student_factory(tutor_id=tutor_id)
    _lesson(tutor_id, student_id=student_id, duration_min=60, price=1200)

    html = client.get("/tutor/finance").text
    compare = _compare_block(html)

    assert "на подготовку" not in html
    assert "Реальная стоимость часа" not in html
    assert "поднять цену" not in html
    assert "коэффициенту" not in html
    # Номинальные значения не изменились.
    assert "Проведено: 1 ч" in compare
    assert f"Средняя стоимость часа: <strong>{_money(1200)}/ч</strong>" in compare


def test_no_completed_lessons_gives_no_preparation(
    client, tutor_factory, student_factory
):
    """Только запланированный урок: часов нет, подготовки и ставок тоже."""
    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    _lesson(tutor_id, student_id=student_id, status="planned", price=1200)

    html = client.get("/tutor/finance").text
    compare = _compare_block(html)

    assert _kpi_value(html, "Проведено часов") == "0 мин"
    assert "на подготовку" not in html
    assert "Реальная стоимость часа" not in html
    assert "поднять цену" not in html
    assert "Средняя стоимость часа: <strong>—</strong>" in compare


# --------------------------------------------------------------------------
# Совместимость и изоляция
# --------------------------------------------------------------------------


def test_preparation_is_isolated_between_tutors(
    client, tutor_factory, student_factory
):
    """Коэффициент и уроки чужого репетитора не попадают в сводку."""
    stranger_tutor = tutor_factory(name="Чужой", email="stranger-prep@example.com")
    _settings(stranger_tutor, preparation_coefficient=Decimal("5.00"))
    stranger_student = student_factory(tutor_id=stranger_tutor, first_name="Чужак")
    _lesson(stranger_tutor, student_id=stranger_student, duration_min=180, price=9000)

    tutor_id = _login(client, tutor_factory)
    student_id = student_factory(tutor_id=tutor_id)
    _lesson(tutor_id, student_id=student_id, duration_min=60, price=1200)

    html = client.get("/tutor/finance").text
    assert _money(9000) not in html
    # У чужого репетитора подготовка была бы 15 ч (180 мин × 5).
    assert "+ 15 ч на подготовку" not in html
    assert "коэффициенту 5" not in html
    assert "коэффициенту 0,7" in html
    assert "+ 42 мин на подготовку" in html


def test_preparation_shown_with_npd_enabled(
    client, tutor_factory, student_factory
):
    """НПД включён: подготовка и реальная ставка выводятся, налог на месте."""
    tutor_id = _login(client, tutor_factory)
    _enable_npd(tutor_id)
    student_id = student_factory(tutor_id=tutor_id, payer_type="individual")
    _lesson(tutor_id, student_id=student_id, duration_min=60, price=1200)

    html = client.get("/tutor/finance").text
    compare = _compare_block(html)

    assert "− Налог НПД (расчётный)" in compare
    assert "= Чистая прибыль (с учётом налогов)" in compare
    assert "+ 42 мин на подготовку" in compare
    assert f"Реальная стоимость часа: <strong>{_money(706)}/ч</strong>" in compare
    assert "поднять цену до" in compare
