"""Разбор формы вкладки «Мессенджеры» (страница `/tutor/settings`).

Токены валидируются по формату конкретного мессенджера, чтобы опечатка
не сохранялась как «подключение»: настоящая валидность всё равно
проверится API при первой отправке. Заодно принимаем вставку полной
ссылки вида `https://api.telegram.org/bot<token>` — токен извлекается
из неё.
"""

import re

from app.messenger.services.messengers import MESSENGER_LABELS, SUPPORTED, token_key

# Формат токена каждого мессенджера. Новый поддерживаемый мессенджер
# обязан добавить сюда свой шаблон: проверка — на очевидную опечатку,
# а не на спецификацию формата.
_TOKEN_FORMATS = {
    "telegram": re.compile(r"^\d+:[A-Za-z0-9_-]{10,}$"),
    # MAX выдаёт длинную строку без разделителей; жёсткую длину не
    # фиксируем — формат токена не задокументирован как контракт.
    "max": re.compile(r"^[A-Za-z0-9_-]{20,200}$"),
}

# Подсказка формата для сообщения об ошибке — по ней пользователь
# понимает, как выглядит правильный токен конкретного мессенджера.
_FORMAT_HINTS = {
    "telegram": (
        "в формате «123456:ABC-DEF…» — возьмите его у @BotFather"
    ),
    "max": (
        "строкой из латинских букв и цифр — её выдал @masterbot "
        "при создании бота"
    ),
}

# Извлечение токена из «большой» вставленной строки: у Telegram токен
# встроен в ссылку на бота, у MAX — выдаётся отдельной строкой.
_TOKEN_EXTRACTORS = {
    "telegram": re.compile(r"bot(\d+:[A-Za-z0-9_-]{10,})"),
}


def parse_messenger_form(form: dict) -> tuple[dict | None, list[str]]:
    """Разбирает форму: (значения для записи, ошибки).

    Возвращает словарь «имя KV-параметра → токен» по всем поддерживаемым
    мессенджерам закрытого списка. Пустое значение — легитимный
    результат («отключить»): вьюха удалит параметр.
    """
    values: dict[str, str] = {}
    errors: list[str] = []
    for messenger in SUPPORTED:
        key = token_key(messenger)
        raw = (form.get(key) or "").strip()
        if not raw:
            values[key] = ""
            continue

        token = raw
        if extractor := _TOKEN_EXTRACTORS.get(messenger):
            if found := extractor.search(raw):
                token = found.group(1)
        if not _TOKEN_FORMATS[messenger].match(token):
            label = MESSENGER_LABELS[messenger]
            errors.append(
                f"Токен {label} должен быть {_FORMAT_HINTS[messenger]}."
            )
            continue
        values[key] = token

    if errors:
        return None, errors
    return values, []
