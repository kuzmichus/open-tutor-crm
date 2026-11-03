"""add student city

Revision ID: 55b9846687b4
Revises: a7d3e1f42b90
Create Date: 2026-11-03 15:12:20.970344

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55b9846687b4'
down_revision: Union[str, Sequence[str], None] = 'a7d3e1f42b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Город необязателен: существующие ученики получают NULL — «город не указан».
    op.add_column('students', sa.Column('city', sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('students', 'city')
