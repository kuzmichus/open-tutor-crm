"""add student payer type

Revision ID: c3f1a9d7e2b4
Revises: 5b38b6d8c1a1
Create Date: 2026-11-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f1a9d7e2b4'
down_revision: Union[str, Sequence[str], None] = '5b38b6d8c1a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Тип плательщика: физлицо (по умолчанию) или юрлицо. Отдельный признак
    # ученика, а не свойство контакта: плательщиком может быть и сам ученик.
    # server_default заполняет существующие строки значением «физлицо» и
    # сохраняет текущее поведение; ORM-дефолт остаётся для INSERT.
    op.add_column(
        'students',
        sa.Column(
            'payer_type',
            sa.String(length=16),
            sa.CheckConstraint(
                "payer_type IN ('individual', 'legal_entity')",
                name='ck_students_payer_type',
            ),
            nullable=False,
            server_default='individual',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('students', 'payer_type')