"""add mailings

Таблицы страницы рассылок: `message_templates` (шаблоны сообщений
репетитора) и `sent_messages` (журнал исходящих сообщений бота).

Миграция записана вручную: `init_db` живого dev-сервера успел создать
таблицы через `create_all` раньше autogenerate, и тот выдал pass/pass
(ловушка schema drift из AGENTS.md/памяти проекта). Схема совпадает с
автогенерируемой: перед применением пустые таблицы дропаются и
пересоздаются самой миграцией.

Revision ID: deee9a4e162e
Revises: b4d18c6f5a27
Create Date: 2026-10-27 22:39:13.826637
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "deee9a4e162e"
down_revision: Union[str, Sequence[str], None] = "b4d18c6f5a27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Кортежи CHECK-ограничений повторяют закрытые списки моделей
# (MESSENGERS, SENT_MESSAGE_STATUSES) — их дублирование в сыром SQL здесь
# неизбежно: autogenerate рендерит их так же.
_MESSENGERS = ("telegram", "max", "vk")
_STATUSES = ("sent", "error")


def _sql_in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "message_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tutor_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tutor_id"], ["tutors.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_message_templates_tutor_id",
        "message_templates",
        ["tutor_id"],
    )

    op.create_table(
        "sent_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tutor_id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=True),
        sa.Column("messenger", sa.String(length=16), nullable=False),
        sa.Column("recipient", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tutor_id"], ["tutors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["student_id"], ["students.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            _sql_in("messenger", _MESSENGERS),
            name="ck_sent_messages_messenger",
        ),
        sa.CheckConstraint(
            _sql_in("status", _STATUSES),
            name="ck_sent_messages_status",
        ),
    )
    op.create_index("ix_sent_messages_tutor_id", "sent_messages", ["tutor_id"])
    op.create_index(
        "ix_sent_messages_student_id", "sent_messages", ["student_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_sent_messages_student_id", table_name="sent_messages")
    op.drop_index("ix_sent_messages_tutor_id", table_name="sent_messages")
    op.drop_table("sent_messages")
    op.drop_index(
        "ix_message_templates_tutor_id", table_name="message_templates"
    )
    op.drop_table("message_templates")
