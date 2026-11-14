"""Приветственное письмо новому пользователю (репетитор, ученик, родитель).

Письмо уходит после успешной регистрации, поэтому собирается отдельным
сервисом, а не во вьюхе: три разных сценария регистрации (репетитор,
ученик по приглашению, родитель по приглашению) используют один и тот же
код выбора шаблона и темы.

Текст письма — файл Jinja2 в `app/common/templates/email/`, а не строка в
коде: правка формулировки не должна требовать релиза приложения. Тема
лежит рядом с подписями — `app/common/email_subjects.py`.

Отправка ровно одна: повторов нет (сценарий не критичный — пользователь
уже зарегистрирован). Ошибку транспорта сервис только логирует: письмо не
должно ломать регистрацию и не должно пробрасывать исключение в
`BackgroundTasks` — иначе FastAPI покажет пользователю 500 вместо
редиректа в кабинет.
"""

import logging

from app.common.email_subjects import (
    WELCOME_PARENT,
    WELCOME_STUDENT,
    WELCOME_TUTOR,
)
from app.mail.services.sender import send_email
from app.templating import templates

logger = logging.getLogger("mail")

# Роль → (шаблон, тема). Один источник истины: вьюхи передают роль, а не
# путь шаблона, поэтому опечатка в имени файла невозможна на месте вызова.
WELCOME_EMAILS = {
    "tutor": ("email/welcome_tutor.html.jinja2", WELCOME_TUTOR),
    "student": ("email/welcome_student.html.jinja2", WELCOME_STUDENT),
    "parent": ("email/welcome_parent.html.jinja2", WELCOME_PARENT),
}


def welcome_template_path(role: str) -> str:
    """Путь шаблона письма для роли — для проверок и диагностики."""
    return WELCOME_EMAILS[role][0]


def send_welcome_email(*, role: str, to_email: str, user_name: str) -> list[str]:
    """Собирает и отправляет приветственное письмо; возвращает ошибки.

    Шаблон читается при каждом вызове (`get_template` кэширует по mtime),
    поэтому правка файла в репозитории отражается в следующем письме без
    перезапуска приложения. Пустой `user_name` заменяется на нейтральное
    обращение: в письме не должно остаться «Здравствуйте, !».
    """
    template_name, subject = WELCOME_EMAILS[role]
    context = {"user_name": (user_name or "").strip() or "друг"}
    html = templates.env.get_template(template_name).render(**context)
    return send_email(to_email=to_email, subject=subject, html=html)


def deliver_welcome_email(*, role: str, to_email: str, user_name: str) -> None:
    """Фоновая отправка: ошибки уходят в лог, наружу ничего не летит.

    Вызывается через `BackgroundTasks` из вьюх регистрации: синхронный
    SMTP в обработчике подвесил бы ответ на время соединения, а его сбой
    влиял бы на HTTP-статус. `send_email` возвращает список ошибок вместо
    исключений, но шаблон может не отрендериться (битый файл, отсутствующая
    переменная) — такой сбой тоже не должен всплывать как необработанное
    исключение задачи.
    """
    try:
        errors = send_welcome_email(role=role, to_email=to_email, user_name=user_name)
    except Exception as exc:  # pragma: no cover - защита от битого шаблона
        logger.warning(
            "Приветственное письмо (%s) на %s не собрано: %s", role, to_email, exc
        )
        return
    if errors:
        logger.warning(
            "Приветственное письмо (%s) на %s не отправлено: %s",
            role,
            to_email,
            "; ".join(errors),
        )
