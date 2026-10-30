"""add student messenger invites

Приглашения учеников в канал уведомлений (`student_messenger_invites`):
одна строка на пару «ученик — мессенджер», код и диплинк — «в процессе»,
chat_id и подпись чата — подключён.

Миграция идемпотентна по таблице: `init_db()` (`Base.metadata.create_all`)
мог создать её раньше, чем миграция до неё дошла (живой dev-сервер
перезапускается при правках моделей), — в этом случае создание
пропускается, а ревизия всё равно фиксируется. Тот же приём, что в
`8f92cc9baa31_add_tasks.py`.

Revision ID: b4d18c6f5a27
Revises: 8f92cc9baa31
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4d18c6f5a27'
down_revision: Union[str, Sequence[str], None] = '8f92cc9baa31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    """True, если таблица уже есть (create_all мог создать её до миграции)."""
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    if _has_table(bind, 'student_messenger_invites'):
        return
    op.create_table('student_messenger_invites',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tutor_id', sa.String(length=36), nullable=False),
    sa.Column('student_id', sa.String(length=36), nullable=False),
    sa.Column('messenger', sa.String(length=16), nullable=False),
    sa.Column('invite_code', sa.String(length=64), nullable=True),
    sa.Column('invite_link', sa.String(length=255), nullable=True),
    sa.Column('chat_id', sa.String(length=64), nullable=True),
    sa.Column('chat_label', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "messenger IN ('telegram', 'max', 'vk')",
        name='ck_student_messenger_invites_messenger',
    ),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tutor_id'], ['tutors.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint(
        'student_id', 'messenger',
        name='uq_student_messenger_invites_student_messenger',
    )
    )
    op.create_index(
        op.f('ix_student_messenger_invites_student_id'),
        'student_messenger_invites', ['student_id'], unique=False,
    )
    op.create_index(
        op.f('ix_student_messenger_invites_tutor_id'),
        'student_messenger_invites', ['tutor_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_student_messenger_invites_tutor_id'),
        table_name='student_messenger_invites',
    )
    op.drop_index(
        op.f('ix_student_messenger_invites_student_id'),
        table_name='student_messenger_invites',
    )
    op.drop_table('student_messenger_invites')
