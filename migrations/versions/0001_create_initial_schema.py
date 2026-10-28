"""Create the initial journal QC schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-28
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=1000), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "volumes",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=1000), primary_key=True),
        sa.Column("volume_code", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "issues",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=1000), primary_key=True),
        sa.Column("volume_id", sa.BigInteger(), nullable=False),
        sa.Column("issue_code", sa.Text(), nullable=False),
        sa.Column("manifest_s3_key", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["volume_id"], ["volumes.id"]),
    )
    op.create_index("ix_issues_volume_id", "issues", ["volume_id"])

    op.create_table(
        "pages",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=10000), primary_key=True),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("dpi", sa.Integer()),
        sa.Column("master_pdf_s3_key", sa.Text()),
        sa.Column("toned_pdf_s3_key", sa.Text()),
        sa.Column("ocr_s3_key", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("is_check_page", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("current_approved_revision_id", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("page_number > 0", name="pages_page_number_check"),
        sa.CheckConstraint("width > 0", name="pages_width_check"),
        sa.CheckConstraint("height > 0", name="pages_height_check"),
        sa.CheckConstraint("dpi > 0", name="pages_dpi_check"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"]),
        sa.UniqueConstraint("issue_id", "page_number"),
    )
    op.create_index("ix_pages_issue_id", "pages", ["issue_id"])
    op.create_table(
        "assignments",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=10000), primary_key=True),
        sa.Column("page_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("lock_expires_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_assignments_page_id", "assignments", ["page_id"])
    op.create_index("ix_assignments_user_id", "assignments", ["user_id"])

    op.create_table(
        "revisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=10000), primary_key=True),
        sa.Column("page_id", sa.BigInteger(), nullable=False),
        sa.Column("saved_by", sa.BigInteger(), nullable=False),
        sa.Column("based_on_revision_id", sa.BigInteger()),
        sa.Column("s3_key", sa.Text(), nullable=False, unique=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.ForeignKeyConstraint(["saved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["based_on_revision_id"], ["revisions.id"]),
        sa.UniqueConstraint("id", "page_id"),
    )
    op.create_index("ix_revisions_page_id", "revisions", ["page_id"])
    op.create_index("ix_revisions_saved_by", "revisions", ["saved_by"])
    op.create_index(
        "ix_revisions_based_on_revision_id", "revisions", ["based_on_revision_id"]
    )
    op.create_foreign_key(
        "fk_pages_current_approved_revision",
        "pages",
        "revisions",
        ["current_approved_revision_id", "id"],
        ["id", "page_id"],
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=10000), primary_key=True),
        sa.Column("revision_id", sa.BigInteger(), nullable=False),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["revisions.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
    )
    op.create_index("ix_reviews_revision_id", "reviews", ["revision_id"])
    op.create_index("ix_reviews_reviewer_id", "reviews", ["reviewer_id"])

    op.create_table(
        "approved_pages",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=10000), primary_key=True),
        sa.Column("page_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("revision_id", sa.BigInteger(), nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["revision_id", "page_id"],
            ["revisions.id", "revisions.page_id"],
            name="fk_approved_pages_revision",
        ),
    )
    op.create_index("ix_approved_pages_approved_by", "approved_pages", ["approved_by"])

    op.create_table(
        "flags",
        sa.Column("id", sa.BigInteger(), sa.Identity(start=10000), primary_key=True),
        sa.Column("page_id", sa.BigInteger(), nullable=False),
        sa.Column("line_revision_id", sa.BigInteger()),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("flag_type", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["line_revision_id", "page_id"],
            ["revisions.id", "revisions.page_id"],
            name="fk_flags_line_revision",
        ),
    )
    op.create_index("ix_flags_page_id", "flags", ["page_id"])
    op.create_index("ix_flags_line_revision_id", "flags", ["line_revision_id"])
    op.create_index("ix_flags_created_by", "flags", ["created_by"])

    op.execute(
        """
        CREATE FUNCTION set_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$
        """
    )
    for table in (
        "users",
        "volumes",
        "issues",
        "pages",
        "assignments",
        "revisions",
        "reviews",
        "approved_pages",
        "flags",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at "
            f"BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    op.drop_table("flags")
    op.drop_table("approved_pages")
    op.drop_table("reviews")
    op.drop_constraint(
        "fk_pages_current_approved_revision", "pages", type_="foreignkey"
    )
    op.drop_table("assignments")
    op.drop_table("revisions")
    op.drop_table("pages")
    op.drop_table("issues")
    op.drop_table("volumes")
    op.drop_table("users")
    op.execute("DROP FUNCTION set_updated_at()")
