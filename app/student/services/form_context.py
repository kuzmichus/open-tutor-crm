"""Контекст модальной формы ученика.

Общий для создания и редактирования: шаблон `_form.html` получает готовые
строки контактов, значения полей и адрес сохранения. Так форма не знает,
создают ученика или меняют, и не дублирует разметку.
"""

from sqlalchemy.orm import Session

from app.common.services.timezones import timezone_options_json
from app.student.models.student import Student, STUDENT_STATUSES
from app.student.services.presentation import (
    contact_row,
    empty_student_form,
    student_to_form,
)
from app.student.services.students import contact_links, contact_options_json

# Вкладки карточки ученика: закрытый список для `?tab=` (design D12).
# Сводка счёта на карточке открывает модалку сразу на «Платежах».
FORM_TABS = ("general", "payments", "settings")


def normalize_tab(value: str | None) -> str:
    """Имя вкладки из адреса; неизвестное или пустое — «Общее».

    Проверка на сервере, а не в шаблоне: `?tab=что-угодно` не должно
    открывать пустой таб, и в разметку не попадает значение из URL.
    """
    return value if value in FORM_TABS else FORM_TABS[0]


def form_context(
    db: Session,
    form: dict,
    *,
    tutor_id: str,
    student: Student | None = None,
    errors: list[str] | None = None,
    rows: list[dict] | None = None,
    from_card: bool = False,
    tab: str = "general",
) -> dict:
    """Готовит контекст `_form.html` для создания или редактирования.

    `rows` — строки контактов, введённые пользователем: при ошибке валидации
    форма показывается повторно с ними, а не с пустыми полями. Такие строки
    отрисовываются раскрытыми (`contact_rows_open`), чтобы ошибку было видно.

    `from_card` — форма открыта со страницы карточки: после сохранения
    обновляется вся страница, а не карточка в сетке (её там нет).

    `tab` — вкладка, на которой открывается модалка: сводка на карточке
    ученика ведёт сразу на «Платежи» (`?tab=payments`, design D12).
    Неизвестное значение сводится к «Общему» — иначе открылся бы пустой таб.

    Блок контактов по умолчанию не содержит пустых строк: привязанные
    контакты показываются свёрнутым списком, а добавление идёт через
    поиск по `contact_options_json` (все контакты репетитора, кроме уже
    привязанных к этой форме).
    """
    if rows is not None:
        contact_rows = [dict(row) for row in rows]
        contact_rows_open = True
    elif student is None:
        contact_rows = []
        contact_rows_open = False
    else:
        links = contact_links(db, [student.id]).get(student.id, [])
        contact_rows = [contact_row(item["link"], item["contact"]) for item in links]
        contact_rows_open = False

    if student is None:
        action = "/tutor/students"
        title = "Новый ученик"
        student_id = ""
    else:
        action = f"/tutor/students/{student.id}"
        title = "Карточка ученика"
        student_id = student.id

    return {
        "form": form,
        "contact_rows": contact_rows,
        "contact_rows_count": len(contact_rows),
        # Строки после ошибки валидации отрисовываются раскрытыми.
        "contact_rows_open": contact_rows_open,
        # Контакты репетитора для выпадающего списка «Добавить контакт»
        # (уже привязанные к форме исключены — они и так в списке строк).
        "contact_options_json": contact_options_json(
            db,
            tutor_id,
            exclude_ids={
                row["contact_id"] for row in contact_rows if row.get("contact_id")
            },
        ),
        "errors": errors or [],
        "student": student,
        "student_id": student_id,
        "action": action,
        "title": title,
        "from_card": from_card,
        # Вкладка, на которой открывается модалка. Пришло из адреса —
        # проверено вьюхой по закрытому списку (см. `TAB_NAMES`).
        "tab": tab,
        # Порядок статусов в селекте задаётся моделью, а не шаблоном.
        "statuses": STUDENT_STATUSES,
        # Справочник часовых зон (IANA) для селекта с поиском.
        "timezone_options_json": timezone_options_json(),
    }


def new_student_form_context() -> dict:
    """Контекст пустой формы создания."""
    return {"form": empty_student_form()}


def edit_student_form_context(db: Session, student: Student) -> dict:
    """Контекст формы редактирования существующего ученика."""
    return {"form": student_to_form(student)}
