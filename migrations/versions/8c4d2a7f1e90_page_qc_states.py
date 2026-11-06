"""Use the shared QC page-state values."""

from typing import Sequence

from alembic import op


revision: str = "8c4d2a7f1e90"
down_revision: str | None = "61b4d6f9c2a1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE pages SET status = 'unverified' WHERE status = 'queued'"
    )
    op.execute(
        "ALTER TABLE pages ADD CONSTRAINT pages_status_qc_state_check "
        "CHECK (status IN ('unverified', 'in_progress', 'in_review', "
        "'needs_changes', 'completed')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE pages VALIDATE CONSTRAINT pages_status_qc_state_check"
    )


def downgrade() -> None:
    op.drop_constraint(
        "pages_status_qc_state_check",
        "pages",
        type_="check",
    )
    op.execute(
        "UPDATE pages SET status = 'queued' WHERE status = 'unverified'"
    )
