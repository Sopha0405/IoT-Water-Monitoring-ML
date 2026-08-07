"""add user floor scope flag

Revision ID: 20260804_0003
Revises: 20260804_0002
Create Date: 2026-08-04
"""

from alembic import op


revision = "20260804_0003"
down_revision = "20260804_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS limit_to_floor BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_limit_to_floor ON users(limit_to_floor)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_limit_to_floor")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS limit_to_floor")
