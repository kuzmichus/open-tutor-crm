"""Отображение статусов ДЗ: подписи, чипы списков и значок календаря.

Чистые функции без БД и HTTP. Живут в домене ДЗ, а не в кабинете: статусы
показывают и кабинет ученика (чип списка, значок в карточке урока), и
календарь репетитора. Один закрытый список `HOMEWORK_STATUSES` — один
источник классов и подписей для обеих поверхностей.

Значок ДЗ в карточке календаря (`homework_badge_class`/`_label`) — тот же
набор статусов, что у чипа вкладки «Домашние задания»: цвет значка кодирует
статус, подпись уходит в `title`/`aria-label`.
"""

from app.homework.models.homework import HOMEWORK_STATUS_LABELS

# Модификатор чипа статуса: «Задано» — нейтральное, «Сдано» — работа
# отправлена, «Проверено» — финальное зелёное, «Не выполнено» — тревожное.
_HOMEWORK_CHIPS = {
    "assigned": "chip--hw-assigned",
    "submitted": "chip--hw-submitted",
    "checked": "chip--hw-checked",
    "not_done": "chip--hw-not-done",
}

# Модификатор значка ДЗ в карточке календаря: цвет кодирует статус —
# «Задано» нейтральное, «Сдано» акцентное, «Проверено» зелёное,
# «Не выполнено» тревожное. Отдельный набор классов, а не чипы: значок
# в карточке урока размером с иконку, плашка статуса там не помещается.
_HOMEWORK_BADGES = {
    "assigned": "cal-hw-badge--assigned",
    "submitted": "cal-hw-badge--submitted",
    "checked": "cal-hw-badge--checked",
    "not_done": "cal-hw-badge--not_done",
}


def homework_status_label(status: str) -> str:
    """Подпись статуса ДЗ: «Задано»; неизвестное значение — как есть."""
    return HOMEWORK_STATUS_LABELS.get(status, status)


def homework_chip_class(status: str) -> str:
    """Класс чипа статуса: «chip--hw-assigned»; неизвестное — нейтральный."""
    return _HOMEWORK_CHIPS.get(status, "chip--hw-assigned")


def homework_badge_class(status: str) -> str:
    """Класс значка ДЗ в карточке календаря; неизвестный статус — «Задано».

    Цвет — единственный носитель смысла значка, поэтому класс задаётся
    сервером по закрытому списку статусов, а не вычисляется в шаблоне.
    """
    return _HOMEWORK_BADGES.get(status, "cal-hw-badge--assigned")


def homework_badge_label(status: str) -> str:
    """Подпись значка ДЗ для `title`/`aria-label`: «Задано», «Проверено»…"""
    return homework_status_label(status)


def register_template_helpers() -> None:
    """Регистрирует функции отображения ДЗ в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        homework_status_label=homework_status_label,
        homework_chip_class=homework_chip_class,
        homework_badge_class=homework_badge_class,
        homework_badge_label=homework_badge_label,
    )
