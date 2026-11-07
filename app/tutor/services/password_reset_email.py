"""Письмо со ссылкой восстановления пароля репетитора.

Сборка письма отделена от транспорта: шаблоны (HTML и текст) лежат в
`app/tutor/templates/email/`, отправку выполняет общий
`app.mail.services.sender.send_email`. Вьюха восстановления не собирает
тему и тело сама — иначе письмо нельзя было бы переиспользовать в других
сценариях (например, приглашение в кабинет).
"""

from app.config import settings
from app.mail.services.sender import send_email
from app.templating import templates
from app.tutor.services.password_reset import TTL

SUBJECT = "Восстановление пароля — Open Tutor CRM"

_TEMPLATE_DIR = "email/password_reset"


def send_password_reset_email(
    *,
    to_email: str,
    tutor_name: str,
    reset_url: str,
) -> list[str]:
    """Отправляет письмо со ссылкой сброса; возвращает ошибки (пусто — ок).

    Срок действия в письме берётся из того же `TTL`, что и у ключа: иначе
    подпись «ссылка действует 24 ч» разошлась бы с реальным сроком после
    изменения константы.
    """
    context = {
        "app_name": settings.app_name,
        "tutor_name": tutor_name,
        "reset_url": reset_url,
        "ttl_hours": int(TTL.total_seconds() // 3600),
        "subject": SUBJECT,
    }
    html = templates.env.get_template(f"{_TEMPLATE_DIR}.html").render(**context)
    text = templates.env.get_template(f"{_TEMPLATE_DIR}.txt").render(**context)
    return send_email(to_email=to_email, subject=SUBJECT, html=html, text=text)
