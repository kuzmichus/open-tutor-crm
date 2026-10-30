"""add tasks

Задачи репетитора (`tasks`) и связка «задача — ученик» (`task_students`).

Этапы и приоритеты — закрытые списки модели: CHECK-ограничения держат
инвариант в БД, а не только в валидации формы.

Миграция идемпотентна по таблицам: `init_db()` (`Base.metadata.create_all`)
мог создать их раньше, чем миграция до них дошла, — в этом случае таблицы
пропускаются, а ревизия всё равно фиксируется. Тот же приём, что в
`b2e5c7f10a3d_add_students_contacts.py`: без него `alembic upgrade head`
на локальной базе падает с «table already exists», хотя схема уже верная.

Revision ID: 8f92cc9baa31
Revises: d73b425a9941
Create Date: 2026-10-26 07:40:29.747727

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f92cc9baa31'
down_revision: Union[str, Sequence[str], None] = 'd73b425a9941'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    """True, если таблица уже есть (create_all мог создать её до миграции)."""
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    if not _has_table(bind, 'tasks'):
        op.create_table('tasks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tutor_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('stage', sa.String(length=16), nullable=False),
        sa.Column('priority', sa.String(length=8), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high')", name='ck_tasks_priority'),
        sa.CheckConstraint("stage IN ('new', 'in_progress', 'review', 'done')", name='ck_tasks_stage'),
        sa.ForeignKeyConstraint(['tutor_id'], ['tutors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_tasks_stage'), 'tasks', ['stage'], unique=False)
        op.create_index(op.f('ix_tasks_tutor_id'), 'tasks', ['tutor_id'], unique=False)
        op.create_index('ix_tasks_tutor_stage', 'tasks', ['tutor_id', 'stage'], unique=False)

    if not _has_table(bind, 'task_students'):
        op.create_table('task_students',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('student_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id', 'student_id', name='uq_task_students_pair')
        )
        op.create_index(op.f('ix_task_students_student_id'), 'task_students', ['student_id'], unique=False)
        op.create_index(op.f('ix_task_students_task_id'), 'task_students', ['task_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    if _has_table(bind, 'task_students'):
        op.drop_index(op.f('ix_task_students_task_id'), table_name='task_students')
        op.drop_index(op.f('ix_task_students_student_id'), table_name='task_students')
        op.drop_table('task_students')

    if _has_table(bind, 'tasks'):
        op.drop_index('ix_tasks_tutor_stage', table_name='tasks')
        op.drop_index(op.f('ix_tasks_tutor_id'), table_name='tasks')
        op.drop_index(op.f('ix_tasks_stage'), table_name='tasks')
        op.drop_table('tasks')
