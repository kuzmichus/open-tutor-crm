"""Валидация полей формы регистрации репетитора."""

import re

# Простая проверка «есть @ и домен»: пакет email-validator в проекте не используется.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value: str) -> bool:
    """True, если `value` похож на email (есть локальная часть, @ и домен)."""
    return bool(_EMAIL_RE.match(value.strip()))
