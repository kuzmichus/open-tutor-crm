"""Агрегатор ORM-моделей.

Импортирует все доменные модели, чтобы они зарегистрировались на
`Base.metadata` — это нужно для `create_all` и для autogenerate в Alembic.
Новые доменные модели добавляются сюда.

Нарушает «один класс — один файл»? Нет: здесь нет ни одного класса,
только импорты-регистраторы.
"""

from app.booking.models.booking import Booking  # noqa: F401
from app.booking.models.booking_attempt import BookingAttempt  # noqa: F401
from app.cabinet.models.contact_access import ContactAccess  # noqa: F401
from app.cabinet.models.contact_invite import ContactCabinetInvite  # noqa: F401
from app.cabinet.models.contact_session import ContactSession  # noqa: F401
from app.cabinet.models.invite import StudentCabinetInvite  # noqa: F401
from app.cabinet.models.session import StudentSession  # noqa: F401
from app.finance.models.account_operation import AccountOperation  # noqa: F401
from app.gcalendar.models.calendar_event import CalendarEvent  # noqa: F401
from app.finance.models.expense import Expense  # noqa: F401
from app.finance.models.forecast_snapshot import ForecastSnapshot  # noqa: F401
from app.group.models.group import Group  # noqa: F401
from app.group.models.group_member import GroupMember  # noqa: F401
from app.homework.models.answer import HomeworkAnswer  # noqa: F401
from app.homework.models.answer_link import HomeworkAnswerLink  # noqa: F401
from app.homework.models.homework import Homework  # noqa: F401
from app.lesson.models.lesson import Lesson  # noqa: F401
from app.lesson.models.lesson_attendance import LessonAttendance  # noqa: F401
from app.lesson.models.lesson_series import LessonSeries  # noqa: F401
from app.mailing.models.message_template import MessageTemplate  # noqa: F401
from app.messenger.models.sent_message import SentMessage  # noqa: F401
from app.messenger.models.student_invite import StudentMessengerInvite  # noqa: F401
from app.slot.models.slot import Slot  # noqa: F401
from app.student.models.contact import Contact  # noqa: F401
from app.student.models.student_access import StudentAccess  # noqa: F401
from app.student.models.student import Student  # noqa: F401
from app.student.models.student_contact import StudentContact  # noqa: F401
from app.task.models.task import Task  # noqa: F401
from app.task.models.task_student import TaskStudent  # noqa: F401
from app.tutor.models.password_reset_token import PasswordResetToken  # noqa: F401
from app.tutor.models.tutor import Tutor  # noqa: F401
from app.tutor.models.tutor_param import TutorParam  # noqa: F401
from app.tutor.models.tutor_session import TutorSession  # noqa: F401
from app.tutor.models.tutor_settings import TutorSettings  # noqa: F401
from app.unavailability.models.unavailability import (  # noqa: F401
    TutorUnavailability,
)
