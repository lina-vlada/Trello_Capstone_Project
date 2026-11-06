"""Add refresh token revocation table.

Revision ID: 7a3c2f9d1e84
Revises: 585bc18b078e
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a3c2f9d1e84"
down_revision: Union[str, Sequence[str], None] = "585bc18b078e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "logout_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("token_hash"),
    )


def downgrade() -> None:
    op.drop_table("logout_tokens")
