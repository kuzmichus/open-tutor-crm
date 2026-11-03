"""add calendar show price

Revision ID: a7d3e1f42b90
Revises: c4b7a1f90d21
Create Date: 2026-11-03 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7d3e1f42b90'
down_revision: Union[str, Sequence[str], None] = 'c4b7a1f90d21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Флаг «Показывать цену» на странице «Календарь». server_default
    # заполняет колонку у существующих строк (NOT NULL без него упал бы на
    # таблице с данными) и сохраняет текущее поведение — цены видны.
    # ORM-дефолт остаётся для INSERT.
    op.add_column(
        'tutor_settings',
        sa.Column('show_calendar_price', sa.Boolean(), nullable=False,
                  server_default='1'),
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tutor_settings', 'show_calendar_price')
