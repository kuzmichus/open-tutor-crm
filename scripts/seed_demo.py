"""Наполнение локальной базы демонстрационными данными.

Скрипт собирает правдоподобный учебный год одного репетитора: 15 учеников
(дети и взрослые), переиспользуемые контакты взрослых (в том числе мама и
папа двух детей), две группы, серии уроков с 1 сентября по 25 мая,
проведённые занятия с сентября, платежи, должники, ДЗ, задачи и расходы.

Запуск (из корня проекта, база — `tutor.db` из `DATABASE_URL`):

    uv run python scripts/seed_demo.py

Скрипт **разрушающий**: данные репетитора `demo@example.com` удаляются
целиком и создаются заново. Сама карточка репетитора пересоздаётся с тем же
email и паролем `12345678`, поэтому вход не меняется. Остальные репетиторы
(если они есть в базе) не затрагиваются.

Данные пишутся через ORM и доменные сервисы (`sync_lesson_charge`), а не
сырым SQL: списания за проведённые уроки должны считаться той же формулой,
что и в приложении, иначе демо-база покажет другой баланс, чем боевая.
"""

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

# Скрипт запускают из корня проекта, но `python scripts/seed_demo.py` не
# добавляет корень в sys.path — делаем это сами, чтобы работали оба способа.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.common.colors import assign_color  # noqa: E402
from app.common.services.tutor_time import to_utc, tutor_zone  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.finance.models.account_operation import AccountOperation  # noqa: E402
from app.finance.models.expense import Expense  # noqa: E402
from app.finance.services.balance import balance  # noqa: E402
from app.finance.services.charges import sync_lesson_charge  # noqa: E402
from app.group.models.group import Group  # noqa: E402
from app.group.models.group_member import GroupMember  # noqa: E402
from app.homework.models.answer import HomeworkAnswer  # noqa: E402
from app.homework.models.answer_link import HomeworkAnswerLink  # noqa: E402
from app.homework.models.homework import Homework  # noqa: E402
from app.lesson.models.lesson import Lesson  # noqa: E402
from app.lesson.models.lesson_attendance import LessonAttendance  # noqa: E402
from app.lesson.models.lesson_series import LessonSeries  # noqa: E402
from app.mailing.models.message_template import MessageTemplate  # noqa: E402
from app.student.models.contact import Contact  # noqa: E402
from app.student.models.student import Student  # noqa: E402
from app.student.models.student_contact import StudentContact  # noqa: E402
from app.task.models.task import Task  # noqa: E402
from app.task.models.task_student import TaskStudent  # noqa: E402
from app.tutor.models.tutor import Tutor  # noqa: E402
from app.tutor.models.tutor_settings import TutorSettings  # noqa: E402
from app.tutor.services.clock import as_utc  # noqa: E402
from app.tutor.services.password_hasher import PasswordHasher  # noqa: E402
from app.unavailability.models.unavailability import TutorUnavailability  # noqa: E402

# Аккаунт демо-репетитора: пересоздаётся с тем же email и паролем.
TUTOR_EMAIL = "demo@example.com"
TUTOR_PASSWORD = "12345678"
TUTOR_TIMEZONE = "Europe/Ulyanovsk"

# Границы учебного года. 1 сентября 2026 — вторник, 25 мая 2027 — вторник.
STUDY_START = date(2026, 9, 1)
STUDY_END = date(2027, 5, 25)
# Зимние каникулы: уроки в этот период не генерируются (как и в жизни —
# серия их пропускает, а не переносит).
VACATION_START = date(2026, 12, 28)
VACATION_END = date(2027, 1, 10)

# Дни недели как в `date.weekday()`: 0 — понедельник, 6 — воскресенье.
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)

# ---------------------------------------------------------------------------
# Контакты взрослых. Один контакт может быть привязан к нескольким ученикам:
# так появляются семьи, где мама и папа ведут двух детей.
# ---------------------------------------------------------------------------

CONTACTS: list[dict] = [
    {
        "key": "olga",
        "full_name": "Ольга Ахматова",
        "phone": "+7 927 100-10-01",
        "email": "olga.ahmatova@example.com",
    },
    {
        "key": "dmitry",
        "full_name": "Дмитрий Ахматов",
        "phone": "+7 927 100-10-02",
        "email": None,
    },
    {
        "key": "elena",
        "full_name": "Елена Смирнова",
        "phone": "+7 927 100-20-01",
        "email": "elena.smirnova@example.com",
    },
    {
        "key": "alexey",
        "full_name": "Алексей Смирнов",
        "phone": "+7 927 100-20-02",
        "email": None,
    },
    {
        "key": "andrey",
        "full_name": "Андрей Кузнецов",
        "phone": "+7 927 100-30-01",
        "email": "andrey.kuznetsov@example.com",
    },
    {
        "key": "nina",
        "full_name": "Нина Петрова",
        "phone": "+7 927 100-40-01",
        "email": None,
    },
    {
        # Мама без телефона — переписка только по email.
        "key": "irina",
        "full_name": "Ирина Волкова",
        "phone": None,
        "email": "irina.volkova@example.com",
    },
    {
        "key": "svetlana",
        "full_name": "Светлана Морозова",
        "phone": "+7 927 100-50-01",
        "email": "svetlana.morozova@example.com",
    },
    {
        "key": "igor",
        "full_name": "Игорь Морозов",
        "phone": "+7 927 100-50-02",
        "email": None,
    },
    {
        "key": "sergey",
        "full_name": "Сергей Лебедев",
        "phone": "+7 927 100-60-01",
        "email": None,
    },
    {
        "key": "oksana",
        "full_name": "Оксана Новикова",
        "phone": "+7 927 100-70-01",
        "email": None,
    },
    {
        "key": "yulia",
        "full_name": "Юлия Зайцева",
        "phone": "+7 927 100-80-01",
        "email": "yulia.zaytseva@example.com",
    },
    {
        # Взрослый ученик: платит супруга, а не он сам.
        "key": "irina_g",
        "full_name": "Ирина Гусева",
        "phone": "+7 927 100-90-01",
        "email": None,
    },
    {
        # Только email: заявка пришла через сайт, телефона ещё нет.
        "key": "marina",
        "full_name": "Марина Тихонова",
        "phone": None,
        "email": "marina.tihonova@example.com",
    },
]

