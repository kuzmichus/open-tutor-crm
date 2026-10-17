"""rebuild tutors: uuid4 id + auth/profile columns

Revision ID: f7c3a1d92b6e
Revises: eb86f21210aa
Create Date: 2026-10-17 16:10:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c3a1d92b6e'
down_revision: Union[str, Sequence[str], None] = 'eb86f21210aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    """True, если таблица уже есть (create_all мог создать её до миграции)."""
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    """Rebuild `tutors`: id becomes uuid4 (string), add profile/auth columns.

    SQLite не позволяет сменить PK и тип `id` через ALTER, поэтому таблица
    пересоздаётся, а существующие строки переносятся: каждая получает новый
    uuid4-идентификатор, имя/email/created_at сохраняются.
    """
    bind = op.get_bind()

    op.create_table(
        'tutors_new',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        # Nullable: у перенесённых строк пароля ещё нет.
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=32), nullable=True),
        sa.Column('about', sa.Text(), nullable=True),
        sa.Column('subject', sa.String(length=100), nullable=True),
        sa.Column('experience', sa.Text(), nullable=True),
        sa.Column('hourly_rate', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('timezone', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Перенос данных: python-цикл с uuid.uuid4() гарантирует формат uuid4.
    rows = bind.execute(
        sa.text('SELECT id, name, email, created_at FROM tutors')
    ).fetchall()
    for _old_id, name, email, created_at in rows:
        bind.execute(
            sa.text(
                'INSERT INTO tutors_new (id, name, email, created_at) '
                'VALUES (:id, :name, :email, :created_at)'
            ),
            {
                'id': str(uuid.uuid4()),
                'name': name,
                'email': email,
                'created_at': created_at,
            },
        )

    op.drop_table('tutors')
    op.rename_table('tutors_new', 'tutors')
    op.create_index(op.f('ix_tutors_email'), 'tutors', ['email'], unique=True)

    # Новые таблицы модуля авторизации/восстановления.
    # Пропускаем, если create_all (init_db при старте) уже создал их:
    # иначе `alembic upgrade head` падает на существующей dev-базе.
    if not _has_table(bind, 'tutor_sessions'):
        op.create_table(
            'tutor_sessions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tutor_id', sa.String(length=36), nullable=False),
            sa.Column('token', sa.String(length=64), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['tutor_id'], ['tutors.id']),
        )
        op.create_index(
            op.f('ix_tutor_sessions_tutor_id'),
            'tutor_sessions',
            ['tutor_id'],
            unique=False,
        )
        op.create_index(
            op.f('ix_tutor_sessions_token'), 'tutor_sessions', ['token'], unique=True
        )

    if not _has_table(bind, 'tutor_password_reset_tokens'):
        op.create_table(
            'tutor_password_reset_tokens',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tutor_id', sa.String(length=36), nullable=False),
            sa.Column('token', sa.String(length=64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['tutor_id'], ['tutors.id']),
        )
        op.create_index(
            op.f('ix_tutor_password_reset_tokens_tutor_id'),
            'tutor_password_reset_tokens',
            ['tutor_id'],
            unique=False,
        )
        op.create_index(
            op.f('ix_tutor_password_reset_tokens_token'),
            'tutor_password_reset_tokens',
            ['token'],
            unique=True,
        )


def downgrade() -> None:
    """Возврат к прежней схеме (id INTEGER PK).

    Осознанный компромисс демо-миграции: uuid4-идентификаторы и новые колонки
    (профиль, пароль) при откате не восстанавливаются — id пересоздаётся как
    последовательность INTEGER.
    """
    bind = op.get_bind()

    # Таблицы модуля авторизации/восстановления удаляем, только если они есть.
    if _has_table(bind, 'tutor_password_reset_tokens'):
        op.drop_index(
            op.f('ix_tutor_password_reset_tokens_token'),
            table_name='tutor_password_reset_tokens',
        )
        op.drop_index(
            op.f('ix_tutor_password_reset_tokens_tutor_id'),
            table_name='tutor_password_reset_tokens',
        )
        op.drop_table('tutor_password_reset_tokens')
    if _has_table(bind, 'tutor_sessions'):
        op.drop_index(op.f('ix_tutor_sessions_token'), table_name='tutor_sessions')
        op.drop_index(op.f('ix_tutor_sessions_tutor_id'), table_name='tutor_sessions')
        op.drop_table('tutor_sessions')

    op.create_table(
        'tutors_old',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    rows = bind.execute(
        sa.text('SELECT name, email, created_at FROM tutors ORDER BY created_at')
    ).fetchall()
    for name, email, created_at in rows:
        bind.execute(
            sa.text(
                'INSERT INTO tutors_old (name, email, created_at) '
                'VALUES (:name, :email, :created_at)'
            ),
            {'name': name, 'email': email, 'created_at': created_at},
        )

    op.drop_table('tutors')
    op.rename_table('tutors_old', 'tutors')
    op.create_index(op.f('ix_tutors_email'), 'tutors', ['email'], unique=True)
