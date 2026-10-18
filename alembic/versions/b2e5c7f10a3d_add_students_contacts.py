"""add students card + contacts + student_contacts

Revision ID: b2e5c7f10a3d
Revises: f7c3a1d92b6e
Create Date: 2026-10-18 10:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2e5c7f10a3d'
down_revision: Union[str, Sequence[str], None] = 'f7c3a1d92b6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    """True, если таблица уже есть (create_all мог создать её до миграции)."""
    return sa.inspect(bind).has_table(name)


def _legacy_tutor_id(bind) -> str:
    """Владелец для строк старой таблицы `students`.

    У прежней схемы владельца не было. Если репетитор ровно один — все
    прежние ученики принадлежат ему; иначе миграция останавливается, чтобы
    данные не «улетели» к случайному владельцу.
    """
    tutor_ids = bind.execute(sa.text('SELECT id FROM tutors')).scalars().all()
    if len(tutor_ids) == 1:
        return tutor_ids[0]
    if not tutor_ids:
        raise RuntimeError(
            'Миграция add-students: в таблице `students` есть строки, но в '
            '`tutors` нет ни одного репетитора. Создайте репетитора или '
            'удалите старые строки `students`, затем повторите миграцию.'
        )
    raise RuntimeError(
        'Миграция add-students: в таблице `students` есть строки, а '
        f'репетиторов {len(tutor_ids)}. Нельзя однозначно назначить '
        'владельца. Удалите старые строки `students` или оставьте одного '
        'репетитора, затем повторите миграцию.'
    )


def upgrade() -> None:
    """Create contacts/student_contacts and rebuild `students` for uuid4 ids.

    Порядок важен: `students.payer_contact_id` ссылается на `contacts`,
    поэтому `contacts` создаётся первой. Старая таблица `students`
    пересобирается через `students_new` → перенос → drop → rename, потому
    что SQLite не умеет менять PK и добавлять NOT NULL FK через ALTER.
    """
    bind = op.get_bind()

    # 1. Контакты взрослых. Пропускаем, если create_all (init_db при старте)
    #    уже создал таблицу — иначе `alembic upgrade head` упадёт на dev-базе.
    if not _has_table(bind, 'contacts'):
        op.create_table(
            'contacts',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('tutor_id', sa.String(length=36), nullable=False),
            sa.Column('full_name', sa.String(length=200), nullable=False),
            sa.Column('phone', sa.String(length=32), nullable=True),
            sa.Column('email', sa.String(length=255), nullable=True),
            sa.Column('timezone', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['tutor_id'], ['tutors.id'], ondelete='CASCADE'),
        )
        op.create_index(op.f('ix_contacts_tutor_id'), 'contacts', ['tutor_id'], unique=False)
        op.create_index(op.f('ix_contacts_phone'), 'contacts', ['phone'], unique=False)
        op.create_index(op.f('ix_contacts_email'), 'contacts', ['email'], unique=False)

    # 2. Привязки «ученик — контакт»: роль и напоминания живут на паре.
    if not _has_table(bind, 'student_contacts'):
        op.create_table(
            'student_contacts',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('student_id', sa.String(length=36), nullable=False),
            sa.Column('contact_id', sa.String(length=36), nullable=False),
            sa.Column('relation', sa.String(length=50), nullable=True),
            sa.Column('remind_lesson', sa.Boolean(), nullable=False),
            sa.Column('remind_homework', sa.Boolean(), nullable=False),
            sa.Column('remind_cancel', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ['student_id'], ['students.id'], ondelete='CASCADE'
            ),
            sa.ForeignKeyConstraint(
                ['contact_id'], ['contacts.id'], ondelete='CASCADE'
            ),
            sa.UniqueConstraint(
                'student_id', 'contact_id', name='uq_student_contacts_pair'
            ),
        )
        op.create_index(
            op.f('ix_student_contacts_student_id'),
            'student_contacts',
            ['student_id'],
            unique=False,
        )
        op.create_index(
            op.f('ix_student_contacts_contact_id'),
            'student_contacts',
            ['contact_id'],
            unique=False,
        )

    # 3. Пересборка `students` на новую схему.
    op.create_table(
        'students_new',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('tutor_id', sa.String(length=36), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('phone', sa.String(length=32), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('grade', sa.Integer(), nullable=True),
        sa.Column('school', sa.String(length=255), nullable=True),
        sa.Column('level', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('timezone', sa.String(length=64), nullable=True),
        sa.Column('remind_lesson', sa.Boolean(), nullable=False),
        sa.Column('remind_homework', sa.Boolean(), nullable=False),
        sa.Column('remind_cancel', sa.Boolean(), nullable=False),
        sa.Column('payer_contact_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('child', 'adult')", name='ck_students_kind'),
        sa.CheckConstraint(
            'grade IS NULL OR (grade BETWEEN 1 AND 11)', name='ck_students_grade'
        ),
        sa.CheckConstraint(
            "status IN ('new', 'active', 'archived')", name='ck_students_status'
        ),
        sa.ForeignKeyConstraint(['tutor_id'], ['tutors.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['payer_contact_id'], ['contacts.id'], ondelete='SET NULL'
        ),
    )

    # Перенос строк старой таблицы (в текущей dev-базе их нет, но база
    # разработчика может отличаться): name → first_name, kind='child',
    # status='new', id — новый uuid4.
    rows = bind.execute(
        sa.text('SELECT id, name, email, created_at FROM students')
    ).fetchall()
    if rows:
        tutor_id = _legacy_tutor_id(bind)
        for _old_id, name, email, created_at in rows:
            bind.execute(
                sa.text(
                    'INSERT INTO students_new ('
                    'id, tutor_id, first_name, email, kind, status, '
                    'remind_lesson, remind_homework, remind_cancel, '
                    'created_at, updated_at'
                    ') VALUES ('
                    ':id, :tutor_id, :first_name, :email, :kind, :status, '
                    ':remind_lesson, :remind_homework, :remind_cancel, '
                    ':created_at, :updated_at'
                    ')'
                ),
                {
                    'id': str(uuid.uuid4()),
                    'tutor_id': tutor_id,
                    'first_name': name,
                    'email': email,
                    'kind': 'child',
                    'status': 'new',
                    'remind_lesson': False,
                    'remind_homework': False,
                    'remind_cancel': False,
                    'created_at': created_at,
                    'updated_at': created_at,
                },
            )

    op.drop_table('students')
    op.rename_table('students_new', 'students')
    op.create_index(op.f('ix_students_tutor_id'), 'students', ['tutor_id'], unique=False)
    op.create_index(op.f('ix_students_phone'), 'students', ['phone'], unique=False)
    op.create_index(op.f('ix_students_email'), 'students', ['email'], unique=False)
    op.create_index(op.f('ix_students_status'), 'students', ['status'], unique=False)


def downgrade() -> None:
    """Возврат к прежней схеме `students` и удаление контактов.

    ВНИМАНИЕ: при откате теряются все контакты, привязки, плательщики и
    настройки напоминаний — прежняя схема не умеет их хранить. Из карточки
    ученика восстанавливаются только имя (first_name + last_name), email и
    дата создания. Ученикам без email подставляется технический адрес вида
    `<id>@students.invalid`, иначе нарушится NOT NULL/UNIQUE старой схемы.
    """
    bind = op.get_bind()

    if _has_table(bind, 'student_contacts'):
        op.drop_index(
            op.f('ix_student_contacts_contact_id'), table_name='student_contacts'
        )
        op.drop_index(
            op.f('ix_student_contacts_student_id'), table_name='student_contacts'
        )
        op.drop_table('student_contacts')

    if _has_table(bind, 'contacts'):
        op.drop_index(op.f('ix_contacts_email'), table_name='contacts')
        op.drop_index(op.f('ix_contacts_phone'), table_name='contacts')
        op.drop_index(op.f('ix_contacts_tutor_id'), table_name='contacts')
        op.drop_table('contacts')

    op.create_table(
        'students_old',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    rows = bind.execute(
        sa.text(
            'SELECT id, first_name, last_name, email, created_at '
            'FROM students ORDER BY created_at'
        )
    ).fetchall()
    for student_id, first_name, last_name, email, created_at in rows:
        name = ' '.join(part for part in (first_name, last_name) if part)
        bind.execute(
            sa.text(
                'INSERT INTO students_old (name, email, created_at) '
                'VALUES (:name, :email, :created_at)'
            ),
            {
                'name': name,
                'email': email or f'{student_id}@students.invalid',
                'created_at': created_at,
            },
        )

    op.drop_table('students')
    op.rename_table('students_old', 'students')
    op.create_index(op.f('ix_students_email'), 'students', ['email'], unique=True)
