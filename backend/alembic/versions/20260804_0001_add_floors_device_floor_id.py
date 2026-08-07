"""add floors and device floor relation

Revision ID: 20260804_0001
Revises:
Create Date: 2026-08-04
"""

from alembic import op


revision = "20260804_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS floors (
            id SERIAL PRIMARY KEY,
            code VARCHAR(20) NOT NULL,
            name VARCHAR(100) NOT NULL,
            description VARCHAR(255),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP,
            CONSTRAINT uq_floors_code UNIQUE (code)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_floors_id ON floors(id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_floors_code ON floors(code)")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS floor_id INTEGER")
    op.execute("CREATE INDEX IF NOT EXISTS ix_devices_floor_id ON devices(floor_id)")
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_devices_floor_id_floors'
          ) THEN
            ALTER TABLE devices
            ADD CONSTRAINT fk_devices_floor_id_floors
            FOREIGN KEY (floor_id) REFERENCES floors(id) ON DELETE RESTRICT;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE devices DROP CONSTRAINT IF EXISTS fk_devices_floor_id_floors")
    op.execute("DROP INDEX IF EXISTS ix_devices_floor_id")
    op.execute("ALTER TABLE devices DROP COLUMN IF EXISTS floor_id")
    op.execute("DROP INDEX IF EXISTS ix_floors_code")
    op.execute("DROP INDEX IF EXISTS ix_floors_id")
    op.execute("DROP TABLE IF EXISTS floors")
