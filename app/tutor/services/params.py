"""Параметры репетитора: чтение и запись KV-таблицы `tutor_params`.

Ключи — открытый набор («telegram_token», …), набор задаётся
сервисами-потребителями, а не БД. Запись — upsert: строка создаётся
лениво, как и у `tutor_settings`.
"""

from sqlalchemy.orm import Session

from app.tutor.models.tutor_param import TutorParam


def get_param(db: Session, tutor_id: str, key: str) -> str | None:
    """Значение параметра или `None`, если репетитор его не задавал."""
    row = db.get(TutorParam, (tutor_id, key))
    return row.value if row is not None else None


def set_param(db: Session, tutor_id: str, key: str, value: str) -> None:
    """Сохраняет параметр, создавая строку при первом наличии (upsert)."""
    row = db.get(TutorParam, (tutor_id, key))
    if row is None:
        row = TutorParam(tutor_id=tutor_id, key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()


def delete_param(db: Session, tutor_id: str, key: str) -> None:
    """Удаляет параметр; отсутствие строки — не ошибка."""
    row = db.get(TutorParam, (tutor_id, key))
    if row is not None:
        db.delete(row)
        db.commit()


def all_params(db: Session, tutor_id: str) -> dict[str, str]:
    """Все параметры репетитора одним запросом, словарём «ключ → значение»."""
    rows = db.query(TutorParam).filter(TutorParam.tutor_id == tutor_id).all()
    return {row.key: row.value for row in rows}
