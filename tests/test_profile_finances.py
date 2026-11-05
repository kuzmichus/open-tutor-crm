"""Тесты вкладки «Финансы» профиля: блок «Налоги» (НПД).

Проверяется путь пользователя через HTTP: вкладка в навигации, значения по
умолчанию до первого сохранения, сохранение и повторный показ, валидация
и изоляция настроек между репетиторами.
"""

import re
from decimal import Decimal

from app.database import SessionLocal
from app.tutor.models.tutor import Tutor
from app.tutor.models.tutor_settings import TutorSettings
from app.tutor.services.finances_form import parse_finances_form
from app.tutor.services.settings import get_settings

PASSWORD = "Секретный-Пароль-1"


def _login(client, email="finances-user@example.com", name="Финансовый"):
    client.post(
        "/tutor/register",
        data={
            "name": name,
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )
    return client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )


def _tutor_by_email(email):
    with SessionLocal() as db:
        return db.query(Tutor).filter_by(email=email).one()


def _settings(email="finances-user@example.com"):
    tutor = _tutor_by_email(email)
    with SessionLocal() as db:
        return db.get(TutorSettings, tutor.id)


def _finances_page(client, **params):
    return client.get("/tutor/profile", params={"tab": "finances", **params}).text


def _field_value(html, name):
    """Значение `value` у поля формы с именем `name` (None — поля нет).

    Проверка не зависит от переносов строк и отступов в разметке.
    """
    match = re.search(rf'name="{re.escape(name)}"[^>]*?value="([^"]*)"', html)
    return match.group(1) if match else None


def _is_checked(html, name):
    """Отмечен ли чекбокс/переключатель с именем `name`."""
    return bool(re.search(rf'name="{re.escape(name)}"\s+checked', html))


