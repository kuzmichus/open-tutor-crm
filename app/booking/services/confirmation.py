"""Подтверждение брони: поиск или создание ученика и урок по времени окна.

Алгоритм design.md D9 — три исхода поиска ученика и один код на все:

1. кандидаты — неархивные ученики этого педагога, у которых совпали
   нормализованные имя и контакт из брони;
2. 0 кандидатов → создать ученика (нужен признак «ребёнок/взрослый»),
   1 кандидат → использовать его, >1 → педагог выбирает явно;
3. повторно проверить пересечение времени: пока бронь ждала, педагог мог
   поставить урок руками, а `UNIQUE` на уроках нет;
4. создать урок `type="individual"`, `status="planned"` по времени окна;
5. связать бронь с учеником и уроком, статус — «Подтверждена».

**Нормализация сравнения** намеренно примитивна и предсказуема: имя —
`casefold` и схлопывание пробелов, контакт — только цифры и ведущий `+`.
«Умное» сравнение российских номеров (`8 999…` = `+7 999…`) в этот change
не входит: неверное склеивание двух разных людей хуже, чем лишний дубль,
который педагог удалит (design.md Risks).

Если контакт в брони вообще без цифр (`@ivan`, «WhatsApp»), сравнение идёт
только по имени: подставлять пустой телефон как совпадение значило бы
склеить заявителя с любым учеником без телефона.
"""

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.booking.models.booking import ACTIVE_BOOKING_STATUSES, Booking
from app.common.colors import assign_color
from app.lesson.models.lesson import Lesson
from app.slot.models.slot import Slot
from app.slot.services.busy import slot_end
from app.slot.services.busy import conflicts as slot_conflicts
from app.student.models.student import STUDENT_KINDS, Student
from app.student.services.phone import format_phone
from app.student.services.presentation import student_full_name
from app.tutor.services.clock import as_utc

# Завершающие статусы: из них перехода нет (спека booking-management,
# «Завершающий статус не меняется»).
FINAL_BOOKING_STATUSES = ("rejected", "cancelled")

BOOKING_FINAL_MESSAGE = "Бронь уже завершена: действие недоступно."
BOOKING_CONFIRMED_MESSAGE = "Бронь уже подтверждена."
BOOKING_NOT_PENDING_MESSAGE = "Подтвердить можно только ожидающую бронь."
KIND_REQUIRED_MESSAGE = (
    "Укажите, кто ученик — ребёнок или взрослый: без этого карточка не создаётся."
)
CHOOSE_STUDENT_MESSAGE = (
    "Найдено несколько учеников с таким именем и контактом: выберите нужного."
)
STUDENT_NOT_FOUND_MESSAGE = "Выбранный ученик не найден."
TIME_BUSY_MESSAGE = "Время окна уже занято уроком: урок не создан."

_WHITESPACE_RE = re.compile(r"\s+")
_NON_DIGITS_RE = re.compile(r"\D")

def normalize_name(value: str | None) -> str:
    """Имя для сравнения: без регистра, лишних и повторных пробелов."""
    return _WHITESPACE_RE.sub(" ", (value or "").strip()).casefold()

def normalize_contact(value: str | None) -> str:
    """Контакт для сравнения: только цифры и ведущий `+`."""
    raw = (value or "").strip()
    digits = _NON_DIGITS_RE.sub("", raw)
    if not digits:
        return ""
    return f"+{digits}" if raw.startswith("+") else digits

def candidate_students(db: Session, tutor_id: str, booking: Booking) -> list[Student]:
    """Неархивные ученики педагога, совпавшие по имени и контакту брони.

    Архивный ученик не подставляется автоматически (спека
    booking-management): подтверждение создаст нового — педагог увидит это
    в диалоге и при желании выберет архивного вручную, но уже осознанно.

    Сравнение в Python, а не в SQL: `lower()` в SQLite не работает с
    кириллицей, а у одного педагога учеников немного (тот же приём, что в
    `student/services/students.py`).
    """
    students = db.scalars(
        select(Student).where(
            Student.tutor_id == tutor_id,
            Student.status != "archived",
        )
    ).all()

    wanted_name = normalize_name(booking.name)
    wanted_contact = normalize_contact(booking.contact)

    matched: list[Student] = []
    for student in students:
        if normalize_name(student_full_name(student)) != wanted_name:
            continue
        # Контакт без цифр (мессенджер) сравнивать не с чем: имя уже совпало.
        if wanted_contact and normalize_contact(student.phone) != wanted_contact:
            continue
        matched.append(student)
    return matched

