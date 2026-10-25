"""Платёж в блоке «Недавние платежи» главной страницы."""

from dataclasses import dataclass
from datetime import datetime

from app.finance.models.account_operation import AccountOperation


@dataclass(frozen=True)
class RecentPayment:
    """Строка «Недавних платежей»: операция счёта и имя ученика.

    Операция передаётся ORM-строкой, а не готовой суммой: подпись
    «+2 000 ₽» выводит `signed_money` из finance — знак и формат те же,
    что в балансе и истории ученика, расхождений не будет.
    """

    occurred_at: datetime
    student_name: str
    operation: AccountOperation
