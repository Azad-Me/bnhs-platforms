"""Add password hashes for the superseded password authentication flow.

Revision ID: 0002_user_password_hash
Revises: 0001_initial
Create Date: 2026-11-01
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_user_password_hash"
down_revision: str | None = "0001_initial"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "password_hash")
