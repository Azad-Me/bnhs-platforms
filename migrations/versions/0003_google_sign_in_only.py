"""Use Google identity for user authentication.

Revision ID: 0003_google_sign_in_only
Revises: 0002_user_password_hash
Create Date: 2026-11-01
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_google_sign_in_only"
down_revision: str | None = "0002_user_password_hash"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.Text(), nullable=True))
    op.create_unique_constraint("users_google_sub_key", "users", ["google_sub"])
    op.drop_column("users", "password_hash")


def downgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.drop_constraint("users_google_sub_key", "users", type_="unique")
    op.drop_column("users", "google_sub")
