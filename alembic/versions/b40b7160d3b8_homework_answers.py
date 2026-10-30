"""homework answers

Revision ID: b40b7160d3b8
Revises: 64eb9bb07f7b
Create Date: 2026-10-30 02:18:12.936537

Миграция записана вручную: autogenerate выдал `pass`, потому что живой
dev-сервер с `--reload` уже создал таблицы через `init_db`/`create_all`
(ловушка schema drift). Таблицы выгружались и создавались этой миграцией
одной атомарной командой.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b40b7160d3b8'
down_revision: Union[str, Sequence[str], None] = '64eb9bb07f7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('homework_answers',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('homework_id', sa.String(length=36), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['homework_id'], ['homework.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_homework_answers_homework_id'), 'homework_answers', ['homework_id'], unique=True)
    op.create_table('homework_answer_links',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('answer_id', sa.String(length=36), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['answer_id'], ['homework_answers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_homework_answer_links_answer_id'), 'homework_answer_links', ['answer_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_homework_answer_links_answer_id'), table_name='homework_answer_links')
    op.drop_table('homework_answer_links')
    op.drop_index(op.f('ix_homework_answers_homework_id'), table_name='homework_answers')
    op.drop_table('homework_answers')
