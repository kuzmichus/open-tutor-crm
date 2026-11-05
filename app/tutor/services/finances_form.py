"""Разбор формы «Финансы»: настройки НПД (налог на профессиональный доход).

Вкладка «Финансы» пока содержит один блок — «Налоги». Он описывает статус
репетитора как плательщика НПД (самозанятого) и параметры налога: ставку
для доходов от физлиц (по умолчанию 4 %), ставку для доходов от юрлиц и ИП
(по умолчанию 6 %) и максимально допустимый доход в год (по умолчанию
2 400 000 ₽).

Правила разбора повторяют «Коэффициент подготовки» вкладки «Календарь»:
пустое числовое поле возвращает значение по умолчанию, а не ошибку —
у каждой из настроек всегда есть осмысленное законодательное значение.
Мусор и значения вне диапазона отклоняются с сообщением на той же вкладке.
"""

from decimal import Decimal

from app.common.services.forms import checked, decimal_or_none, int_or_none
from app.tutor.models.tutor_settings import (
    DEFAULT_NPD_ANNUAL_INCOME_LIMIT,
    DEFAULT_NPD_TAX_RATE_INDIVIDUAL,
    DEFAULT_NPD_TAX_RATE_LEGAL_ENTITY,
    NPD_TAX_RATE_MAX,
)

# Ставки налога в процентах: ключ формы → (подпись в ошибке, дефолт).
TAX_RATE_FIELDS = {
    "npd_tax_rate_individual": (
        "Ставка налога для физических лиц",
        DEFAULT_NPD_TAX_RATE_INDIVIDUAL,
    ),
    "npd_tax_rate_legal_entity": (
        "Ставка налога для юридических лиц и ИП",
        DEFAULT_NPD_TAX_RATE_LEGAL_ENTITY,
    ),
}


def _parse_tax_rate(form: dict, field: str, label: str, default: Decimal, errors: list[str]):
    """Ставка налога: пусто → дефолт, иначе конечное число 0..100."""
    raw = (form.get(field) or "").strip()
    if raw == "":
        return default
    value = decimal_or_none(raw)
    if value is None or not Decimal(0) <= value <= NPD_TAX_RATE_MAX:
        errors.append(f"{label} — число от 0 до {NPD_TAX_RATE_MAX}.")
        return None
    return value


def parse_finances_form(form: dict) -> tuple[dict | None, list[str]]:
    """Разбирает форму вкладки «Финансы»: (значения для записи, ошибки)."""
    errors: list[str] = []

    values: dict = {"npd_enabled": checked(form, "npd_enabled")}

    for field, (label, default) in TAX_RATE_FIELDS.items():
        rate = _parse_tax_rate(form, field, label, default, errors)
        if rate is not None:
            values[field] = rate

    # «Максимально допустимый доход в год» — целое число рублей. Пустое поле
    # возвращает значение по умолчанию (2 400 000 ₽): лимит — условие
    # применения НПД, «не задан» для него не имеет смысла.
    limit_raw = (form.get("npd_annual_income_limit") or "").strip()
    if limit_raw == "":
        values["npd_annual_income_limit"] = DEFAULT_NPD_ANNUAL_INCOME_LIMIT
    else:
        # Пробелы внутри числа (в том числе неразрывные) — привычное
        # написание суммы: «2 400 000» та же цифра, что «2400000».
        limit = int_or_none("".join(limit_raw.split()))
        if limit is None or limit < 0:
            errors.append(
                "Максимально допустимый доход — целое число рублей "
                "не меньше нуля."
            )
        else:
            values["npd_annual_income_limit"] = limit

    if errors:
        return None, errors

    return values, []
