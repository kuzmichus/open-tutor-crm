"""Общие парсеры полей HTML-форм.

Один и тот же разбор «строковое поле», «чекбокс», «целое число», «сумма
в рублях» нужен формам всех доменов (ученики, группы, уроки, счёт, окна,
недоступность) — до общего модуля каждый файл формы носил свою копию
`_get`/`_text`/`_checked`/`_int_or_none`, и копии незаметно
расходились (например, guard на не-строкое значение был не везде).

Сервисы по правилу AGENTS.md не знают про FastAPI: функции принимают
любой `Mapping` (вьюха передаёт `FormData`, тесты — обычный `dict`),
никогда не поднимают HTTP-исключений и не трогают БД. Ошибки дописываются
в переданный список `errors` — соглашение форм модуля: `(данные, ошибки)`.
"""

from collections.abc import Mapping


def text_value(form: Mapping, key: str) -> str:
    """Строковое значение поля формы (отсутствие = пустая строка).

    Guard на `isinstance` обязателен: multipart-форма может прислать
    файл (UploadFile), и `.strip()` на нём падал бы с AttributeError.
    """
    value = form.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def checked(form: Mapping, key: str) -> bool:
    """Флаг чекбокса/переключателя: `on`/`1`/`true`/`yes` — включён.

    Неотмеченный чекбокс поле в форму не присылает вовсе — отсутствие
    значения тоже «выключено». Значение нормализуется: одна и та же
    проверка обслуживает скрытое поле формы и query-параметр.
    """
    value = form.get(key, "")
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"1", "on", "true", "yes"}


def int_or_none(raw: str | None) -> int | None:
    """Целое число из строки; пусто, мусор или не-строка — None."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def parse_rubles(raw: str, label: str, errors: list[str]) -> int | None:
    """Сумма в рублях: целое число больше нуля; ошибки — в `errors`.

    `label` — родительный падеж названия («платежа», «возврата»,
    «расхода») для сообщений. Пробелы (в том числе неразрывные) внутри
    числа допускаются: «1 200» — та же тысяча двести, отказ на пробеле
    был бы придиркой к форматированию, а не проверкой данных.
    """
    if not raw:
        errors.append(f"Укажите сумму {label}.")
        return None
    cleaned = "".join(raw.split())
    try:
        value = int(cleaned)
    except ValueError:
        errors.append(f"Сумма {label} — целое число рублей.")
        return None
    if value <= 0:
        errors.append(f"Сумма {label} должна быть больше нуля.")
        return None
    return value
