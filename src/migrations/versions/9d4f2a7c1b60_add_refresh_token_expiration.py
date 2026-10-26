"""Add refresh-token expiration timestamp.

Revision ID: 9d4f2a7c1b60
Revises: 8c2d4e6f1a90
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d4f2a7c1b60"
down_revision: Union[str, Sequence[str], None] = "8c2d4e6f1a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE refresh_tokens SET expires_at = CURRENT_TIMESTAMP")
    op.alter_column("refresh_tokens", "expires_at", nullable=False)


def downgrade() -> None:
    op.drop_column("refresh_tokens", "expires_at")
