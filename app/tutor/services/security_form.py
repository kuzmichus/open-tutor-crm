"""Разбор формы «Безопасность»: смена email и пароля.

Пароль меняется без ввода текущего (design D5): страница доступна
только из-под сессии. Новый пароль применяется только парой с
совпадающим повтором; пустая пара — пароль не трогается.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tutor.models.tutor import Tutor
from app.tutor.services.validation import is_valid_email


def parse_security_form(
    db: Session, tutor: Tutor, form: dict
) -> tuple[dict | None, list[str]]:
    """Разбирает форму безопасности: (значения для записи, ошибки).

    В значениях `new_password` — уже готовый к записи пароль
    (None — не менять); хеширует вызывающая сторона.
    """
    email = (form.get("email") or "").strip()
    password = form.get("new_password") or ""
    password_confirm = form.get("new_password_confirm") or ""

    errors: list[str] = []

    if not email or not is_valid_email(email):
        errors.append("Укажите корректный email.")
    elif email != tutor.email:
        # Свой текущий email конфликтом не считается: репетитор может
        # пересохранить форму, не трогая почту.
        busy = db.scalars(select(Tutor).where(Tutor.email == email)).first()
        if busy is not None:
            errors.append("Репетитор с таким email уже зарегистрирован.")

    if password or password_confirm:
        if password != password_confirm:
            errors.append("Пароли не совпадают.")

    if errors:
        return None, errors

    return {"email": email, "new_password": password or None}, []