# ---------------------------------------------------------------------------
# Ученики. `slots` — недельное расписание индивидуальных уроков;
# `contacts` — привязки «контакт, роль, напоминания (урок, ДЗ, отмена)».
# ---------------------------------------------------------------------------

STUDENTS: list[dict] = [
    {
        "key": "petya",
        "first_name": "Петя",
        "last_name": "Ахматов",
        "kind": "child",
        "grade": 7,
        "school": "Гимназия №1",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Средний",
        "notes": "Уверенно решает линейные уравнения, проседает геометрия.",
        "price": 1500,
        "payer": "olga",
        "slots": [{"weekday": MON, "start": "16:00", "duration": 60}],
        "contacts": [
            ("olga", "мама", True, True, True),
            ("dmitry", "папа", True, False, False),
        ],
    },
    {
        # Сестра Пети: тот же контакт мамы и папы, второй ребёнок в семье.
        "key": "masha",
        "first_name": "Маша",
        "last_name": "Ахматова",
        "kind": "child",
        "grade": 5,
        "school": "Гимназия №1",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Начальный",
        "notes": "Только перешли в пятый класс, привыкаем к дробям.",
        "price": 1300,
        "payer": "dmitry",
        "slots": [{"weekday": MON, "start": "17:00", "duration": 60}],
        "contacts": [
            ("olga", "мама", True, True, True),
            ("dmitry", "папа", True, False, False),
        ],
    },
    {
        "key": "vanya",
        "first_name": "Ваня",
        "last_name": "Смирнов",
        "kind": "child",
        "grade": 9,
        "school": "Лицей №2",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Выше среднего",
        "notes": "Готовимся к ОГЭ, нужен упор на вторую часть.",
        "price": 1800,
        "payer": "elena",
        "slots": [{"weekday": WED, "start": "17:00", "duration": 90}],
        "contacts": [
            ("elena", "мама", True, True, True),
            ("alexey", "папа", True, False, False),
        ],
    },
    {
        # Младшая сестра Вани — тот же контакт родителей, второй ребёнок.
        "key": "sonya",
        "first_name": "Соня",
        "last_name": "Смирнова",
        "kind": "child",
        "grade": 3,
        "school": "Лицей №2",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Начальный",
        "notes": "Таблица умножения, счёт в столбик.",
        "price": 900,
        "payer": "elena",
        "slots": [{"weekday": WED, "start": "16:00", "duration": 45}],
        "contacts": [
            ("elena", "мама", True, True, False),
            ("alexey", "папа", True, False, False),
        ],
    },
    {
        "key": "artem",
        "first_name": "Артём",
        "last_name": "Кузнецов",
        "kind": "child",
        "grade": 11,
        "school": "Школа №7",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Высокий",
        "notes": "ЕГЭ профиль, цель — 80+. Октябрь не оплачен.",
        "price": 2000,
        "payer": "andrey",
        "slots": [
            {"weekday": TUE, "start": "19:00", "duration": 90},
            {"weekday": THU, "start": "19:30", "duration": 90},
        ],
        "contacts": [("andrey", "папа", True, False, True)],
    },
    {
        # Плательщик — бабушка, родителей в CRM нет.
        "key": "liza",
        "first_name": "Лиза",
        "last_name": "Петрова",
        "kind": "child",
        "grade": 8,
        "school": "Гимназия №1",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Средний",
        "notes": "Живёт с бабушкой, вопросы по деньгам — только ей.",
        "price": 1400,
        "payer": "nina",
        "slots": [{"weekday": THU, "start": "17:00", "duration": 60}],
        "contacts": [("nina", "бабушка", True, True, True)],
    },
    {
        "key": "gleb",
        "first_name": "Глеб",
        "last_name": "Волков",
        "kind": "child",
        "grade": 6,
        "school": "Школа №7",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Средний",
        "notes": "Онлайн. Мама просит писать только на почту.",
        "price": 1300,
        "payer": "irina",
        "slots": [{"weekday": FRI, "start": "16:00", "duration": 60}],
        "contacts": [("irina", "мама", True, True, False)],
    },
    {
        "key": "nastya",
        "first_name": "Настя",
        "last_name": "Морозова",
        "kind": "child",
        "grade": 10,
        "school": "Лицей №2",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Высокий",
        "notes": "Внесла предоплату за два месяца вперёд.",
        "price": 1900,
        "payer": "svetlana",
        "slots": [{"weekday": MON, "start": "18:30", "duration": 90}],
        "contacts": [
            ("svetlana", "мама", True, True, True),
            ("igor", "папа", True, False, False),
        ],
    },
    {
        "key": "kirill",
        "first_name": "Кирилл",
        "last_name": "Лебедев",
        "kind": "child",
        "grade": 4,
        "school": "Школа №3",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Начальный",
        "notes": "Занимаемся по 45 минут, тяжело удерживает внимание.",
        "price": 900,
        "payer": "sergey",
        "slots": [{"weekday": TUE, "start": "16:00", "duration": 45}],
        "contacts": [("sergey", "папа", True, False, False)],
    },
    {
        "key": "polina",
        "first_name": "Полина",
        "last_name": "Новикова",
        "kind": "child",
        "grade": 9,
        "school": "Гимназия №1",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Средний",
        "notes": "Октябрь оплачен наполовину, напомнить о долге.",
        "price": 1800,
        "payer": "oksana",
        "slots": [{"weekday": THU, "start": "18:00", "duration": 90}],
        "contacts": [("oksana", "мама", True, True, True)],
    },
    {
        # Ученик без контакта взрослого: платит сам, связь по его телефону.
        "key": "danila",
        "first_name": "Данила",
        "last_name": "Орлов",
        "kind": "child",
        "grade": 7,
        "school": "Школа №3",
        "phone": "+7 927 200-11-22",
        "email": None,
        "status": "active",
        "level": "Средний",
        "notes": "Приходит сам, деньги передаёт наличными через репетитора.",
        "price": 1400,
        "payer": None,
        "slots": [{"weekday": WED, "start": "19:00", "duration": 60}],
        "contacts": [],
    },
    {
        "key": "timofey",
        "first_name": "Тимофей",
        "last_name": "Зайцев",
        "kind": "child",
        "grade": 2,
        "school": "Школа №3",
        "phone": None,
        "email": None,
        "status": "active",
        "level": "Начальный",
        "notes": "Самый младший ученик, занимаемся по субботам.",
        "price": 800,
        "payer": "yulia",
        "slots": [{"weekday": SAT, "start": "10:00", "duration": 45}],
        "contacts": [("yulia", "мама", True, True, True)],
    },
    {
        # Взрослая ученица: своя карточка, контактов взрослых нет.
        "key": "alisa",
        "first_name": "Алиса",
        "last_name": "Белова",
        "kind": "adult",
        "grade": None,
        "school": None,
        "phone": "+7 927 300-44-55",
        "email": "alisa.belova@example.com",
        "status": "active",
        "level": "Средний",
        "notes": "Готовится к вступительному экзамену в магистратуру.",
        "price": 2200,
        "payer": None,
        "slots": [{"weekday": WED, "start": "20:00", "duration": 90}],
        "contacts": [],
    },
    {
        # Взрослый ученик, плательщик — супруга.
        "key": "mark",
        "first_name": "Марк",
        "last_name": "Гусев",
        "kind": "adult",
        "grade": None,
        "school": None,
        "phone": "+7 927 300-66-77",
        "email": "mark.gusev@example.com",
        "status": "active",
        "level": "Начальный",
        "notes": "Взрослый, восстанавливает школьную программу.",
        "price": 1800,
        "payer": "irina_g",
        "slots": [{"weekday": THU, "start": "16:00", "duration": 60}],
        "contacts": [("irina_g", "супруга", True, False, False)],
    },
    {
        # Новый ученик: только пробный урок, денег ещё нет.
        "key": "egor",
        "first_name": "Егор",
        "last_name": "Тихонов",
        "kind": "child",
        "grade": 6,
        "school": "Школа №7",
        "phone": None,
        "email": None,
        "status": "new",
        "level": None,
        "notes": "Заявка с сайта, пробный урок 3 ноября.",
        "price": None,
        "payer": "marina",
        "slots": [],
        "contacts": [("marina", "мама", True, False, False)],
    },
]