def _split_name(full_name: str) -> tuple[str, str | None]:
    """«Мария Петрова» → («Мария», «Петрова»); одно слово — без фамилии.

    Длины обрезаются под колонки модели (по 100 символов): бронь принимает
    имя до 200 символов, и без обрезки вставка упала бы на ограничении БД.
    """
    parts = (full_name or "").strip().split(maxsplit=1)
    if not parts:
        return "", None
    first = parts[0][:100]
    last = parts[1][:100] if len(parts) > 1 else None
    return first, last

def _contact_fields(contact: str) -> dict:
    """Контакт брони в поля карточки ученика.

    Телефон — если в контакте есть цифры; email — если это похоже на
    почту; иначе контакт остаётся только в брони (он не теряется: педагог
    видит его в диалоге окна).
    """
    if _NON_DIGITS_RE.search(contact):
        return {"phone": format_phone(contact)}
    if "@" in contact:
        return {"email": contact[:255]}
    return {}

def _create_student(db: Session, tutor_id: str, booking: Booking, kind: str) -> Student:
    """Ученик из данных брони: имя, контакт и признак, выбранный педагогом."""
    first_name, last_name = _split_name(booking.name)
    student = Student(
        tutor_id=tutor_id,
        first_name=first_name,
        last_name=last_name,
        kind=kind,
        color=assign_color(db, tutor_id),
        **_contact_fields(booking.contact),
    )
    db.add(student)
    db.flush()
    return student

def _chosen_student(db: Session, tutor_id: str, student_id: str) -> Student | None:
    """Ученик этого педагога по id; чужой и архивный недоступны."""
    return db.scalars(
        select(Student).where(
            Student.id == student_id,
            Student.tutor_id == tutor_id,
            Student.status != "archived",
        )
    ).one_or_none()

def _time_is_busy(db: Session, slot: Slot) -> bool:
    """Пересекается ли окно с уроком или другим окном педагога (D9, шаг 3)."""
    kinds = slot_conflicts(
        db,
        slot.tutor_id,
        as_utc(slot.starts_at),
        slot_end(slot),
        exclude_slot_id=slot.id,
    )
    return bool(kinds)

def confirm(
    db: Session,
    booking: Booking,
    tutor,
    *,
    chosen_student_id: str | None = None,
    kind: str | None = None,
    now: datetime,
) -> tuple[Booking | None, list[str]]:
    """Подтверждает ожидающую бронь; при ошибке ничего не пишет.

    `chosen_student_id` — выбор педагога при нескольких совпадениях,
    `kind` — признак создаваемого ученика. Оба необязательны: они нужны
    только в своих исходах (design.md D9), и требование возникает по факту,
    а не всегда.
    """
    if booking.status in FINAL_BOOKING_STATUSES:
        return None, [BOOKING_FINAL_MESSAGE]
    if booking.status == "confirmed":
        return None, [BOOKING_CONFIRMED_MESSAGE]
    if booking.status != "pending":
        return None, [BOOKING_NOT_PENDING_MESSAGE]

    slot = db.get(Slot, booking.slot_id)
    if slot is None:
        # Окно удалено — каскад снёс бы и бронь; сюда попадаем только при
        # рассинхроне данных, но отвечаем понятно, а не падаем.
        return None, [BOOKING_FINAL_MESSAGE]

    student: Student | None = None
    if chosen_student_id:
        student = _chosen_student(db, tutor.id, chosen_student_id)
        if student is None:
            return None, [STUDENT_NOT_FOUND_MESSAGE]
    else:
        candidates = candidate_students(db, tutor.id, booking)
        if len(candidates) > 1:
            return None, [CHOOSE_STUDENT_MESSAGE]
        if len(candidates) == 1:
            student = candidates[0]

    # Новый ученик требует признака «ребёнок/взрослый» (спека
    # booking-management): без него бронь остаётся ожидающей, а не
    # создаётся карточка с угаданным значением.
    if student is None and kind not in STUDENT_KINDS:
        return None, [KIND_REQUIRED_MESSAGE]

    if _time_is_busy(db, slot):
        return None, [TIME_BUSY_MESSAGE]

    try:
        if student is None:
            student = _create_student(db, tutor.id, booking, kind)

        lesson = Lesson(
            student_id=student.id,
            type="individual",
            starts_at=as_utc(slot.starts_at),
            duration_min=slot.duration_min,
            status="planned",
        )
        db.add(lesson)
        db.flush()

        booking.status = "confirmed"
        booking.student_id = student.id
        booking.lesson_id = lesson.id
        booking.decided_at = as_utc(now)
        db.commit()
    except Exception:
        # Ни ученик, ни урок, ни смена статуса не должны остаться
        # наполовину: подтверждение — одна транзакция.
        db.rollback()
        raise
    return booking, []

def is_active(booking: Booking) -> bool:
    """Активна ли бронь (ожидает решения или подтверждена)."""
    return booking.status in ACTIVE_BOOKING_STATUSES
