"""add tutor working hours

Revision ID: feb74d4da12e
Revises: deee9a4e162e
Create Date: 2026-10-28 02:11:40.866430

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'feb74d4da12e'
down_revision: Union[str, Sequence[str], None] = 'deee9a4e162e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default заполняет колонки у существующих строк: NOT NULL без
    # него упал бы на таблице с данными. ORM-дефолт остаётся для INSERT.
    op.add_column(
        'tutor_settings',
        sa.Column('workday_start', sa.String(length=5), nullable=False,
                  server_default='06:00'),
    )
    op.add_column(
        'tutor_settings',
        sa.Column('workday_end', sa.String(length=5), nullable=False,
                  server_default='23:00'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tutor_settings', 'workday_end')
    op.drop_column('tutor_settings', 'workday_start')
