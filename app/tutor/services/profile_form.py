"""Разбор формы «Личная информация и Тарифы» (вкладка «Профиль»).

На вход — сырые значения формы и карточка вошедшего репетитора, на
выход — очищенные значения или список ошибок. Поля «Предметы» референса
в форме нет по решению владельца: `subject` остаётся как был.

Форма пишет в две таблицы: карточку `Tutor` (имя, телефон, о себе, ставка,
опыт) и `tutor_settings` (параметры НПД — флаг, ставки, годовой лимит).
Поэтому результат разбора — две группы значений; разделение здесь, а не
во вьюхе: правила валидации живут рядом с полями.
"""

from decimal import Decimal, InvalidOperation

from app.common.services.forms import checked, text_value
from app.tutor.models.tutor_settings import NPD_RATE_MAX_BP


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


def _parse_rate_bp(raw: str, label: str, errors: list[str]) -> int | None:
    """Ставка НПД в процентах → базисные пункты (целое).

    Проценты, а не рубли: «4» значит 4 %, запятая допустима («4,5»).
    В базисные пункты переводим целым числом (`Decimal * 100`), чтобы в
    расчёте налога не появилось float. Верхняя граница 50 % отсекает
    опечатки вроде «400» вместо «4».
    """
    raw = raw.strip().replace(",", ".")
    if not raw:
        errors.append(f"Ставка НПД {label} — число от 0 до 50.")
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        errors.append(f"Ставка НПД {label} — число от 0 до 50.")
        return None
    if not value.is_finite() or value <= 0:
        errors.append(f"Ставка НПД {label} — число от 0 до 50.")
        return None
    basis_points = value * 100
    if basis_points != basis_points.to_integral_value():
        # Две цифры после запятой — предел точности: 0.001 % уже не ставка.
        errors.append(f"Ставка НПД {label} — число от 0 до 50.")
        return None
    result = int(basis_points)
    if result > NPD_RATE_MAX_BP:
        errors.append(f"Ставка НПД {label} — число от 0 до 50.")
        return None
    return result


def _parse_income_limit(raw: str, errors: list[str]) -> int | None:
    """Годовой лимит дохода: целое число рублей больше нуля.

    Пробелы внутри числа допускаются («2 400 000» — та же сумма): отказ
    на пробеле был бы придиркой к форматированию, а не проверкой данных.
    """
    cleaned = "".join(raw.split())
    if not cleaned:
        errors.append("Годовой лимит дохода — целое число рублей больше нуля.")
        return None
    try:
        value = int(cleaned)
    except ValueError:
        errors.append("Годовой лимит дохода — целое число рублей больше нуля.")
        return None
    if value <= 0:
        errors.append("Годовой лимит дохода — целое число рублей больше нуля.")
        return None
    return value


def parse_profile_form(form: dict) -> tuple[dict | None, dict | None, list[str]]:
    """Разбирает форму профиля: (поля карточки, настройки НПД, ошибки).

    Первый словарь пишется в `Tutor`, второй — в `tutor_settings`. При
    ошибках оба `None`: частичное сохранение одной карточки при ошибке в
    другой было бы неожиданным.

    Второй словарь равен `None`, если форма не прислала маркер блока НПД
    (`npd_present`): у чекбокса отсутствие поля значит «выключено», и без
    маркера частичный POST (например, из старого клиента) молча сбросил бы
    настройки налога. Маркер ставит скрытое поле карточки НПД.
    """
    name = text_value(form, "name")
    phone = text_value(form, "phone")
    about = text_value(form, "about")
    experience = text_value(form, "experience")
    rate_raw = text_value(form, "hourly_rate")

    errors: list[str] = []
    if not name:
        errors.append("Укажите имя.")

    hourly_rate, rate_error = _parse_hourly_rate(rate_raw)
    if rate_error:
        errors.append("Стоимость часа — неотрицательное число.")

    has_npd = bool(text_value(form, "npd_present"))
    npd_rate_individual_bp = npd_rate_legal_bp = npd_income_limit = None
    if has_npd:
        npd_rate_individual_bp = _parse_rate_bp(
            text_value(form, "npd_rate_individual"), "с физлиц", errors
        )
        npd_rate_legal_bp = _parse_rate_bp(
            text_value(form, "npd_rate_legal"), "с юрлиц", errors
        )
        npd_income_limit = _parse_income_limit(
            text_value(form, "npd_income_limit"), errors
        )

    if errors:
        return None, None, errors

    values = {
        "name": name,
        "phone": phone or None,
        "about": about or None,
        "experience": experience or None,
        "hourly_rate": hourly_rate,
    }
    settings_values = None
    if has_npd:
        settings_values = {
            "is_npd_payer": checked(form, "is_npd_payer"),
            "npd_rate_individual_bp": npd_rate_individual_bp,
            "npd_rate_legal_bp": npd_rate_legal_bp,
            "npd_income_limit": npd_income_limit,
        }
    return values, settings_values, []
