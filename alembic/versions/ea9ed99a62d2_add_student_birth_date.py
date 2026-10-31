"""add student birth date

Revision ID: ea9ed99a62d2
Revises: 10c3311d3321
Create Date: 2026-11-01 00:42:40.184072

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea9ed99a62d2'
down_revision: Union[str, Sequence[str], None] = '10c3311d3321'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Дата необязательна: существующие ученики получают NULL — «дата не указана».
    op.add_column('students', sa.Column('birth_date', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('students', 'birth_date')
