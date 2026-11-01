"""add calendar events

Revision ID: c4b7a1f90d21
Revises: ea9ed99a62d2
Create Date: 2026-11-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4b7a1f90d21'
down_revision: Union[str, Sequence[str], None] = 'ea9ed99a62d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Строка соответствия «урок → событие Google»: PK по уроку (у урока не
    # больше одного события), каскад сносит её вместе с уроком. Существующие
    # данные не затрагиваются: без подключённого календаря таблица пуста.
    op.create_table(
        'calendar_events',
        sa.Column('lesson_id', sa.String(length=36), nullable=False),
        sa.Column('event_id', sa.String(length=1024), nullable=False),
        sa.Column('calendar_id', sa.String(length=255), nullable=False,
                  server_default='primary'),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['lesson_id'], ['lessons.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('lesson_id'),
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('calendar_events')
