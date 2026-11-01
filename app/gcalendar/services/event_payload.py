"""Тело события Google из урока: чистые функции без БД и HTTP.

Правила (design D7, D8):

- событие строится в зоне педагога: `dateTime` — настенное время без
  смещения плюс `timeZone` IANA. Так Google сам разбирается с переводом
  часов, а репетитор видит занятие в своём поясе;
- конец считается **локально** от `duration_min`, а не прибавлением
  `timedelta` к UTC: в ночь перевода часов занятие длиной 60 минут не
  должно «съедать» или «дарить» час;
- `content_hash` — sha256 канонического JSON тела: сравнение хешей решает
  «создать / обновить / ничего не делать» без запроса к Google, когда
  урок не менялся (design D4).
"""

import hashlib
import json
from datetime import timedelta

from app.common.services.tutor_time import to_local, tutor_zone_name
from app.lesson.models.lesson import LESSON_TYPE_LABELS

# Заголовок события: «Занятие — Иван Петров», «Занятие — Группа: X».
SUMMARY_PREFIX = "Занятие — "

# Ключи, которые участвуют в хеше: всё, что уходит в Google. Служебные
# поля ответа (id, etag, htmlLink) в тело запроса не попадают.
_HASH_FIELDS = ("summary", "description", "location", "start", "end")

def build_event(
    lesson,
    tutor,
    *,
    student_name: str | None = None,
    group_name: str | None = None,
) -> dict:
    """Тело события Calendar API из урока.

    `student_name`/`group_name` передаёт вызывающая сторона (у неё уже
    есть связанные записи): сервис не ходит в БД и не зависит от ленивых
    связей ORM.
    """
    start = to_local(lesson.starts_at, tutor)
    # Локальная арифметика: `+ timedelta` к aware-значению в зоне педагога
    # даёт настенное время конца, включая переход на летнее время.
    end = start + timedelta(minutes=lesson.duration_min)

    payload = {
        "summary": _summary(lesson, student_name=student_name, group_name=group_name),
        "description": _description(lesson, student_name=student_name, group_name=group_name),
        "location": lesson.meeting_url or "",
        "start": {
            "dateTime": start.replace(tzinfo=None).isoformat(timespec="seconds"),
            "timeZone": tutor_zone_name(tutor),
        },
        "end": {
            "dateTime": end.replace(tzinfo=None).isoformat(timespec="seconds"),
            "timeZone": tutor_zone_name(tutor),
        },
    }
    return payload

def content_hash(payload: dict) -> str:
    """sha256 тела события: одинаковый урок — одинаковый хеш.

    `sort_keys` и разделители без пробелов делают хеш независимым от
    порядка ключей в словаре: сравниваются данные, а не сериализация.
    """
    canonical = {key: payload.get(key) for key in _HASH_FIELDS}
    raw = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()

def _target_name(
    lesson, *, student_name: str | None, group_name: str | None
) -> str:
    """Цель урока так же, как в списке занятий: «Группа: X» или имя ученика."""
    if lesson.type == "group":
        return f"Группа: {group_name or '—'}"
    return student_name or "—"

def _summary(
    lesson, *, student_name: str | None, group_name: str | None
) -> str:
    return SUMMARY_PREFIX + _target_name(
        lesson, student_name=student_name, group_name=group_name
    )

def _description(
    lesson, *, student_name: str | None, group_name: str | None
) -> str:
    """Описание события: тип, стоимость, заметка и ссылка на встречу.

    Строки собираются только из заполненных полей — пустых подписей и
    «None» в календаре не бывает. Заметка репетитора уходит в его же
    календарь: это не раскрытие данных ученику, приглашений нет
    (`sendUpdates=none`).
    """
    lines = [f"Тип: {LESSON_TYPE_LABELS.get(lesson.type, lesson.type)}"]
    if lesson.type != "group" and lesson.price is not None:
        lines.append(f"Стоимость: {lesson.price} ₽")
    if lesson.note:
        lines.append(f"Заметка: {lesson.note}")
    if lesson.meeting_url:
        lines.append(f"Встреча: {lesson.meeting_url}")
    return "\n".join(lines)