# ---------------------------------------------------------------------------
# Группы. Цена — за урок с человека; у участника может быть своя цена.
# ---------------------------------------------------------------------------

GROUPS: list[dict] = [
    {
        "key": "oge",
        "name": "ОГЭ математика",
        "description": "Подготовка к ОГЭ, вторник 17:00. Разбираем вторую часть.",
        "price_per_lesson": 900,
        "meeting_url": "https://meet.example.com/oge-math",
        "notes": "Домашку сдаём в чат группы до следующего занятия.",
        "slots": [{"weekday": TUE, "start": "17:00", "duration": 90}],
        "members": [("vanya", 800), ("polina", None)],
    },
    {
        "key": "club",
        "name": "Математический кружок",
        "description": "6–8 класс, суббота 11:00: олимпиадные задачи и логика.",
        "price_per_lesson": 700,
        "meeting_url": None,
        "notes": "Оплата помесячно, можно присоединиться в любой момент.",
        "slots": [{"weekday": SAT, "start": "11:00", "duration": 90}],
        "members": [("petya", None), ("gleb", None), ("liza", None), ("danila", None)],
    },
]

# Отметки присутствия на групповых уроках (остальные — по умолчанию все были).
# Отсутствовавший не получает списание за это занятие.
ATTENDANCE: list[tuple[str, date, str, bool, str | None]] = [
    ("oge", date(2026, 10, 13), "polina", False, "excused"),
    ("oge", date(2026, 9, 22), "vanya", False, "no_reason"),
    ("club", date(2026, 10, 10), "gleb", False, "no_reason"),
    ("club", date(2026, 10, 24), "liza", False, "excused"),
]

