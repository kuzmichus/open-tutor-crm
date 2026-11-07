"""Режим работы CRM: открыта ли регистрация репетитора.

Флаг `SINGLE_MODE` (`app.config.settings.single_mode`) отделяет персональную
установку от общей: в сингл-режиме аккаунт в CRM один, и страница
регистрации нужна только для первого запуска — пока в таблице `tutors` нет
ни одной строки. После появления первого репетитора регистрация закрыта
(404 и на GET, и на POST), а вход перестаёт отправлять на неё.

`settings` читается в момент вызова, а не при импорте: тесты подменяют
значение через `monkeypatch`, а владелец сервера меняет режим переменной
окружения и перезапуском приложения (design D2).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.tutor.models.tutor import Tutor


def has_tutors(db: Session) -> bool:
    """True, если в базе уже есть хотя бы один репетитор."""
    return db.scalars(select(Tutor.id).limit(1)).first() is not None


def is_first_run(db: Session) -> bool:
    """True, если включён сингл-режим и репетиторов ещё нет.

    Именно это состояние открывает регистрацию: владельцу персональной
    установки нужно создать единственный аккаунт.
    """
    return settings.single_mode and not has_tutors(db)


def registration_open(db: Session) -> bool:
    """True, если страница регистрации должна работать.

    В мульти-режиме — всегда; в сингл-режиме — только на первом запуске
    (пока нет ни одного репетитора).
    """
    return not settings.single_mode or is_first_run(db)
