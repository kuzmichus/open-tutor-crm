"""Ученик в дневной сводке: имя, цена урока и кто платит."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DigestTarget:
    """Ученик в сводке: кто платит за урок и сколько он стоит.

    `price is None` — цена не задана: пометку о нехватке средств по такому
    ученику поставить нельзя, сравнивать баланс не с чем.
    """

    student_id: str
    name: str
    price: int | None
