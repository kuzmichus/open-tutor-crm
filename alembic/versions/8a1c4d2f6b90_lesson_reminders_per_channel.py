"""lesson reminders per channel

Маркеры напоминаний о начале урока становятся пофайловыми (по каналу) и
получают захват доставки:

- `channel` — мессенджер, в который ушло сообщение: при сбое одного канала
  второй получает напоминание сразу, а сбойный повторяется следующим
  прогоном, не дублируя уже доставленное;
- `claimed_at` — момент захвата доставки: строка коммитится **до**
  обращения к мессенджеру, поэтому наложившийся прогон cron видит захват и
  не отправляет дубль, а упавший прогон отпускает доставку по истечении
  `REMINDER_CLAIM_LEASE`;
- `delivered_at` — подтверждённая доставка (NULL — ещё не доставлено).

Старые маркеры канала не содержат и сопоставить их с мессенджером нечем,
поэтому таблица пересоздаётся: после обновления напоминания, попавшие в
окно, могут прийти повторно один раз — это безопаснее, чем потерять
напоминание или угадать канал.

Revision ID: 8a1c4d2f6b90
Revises: 72b3700d370b
Create Date: 2026-11-13 15:12:44.517306

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a1c4d2f6b90'
down_revision: Union[str, Sequence[str], None] = '72b3700d370b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f('ix_lesson_reminders_lesson_id'), table_name='lesson_reminders')
    op.drop_table('lesson_reminders')
    op.create_table('lesson_reminders',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('lesson_id', sa.String(length=36), nullable=False),
    sa.Column('offset_min', sa.Integer(), nullable=False),
    sa.Column('audience', sa.String(length=8), nullable=False),
    sa.Column('recipient_id', sa.String(length=36), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("audience IN ('tutor', 'student')", name='ck_lesson_reminders_audience'),
    sa.CheckConstraint("channel IN ('telegram', 'max', 'vk')", name='ck_lesson_reminders_channel'),
    sa.CheckConstraint('offset_min IN (15, 60, 1440)', name='ck_lesson_reminders_offset'),
    sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('lesson_id', 'offset_min', 'audience', 'recipient_id', 'channel', name='uq_lesson_reminders_channel')
    )
    op.create_index(op.f('ix_lesson_reminders_lesson_id'), 'lesson_reminders', ['lesson_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_lesson_reminders_lesson_id'), table_name='lesson_reminders')
    op.drop_table('lesson_reminders')
    op.create_table('lesson_reminders',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('lesson_id', sa.String(length=36), nullable=False),
    sa.Column('offset_min', sa.Integer(), nullable=False),
    sa.Column('audience', sa.String(length=8), nullable=False),
    sa.Column('recipient_id', sa.String(length=36), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("audience IN ('tutor', 'student')", name='ck_lesson_reminders_audience'),
    sa.CheckConstraint('offset_min IN (15, 60, 1440)', name='ck_lesson_reminders_offset'),
    sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('lesson_id', 'offset_min', 'audience', 'recipient_id', name='uq_lesson_reminders_target')
    )
    op.create_index(op.f('ix_lesson_reminders_lesson_id'), 'lesson_reminders', ['lesson_id'], unique=False)
