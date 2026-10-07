"""Update ticket user relationships

Revision ID: c9d5953bbb41
Revises: 339b9b544acd
Create Date: 2026-10-06 13:33:07.716962

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c9d5953bbb41'
down_revision: Union[str, Sequence[str], None] = '339b9b544acd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE TYPE rolesenum AS ENUM ('OWNER', 'EDITOR', 'VIEWER')")
    op.add_column(
        'boards_users',
        sa.Column(
            'role',
            postgresql.ENUM('OWNER', 'EDITOR', 'VIEWER', name='rolesenum', create_type=False),
            nullable=False,
        ),
    )
    op.drop_column('boards_users', 'is_admin')
    op.create_table(
        'tickets_users',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column(
            'role',
            postgresql.ENUM('OWNER', 'EDITOR', 'VIEWER', name='rolesenum', create_type=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id', 'ticket_id'),
    )
    op.drop_constraint(op.f('tickets_creator_id_fkey'), 'tickets', type_='foreignkey')
    op.drop_constraint(op.f('tickets_assignee_id_fkey'), 'tickets', type_='foreignkey')
    op.drop_column('tickets', 'creator_id')
    op.drop_column('tickets', 'assignee_id')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('tickets', sa.Column('assignee_id', sa.Integer(), autoincrement=False, nullable=False))
    op.add_column('tickets', sa.Column('creator_id', sa.Integer(), autoincrement=False, nullable=False))
    op.create_foreign_key(op.f('tickets_assignee_id_fkey'), 'tickets', 'users', ['assignee_id'], ['id'])
    op.create_foreign_key(op.f('tickets_creator_id_fkey'), 'tickets', 'users', ['creator_id'], ['id'])
    op.add_column('boards_users', sa.Column('is_admin', sa.Boolean(), autoincrement=False, nullable=False))
    op.drop_column('tickets_users', 'role')
    op.drop_table('tickets_users')
    op.drop_column('boards_users', 'role')
    op.execute("DROP TYPE rolesenum")