# Модель оплаты ученика за сентябрь и октябрь:
#   full        — платит ровно сумму списаний месяца (баланс около нуля);
#   credit      — платит с запасом (предоплата, положительный баланс);
#   debt_full   — сентябрь оплачен, октябрь нет (должник);
#   debt_half   — сентябрь оплачен, октябрь наполовину (должник).
PAYMENT_POLICY: dict[str, dict] = {
    "petya": {"kind": "full", "method": "transfer"},
    "masha": {"kind": "full", "method": "card"},
    "vanya": {"kind": "full", "method": "transfer"},
    "sonya": {"kind": "credit", "method": "card", "extra": 3000},
    "artem": {"kind": "debt_full", "method": "transfer"},
    "liza": {"kind": "full", "method": "card"},
    "gleb": {"kind": "full", "method": "online"},
    "nastya": {"kind": "credit", "method": "transfer", "extra": 6000},
    "kirill": {"kind": "full", "method": "card"},
    "polina": {"kind": "debt_half", "method": "transfer"},
    "danila": {"kind": "full", "method": "online"},
    "timofey": {"kind": "full", "method": "card"},
    "alisa": {"kind": "credit", "method": "online", "extra": 5000},
    "mark": {"kind": "full", "method": "transfer"},
}

# ДЗ по урокам: (ключ ученика, дата урока, задание, срок, статус, ответ, ссылка).
HOMEWORK: list[dict] = [
    {
        "student": "petya",
        "lesson_date": date(2026, 10, 26),
        "assignment": "№ 4.12–4.18 из сборника: системы уравнений.",
        "due": date(2026, 10, 29),
        "status": "checked",
        "answer": "Решил всё, кроме 4.17 — не сходится ответ.",
        "link": "https://disk.example.com/petya/hw-1026.pdf",
        "teacher_comment": "4.17 разберём на уроке, остальное верно.",
    },
    {
        "student": "masha",
        "lesson_date": date(2026, 10, 26),
        "assignment": "Сложение дробей с разными знаменателями, карточка 3.",
        "due": date(2026, 10, 28),
        "status": "submitted",
        "answer": "Фото решения прикрепила.",
        "link": "https://disk.example.com/masha/hw-1026.jpg",
    },
    {
        "student": "vanya",
        "lesson_date": date(2026, 10, 21),
        "assignment": "Вариант № 7, задания 1–19.",
        "due": date(2026, 10, 27),
        "status": "assigned",
    },
    {
        "student": "gleb",
        "lesson_date": date(2026, 10, 23),
        "assignment": "Задачи на проценты, № 5–12.",
        "due": date(2026, 10, 26),
        "status": "not_done",
    },
    {
        "student": "polina",
        "lesson_date": date(2026, 10, 22),
        "assignment": "Геометрическая задача № 24 (ОГЭ), оформить полностью.",
        "due": date(2026, 10, 29),
        "status": "checked",
        "answer": "Оформила с чертежом.",
        "link": "https://disk.example.com/polina/hw-1022.pdf",
        "teacher_comment": "Отлично, только подпиши единицы измерения.",
    },
    {
        # ДЗ к ещё не проведённому уроку: статус «Задано», ответа нет.
        "student": "nastya",
        "lesson_date": date(2026, 11, 2),
        "assignment": "Повторить тригонометрию, решить вариант 3 из сборника ЕГЭ.",
        "due": date(2026, 11, 6),
        "status": "assigned",
    },
    {
        "student": "alisa",
        "lesson_date": date(2026, 10, 28),
        "assignment": "Производная: разобрать примеры 1–9 по конспекту.",
        "due": date(2026, 11, 4),
        "status": "checked",
        "answer": "Разобрала, вопрос по пределу в примере 7.",
        "recording": "https://disk.example.com/alisa/lesson-1028.mp4",
        "teacher_comment": "Запись урока приложена, предел разберём в среду.",
    },
]

# Задачи репетитора: (название, этап, приоритет, срок, описание, ученики).
TASKS: list[tuple[str, str, str, date | None, str, list[str]]] = [
    (
        "Напомнить Артёму об оплате за октябрь",
        "new",
        "high",
        date(2026, 11, 3),
        "Долг 18 000 ₽ за 9 уроков, папа просил счёт на почту.",
        ["artem"],
    ),
    (
        "Собрать результаты пробника ОГЭ",
        "in_progress",
        "high",
        date(2026, 11, 10),
        "Ваня и Полина писали пробник 25 октября, нужно свести баллы.",
        ["vanya", "polina"],
    ),
    (
        "Согласовать расписание на январь",
        "new",
        "medium",
        date(2026, 12, 20),
        "Каникулы с 28 декабря, часть учеников уезжает до 12 января.",
        [],
    ),
    (
        "Продлить подписку на онлайн-доску",
        "review",
        "low",
        date(2026, 11, 5),
        "Оплачено до 7 ноября, продлить на год со скидкой.",
        [],
    ),
    (
        "Заказать рабочие тетради на второе полугодие",
        "in_progress",
        "low",
        date(2026, 11, 15),
        "Для Сони и Кирилла — по одной тетради.",
        ["sonya", "kirill"],
    ),
    (
        "Проверить ДЗ за октябрь",
        "done",
        "medium",
        date(2026, 10, 30),
        "Все присланные работы проверены и прокомментированы.",
        [],
    ),
]

