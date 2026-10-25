"""Модель «Настройки репетитора»: уведомления, учебный год, уроки по умолчанию."""

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Закрытый набор оффсетов «напомнить за» (минуты до урока). Один источник
# истины для чекбоксов формы и для валидации: значение вне набора
# отбрасывается, а не сохраняется «как получится».
REMINDER_OFFSETS = (15, 60, 1440)
REMINDER_OFFSET_LABELS = {
    15: "15 минут",
    60: "1 час",
    1440: "24 часа",
}

# Дефолтное время дневной сводки («список уроков на день»).
DEFAULT_DIGEST_TIME = "09:00"

# Дефолтные даты окончания четвертей (ММ-ДД): пресеты серии уроков
# подставляют ближайшую будущую дату. Год не хранится — он вычисляется
# в момент использования.
QUARTER_DEFAULTS = ("10-25", "12-25", "03-20", "05-25")

# Дефолтная длительность урока (мин) и порог «низкого баланса» (₽).
DEFAULT_LESSON_DURATION = 60
DEFAULT_LOW_BALANCE_THRESHOLD = 0

# Значения полей по умолчанию — один источник истины для column-defaults
# и для объекта-заглушки, пока строка в БД не создана (column-defaults
# применяются только при INSERT, у transient-объекта поля были бы None).
DEFAULTS = {
    "notify_lesson_reminder": True,
    "notify_lesson_confirmation": True,
    "notify_daily_digest": True,
    "notify_cancellation": True,
    "notify_homework": True,
    "notify_debtors_weekly": True,
    "notify_low_balance": True,
    "notify_insufficient_funds": True,
    "notify_birthday": True,
    "reminder_offsets": [60],
    "digest_time": DEFAULT_DIGEST_TIME,
    "low_balance_threshold": DEFAULT_LOW_BALANCE_THRESHOLD,
    "default_lesson_duration": DEFAULT_LESSON_DURATION,
    "default_lesson_price": None,
    "quarter1_end": QUARTER_DEFAULTS[0],
    "quarter2_end": QUARTER_DEFAULTS[1],
    "quarter3_end": QUARTER_DEFAULTS[2],
    "quarter4_end": QUARTER_DEFAULTS[3],
}


def default_values() -> dict:
    """Свежий словарь значений по умолчанию.

    JSON-список копируется: разделяемый между строками объект был бы
    мутируемой бомбой (одна правка изменила бы «дефолт» для всех).
    """
    values = dict(DEFAULTS)
    values["reminder_offsets"] = list(DEFAULTS["reminder_offsets"])
    return values


class TutorSettings(Base):
    """Настройки репетитора — ровно одна строка на карточку.

    PK совпадает с FK: строка живёт и умирает вместе с репетитором
    (CASCADE), вторая строка на владельца невозможна. До первого
    сохранения строки нет — сервис отдаёт дефолты (см.
    app.tutor.services.settings).
    """

    __tablename__ = "tutor_settings"

    tutor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutors.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Уведомления. По умолчанию включены: настройка ahead-of-time —
    # при появлении каналов доставки переключатели уже значимы.
    notify_lesson_reminder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=DEFAULTS["notify_lesson_reminder"]
    )
    notify_lesson_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=DEFAULTS["notify_lesson_confirmation"]
    )
    notify_daily_digest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=DEFAULTS["notify_daily_digest"]
    )
    notify_cancellation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=DEFAULTS["notify_cancellation"]
    )
    notify_homework: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=DEFAULTS["notify_homework"]
    )
    notify_debtors_weekly: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=DEFAULTS["notify_debtors_weekly"]
    )
    notify_low_balance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=DEFAULTS["notify_low_balance"]
    )
    notify_insufficient_funds: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=DEFAULTS["notify_insufficient_funds"]
    )
    notify_birthday: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=DEFAULTS["notify_birthday"]
    )

    # За сколько напоминать об уроке: JSON-список минут из REMINDER_OFFSETS.
    # Читателю списка нельзя мутировать его на месте — присваивайте новый
    # список (SQLAlchemy не отслеживает правки содержимого JSON).
    reminder_offsets: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: list(DEFAULTS["reminder_offsets"])
    )

    # Время отправки дневной сводки, «ЧЧ:ММ» (настенное время зоны педагога).
    digest_time: Mapped[str] = mapped_column(
        String(5), nullable=False, default=DEFAULTS["digest_time"]
    )

    # Порог «низкого баланса»: уведомление при уходе баланса ниже суммы.
    low_balance_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULTS["low_balance_threshold"]
    )

    # Длительность и стоимость урока по умолчанию (мин, ₽). Длительность
    # валидируется формой по закрытому списку LESSON_DURATIONS модуля
    # lesson: CHECK дублировал бы список, а заполняется поле только формой.
    default_lesson_duration: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULTS["default_lesson_duration"]
    )
    default_lesson_price: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Учебный год: даты окончания четвертей, строки «ММ-ДД».
    quarter1_end: Mapped[str] = mapped_column(
        String(5), nullable=False, default=DEFAULTS["quarter1_end"]
    )
    quarter2_end: Mapped[str] = mapped_column(
        String(5), nullable=False, default=DEFAULTS["quarter2_end"]
    )
    quarter3_end: Mapped[str] = mapped_column(
        String(5), nullable=False, default=DEFAULTS["quarter3_end"]
    )
    quarter4_end: Mapped[str] = mapped_column(
        String(5), nullable=False, default=DEFAULTS["quarter4_end"]
    )

    def __repr__(self) -> str:
        return f"<TutorSettings tutor_id={self.tutor_id!r}>"
