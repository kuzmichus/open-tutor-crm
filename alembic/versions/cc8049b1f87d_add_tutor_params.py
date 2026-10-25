"""add tutor params

KV-хранилище параметров репетитора: одна строка на пару
«репетитор + ключ» (составной PK). Сюда идут необязательные параметры
без фиксированного набора — токены мессенджеров (`telegram_token`, …)
и будущие настройки; широкий набор колонок с дефолтами остаётся в
`tutor_settings`. Строка каскадируется вместе с карточкой репетитора,
а сервис записи делает upsert, поэтому серверные дефолты не нужны.

Revision ID: cc8049b1f87d
Revises: 675dadfd810e
Create Date: 2026-10-25 02:16:39.187470

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc8049b1f87d'
down_revision: Union[str, Sequence[str], None] = '675dadfd810e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('tutor_params',
    sa.Column('tutor_id', sa.String(length=36), nullable=False),
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['tutor_id'], ['tutors.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('tutor_id', 'key')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('tutor_params')