# Расходы репетитора: (категория, сумма, дата, комментарий).
EXPENSES: list[tuple[str, int, date, str]] = [
    ("rent", 15000, date(2026, 9, 1), "Аренда кабинета, сентябрь"),
    ("rent", 15000, date(2026, 10, 1), "Аренда кабинета, октябрь"),
    ("rent", 15000, date(2026, 11, 1), "Аренда кабинета, ноябрь"),
    ("software", 990, date(2026, 10, 3), "Подписка на онлайн-доску"),
    ("materials", 2400, date(2026, 9, 12), "Рабочие тетради и сборники ОГЭ"),
    ("ads", 3000, date(2026, 10, 5), "Реклама в соцсетях, октябрь"),
]

# Шаблоны рассылок: (название, текст с подстановками).
TEMPLATES: list[tuple[str, str]] = [
    (
        "Напоминание об оплате",
        "Здравствуйте, {имя}! Напоминаю об оплате занятий: баланс {баланс}. "
        "Спасибо!",
    ),
    (
        "Перенос урока",
        "{имя}, добрый день! Нужно перенести занятие {дата}. "
        "Напишите, какое время вам удобно.",
    ),
]


def _slot(weekday: int, start: str, duration: int) -> dict:
    """Слот расписания: день недели, начало «ЧЧ:ММ» и длительность."""
    hours, minutes = (int(part) for part in start.split(":"))
    started = time(hours, minutes)
    ended = (datetime.combine(date(2000, 1, 1), started) + timedelta(minutes=duration)).time()
    return {
        "weekday": weekday,
        "start_time": started.strftime("%H:%M"),
        "end_time": ended.strftime("%H:%M"),
        "start": started,
        "duration": duration,
    }


def _in_vacation(day: date) -> bool:
    """Попадает ли день в зимние каникулы (уроки не генерируются)."""
    return VACATION_START <= day <= VACATION_END


def _reset_demo_data(db, email: str) -> None:
    """Удаляет демо-репетитора со всеми его данными.

    Два исключения из каскада, которые приходится удалять руками:

    * `tutor_sessions` и `tutor_password_reset_tokens` — их FK объявлен без
      `ondelete="CASCADE"`, поэтому DELETE репетитора упирается в них;
    * серии уроков — у них нет `tutor_id`, каскад от репетитора их не достанет.

    Серии собираются **по урокам этого репетитора**, а не глобальным
    `DELETE FROM lesson_series`: иначе прогон скрипта стёр бы расписания
    всех остальных аккаунтов в базе. Остальное уходит каскадом от `tutors`.
    """
    tutor_ids = [
        row[0]
        for row in db.execute(
            text("SELECT id FROM tutors WHERE email = :email"), {"email": email}
        )
    ]
    if not tutor_ids:
        db.commit()
        return

    for table in ("tutor_sessions", "tutor_password_reset_tokens"):
        db.execute(
            text(f"DELETE FROM {table} WHERE tutor_id = :id"),
            [{"id": tutor_id} for tutor_id in tutor_ids],
        )

    # Серии, на которые ссылаются уроки этого репетитора — до каскадного
    # удаления уроков, иначе связь уже потеряна.
    series_ids = [
        row[0]
        for row in db.execute(
            text(
                "SELECT DISTINCT l.series_id FROM lessons l "
                "WHERE l.series_id IS NOT NULL AND ("
                "l.student_id IN (SELECT id FROM students WHERE tutor_id = :id) "
                "OR l.group_id IN (SELECT id FROM groups WHERE tutor_id = :id))"
            ),
            [{"id": tutor_id} for tutor_id in tutor_ids],
        )
    ]

    db.execute(text("DELETE FROM tutors WHERE email = :email"), {"email": email})
    if series_ids:
        db.execute(
            text("DELETE FROM lesson_series WHERE id = :id"),
            [{"id": series_id} for series_id in series_ids],
        )
    db.commit()


def _create_tutor(db) -> Tutor:
    """Пересоздаёт карточку демо-репетитора с прежними учётными данными."""
    tutor = Tutor(
        name="Сергей Кузин",
        email=TUTOR_EMAIL,
        password_hash=PasswordHasher().hash(TUTOR_PASSWORD),
        phone="+7 927 000-00-01",
        about="Репетитор по математике: ОГЭ, ЕГЭ и школьная программа 5–11 классов.",
        subject="Математика",
        experience="12 лет, из них 5 — подготовка к ОГЭ и ЕГЭ.",
        timezone=TUTOR_TIMEZONE,
    )
    db.add(tutor)
    db.flush()

    db.add(
        TutorSettings(
            tutor_id=tutor.id,
            reminder_offsets=[60, 1440],
            digest_time="08:30",
            workday_start="07:00",
            workday_end="22:00",
            default_lesson_duration=60,
            default_lesson_price=1500,
            quarter1_end="10-25",
            quarter2_end="12-25",
            quarter3_end="03-20",
            quarter4_end="05-25",
        )
    )
    db.flush()
    return tutor


def _create_contacts(db, tutor: Tutor) -> dict[str, Contact]:
    """Создаёт контакты взрослых; возвращает их по ключу."""
    contacts: dict[str, Contact] = {}
    for data in CONTACTS:
        contact = Contact(
            tutor_id=tutor.id,
            full_name=data["full_name"],
            phone=data["phone"],
            email=data["email"],
        )
        db.add(contact)
        contacts[data["key"]] = contact
    db.flush()
    return contacts


