"""Сводка счёта для страницы карточки ученика (design D12).

Блок «Уроки и оплаты» был заглушкой без чисел: страница не могла показать
ни баланс, ни последние операции. Теперь на его месте — короткая сводка:
баланс, последние операции и действие «Платежи», открывающее карточку
сразу на вкладке «Платежи».

Сводка намеренно короче панели вкладки: страница — обзор, а не рабочее
место со счётом. Истории здесь 5 строк вместо 20 (`HISTORY_LIMIT`):
блок стоит под контактами и не должен отодвигать остальное содержимое.

Сервис не знает про FastAPI: на вход — сессия, ученик и репетитор, на
выход — контекст шаблона `finance/_card_summary.html`.
"""

from sqlalchemy.orm import Session

from app.finance.services.balance import balance
from app.finance.services.operations import student_history

# Сколько последних операций показывает сводка на странице ученика.
CARD_HISTORY_LIMIT = 5


def card_summary_context(db: Session, student, tutor) -> dict:
    """Контекст сводки счёта для страницы карточки ученика.

    Отдельный от `panel_context` контекст, а не его подмножество: у сводки
    нет ни списка платежей с кнопками, ни баннера пересчёта — пересчёт
    живёт в панели, где рядом стоят действия. Смешивать два набора ключей
    значило бы тащить в страницу половину неиспользуемого.
    """
    return {
        "finance_student": student,
        "finance_tutor": tutor,
        "finance_balance": balance(db, student.id),
        "finance_history": student_history(
            db, student.id, limit=CARD_HISTORY_LIMIT
        ),
        "finance_history_limit": CARD_HISTORY_LIMIT,
    }
