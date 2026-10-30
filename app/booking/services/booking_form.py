"""Разбор формы заявки на окно (спека public-booking, «Форма заявки»).

Сервис не знает про FastAPI: на вход — отображение с полями формы
(`FormData` или dict), на выход — очищенные значения и список ошибок
(паттерн `slot_form.py`).

Заявка просит имя и контакт, плюс необязательный комментарий. Контакт —
телефон **или** мессенджер, поэтому формат не навязывается: публичная форма
не должна отклонять «@ivan» или «WhatsApp +7…» из-за того, что значение не
похоже на телефон. Проверяется только непустота и разумная длина — этого
хватает, чтобы педагог мог ответить. Комментарий свободный: пустой
превращается в None, чтобы в БД «нет комментария» было одним значением.
"""

from dataclasses import dataclass

from app.common.services.forms import text_value

# Пределы длины: те же, что у колонок `bookings.name` (200),
# `bookings.contact` (64) и `bookings.comment` (500). Слишком длинное
# значение отсекается на входе, иначе БД отклонила бы вставку и
# пользователь увидел бы 500.
MAX_NAME_LEN = 200
MAX_CONTACT_LEN = 64
MAX_COMMENT_LEN = 500

# Сообщения об ошибках: одни и те же для публичной страницы и для
# повторной отрисовки формы после отказа.
NAME_REQUIRED = "Укажите имя."
CONTACT_REQUIRED = "Укажите телефон или мессенджер для связи."
NAME_TOO_LONG = f"Имя — не длиннее {MAX_NAME_LEN} символов."
CONTACT_TOO_LONG = f"Контакт — не длиннее {MAX_CONTACT_LEN} символов."
COMMENT_TOO_LONG = f"Комментарий — не длиннее {MAX_COMMENT_LEN} символов."

@dataclass(frozen=True)
class BookingParams:
    """Очищенные значения заявки: кто, как связаться и что обсудить."""

    name: str
    contact: str
    comment: str | None = None

def booking_form_values(form) -> dict:
    """Присланные значения заявки — для повторного показа в форме.

    Разбор мог не удаться (пустое имя), а форма обязана показать
    введённое, чтобы человек не набирал заново (паттерн
    `slot_form_values`).
    """
    return {
        "name": text_value(form, "name"),
        "contact": text_value(form, "contact"),
        "comment": text_value(form, "comment"),
    }

def parse_booking_form(form) -> tuple[BookingParams | None, list[str]]:
    """Разбор формы заявки: значения или список ошибок.

    Имя и контакт обязательны (спека public-booking, «Форма заявки принимает
    имя и контакт»), комментарий — нет. Значение из одних пробелов пустым и
    считается — `strip` выполняется до проверки.
    """
    name = text_value(form, "name")
    contact = text_value(form, "contact")
    comment = text_value(form, "comment")

    errors: list[str] = []
    if not name:
        errors.append(NAME_REQUIRED)
    elif len(name) > MAX_NAME_LEN:
        errors.append(NAME_TOO_LONG)
    if not contact:
        errors.append(CONTACT_REQUIRED)
    elif len(contact) > MAX_CONTACT_LEN:
        errors.append(CONTACT_TOO_LONG)
    if len(comment) > MAX_COMMENT_LEN:
        errors.append(COMMENT_TOO_LONG)

    if errors:
        return None, errors
    return (
        BookingParams(name=name, contact=contact, comment=comment or None),
        [],
    )
