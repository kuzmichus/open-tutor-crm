"""Агрегатор ORM-моделей.

Импортирует все доменные модели, чтобы они зарегистрировались на
`Base.metadata` — это нужно для `create_all` и для autogenerate в Alembic.
Новые доменные модели добавляются сюда.

Нарушает «один класс — один файл»? Нет: здесь нет ни одного класса,
только импорты-регистраторы.
"""

from app.group.models.group import Group  # noqa: F401
from app.group.models.group_member import GroupMember  # noqa: F401
from app.homework.models.homework import Homework  # noqa: F401
from app.lesson.models.lesson import Lesson  # noqa: F401
from app.lesson.models.lesson_series import LessonSeries  # noqa: F401
from app.student.models.contact import Contact  # noqa: F401
from app.student.models.student import Student  # noqa: F401
from app.student.models.student_contact import StudentContact  # noqa: F401
from app.tutor.models.password_reset_token import PasswordResetToken  # noqa: F401
from app.tutor.models.tutor import Tutor  # noqa: F401
from app.tutor.models.tutor_session import TutorSession  # noqa: F401
