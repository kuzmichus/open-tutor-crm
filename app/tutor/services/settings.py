"""Настройки репетитора: чтение с дефолтами и ленивое сохранение.

Строки `tutor_settings` создаётся только при первом сохранении (design
D2): чтение без строки возвращает объект с дефолтами, поэтому
регистрация и все страницы работают без «инициализации настроек».
"""

from sqlalchemy.orm import Session

from app.tutor.models.tutor_settings import TutorSettings, default_values


def get_settings(db: Session, tutor_id: str) -> TutorSettings:
    """Настройки репетитора; строки в БД нет — объект с дефолтами.

    Column-defaults применяются только при INSERT, поэтому transient-
    объект наполняется из `default_values()` явно: иначе все поля были
    бы None, и страница до первого сохранения показывала пустоту.
    Возвращаемый объект не привязан к сессии: только для чтения, запись —
    через `save_settings`.
    """
    row = db.get(TutorSettings, tutor_id)
    if row is not None:
        return row
    return TutorSettings(tutor_id=tutor_id, **default_values())


def save_settings(db: Session, tutor_id: str, values: dict) -> TutorSettings:
    """Сохраняет настройки; строки ещё нет — создаёт её (ленивый upsert).

    Новая строка строится от дефолтов, затем перезаписывается значениями
    формы: каждая вкладка присылает только свои поля, и absent-поля не
    должны оставить NULL в NOT NULL-колонках.
    """
    row = db.get(TutorSettings, tutor_id)
    if row is None:
        row = TutorSettings(tutor_id=tutor_id, **default_values())
        db.add(row)
    for name, value in values.items():
        setattr(row, name, value)
    db.commit()
    return row
