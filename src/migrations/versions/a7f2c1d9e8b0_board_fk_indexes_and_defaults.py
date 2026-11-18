"""Add board FK indexes and archive defaults.

Revision ID: a7f2c1d9e8b0
Revises: 9d4f2a7c1b60
Create Date: 2026-11-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7f2c1d9e8b0"
down_revision: Union[str, Sequence[str], None] = "9d4f2a7c1b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_boards_users_board_id", "boards_users", ["board_id"])
    op.create_index("ix_sections_board_id", "sections", ["board_id"])
    op.create_index("ix_tickets_section_id", "tickets", ["section_id"])
    op.create_index("ix_tickets_users_ticket_id", "tickets_users", ["ticket_id"])

    op.alter_column("boards", "is_archived", server_default=sa.false(), existing_type=sa.Boolean(), existing_nullable=False)
    op.alter_column("sections", "is_archived", server_default=sa.false(), existing_type=sa.Boolean(), existing_nullable=False)
    op.alter_column("tickets", "is_archived", server_default=sa.false(), existing_type=sa.Boolean(), existing_nullable=False)

    op.execute("UPDATE users SET email = lower(email)")
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")

    op.alter_column("tickets", "is_archived", server_default=None, existing_type=sa.Boolean(), existing_nullable=False)
    op.alter_column("sections", "is_archived", server_default=None, existing_type=sa.Boolean(), existing_nullable=False)
    op.alter_column("boards", "is_archived", server_default=None, existing_type=sa.Boolean(), existing_nullable=False)

    op.drop_index("ix_tickets_users_ticket_id", table_name="tickets_users")
    op.drop_index("ix_tickets_section_id", table_name="tickets")
    op.drop_index("ix_sections_board_id", table_name="sections")
    op.drop_index("ix_boards_users_board_id", table_name="boards_users")
