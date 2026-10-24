"""Блок брони в диалоге окна: кто заявился и какие действия доступны.

Действия с бронью живут в диалоге окна на календаре (design.md Risks:
отдельной страницы «Брони» пока нет), поэтому диалогу нужны не только
данные брони, но и решение, что показывать:

- ожидающая бронь → «Подтвердить» и «Отклонить», плюс выбор ученика,
  если по имени и контакту нашлось несколько совпадений (design D9);
- подтверждённая бронь → «Отменить» (урок и ученик при этом остаются,
  design D10);
- завершающая бронь → действий нет, показывается только статус.

Логика «что можно с бронью» — знание домена броней, поэтому живёт здесь,
а не в шаблоне окна. Зависимость `slot → booking` уже существует и без
этого модуля: состояние окна считается пересечением с активными бронями
(`slot/services/busy.py`), обратной зависимости нет.
"""

from sqlalchemy.orm import Session

from app.booking.models.booking import Booking
from app.booking.services.confirmation import candidate_students
from app.slot.models.slot import Slot
from app.slot.services.busy import active_bookings
from app.student.models.student import STUDENT_KINDS
from app.student.services.presentation import kind_label, student_full_name

def _candidate_row(student) -> dict:
    """Кандидат в ученики для выбора: id и подпись «Имя, телефон»."""
    parts = [student_full_name(student)]
    if student.phone:
        parts.append(student.phone)
    return {"id": student.id, "label": ", ".join(parts)}

def booking_panel(db: Session, slot: Slot | None) -> dict:
    """Контекст блока брони диалога окна.

    Возвращает плоские ключи, которые читает `slot/_dialog.html`:
    `slot_booking`, `slot_booking_pending`, `slot_booking_confirmed`,
    `slot_booking_candidates`, `slot_needs_student_choice`,
    `slot_student_kinds`.
    """
    empty = {
        "slot_booking": None,
        "slot_booking_pending": False,
        "slot_booking_confirmed": False,
        "slot_booking_candidates": [],
        "slot_needs_student_choice": False,
        "slot_student_kinds": tuple(
            (kind, kind_label(kind)) for kind in STUDENT_KINDS
        ),
    }
    if slot is None:
        return empty

    booking: Booking | None = active_bookings(db, [slot.id]).get(slot.id)
    if booking is None:
        return empty

    candidates: list[dict] = []
    if booking.status == "pending":
        # Кандидаты считаются сразу: при нескольких совпадениях педагог
        # обязан выбрать ученика (design D9), и выбор должен быть виден до
        # нажатия «Подтвердить», а не появляться после отказа.
        candidates = [
            _candidate_row(student)
            for student in candidate_students(db, slot.tutor_id, booking)
        ]

    return {
        **empty,
        "slot_booking": booking,
        "slot_booking_pending": booking.status == "pending",
        "slot_booking_confirmed": booking.status == "confirmed",
        "slot_booking_candidates": candidates,
        "slot_needs_student_choice": len(candidates) > 1,
    }