def _create_students(
    db, tutor: Tutor, contacts: dict[str, Contact]
) -> dict[str, Student]:
    """Создаёт учеников, их привязки к контактам и плательщика."""
    students: dict[str, Student] = {}
    for data in STUDENTS:
        payer = contacts.get(data["payer"]) if data["payer"] else None
        student = Student(
            tutor_id=tutor.id,
            first_name=data["first_name"],
            last_name=data["last_name"],
            kind=data["kind"],
            grade=data["grade"],
            school=data["school"],
            phone=data["phone"],
            email=data["email"],
            level=data["level"],
            notes=data["notes"],
            status=data["status"],
            remind_lesson=True,
            remind_homework=data["kind"] == "child",
            remind_cancel=True,
            payer_contact_id=payer.id if payer else None,
        )
        db.add(student)
        db.flush()
        # Цвет выдаём после flush: `assign_color` смотрит на занятые цвета
        # в базе, и без flush соседние ученики получили бы один и тот же.
        student.color = assign_color(db, tutor.id)
        db.flush()
        students[data["key"]] = student

        for contact_key, relation, remind_lesson, remind_homework, remind_cancel in data[
            "contacts"
        ]:
            db.add(
                StudentContact(
                    student_id=student.id,
                    contact_id=contacts[contact_key].id,
                    relation=relation,
                    remind_lesson=remind_lesson,
                    remind_homework=remind_homework,
                    remind_cancel=remind_cancel,
                )
            )
    db.flush()
    return students


def _create_groups(
    db, tutor: Tutor, students: dict[str, Student]
) -> dict[str, Group]:
    """Создаёт группы и их состав (с индивидуальными ценами участников)."""
    groups: dict[str, Group] = {}
    joined = to_utc(datetime.combine(STUDY_START, time(10, 0)), tutor)
    for data in GROUPS:
        group = Group(
            tutor_id=tutor.id,
            name=data["name"],
            description=data["description"],
            price_per_lesson=data["price_per_lesson"],
            meeting_url=data["meeting_url"],
            notes=data["notes"],
        )
        db.add(group)
        db.flush()
        group.color = assign_color(db, tutor.id)
        db.flush()
        groups[data["key"]] = group

        for student_key, override in data["members"]:
            db.add(
                GroupMember(
                    group_id=group.id,
                    student_id=students[student_key].id,
                    joined_at=joined,
                    price_override=override,
                )
            )
    db.flush()
    return groups


def _create_series(
    db,
    tutor: Tutor,
    slots: list[dict],
) -> LessonSeries:
    """Серия повторяющихся уроков: слоты, интервал и конец учебного года."""
    series = LessonSeries(
        slots=[
            {
                "weekday": slot["weekday"],
                "start_time": slot["start_time"],
                "end_time": slot["end_time"],
            }
            for slot in slots
        ],
        interval_weeks=1,
        until_date=STUDY_END,
    )
    db.add(series)
    db.flush()
    return series


def _generate_lessons(
    db,
    tutor: Tutor,
    series: LessonSeries,
    slots: list[dict],
    *,
    now: datetime,
    student: Student | None = None,
    group: Group | None = None,
    lesson_type: str,
    price: int | None,
    meeting_url: str | None = None,
    note: str | None = None,
) -> list[Lesson]:
    """Материализует уроки серии от начала учебного года до его конца.

    Прошедшие занятия сразу помечаются проведёнными: демо-база должна
    выглядеть как живой журнал, а не как «всё запланировано».
    """
    created: list[Lesson] = []
    day = STUDY_START
    while day <= STUDY_END:
        for slot in slots:
            if day.weekday() != slot["weekday"] or _in_vacation(day):
                continue
            starts_at = to_utc(datetime.combine(day, slot["start"]), tutor)
            lesson = Lesson(
                student_id=student.id if student else None,
                group_id=group.id if group else None,
                series_id=series.id,
                type=lesson_type,
                starts_at=starts_at,
                duration_min=slot["duration"],
                price=price,
                status="completed" if starts_at < now else "planned",
                meeting_url=meeting_url,
                note=note,
            )
            db.add(lesson)
            created.append(lesson)
        day += timedelta(days=1)
    db.flush()
    return created


def _add_extra_lessons(
    db, tutor: Tutor, students: dict[str, Student]
) -> list[Lesson]:
    """Разовые уроки вне серий: отработка и пробный урок нового ученика.

    Возвращает созданные уроки — вызывающий обязан включить их в общий
    список для синхронизации списаний, иначе проведённая отработка
    останется без списания и «Пересчитать баланс» придётся жать вручную.
    """
    # Отработка: Петя пропустил занятие 12 октября (болезнь) — занимались
    # в субботу. Тип «Отработка», цена как у обычного урока.
    practice = Lesson(
        student_id=students["petya"].id,
        type="practice",
        starts_at=to_utc(datetime.combine(date(2026, 10, 17), time(12, 30)), tutor),
        duration_min=60,
        price=1500,
        status="completed",
        note="Отработка пропущенного урока от 12 октября.",
    )
    # Пробный урок Егора: плановый, цена не задана — денег он не списывает.
    trial = Lesson(
        student_id=students["egor"].id,
        type="trial",
        starts_at=to_utc(datetime.combine(date(2026, 11, 3), time(15, 0)), tutor),
        duration_min=45,
        price=None,
        status="planned",
        note="Пробный урок по заявке с сайта.",
    )
    db.add_all([practice, trial])
    db.flush()
    return [practice, trial]


