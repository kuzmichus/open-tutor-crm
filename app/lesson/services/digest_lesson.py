"""Урок в дневной сводке: когда, с кем и сколько стоит участие."""

from dataclasses import dataclass
from datetime import datetime

from app.lesson.services.digest_target import DigestTarget


@dataclass(frozen=True)
class DigestLesson:
    """Урок дня для сводки: когда, с кем и сколько стоит участие.

    `targets` у индивидуального урока — один ученик, у группового — все
    участники с их ценами: пометка о нехватке средств ставится по каждому
    ученику отдельно (у участников разные балансы и цены).
    """

    starts_at: datetime
    target_name: str
    is_group: bool
    targets: tuple[DigestTarget, ...]
