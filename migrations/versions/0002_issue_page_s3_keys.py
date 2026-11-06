"""Add source keys for issues and page scans.

Revision ID: 0002_issue_page_s3_keys
Revises: 0001_initial
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_issue_page_s3_keys"
down_revision: str | None = "0001_initial"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:

    op.add_column(
        "issues", sa.Column("toned_pdf_s3_key", sa.Text(), nullable=True)
    )
    op.add_column("pages", sa.Column("image_s3_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pages", "image_s3_key")
    op.drop_column("issues", "toned_pdf_s3_key")
    op.drop_column("issues", "master_pdf_s3_key")
