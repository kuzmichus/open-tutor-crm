"""Разбор формы «Личная информация и Тарифы» (вкладка «Профиль»).

На вход — сырые значения формы и карточка вошедшего репетитора, на
выход — очищенные значения или список ошибок. Поля «Предметы» референса
в форме нет по решению владельца: `subject` остаётся как был.
"""

from decimal import Decimal, InvalidOperation


def _parse_hourly_rate(raw: str) -> tuple[Decimal | None, bool]:
    """Стоимость часа: (значение, ошибка). Пусто — None без ошибки.

    Decimal, а не float: колонка `Numeric(10, 2)`, и «1990.10» в float
    превращается в 1990.0999…, что при записи в Numeric даёт сюрпризы
    округления.
    """
    if raw == "":
        return None, False
    try:
        value = Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None, True
    if value < 0:
        return None, True
    return value, False


def parse_profile_form(form: dict) -> tuple[dict | None, list[str]]:
    """Разбирает форму профиля: (значения для записи, ошибки)."""
    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()
    about = (form.get("about") or "").strip()
    experience = (form.get("experience") or "").strip()
    rate_raw = (form.get("hourly_rate") or "").strip()

    errors: list[str] = []
    if not name:
        errors.append("Укажите имя.")

    hourly_rate, rate_error = _parse_hourly_rate(rate_raw)
    if rate_error:
        errors.append("Стоимость часа — неотрицательное число.")

    if errors:
        return None, errors

    values = {
        "name": name,
        "phone": phone or None,
        "about": about or None,
        "experience": experience or None,
        "hourly_rate": hourly_rate,
    }
    return values, []
