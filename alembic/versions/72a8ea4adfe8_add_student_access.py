"""add student_access

Вход ученика в личный кабинет (готовит его появление): логин и хеш
пароля. `student_id` уникален — у ученика ровно один вход; `login`
уникален глобально, потому что будущий кабинет входит без указания
репетитора. Удаление ученика каскадом уносит вход.

Миграция написана вручную: autogenerate выдал пустой файл, потому что
`init_db()`/`create_all` уже создал таблицу в локальном tutor.db
(известная ловушка проекта — пустой diff не значит «схема уже есть у
всех»).

Revision ID: 72a8ea4adfe8
Revises: cc8049b1f87d
Create Date: 2026-10-25 03:17:49.774011

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72a8ea4adfe8'
down_revision: Union[str, Sequence[str], None] = 'cc8049b1f87d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('student_access',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('student_id', sa.String(length=36), nullable=False),
    sa.Column('login', sa.String(length=50), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('length(login) >= 3', name='ck_student_access_login_length'),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_id'),
    sa.UniqueConstraint('login')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('student_access')
