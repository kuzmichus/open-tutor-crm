"""add preparation coefficient

Revision ID: 5eb0e460963e
Revises: 5b38b6d8c1a1
Create Date: 2026-11-05 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5eb0e460963e'
down_revision: Union[str, Sequence[str], None] = '5b38b6d8c1a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # «Коэффициент подготовки» — доля времени урока на подготовку и проверку
    # ДЗ. NOT NULL, поэтому server_default заполняет колонку у существующих
    # строк значением по умолчанию 0.7; ORM-дефолт остаётся для INSERT.
    op.add_column(
        'tutor_settings',
        sa.Column('preparation_coefficient', sa.Numeric(precision=4, scale=2),
                  nullable=False, server_default='0.7'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tutor_settings', 'preparation_coefficient')