def _mark_attendance(
    db,
    lessons_by_key: dict[tuple[str, date], Lesson],
    students: dict[str, Student],
) -> None:
    """Ставит отметки неявки на групповых уроках (причина из закрытого списка)."""
    for group_key, day, student_key, present, reason in ATTENDANCE:
        lesson = lessons_by_key.get((f"group:{group_key}", day))
        if lesson is None:  # урок попал в каникулы или не сгенерирован
            continue
        db.add(
            LessonAttendance(
                lesson_id=lesson.id,
                student_id=students[student_key].id,
                present=present,
                reason=reason,
            )
        )
    db.flush()


def _sync_charges(db, lessons: list[Lesson]) -> None:
    """Создаёт списания за проведённые уроки общей формулой приложения."""
    for lesson in lessons:
        if lesson.status == "completed":
            sync_lesson_charge(db, lesson)
    db.flush()


def _month_charges(db, tutor: Tutor, student_id: str, year: int, month: int) -> int:
    """Сумма списаний ученика за календарный месяц (в зоне педагога).

    Считается по уже созданным строкам счёта, а не по расписанию: тогда
    платежи в демо-базе сходятся с балансом даже там, где были неявки.
    """
    rows = db.execute(
        select(AccountOperation.amount, AccountOperation.occurred_at).where(
            AccountOperation.student_id == student_id,
            AccountOperation.kind == "lesson",
        )
    ).all()
    total = 0
    for amount, occurred_at in rows:
        local = as_utc(occurred_at).astimezone(tutor_zone(tutor))
        if (local.year, local.month) == (year, month):
            total += amount
    return total


def _round_up(value: int, step: int = 100) -> int:
    """Округление вверх до шага: суммы платежей выглядят «человеческими»."""
    if value <= 0:
        return 0
    return ((value + step - 1) // step) * step


def _payment_at(tutor: Tutor, day: date, hour: int = 12) -> datetime:
    """Момент операции: календарный день и время ввода в зоне педагога (UTC)."""
    return to_utc(datetime.combine(day, time(hour, 0)), tutor)


def _create_payments(
    db, tutor: Tutor, students: dict[str, Student]
) -> dict[str, AccountOperation]:
    """Платежи за сентябрь и октябрь по модели оплаты каждого ученика."""
    payments: dict[str, AccountOperation] = {}
    for key, plan in PAYMENT_POLICY.items():
        student = students[key]
        september = _month_charges(db, tutor, student.id, 2026, 9)
        october = _month_charges(db, tutor, student.id, 2026, 10)
        kind = plan["kind"]

        first_amount = _round_up(september)
        if kind == "credit":
            first_amount += plan.get("extra", 0)
        second_amount = _round_up(october)
        if kind == "debt_full":
            second_amount = 0
        elif kind == "debt_half":
            second_amount = (october // 2) // 100 * 100

        for amount, day, comment in (
            (first_amount, date(2026, 9, 3), "Оплата за сентябрь"),
            (second_amount, date(2026, 10, 5), "Оплата за октябрь"),
        ):
            if amount <= 0:
                continue
            payment = AccountOperation(
                student_id=student.id,
                kind="payment",
                amount=amount,
                occurred_at=_payment_at(tutor, day),
                status="paid",
                method=plan["method"],
                comment=comment,
            )
            db.add(payment)
            payments[key] = payment
    db.flush()

    # Возврат по платежу Насти: предоплата оказалась больше, чем нужно —
    # часть денег вернули на карту. Должнику возврат не делают, поэтому
    # история привязана к ученику с положительным балансом.
    refund = AccountOperation(
        student_id=students["nastya"].id,
        kind="refund",
        amount=2000,
        occurred_at=_payment_at(tutor, date(2026, 10, 20), 18),
        payment_id=payments["nastya"].id,
        comment="Возврат части предоплаты за октябрь.",
    )
    db.add(refund)

    # «Ожидает»: Марк перевёл деньги, но платёж ещё не подтверждён —
    # на баланс он не влияет, но виден в истории.
    db.add(
        AccountOperation(
            student_id=students["mark"].id,
            kind="payment",
            amount=1800,
            occurred_at=_payment_at(tutor, date(2026, 11, 1), 10),
            status="pending",
            method="transfer",
            comment="Перевод за ноябрь, ждём подтверждение.",
        )
    )

    # «Отменено»: у Тимофея сорвался перевод, платёж не прошёл.
    db.add(
        AccountOperation(
            student_id=students["timofey"].id,
            kind="payment",
            amount=4000,
            occurred_at=_payment_at(tutor, date(2026, 10, 6), 9),
            status="cancelled",
            method="card",
            comment="Ошибка перевода, оплата не прошла.",
        )
    )
    db.flush()
    return payments


def _create_homework(
    db, tutor: Tutor, lessons_by_key: dict[tuple[str, date], Lesson]
) -> None:
    """Домашние задания с разными статусами, ответами и ссылками."""
    for data in HOMEWORK:
        lesson = lessons_by_key.get((data["student"], data["lesson_date"]))
        if lesson is None:
            continue
        homework = Homework(
            lesson_id=lesson.id,
            assignment=data["assignment"],
            due_at=to_utc(datetime.combine(data["due"], time(20, 0)), tutor)
            if data.get("due")
            else None,
            status=data["status"],
            recording_url=data.get("recording"),
            teacher_comment=data.get("teacher_comment"),
        )
        db.add(homework)
        db.flush()

        if not data.get("answer"):
            continue
        answer = HomeworkAnswer(
            homework_id=homework.id,
            text=data["answer"],
            submitted_at=to_utc(
                datetime.combine(data["due"] or data["lesson_date"], time(19, 30)), tutor
            ),
        )
        db.add(answer)
        db.flush()
        if data.get("link"):
            db.add(
                HomeworkAnswerLink(
                    answer_id=answer.id,
                    url=data["link"],
                    position=0,
                )
            )
    db.flush()


def _create_tasks(db, tutor: Tutor, students: dict[str, Student]) -> None:
    """Задачи на канбан-доске с привязкой к ученикам."""
    now = datetime.now(tutor_zone(tutor))
    for title, stage, priority, due_date, description, student_keys in TASKS:
        task = Task(
            tutor_id=tutor.id,
            title=title,
            stage=stage,
            priority=priority,
            due_date=due_date,
            description=description,
            completed_at=now if stage == "done" else None,
        )
        db.add(task)
        db.flush()
        for student_key in student_keys:
            db.add(TaskStudent(task_id=task.id, student_id=students[student_key].id))
    db.flush()


def _create_expenses(db, tutor: Tutor) -> None:
    """Расходы репетитора: аренда, подписки, материалы, реклама."""
    for category, amount, day, comment in EXPENSES:
        db.add(
            Expense(
                tutor_id=tutor.id,
                category=category,
                amount=amount,
                spent_at=_payment_at(tutor, day, 10),
                comment=comment,
            )
        )
    db.flush()


def _create_misc(db, tutor: Tutor) -> None:
    """Шаблоны рассылок и недоступность: отпуск и постоянный выходной."""
    for title, text_value in TEMPLATES:
        db.add(MessageTemplate(tutor_id=tutor.id, title=title, text=text_value))

    db.add(
        TutorUnavailability(
            tutor_id=tutor.id,
            mode="period",
            reason="vacation",
            start_date=VACATION_START,
            end_date=VACATION_END,
        )
    )
    db.add(
        TutorUnavailability(
            tutor_id=tutor.id,
            mode="weekday",
            reason="dayoff",
            weekday=SUN,
        )
    )
    db.flush()


def _print_report(db, tutor: Tutor, students: dict[str, Student]) -> None:
    """Короткая сводка: что получилось и у кого какой баланс."""
    lessons = db.scalars(select(Lesson)).all()
    completed = sum(1 for lesson in lessons if lesson.status == "completed")
    print(f"Учеников: {len(students)}")
    print(f"Уроков: {len(lessons)} (проведено {completed}, "
          f"запланировано {len(lessons) - completed})")
    print(f"Списаний: {db.scalar(text(
        'SELECT count(*) FROM account_operations WHERE kind = :kind'
    ).bindparams(kind='lesson'))}")
    print()
    print(f"{'Ученик':28} {'Баланс':>10}  Статус")
    print("-" * 60)
    for data in STUDENTS:
        student = students[data["key"]]
        value = balance(db, student.id)
        debt = "должник" if value < 0 else ("предоплата" if value > 0 else "ровно")
        print(
            f"{data['first_name'] + ' ' + (data['last_name'] or ''):28} "
            f"{value:>10}  {debt}"
        )


