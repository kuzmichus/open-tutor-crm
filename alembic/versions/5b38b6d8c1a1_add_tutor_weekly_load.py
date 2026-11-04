"""add tutor weekly load

Revision ID: 5b38b6d8c1a1
Revises: 7ce02b7b728c
Create Date: 2026-11-04 19:56:02.245190

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b38b6d8c1a1'
down_revision: Union[str, Sequence[str], None] = '7ce02b7b728c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # «Желаемая нагрузка в неделю» — астрономические часы, целые. Колонка
    # nullable: до первого сохранения параметр не задан, существующие
    # строки получают NULL, поэтому server_default не нужен.
    op.add_column(
        'tutor_settings',
        sa.Column('weekly_load_hours', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tutor_settings', 'weekly_load_hours')

