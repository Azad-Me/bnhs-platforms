"""Apply the JBNHS QC schema."""

from typing import Sequence

from alembic import op


revision: str = "0002_jbnhs_schema"
down_revision: str | None = "0001_initial"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE issues "
        "ADD COLUMN IF NOT EXISTS toned_pdf_s3_key TEXT"
    )
    op.execute(
        "ALTER TABLE pages "
        "ADD COLUMN IF NOT EXISTS page_source_file TEXT"
    )
   
    op.alter_column("pages", "page_source_file", nullable=False)

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO roles (key, name) VALUES
            ('admin', 'Admin'),
            ('qc_user', 'QC user'),
            ('publisher', 'Publisher')
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_users_level_roles'
                  AND conrelid = 'users'::regclass
            ) THEN
                ALTER TABLE users
                ADD CONSTRAINT fk_users_level_roles
                FOREIGN KEY (level) REFERENCES roles (key);
            END IF;
        END;
        $$;
        """
    )

    op.execute(
        "ALTER TABLE pages "
        "VALIDATE CONSTRAINT pages_status_qc_state_check"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE users "
        "DROP CONSTRAINT IF EXISTS fk_users_level_roles"
    )
    op.execute(
        "UPDATE users SET level = 'reviewer' "
        "WHERE lower(trim(level)) = 'publisher'"
    )
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("ALTER TABLE pages DROP COLUMN IF EXISTS page_source_file")
    op.execute("ALTER TABLE issues DROP COLUMN IF EXISTS toned_pdf_s3_key")
