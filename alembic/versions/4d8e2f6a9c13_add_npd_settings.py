"""add npd settings for finance tax block

Revision ID: 4d8e2f6a9c13
Revises: b7d24c9e5f10
Create Date: 2026-11-06 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d8e2f6a9c13'
down_revision: Union[str, Sequence[str], None] = 'b7d24c9e5f10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # НПД: флаг самозанятого, ставки (базисные пункты) и годовой лимит.
    # server_default заполняет существующие строки дефолтами — выключенный
    # флаг сохраняет прежний вид страницы «Финансы»; ORM-дефолты остаются
    # для INSERT.
    op.add_column(
        'tutor_settings',
        sa.Column('is_npd_payer', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )
    op.add_column(
        'tutor_settings',
        sa.Column('npd_rate_individual_bp', sa.Integer(), nullable=False,
                  server_default='400'),
    )
    op.add_column(
        'tutor_settings',
        sa.Column('npd_rate_legal_bp', sa.Integer(), nullable=False,
                  server_default='600'),
    )
    op.add_column(
        'tutor_settings',
        sa.Column('npd_income_limit', sa.Integer(), nullable=False,
                  server_default='2400000'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tutor_settings', 'npd_income_limit')
    op.drop_column('tutor_settings', 'npd_rate_legal_bp')
    op.drop_column('tutor_settings', 'npd_rate_individual_bp')
    op.drop_column('tutor_settings', 'is_npd_payer')