def main() -> None:
    """Точка входа: сброс демо-данных и сборка учебного года заново."""
    with SessionLocal() as db:
        _reset_demo_data(db, TUTOR_EMAIL)
        tutor = _create_tutor(db)
        # «Сейчас» считаем в зоне педагога: по нему решается, что уже
        # проведено, а что ещё запланировано.
        now = datetime.now(tutor_zone(tutor))

        contacts = _create_contacts(db, tutor)
        students = _create_students(db, tutor, contacts)
        groups = _create_groups(db, tutor, students)

        lessons_by_key: dict[tuple[str, date], Lesson] = {}
        all_lessons: list[Lesson] = []

        for data in STUDENTS:
            if not data["slots"]:
                continue
            slots = [_slot(**slot) for slot in data["slots"]]
            series = _create_series(db, tutor, slots)
            created = _generate_lessons(
                db,
                tutor,
                series,
                slots,
                now=now,
                student=students[data["key"]],
                lesson_type="individual",
                price=data["price"],
                meeting_url=(
                    f"https://meet.example.com/{data['key']}"
                    if data["kind"] == "adult"
                    else None
                ),
            )
            all_lessons.extend(created)
            for lesson in created:
                local_day = as_utc(lesson.starts_at).astimezone(tutor_zone(tutor)).date()
                lessons_by_key[(data["key"], local_day)] = lesson

        for data in GROUPS:
            slots = [_slot(**slot) for slot in data["slots"]]
            series = _create_series(db, tutor, slots)
            created = _generate_lessons(
                db,
                tutor,
                series,
                slots,
                now=now,
                group=groups[data["key"]],
                lesson_type="group",
                price=None,
                meeting_url=data["meeting_url"],
            )
            all_lessons.extend(created)
            for lesson in created:
                local_day = as_utc(lesson.starts_at).astimezone(tutor_zone(tutor)).date()
                lessons_by_key[(f"group:{data['key']}", local_day)] = lesson

        all_lessons.extend(_add_extra_lessons(db, tutor, students))
        _mark_attendance(db, lessons_by_key, students)
        _sync_charges(db, all_lessons)

        _create_payments(db, tutor, students)
        _create_homework(db, tutor, lessons_by_key)
        _create_tasks(db, tutor, students)
        _create_expenses(db, tutor)
        _create_misc(db, tutor)

        db.commit()
        _print_report(db, tutor, students)
        print()
        print(f"Вход: {TUTOR_EMAIL} / {TUTOR_PASSWORD}")


if __name__ == "__main__":
    main()
