"""add npd tax settings

Revision ID: b7d24c9e5f10
Revises: c3f1a9d7e2b4
Create Date: 2026-11-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d24c9e5f10'
down_revision: Union[str, Sequence[str], None] = 'c3f1a9d7e2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # НПД (налог на профессиональный доход): признак статуса плательщика,
    # две ставки и годовой лимит дохода. NOT NULL + server_default, чтобы
    # существующие строки получили законодательные значения по умолчанию
    # (не плательщик, 4 %, 6 %, 2 400 000 ₽); ORM-дефолты остаются для INSERT.
    op.add_column(
        'tutor_settings',
        sa.Column('npd_enabled', sa.Boolean(), nullable=False,
                  server_default='0'),
    )
    op.add_column(
        'tutor_settings',
        sa.Column('npd_tax_rate_individual', sa.Numeric(precision=5, scale=2),
                  nullable=False, server_default='4'),
    )
    op.add_column(
        'tutor_settings',
        sa.Column('npd_tax_rate_legal_entity', sa.Numeric(precision=5, scale=2),
                  nullable=False, server_default='6'),
    )
    op.add_column(
        'tutor_settings',
        sa.Column('npd_annual_income_limit', sa.Integer(), nullable=False,
                  server_default='2400000'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tutor_settings', 'npd_annual_income_limit')
    op.drop_column('tutor_settings', 'npd_tax_rate_legal_entity')
    op.drop_column('tutor_settings', 'npd_tax_rate_individual')
    op.drop_column('tutor_settings', 'npd_enabled')
