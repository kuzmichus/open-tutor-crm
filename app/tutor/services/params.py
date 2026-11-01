"""Параметры репетитора: чтение и запись KV-таблицы `tutor_params`.

Ключи — открытый набор («telegram_token», …), набор задаётся
сервисами-потребителями, а не БД. Запись — upsert: строка создаётся
лениво, как и у `tutor_settings`.

Две формы записи: `save_param` — только изменения в текущей транзакции
(её использует cron: коммит — обязанность runner'а), `set_param` —
изменения плюс немедленный коммит (действия пользователя в веб-запросе).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tutor.models.tutor_param import TutorParam

def get_param(db: Session, tutor_id: str, key: str) -> str | None:
    """Значение параметра или `None`, если репетитор его не задавал."""
    row = db.get(TutorParam, (tutor_id, key))
    return row.value if row is not None else None

def save_param(db: Session, tutor_id: str, key: str, value: str) -> None:
    """Сохраняет параметр в текущей транзакции, без коммита (upsert).

    Задание cron живёт в транзакции runner'а: коммит внутри сервиса
    разрывал бы правило «одна транзакция на задание» и оставлял бы
    частично применённые изменения при падении.
    """
    row = db.get(TutorParam, (tutor_id, key))
    if row is None:
        row = TutorParam(tutor_id=tutor_id, key=key, value=value)
        db.add(row)
    else:
        row.value = value

def set_param(db: Session, tutor_id: str, key: str, value: str) -> None:
    """Сохраняет параметр, создавая строку при первом наличии (upsert)."""
    save_param(db, tutor_id, key, value)
    db.commit()

def delete_param(db: Session, tutor_id: str, key: str) -> None:
    """Удаляет параметр; отсутствие строки — не ошибка."""
    forget_param(db, tutor_id, key)
    db.commit()

def forget_param(db: Session, tutor_id: str, key: str) -> None:
    """Удаляет параметр в текущей транзакции, без коммита.

    Нужен операциям, которые меняют несколько параметров одной
    транзакцией (подключение календаря): коммит на каждом ключе разрывал
    бы атомарность «токены сохранены целиком или не сохранены вовсе».
    """
    row = db.get(TutorParam, (tutor_id, key))
    if row is not None:
        db.delete(row)

def all_params(db: Session, tutor_id: str) -> dict[str, str]:
    """Все параметры репетитора одним запросом, словарём «ключ → значение»."""
    rows = db.query(TutorParam).filter(TutorParam.tutor_id == tutor_id).all()
    return {row.key: row.value for row in rows}

def all_params_by_tutors(
    db: Session, tutor_ids: list[str]
) -> dict[str, dict[str, str]]:
    """Параметры пачки репетиторов одним запросом: «id → ключ → значение».

    Нужен заданиям cron, которые обходят всех репетиторов: чтение по
    одному репетитору дало бы N+1 запрос на прогон. Репетитор без
    параметров в результат не попадает — вызывающий код читает через
    `result.get(tutor_id, {})`.
    """
    if not tutor_ids:
        return {}
    rows = db.scalars(
        select(TutorParam).where(TutorParam.tutor_id.in_(tutor_ids))
    ).all()
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        result.setdefault(row.tutor_id, {})[row.key] = row.value
    return result
