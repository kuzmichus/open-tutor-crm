"""Разбор и валидация формы ответа ученика на ДЗ (спека homework-management).

Сервис не знает про FastAPI: на вход — форма (`FormData` или обычный dict),
на выход — очищенные значения и список ошибок (паттерн
`homework_form.py` / `lesson_form.py`).

Правила (change cabinet-homework, D6):

- пустой ответ — ни текста, ни ссылок → ошибка;
- ссылки приходят несколькими полями `links`; пустые строки отбрасываются
  (пустая добавленная строка — не ошибка, а «поле не заполняли»);
- каждая ссылка — `http://`/`https://`, не длиннее размера колонки.
"""

from app.common.services.forms import text_value
from app.homework.models.answer_link import MAX_LINK_LENGTH


def _collect_links(form) -> list[str]:
    """Непустые значения полей `links` в порядке формы.

    `FormData` хранит повторяющиеся поля только в `getlist`; у обычного
    dict значения может не быть вовсе или лежать одной строкой (тесты) —
    обе формы сводятся к списку строк. Не-строковое значение (multipart
    мог прислать файл) пропускается, как в `text_value`.
    """
    getlist = getattr(form, "getlist", None)
    raw = getlist("links") if getlist is not None else form.get("links", [])
    if isinstance(raw, str):
        raw = [raw]
    links: list[str] = []
    for item in raw or []:
        if not isinstance(item, str):
            continue
        url = item.strip()
        if url:
            links.append(url)
    return links


def validate_answer_data(data: dict) -> list[str]:
    """Проверки очищенных значений ответа (повторно проверяются в writer)."""
    errors: list[str] = []
    links = data.get("links") or []

    if not (data.get("text") or "").strip() and not links:
        errors.append("Напишите ответ или добавьте ссылку на работу.")

    for url in links:
        if not url.startswith(("http://", "https://")):
            errors.append("Каждая ссылка должна начинаться с http:// или https://.")
            break

    if any(len(url) > MAX_LINK_LENGTH for url in links):
        errors.append(f"Ссылка не может быть длиннее {MAX_LINK_LENGTH} символов.")

    return errors


def parse_answer_form(form) -> tuple[dict, list[str]]:
    """Данные формы ответа и ошибки разбора полей: `(данные, ошибки)`."""
    data = {
        "text": text_value(form, "text"),
        "links": _collect_links(form),
    }
    return data, validate_answer_data(data)
