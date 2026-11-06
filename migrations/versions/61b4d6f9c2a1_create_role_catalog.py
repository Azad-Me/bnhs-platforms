"""Create a fixed database-backed role catalog.

Revision ID: 61b4d6f9c2a1
Revises: f9539e19377d
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "61b4d6f9c2a1"
down_revision: str | None = "f9539e19377d"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name="roles_pkey"),
        sa.UniqueConstraint("name", name="roles_name_key"),
    )
    op.execute(
        """
        INSERT INTO roles (key, name) VALUES
            ('admin', 'Admin'),
            ('qc_user', 'QC user'),
            ('publisher', 'Publisher')
        """
    )

    op.create_foreign_key(
        "fk_users_level_roles",
        "users",
        "roles",
        ["level"],
        ["key"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_level_roles", "users", type_="foreignkey")
    op.execute(
        "UPDATE users SET level = 'reviewer' "
        "WHERE lower(trim(level)) = 'publisher'"
    )
    op.drop_table("roles")
