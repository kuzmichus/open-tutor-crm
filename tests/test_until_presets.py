"""Пресеты «До даты» панели расписания серии.

Значения берутся из настроек календаря репетитора: кварталы хранятся
«ММ-ДД» без года (design D6 change tutor-profile-settings), пресет
подставляет ближайшую будущую дату такого дня. Проверяются сервис
(дефолты, сдвиг на следующий год, кривое значение в БД) и чипы в форме
создания урока.
"""

from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.database import SessionLocal
from app.lesson.services.until_presets import until_presets
from app.tutor.services.settings import save_settings

PASSWORD = "Секретный-Пароль-1"

DEFAULT_QUARTERS = ("10-25", "12-25", "03-20", "05-25")

QUARTER_LABELS = (
    "До конца I четв.",
    "До конца II четв.",
    "До конца III четв.",
    "До конца IV четв.",
)


def _expected_value(month_day: str) -> str:
    """Ближайшая будущая дата дня «ММ-ДД» — та же логика, что в сервисе."""
    today = datetime.now(UTC).date()
    month, day = (int(part) for part in month_day.split("-"))
    value = date(today.year, month, day)
    if value < today:
        value = date(today.year + 1, month, day)
    return value.isoformat()


def test_default_settings_give_four_quarter_presets():
    """Дефолтные четверти настроек — четыре чипа с ближайшими датами.

    Строки настроек нет — сервис отдаёт дефолты; репетитор-заглушка:
    чтению нужны только id и зона (UTC — тесты не зависят от системной
    зоны машины, как в test_homework.py).
    """
    with SessionLocal() as db:
        presets = until_presets(db, SimpleNamespace(id="ghost", timezone="UTC"))

    assert [preset["label"] for preset in presets] == list(QUARTER_LABELS)
    assert [preset["value"] for preset in presets] == [
        _expected_value(month_day) for month_day in DEFAULT_QUARTERS
    ]
    # Подсказка чипа — конкретная дата «ДД.ММ.ГГГГ», видно до клика.
    for preset in presets:
        assert preset["title"] == date.fromisoformat(preset["value"]).strftime(
            "%d.%m.%Y"
        )


def test_passed_quarter_moves_to_next_year(tutor_factory):
    """Прошедшая дата четверти подставляется следующим годом.

    «До конца I четв.» в мае — это конец I четверти будущего учебного
    года, а не дата годичной давности: until_date в прошлом серию бы
    не сгенерировала.
    """
    tutor_id = tutor_factory(email="until-presets-year@example.com")
    with SessionLocal() as db:
        save_settings(db, tutor_id, {"quarter1_end": "09-30"})
        presets = until_presets(db, SimpleNamespace(id=tutor_id, timezone="UTC"))

    # 30 сентября к моменту тестов (после сентября) прошло — ожидаем
    # следующий год: дата не в прошлом.
    expected = _expected_value("09-30")
    assert presets[0]["value"] == expected
    assert date.fromisoformat(expected) >= datetime.now(UTC).date()


def test_broken_quarter_value_is_skipped(tutor_factory):
    """Кривое значение в БД не ломает форму: такой пресет пропускается.

    Валидация формы календаря не пускает «ММ-ДД» вне формата, но строка
    могла появиться до введения валидации — страница не должна падать.
    """
    tutor_id = tutor_factory(email="until-presets-bad@example.com")
    with SessionLocal() as db:
        settings = save_settings(db, tutor_id, {})
        settings.quarter3_end = "13-99"
        db.commit()
        presets = until_presets(db, SimpleNamespace(id=tutor_id, timezone="UTC"))

    assert len(presets) == 3
    assert "III" not in " ".join(preset["label"] for preset in presets)


def test_create_form_shows_presets_from_saved_settings(client, tutor_factory):
    """Форма создания показывает чипы по сохранённым настройкам календаря."""
    email = "until-presets-ui@example.com"
    tutor_id = tutor_factory(email=email, password=PASSWORD)
    with SessionLocal() as db:
        save_settings(db, tutor_id, {"quarter2_end": "01-15"})
    client.post("/tutor/login", data={"email": email, "password": PASSWORD})

    page = client.get("/tutor/lessons/new").text

    # II четверть взята из настроек (15 января ближайшего будущего года),
    # I — из дефолта (12-25 переопределён, 10-25 остался).
    assert f"setUntil('{_expected_value('01-15')}')" in page
    assert f"setUntil('{_expected_value('10-25')}')" in page
    assert "До конца II четв." in page
