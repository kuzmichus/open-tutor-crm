"""add lesson statuses «rescheduled» and «cancelled»

Revision ID: c4f8a1e93b57
Revises: b7d24c9e5f10
Create Date: 2026-11-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f8a1e93b57'
down_revision: Union[str, Sequence[str], None] = 'b7d24c9e5f10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Значения заморожены в миграции: модель может уйти вперёд, а применённая
# миграция обязана оставаться воспроизводимой (правило проекта).
OLD_STATUSES = ('planned', 'completed')
NEW_STATUSES = ('planned', 'completed', 'rescheduled', 'cancelled')

# Колонки `lessons` на момент миграции — нужны для пересборки таблицы в
# SQLite: ALTER CHECK и смена длины VARCHAR там не поддерживаются.
LESSON_COLUMNS = (
    'id',
    'student_id',
    'group_id',
    'series_id',
    'type',
    'starts_at',
    'duration_min',
    'note',
    'meeting_url',
    'price',
    'status',
    'rating',
    'family_comment',
    'created_at',
    'updated_at',
)

LESSON_INDEXES = (
    'ix_lessons_group_id',
    'ix_lessons_series_id',
    'ix_lessons_starts_at',
    'ix_lessons_student_id',
)


def _check_sql(values: tuple[str, ...]) -> str:
    """SQL CHECK-ограничения статуса из закрытого списка."""
    joined = ', '.join(f"'{value}'" for value in values)
    return f'status IN ({joined})'


def _create_lessons_table(name: str, status_length: int, statuses) -> None:
    """Создаёт таблицу уроков с нужной шириной и CHECK-списком статусов."""
    op.create_table(
        name,
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('student_id', sa.String(length=36), nullable=True),
        sa.Column('group_id', sa.String(length=36), nullable=True),
        sa.Column('series_id', sa.String(length=36), nullable=True),
        sa.Column('type', sa.String(length=12), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duration_min', sa.Integer(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('meeting_url', sa.String(length=500), nullable=True),
        sa.Column('price', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=status_length), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('family_comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            _check_sql(statuses), name='ck_lessons_status'
        ),
        sa.CheckConstraint(
            "type IN ('individual', 'group', 'trial', 'practice')",
            name='ck_lessons_type',
        ),
        sa.CheckConstraint(
            '(student_id IS NOT NULL) <> (group_id IS NOT NULL)',
            name='ck_lessons_target_xor',
        ),
        sa.CheckConstraint(
            'duration_min IN (30, 35, 40, 45, 50, 55, 60, 65, 70, 75, '
            '90, 105, 120, 150, 180)',
            name='ck_lessons_duration',
        ),
        sa.CheckConstraint(
            'rating IS NULL OR (rating BETWEEN 1 AND 5)',
            name='ck_lessons_rating',
        ),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['series_id'], ['lesson_series.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['student_id'], ['students.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )


def _rebuild_sqlite(*, status_length: int, statuses, mapping: str) -> None:
    """Пересобирает `lessons` в SQLite: ALTER CHECK там не поддерживается.

    `mapping` — SQL-выражение для колонки `status` при переносе строк:
    upgrade копирует значения как есть, downgrade схлопывает новые статусы
    в «Запланирован», чтобы уроки не потерялись.

    `PRAGMA foreign_keys=OFF` обязателен: при включённых FK `DROP TABLE
    lessons` каскадно удалил бы `homework`, `account_operations` (списания
    по урокам), `calendar_events` и `lesson_attendance`. Pragma внутри
    транзакции молча не срабатывает, поэтому она выставляется в
    autocommit-блоке.
    """
    columns = ', '.join(LESSON_COLUMNS)
    # `status` переносится выражением (в downgrade новые значения схлопываются
    # в «Запланирован»), остальные колонки — как есть.
    selected = ', '.join(
        mapping if column == 'status' else column for column in LESSON_COLUMNS
    )
    with op.get_context().autocommit_block():
        op.execute('PRAGMA foreign_keys=OFF')

    _create_lessons_table('lessons_new', status_length, statuses)
    op.execute(
        f'INSERT INTO lessons_new ({columns}) SELECT {selected} FROM lessons'
    )
    op.drop_table('lessons')
    op.rename_table('lessons_new', 'lessons')
    for index in LESSON_INDEXES:
        column = index.removeprefix('ix_lessons_')
        op.create_index(op.f(index), 'lessons', [column], unique=False)

    with op.get_context().autocommit_block():
        op.execute('PRAGMA foreign_keys=ON')


def upgrade() -> None:
    """Добавляет статусы «Перенесён» и «Отменён»."""
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        _rebuild_sqlite(
            status_length=12, statuses=NEW_STATUSES, mapping='status'
        )
        return

    op.drop_constraint('ck_lessons_status', 'lessons', type_='check')
    op.alter_column(
        'lessons',
        'status',
        type_=sa.String(length=12),
        existing_type=sa.String(length=10),
        existing_nullable=False,
    )
    op.create_check_constraint(
        'ck_lessons_status', 'lessons', _check_sql(NEW_STATUSES)
    )


def downgrade() -> None:
    """Возвращает два статуса; отменённые и перенесённые — «Запланирован»."""
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        _rebuild_sqlite(
            status_length=10,
            statuses=OLD_STATUSES,
            mapping=(
                "CASE WHEN status IN ('rescheduled', 'cancelled') "
                "THEN 'planned' ELSE status END"
            ),
        )
        return

    op.execute(
        "UPDATE lessons SET status = 'planned' "
        "WHERE status IN ('rescheduled', 'cancelled')"
    )
    op.drop_constraint('ck_lessons_status', 'lessons', type_='check')
    op.alter_column(
        'lessons',
        'status',
        type_=sa.String(length=10),
        existing_type=sa.String(length=12),
        existing_nullable=False,
    )
    op.create_check_constraint(
        'ck_lessons_status', 'lessons', _check_sql(OLD_STATUSES)
    )