def _payload(**overrides):
    """Полный набор полей блока «Налоги» для POST."""
    data = {
        "npd_tax_rate_individual": "4",
        "npd_tax_rate_legal_entity": "6",
        "npd_annual_income_limit": "2400000",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Доступ и навигация
# ---------------------------------------------------------------------------


def test_finances_tab_requires_session(client):
    response = client.get("/tutor/profile", params={"tab": "finances"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_post_finances_requires_session(client):
    response = client.post("/tutor/profile/finances", data=_payload(), follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_finances_tab_present_and_active(client):
    _login(client)
    html = client.get("/tutor/profile").text
    assert "/tutor/profile?tab=finances" in html
    assert "Финансы" in html

    html = _finances_page(client)
    assert 'aria-current="page"\n                   href="/tutor/profile?tab=finances"' in html


def test_finances_tab_shows_tax_block(client):
    """Блок «Налоги»: переключатель НПД, две ставки и лимит дохода."""
    _login(client)
    html = _finances_page(client)
    assert "Налоги" in html
    assert "Является ли пользователь плательщиком НПД (самозанятым)" in html
    assert 'name="npd_enabled"' in html
    assert 'name="npd_tax_rate_individual"' in html
    assert 'name="npd_tax_rate_legal_entity"' in html
    assert 'name="npd_annual_income_limit"' in html
    # Подписи под полями ставок.
    assert "если плательщик" in html
    assert "физическим лицом" in html
    assert "юридическим лицом или ИП" in html


# ---------------------------------------------------------------------------
# Значения по умолчанию
# ---------------------------------------------------------------------------


def test_finances_defaults_without_settings_row(client):
    """До первого сохранения: не плательщик, 4 %, 6 %, 2 400 000 ₽."""
    _login(client)
    tutor = _tutor_by_email("finances-user@example.com")
    with SessionLocal() as db:
        assert db.get(TutorSettings, tutor.id) is None
        settings = get_settings(db, tutor.id)
    assert settings.npd_enabled is False
    assert settings.npd_tax_rate_individual == Decimal("4.00")
    assert settings.npd_tax_rate_legal_entity == Decimal("6.00")
    assert settings.npd_annual_income_limit == 2_400_000

    html = _finances_page(client)
    assert not _is_checked(html, "npd_enabled")
    assert _field_value(html, "npd_tax_rate_individual") == "4"
    assert _field_value(html, "npd_tax_rate_legal_entity") == "6"
    assert _field_value(html, "npd_annual_income_limit") == "2400000"


# ---------------------------------------------------------------------------
# Сохранение
# ---------------------------------------------------------------------------


def test_finances_save_and_show(client):
    _login(client)
    response = client.post(
        "/tutor/profile/finances",
        data=_payload(
            npd_enabled="on",
            npd_tax_rate_individual="5",
            npd_tax_rate_legal_entity="7.5",
            npd_annual_income_limit="1800000",
        ),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/profile?tab=finances&saved=1"

    settings = _settings()
    assert settings.npd_enabled is True
    assert settings.npd_tax_rate_individual == Decimal("5.00")
    assert settings.npd_tax_rate_legal_entity == Decimal("7.50")
    assert settings.npd_annual_income_limit == 1_800_000

    html = _finances_page(client)
    assert _is_checked(html, "npd_enabled")
    assert _field_value(html, "npd_tax_rate_individual") == "5"
    assert _field_value(html, "npd_tax_rate_legal_entity") == "7.5"
    assert _field_value(html, "npd_annual_income_limit") == "1800000"
    assert "Изменения сохранены" in _finances_page(client, saved="1")


def test_finances_comma_as_decimal_separator(client):
    _login(client)
    response = client.post(
        "/tutor/profile/finances",
        data=_payload(npd_tax_rate_individual="4,5"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert _settings().npd_tax_rate_individual == Decimal("4.50")
    assert _field_value(_finances_page(client), "npd_tax_rate_individual") == "4.5"


def test_finances_income_limit_with_spaces(client):
    """Сумма с пробелами внутри числа принимается: «2 400 000» = 2400000."""
    _login(client)
    response = client.post(
        "/tutor/profile/finances",
        data=_payload(npd_annual_income_limit="2 400 000"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert _settings().npd_annual_income_limit == 2_400_000


def test_finances_empty_fields_return_defaults(client):
    """Пустые числовые поля возвращают значения по умолчанию, а не ошибку."""
    _login(client)
    client.post(
        "/tutor/profile/finances",
        data=_payload(npd_tax_rate_individual="9", npd_annual_income_limit="1000000"),
        follow_redirects=False,
    )
    response = client.post(
        "/tutor/profile/finances",
        data={
            "npd_tax_rate_individual": "",
            "npd_tax_rate_legal_entity": "",
            "npd_annual_income_limit": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    settings = _settings()
    assert settings.npd_tax_rate_individual == Decimal("4.00")
    assert settings.npd_tax_rate_legal_entity == Decimal("6.00")
    assert settings.npd_annual_income_limit == 2_400_000


def test_finances_toggle_off_is_saved(client):
    """Выключенный переключатель сохраняется как False и не сбрасывает поля."""
    _login(client)
    client.post(
        "/tutor/profile/finances",
        data=_payload(npd_enabled="on", npd_tax_rate_individual="5"),
        follow_redirects=False,
    )
    assert _settings().npd_enabled is True

    # Чекбокс не отмечен — поле в форму не приходит.
    response = client.post(
        "/tutor/profile/finances",
        data=_payload(npd_tax_rate_individual="5"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    settings = _settings()
    assert settings.npd_enabled is False
    # Ставка при выключении статуса не потерялась.
    assert settings.npd_tax_rate_individual == Decimal("5.00")


# ---------------------------------------------------------------------------
# Валидация
# ---------------------------------------------------------------------------


def test_finances_rate_out_of_range_shows_error(client):
    _login(client)
    response = client.post(
        "/tutor/profile/finances",
        data=_payload(npd_tax_rate_individual="101"),
    )
    assert response.status_code == 200
    assert "Ставка налога для физических лиц — число от 0 до 100." in response.text
    # Сохранения не было: строки настроек нет.
    assert _settings() is None


def test_finances_rate_garbage_shows_error(client):
    _login(client)
    response = client.post(
        "/tutor/profile/finances",
        data=_payload(npd_tax_rate_legal_entity="abc"),
    )
    assert response.status_code == 200
    assert "Ставка налога для юридических лиц и ИП — число от 0 до 100." in response.text
    assert _settings() is None


def test_finances_negative_limit_shows_error(client):
    _login(client)
    response = client.post(
        "/tutor/profile/finances",
        data=_payload(npd_annual_income_limit="-1"),
    )
    assert response.status_code == 200
    assert "Максимально допустимый доход" in response.text
    assert _settings() is None


def test_finances_errors_keep_entered_values(client):
    """При ошибке на вкладке остаются введённые значения, а не дефолты."""
    _login(client)
    response = client.post(
        "/tutor/profile/finances",
        data=_payload(npd_tax_rate_individual="150", npd_annual_income_limit="1000000"),
    )
    assert _field_value(response.text, "npd_tax_rate_individual") == "150"
    assert _field_value(response.text, "npd_annual_income_limit") == "1000000"


def test_finances_boundary_rates_are_accepted(client):
    """Границы 0 и 100 включены."""
    _login(client)
    response = client.post(
        "/tutor/profile/finances",
        data=_payload(npd_tax_rate_individual="0", npd_tax_rate_legal_entity="100"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    settings = _settings()
    assert settings.npd_tax_rate_individual == Decimal("0.00")
    assert settings.npd_tax_rate_legal_entity == Decimal("100.00")


# ---------------------------------------------------------------------------
# Изоляция по репетитору
# ---------------------------------------------------------------------------


def test_finances_settings_are_isolated(client, tutor_factory):
    tutor_factory(name="Чужой Репетитор", email="other-finances@example.com", password=PASSWORD)
    _login(client)
    client.post(
        "/tutor/profile/finances",
        data=_payload(npd_enabled="on", npd_tax_rate_individual="5"),
        follow_redirects=False,
    )
    assert _settings() is not None
    # У второго репетитора строки настроек не появилось.
    assert _settings("other-finances@example.com") is None

    html = _finances_page(client)
    assert _field_value(html, "npd_tax_rate_individual") == "5"


# ---------------------------------------------------------------------------
# Разбор формы (без HTTP)
# ---------------------------------------------------------------------------


def test_parse_finances_form_defaults():
    values, errors = parse_finances_form({})
    assert errors == []
    assert values == {
        "npd_enabled": False,
        "npd_tax_rate_individual": Decimal("4.00"),
        "npd_tax_rate_legal_entity": Decimal("6.00"),
        "npd_annual_income_limit": 2_400_000,
    }


def test_parse_finances_form_rejects_nan_and_infinity():
    for raw in ("NaN", "Infinity", "-Infinity"):
        values, errors = parse_finances_form({"npd_tax_rate_individual": raw})
        assert values is None
        assert errors
