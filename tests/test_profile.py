"""Тесты страницы настроек репетитора (`/tutor/profile`).

Страница — четыре вкладки (профиль, безопасность, уведомления,
календарь). Поведение проверяется через HTTP тем же путём, что у
пользователя: те же маршруты и поля формы, разметка — по тексту и
атрибутам.
"""

import re

from app.database import SessionLocal
from app.tutor.models.tutor import Tutor
from app.tutor.models.tutor_settings import TutorSettings

PASSWORD = "Секретный-Пароль-1"


def _register_and_login(client, email, name="Настройки", password=PASSWORD):
    client.post(
        "/tutor/register",
        data={
            "name": name,
            "email": email,
            "password": password,
            "password_confirm": password,
        },
    )
    return client.post(
        "/tutor/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def _login(client, email="profile-user@example.com", name="Профильный", password=PASSWORD):
    return _register_and_login(client, email=email, name=name, password=password)


def _tutor_by_email(email):
    with SessionLocal() as db:
        return db.query(Tutor).filter_by(email=email).one()


# ---------------------------------------------------------------------------
# Доступ и вкладки
# ---------------------------------------------------------------------------


def test_redirect_to_login_without_session(client):
    response = client.get("/tutor/profile", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_post_without_session_redirects_to_login(client):
    """POST-роуты страницы тоже закрыты сессией."""
    response = client.post("/tutor/profile/save", data={"name": "X"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_default_tab_is_profile(client):
    _login(client)
    response = client.get("/tutor/profile")
    assert response.status_code == 200
    # Заголовок страницы — «Профиль» и в тайтле вкладки, и в h1.
    assert "<title>Профиль — Open Tutor CRM</title>" in response.text
    assert "<h1>Профиль</h1>" in response.text
    assert "Профиль, безопасность, уведомления и календарь" in response.text
    # Активна вкладка «Профиль»: только у неё aria-current.
    assert 'aria-current="page"\n                   href="/tutor/profile?tab=profile"' in response.text


def test_all_four_tabs_present(client):
    _login(client)
    response = client.get("/tutor/profile")
    for tab in ("profile", "security", "notifications", "calendar"):
        assert f"/tutor/profile?tab={tab}" in response.text


def test_tab_selected_by_query_param(client):
    _login(client)
    security = client.get("/tutor/profile", params={"tab": "security"}).text
    assert 'aria-current="page"\n                   href="/tutor/profile?tab=security"' in security
    # Форма безопасности на своей вкладке.
    assert 'name="new_password"' in security

    calendar = client.get("/tutor/profile", params={"tab": "calendar"}).text
    assert 'href="/tutor/profile?tab=calendar"' in calendar
    assert 'name="quarter1_end"' in calendar


def test_unknown_tab_falls_back_to_profile(client):
    _login(client)
    response = client.get("/tutor/profile", params={"tab": "hacker"})
    assert 'aria-current="page"\n                   href="/tutor/profile?tab=profile"' in response.text


def test_profile_shows_own_data(client):
    _login(client)
    profile = client.get("/tutor/profile")
    assert profile.status_code == 200
    assert 'value="Профильный"' in profile.text
    # Email живёт на вкладке «Безопасность».
    security = client.get("/tutor/profile", params={"tab": "security"}).text
    assert 'value="profile-user@example.com"' in security


def test_profile_shows_optional_fields(client, tutor_factory):
    """Заданные необязательные поля подставляются в форму профиля."""
    tutor_factory(
        name="Полный Профиль",
        email="full@example.com",
        password=PASSWORD,
        phone="+7 900 000-00-00",
        about="Рассказ о себе",
        experience="10 лет",
        hourly_rate=2000,
    )
    client.post("/tutor/login", data={"email": "full@example.com", "password": PASSWORD})
    response = client.get("/tutor/profile")
    for fragment in (
        'value="+7 900 000-00-00"',
        "Рассказ о себе",
        'value="10 лет"',
        'value="2000"',
    ):
        assert fragment in response.text


# ---------------------------------------------------------------------------
# Изоляция по репетитору
# ---------------------------------------------------------------------------


def test_profile_hides_other_tutors_data(client, tutor_factory):
    """Вошедший видит только свои данные, а не чужие."""
    tutor_factory(name="Чужой Репетитор", email="chuzhoy@example.com", password=PASSWORD)
    _login(client, email="mine@example.com", name="Мой")

    response = client.get("/tutor/profile")
    assert "Мой" in response.text
    assert "Чужой Репетитор" not in response.text
    assert "chuzhoy@example.com" not in response.text


def test_save_touches_only_own_row(client, tutor_factory):
    """Сохранение профиля не задевает карточку другого репетитора."""
    tutor_factory(name="Чужой Репетитор", email="chuzhoy@example.com", password=PASSWORD)
    _login(client, email="mine@example.com", name="Мой")

    client.post("/tutor/profile/save", data={"name": "Моё Новое Имя"})
    assert _tutor_by_email("chuzhoy@example.com").name == "Чужой Репетитор"
    assert _tutor_by_email("mine@example.com").name == "Моё Новое Имя"


# ---------------------------------------------------------------------------
# Вкладка «Профиль»: сохранение личных данных
# ---------------------------------------------------------------------------


def test_profile_save_updates_fields(client):
    _login(client)
    response = client.post(
        "/tutor/profile/save",
        data={
            "name": "Сергей",
            "phone": "+7 999 000-00-00",
            "about": "Репетитор с опытом",
            "hourly_rate": "2000.50",
            "experience": "5",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/profile?tab=profile&saved=1"

    tutor = _tutor_by_email("profile-user@example.com")
    assert tutor.name == "Сергей"
    assert tutor.phone == "+7 999 000-00-00"
    assert tutor.about == "Репетитор с опытом"
    assert str(tutor.hourly_rate) == "2000.50"
    assert tutor.experience == "5"


def test_profile_save_shows_saved_notice(client):
    _login(client)
    client.post("/tutor/profile/save", data={"name": "Сергей"})
    response = client.get("/tutor/profile", params={"tab": "profile", "saved": "1"})
    assert "Изменения сохранены" in response.text


def test_profile_save_empty_name_shows_error(client):
    _login(client)
    response = client.post("/tutor/profile/save", data={"name": "  "})
    assert response.status_code == 200
    assert "Укажите имя." in response.text
    # Сохранения не было.
    assert _tutor_by_email("profile-user@example.com").name == "Профильный"


def test_profile_save_negative_rate_shows_error(client):
    _login(client)
    response = client.post("/tutor/profile/save", data={"name": "Сергей", "hourly_rate": "-5"})
    assert "Стоимость часа" in response.text


# ---------------------------------------------------------------------------
# Вкладка «Безопасность»: email и пароль
# ---------------------------------------------------------------------------


def test_security_email_change(client):
    _login(client)
    response = client.post(
        "/tutor/profile/security",
        data={"email": "new-address@example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/profile?tab=security&saved=1"

    # Вход работает по новому email.
    assert _tutor_by_email("new-address@example.com") is not None
    login = client.post(
        "/tutor/login",
        data={"email": "new-address@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert login.status_code == 303


def test_security_busy_email_shows_error(client, tutor_factory):
    tutor_factory(name="Другой", email="busy@example.com", password=PASSWORD)
    _login(client)

    response = client.post("/tutor/profile/security", data={"email": "busy@example.com"})
    assert "уже зарегистрирован" in response.text
    # Свой email не изменился.
    assert _tutor_by_email("profile-user@example.com") is not None


def test_security_own_email_not_a_conflict(client):
    _login(client)
    response = client.post(
        "/tutor/profile/security",
        data={"email": "profile-user@example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_security_password_change(client):
    _login(client)
    response = client.post(
        "/tutor/profile/security",
        data={
            "email": "profile-user@example.com",
            "new_password": "Новый-Пароль-2",
            "new_password_confirm": "Новый-Пароль-2",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    # Старый пароль больше не подходит, новый — работает.
    old = client.post(
        "/tutor/login",
        data={"email": "profile-user@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert old.status_code == 200  # страница входа с ошибкой
    new = client.post(
        "/tutor/login",
        data={"email": "profile-user@example.com", "password": "Новый-Пароль-2"},
        follow_redirects=False,
    )
    assert new.status_code == 303


def test_security_password_mismatch_shows_error(client):
    _login(client)
    response = client.post(
        "/tutor/profile/security",
        data={"email": "profile-user@example.com", "new_password": "a", "new_password_confirm": "b"},
    )
    assert "Пароли не совпадают." in response.text
    # Пароль не поменялся: старый всё ещё работает.
    assert client.post(
        "/tutor/login",
        data={"email": "profile-user@example.com", "password": PASSWORD},
        follow_redirects=False,
    ).status_code == 303


def test_password_never_rendered(client):
    """Ни открытый пароль, ни его хеш не попадают в HTML страницы."""
    _login(client)
    response = client.get("/tutor/profile")
    with SessionLocal() as db:
        tutor = db.query(Tutor).filter_by(email="profile-user@example.com").one()
    assert PASSWORD not in response.text
    assert tutor.password_hash not in response.text


# ---------------------------------------------------------------------------
# Вкладка «Уведомления»: переключатели
# ---------------------------------------------------------------------------

_TOGGLE_NAMES = (
    "notify_lesson_reminder",
    "notify_lesson_confirmation",
    "notify_daily_digest",
    "notify_cancellation",
    "notify_homework",
    "notify_debtors_weekly",
    "notify_low_balance",
    "notify_insufficient_funds",
    "notify_birthday",
)


def _notifications_page(client, **params):
    return client.get("/tutor/profile", params={"tab": "notifications", **params}).text


def test_notifications_defaults(client):
    """До первого сохранения: всё включено, напоминание за 1 час, 09:00, порог 0."""
    _login(client)
    html = _notifications_page(client)
    for name in _TOGGLE_NAMES:
        assert re.search(rf'name="{name}"\s+checked', html), name
    assert re.search(r'name="reminder_offsets" value="60"\s+checked', html)
    assert not re.search(r'name="reminder_offsets" value="15"\s+checked', html)
    assert 'name="digest_time" value="09:00"' in html
    assert 'name="low_balance_threshold" value="0"' in html


def test_notifications_save(client):
    _login(client)
    data = {
        "digest_time": "08:30",
        "low_balance_threshold": "500",
        "reminder_offsets": ["15", "1440"],
        # Включены только два тоггла, остальные не шлются (чекбоксы).
        "notify_lesson_reminder": "on",
        "notify_homework": "on",
    }
    response = client.post("/tutor/profile/notifications", data=data, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/profile?tab=notifications&saved=1"

    with SessionLocal() as db:
        settings = db.get(TutorSettings, _tutor_by_email("profile-user@example.com").id)
    assert settings.notify_lesson_reminder is True
    assert settings.notify_homework is True
    assert settings.notify_daily_digest is False
    assert settings.notify_cancellation is False
    assert settings.reminder_offsets == [15, 1440]
    assert settings.digest_time == "08:30"
    assert settings.low_balance_threshold == 500

    # Повторный показ вкладки отражает сохранённое состояние.
    html = _notifications_page(client)
    assert re.search(r'name="notify_homework"\s+checked', html)
    assert not re.search(r'name="notify_daily_digest"\s+checked', html)
    assert 'name="digest_time" value="08:30"' in html
    assert 'name="low_balance_threshold" value="500"' in html


def test_notifications_birthday_toggle_is_saved(client):
    """«День рождения» сохраняется и показывается; отдельного поля времени нет."""
    _login(client)
    response = client.post(
        "/tutor/profile/notifications",
        data={"digest_time": "09:00", "low_balance_threshold": "0", "notify_birthday": "on"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        settings = db.get(TutorSettings, _tutor_by_email("profile-user@example.com").id)
    assert settings.notify_birthday is True

    html = _notifications_page(client)
    assert re.search(r'name="notify_birthday"\s+checked', html)
    # Время рассылки дней рождения — общее поле «Время отправки».
    assert html.count('name="digest_time"') == 1
    assert 'name="birthday_time"' not in html


def test_notifications_invalid_time_shows_error(client):
    _login(client)
    response = client.post(
        "/tutor/profile/notifications",
        data={"digest_time": "25:99", "low_balance_threshold": "0"},
    )
    assert "ЧЧ:ММ" in response.text


def test_notifications_negative_threshold_shows_error(client):
    _login(client)
    response = client.post(
        "/tutor/profile/notifications",
        data={"digest_time": "09:00", "low_balance_threshold": "-1"},
    )
    assert "Порог низкого баланса" in response.text


# ---------------------------------------------------------------------------
# Вкладка «Календарь»: пояс, учебный год, уроки по умолчанию
# ---------------------------------------------------------------------------


def _calendar_page(client, **params):
    return client.get("/tutor/profile", params={"tab": "calendar", **params}).text


def test_workday_defaults_without_settings_row(client):
    """1.1: без строки в БД `get_settings` отдаёт дефолт рабочего времени."""
    from app.tutor.services.settings import get_settings

    _login(client)
    tutor = _tutor_by_email("profile-user@example.com")
    with SessionLocal() as db:
        assert db.get(TutorSettings, tutor.id) is None
        settings = get_settings(db, tutor.id)

    assert settings.workday_start == "06:00"
    assert settings.workday_end == "23:00"


# ---------------------------------------------------------------------------
# Разбор рабочего времени (сервис формы вкладки «Календарь»)
# ---------------------------------------------------------------------------


def _calendar_values(**overrides):
    from app.tutor.services.calendar_form import parse_calendar_form

    form = {
        "timezone": "UTC",
        "quarter1_end": "10-25",
        "quarter2_end": "12-25",
        "quarter3_end": "03-20",
        "quarter4_end": "05-25",
        "default_lesson_duration": "60",
        "default_lesson_price": "",
        "workday_start": "09:00",
        "workday_end": "18:00",
    }
    form.update(overrides)
    return parse_calendar_form(form)


def test_calendar_form_accepts_whole_hour_interval():
    """2.1: валидный интервал целых часов разбирается в значения записи."""
    values, errors = _calendar_values()
    assert errors == []
    assert values["workday_start"] == "09:00"
    assert values["workday_end"] == "18:00"


def test_calendar_form_rejects_broken_format():
    """2.1: строка не «ЧЧ:ММ» — ошибка, значений записи нет."""
    values, errors = _calendar_values(workday_start="9 утра")
    assert values is None
    assert any("Рабочее время" in message for message in errors)


def test_calendar_form_rejects_non_whole_hours():
    """2.1: минуты не 00 отбраковываются — сетка моделируется целым часом."""
    values, errors = _calendar_values(workday_start="09:30")
    assert values is None
    assert any("Рабочее время" in message for message in errors)


def test_calendar_form_rejects_reversed_interval():
    """2.1: конец раньше начала (в т.ч. «равно») — ошибка порядка."""
    values, errors = _calendar_values(workday_start="18:00", workday_end="09:00")
    assert values is None
    assert any("раньше окончания" in message for message in errors)

    values, errors = _calendar_values(workday_start="09:00", workday_end="09:00")
    assert values is None
    assert any("раньше окончания" in message for message in errors)


def test_calendar_defaults(client):
    _login(client)
    html = _calendar_page(client)
    assert 'name="quarter1_end"\n                       value="10-25"' in html
    assert 'name="default_lesson_duration"\n                       value="60"' in html
    assert 'name="default_lesson_price"\n                       value=""' in html


def test_calendar_save(client):
    _login(client)
    data = {
        "timezone": "Europe/Samara",
        "quarter1_end": "10-25",
        "quarter2_end": "12-25",
        "quarter3_end": "03-20",
        "quarter4_end": "05-25",
        "workday_start": "09:00",
        "workday_end": "18:00",
        "default_lesson_duration": "90",
        "default_lesson_price": "1500",
    }
    response = client.post("/tutor/profile/calendar", data=data, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/profile?tab=calendar&saved=1"

    tutor = _tutor_by_email("profile-user@example.com")
    assert tutor.timezone == "Europe/Samara"
    with SessionLocal() as db:
        settings = db.get(TutorSettings, tutor.id)
    assert settings.default_lesson_duration == 90
    assert settings.default_lesson_price == 1500
    assert settings.workday_start == "09:00"
    assert settings.workday_end == "18:00"

    html = _calendar_page(client)
    assert 'name="timezone"\n                           value="Europe/Samara"' in html
    assert 'name="default_lesson_duration"\n                       value="90"' in html
    assert 'name="default_lesson_price"\n                       value="1500"' in html
    # Сохранённое рабочее время выделено в своих селектах (не перепутаны).
    start_select = re.search(
        r'<select class="input" id="tutor-workday-start".*?</select>', html, re.S
    )
    end_select = re.search(
        r'<select class="input" id="tutor-workday-end".*?</select>', html, re.S
    )
    assert start_select and '<option value="09:00" selected>' in start_select.group(0)
    assert end_select and '<option value="18:00" selected>' in end_select.group(0)


def test_calendar_workday_defaults_shown_on_tab(client):
    """2.2: до первого сохранения в селектах дефолт 06:00–23:00."""
    _login(client)
    html = _calendar_page(client)
    assert '<option value="06:00" selected>06:00</option>' in html
    assert '<option value="23:00" selected>23:00</option>' in html


def test_calendar_bad_quarter_shows_error(client):
    _login(client)
    response = client.post(
        "/tutor/profile/calendar",
        data={"timezone": "UTC", "quarter1_end": "25-10"},
    )
    assert "ММ-ДД" in response.text


def test_calendar_bad_duration_shows_error(client):
    """Длительность — из закрытого списка длительностей урока."""
    _login(client)
    response = client.post(
        "/tutor/profile/calendar",
        data={"timezone": "UTC", "default_lesson_duration": "61"},
    )
    assert "Длительность урока по умолчанию" in response.text


def test_calendar_bad_timezone_shows_error(client):
    _login(client)
    response = client.post("/tutor/profile/calendar", data={"timezone": "Mars/Olympus"})
    assert "Часовой пояс" in response.text


def test_calendar_reversed_workday_shows_error(client):
    """2.3: «18:00–09:00» — сохранения нет, ошибка порядка на вкладке."""
    _login(client)
    response = client.post("/tutor/profile/calendar", data={
        "timezone": "UTC",
        "workday_start": "18:00",
        "workday_end": "09:00",
    })
    assert response.status_code == 200
    assert "начало должно быть раньше окончания" in response.text
    # Ошибка показывается на вкладке «Календарь».
    assert 'name="workday_start"' in response.text

    tutor = _tutor_by_email("profile-user@example.com")
    with SessionLocal() as db:
        assert db.get(TutorSettings, tutor.id) is None


def test_calendar_workday_isolation(client, tutor_factory):
    """2.3: сохранение рабочего времени не задевает настройки другого."""
    tutor_factory(email="workday-other@example.com", password=PASSWORD)
    _login(client, email="workday-mine@example.com", name="Мой")

    response = client.post("/tutor/profile/calendar", data={
        "timezone": "UTC",
        "quarter1_end": "10-25",
        "quarter2_end": "12-25",
        "quarter3_end": "03-20",
        "quarter4_end": "05-25",
        "workday_start": "09:00",
        "workday_end": "18:00",
        "default_lesson_duration": "60",
    }, follow_redirects=False)
    assert response.status_code == 303

    with SessionLocal() as db:
        other = db.get(TutorSettings, _tutor_by_email("workday-other@example.com").id)
        assert other is None  # у чужого строки настроек нет и не появилось
        mine = db.get(TutorSettings, _tutor_by_email("workday-mine@example.com").id)
        assert mine.workday_start == "09:00"
        assert mine.workday_end == "18:00"
