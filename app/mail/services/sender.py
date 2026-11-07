"""Отправка писем через SMTP-сервер.

Транспорт один на всё приложение: восстановление пароля (и будущие
сценарии) не заводят собственный smtplib — здесь собирается письмо,
выбирается шифрование и ошибки возвращаются списком строк, как у
`send_message` мессенджеров.

Почта включается переменной `SMTP_HOST` (см. `app/config.py`). Пока она
не задана, `email_enabled()` возвращает False, а вызывающий код работает
в демо-режиме — приложение «из коробки» не требует почтового сервера.

Зависимостей не добавляем: `smtplib` и `email` — stdlib, а ради одного
письма тянуть отдельную библиотеку незачем (то же решение, что у
Google OAuth и Bot API мессенджеров).
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.config import settings

logger = logging.getLogger("mail")

# Письмо без явного `text` всё равно уходит с текстовой частью: часть
# клиентов (и корпоративные фильтры) не показывают письмо только из HTML.
PLAIN_FALLBACK = "Откройте письмо в клиенте с поддержкой HTML."


def email_enabled() -> bool:
    """Почта включена: в окружении задан адрес SMTP-сервера."""
    return settings.email_enabled


def build_message(
    *,
    to_email: str,
    subject: str,
    html: str,
    text: str | None = None,
) -> EmailMessage:
    """Собирает письмо `multipart/alternative` в UTF-8.

    Отдельная функция, а не строки внутри `send_email`: сборку письма
    проверяют тесты (получатель, тема, ссылка в обеих частях), и она не
    требует ни сети, ни SMTP-сервера.
    """
    message = EmailMessage()
    message["From"] = formataddr((settings.app_name, settings.mail_from))
    message["To"] = to_email
    message["Subject"] = subject
    # Message-ID с доменом отправителя: без него часть провайдеров
    # помечает письмо как подозрительное.
    message["Message-ID"] = make_msgid(domain=_domain(settings.mail_from))
    message.set_content(text or PLAIN_FALLBACK)
    message.add_alternative(html, subtype="html")
    return message


def send_email(
    *,
    to_email: str,
    subject: str,
    html: str,
    text: str | None = None,
) -> list[str]:
    """Отправляет письмо; возвращает список ошибок (пусто — доставлено).

    Ошибки не бросаются исключением: соглашение сервисов проекта — отдать
    вызывающему список строк, чтобы форма могла показать причину, а
    сценарий (например, восстановление пароля) — не раскрывать её
    пользователю, но залогировать.
    """
    if not email_enabled():
        return ["Отправка почты не настроена на сервере: задайте SMTP_HOST."]
    if not to_email or not to_email.strip():
        return ["Не указан получатель письма."]
    if not subject or not subject.strip():
        return ["Не указана тема письма."]

    try:
        message = build_message(
            to_email=to_email.strip(),
            subject=subject.strip(),
            html=html,
            text=text,
        )
    except Exception as exc:  # pragma: no cover - защита от битых данных
        logger.warning("Письмо не собрано: %s", exc)
        return [f"Не удалось собрать письмо: {exc}"]

    try:
        _deliver(message)
    except smtplib.SMTPException as exc:
        logger.warning("Письмо на %s не отправлено: %s", to_email, exc)
        return [f"Почтовый сервер отклонил письмо: {exc}"]
    except OSError as exc:
        # Сеть, DNS, таймаут — пользователю нужна причина, но без трейсбека.
        logger.warning("Письмо на %s не отправлено: %s", to_email, exc)
        return [f"Не удалось связаться с почтовым сервером: {exc}"]
    return []


def _deliver(message: EmailMessage) -> None:
    """Открывает соединение с SMTP и отправляет письмо.

    Два режима шифрования: `SMTP_USE_SSL` (обычно порт 465) — TLS с самого
    начала; иначе STARTTLS (обычно 587) — апгрейд после `EHLO`. Взаимоисключение
    проверяет конфигурация, поэтому здесь достаточно флага.
    """
    host = settings.smtp_host.strip()
    port = settings.smtp_port
    context = ssl.create_default_context()

    if settings.smtp_use_ssl:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            host, port, timeout=settings.smtp_timeout, context=context
        )
    else:
        client = smtplib.SMTP(host, port, timeout=settings.smtp_timeout)

    with client:
        client.ehlo()
        if not settings.smtp_use_ssl and settings.smtp_starttls:
            client.starttls(context=context)
            client.ehlo()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)


def _domain(address: str) -> str | None:
    """Домен адреса отправителя для Message-ID; None — пусть выберет email."""
    _, _, domain = (address or "").rpartition("@")
    return domain or None
