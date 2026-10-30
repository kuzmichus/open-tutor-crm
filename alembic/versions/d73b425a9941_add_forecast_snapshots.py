"""add forecast snapshots

Снимок прогноза на месяц для вкладки «Прогноз на месяц»: репетитор
фиксирует диапазон ожидаемой выручки, и позже карточка «Прогноз vs факт»
сравнивает его с реальными списаниями.

Один снимок на пару «репетитор + месяц» (`uq_forecast_snapshots_period`):
повторная фиксация заменяет прогноз, а не плодит строки.

Revision ID: d73b425a9941
Revises: 701c3ab18383
Create Date: 2026-10-26 07:36:36.142082

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd73b425a9941'
down_revision: Union[str, Sequence[str], None] = '701c3ab18383'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('forecast_snapshots',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tutor_id', sa.String(length=36), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('month', sa.Integer(), nullable=False),
    sa.Column('revenue_low', sa.Integer(), nullable=False),
    sa.Column('revenue_high', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('month BETWEEN 1 AND 12', name='ck_forecast_snapshots_month'),
    sa.CheckConstraint('revenue_low <= revenue_high', name='ck_forecast_snapshots_range'),
    sa.ForeignKeyConstraint(['tutor_id'], ['tutors.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tutor_id', 'year', 'month', name='uq_forecast_snapshots_period')
    )
    op.create_index(op.f('ix_forecast_snapshots_tutor_id'), 'forecast_snapshots', ['tutor_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_forecast_snapshots_tutor_id'), table_name='forecast_snapshots')
    op.drop_table('forecast_snapshots')
