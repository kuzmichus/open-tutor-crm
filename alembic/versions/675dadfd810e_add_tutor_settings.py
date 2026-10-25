"""add tutor settings

Настройки репетитора: переключатели уведомлений (страница
`/tutor/profile`, вкладка «Уведомления»), учебный год — даты окончания
четвертей — и уроки по умолчанию (вкладка «Календарь»). Одна строка на
репетитора: PK совпадает с FK, строка каскадируется вместе с карточкой.
До первого сохранения строки нет — сервис отдаёт дефолты, поэтому
колонкам серверные дефолты не нужны (значения проставляет модель).

Revision ID: 675dadfd810e
Revises: 239fcddf04f3
Create Date: 2026-10-25 00:45:21.452841

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '675dadfd810e'
down_revision: Union[str, Sequence[str], None] = '239fcddf04f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('tutor_settings',
    sa.Column('tutor_id', sa.String(length=36), nullable=False),
    sa.Column('notify_lesson_reminder', sa.Boolean(), nullable=False),
    sa.Column('notify_lesson_confirmation', sa.Boolean(), nullable=False),
    sa.Column('notify_daily_digest', sa.Boolean(), nullable=False),
    sa.Column('notify_cancellation', sa.Boolean(), nullable=False),
    sa.Column('notify_homework', sa.Boolean(), nullable=False),
    sa.Column('notify_debtors_weekly', sa.Boolean(), nullable=False),
    sa.Column('notify_low_balance', sa.Boolean(), nullable=False),
    sa.Column('notify_insufficient_funds', sa.Boolean(), nullable=False),
    sa.Column('notify_birthday', sa.Boolean(), nullable=False),
    sa.Column('reminder_offsets', sa.JSON(), nullable=False),
    sa.Column('digest_time', sa.String(length=5), nullable=False),
    sa.Column('low_balance_threshold', sa.Integer(), nullable=False),
    sa.Column('default_lesson_duration', sa.Integer(), nullable=False),
    sa.Column('default_lesson_price', sa.Integer(), nullable=True),
    sa.Column('quarter1_end', sa.String(length=5), nullable=False),
    sa.Column('quarter2_end', sa.String(length=5), nullable=False),
    sa.Column('quarter3_end', sa.String(length=5), nullable=False),
    sa.Column('quarter4_end', sa.String(length=5), nullable=False),
    sa.ForeignKeyConstraint(['tutor_id'], ['tutors.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('tutor_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('tutor_settings')
