"""Add hashed refresh token storage.

Revision ID: 8c2d4e6f1a90
Revises: 7a3c2f9d1e84
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c2d4e6f1a90"
down_revision: Union[str, Sequence[str], None] = "7a3c2f9d1e84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "token_hash"),
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
