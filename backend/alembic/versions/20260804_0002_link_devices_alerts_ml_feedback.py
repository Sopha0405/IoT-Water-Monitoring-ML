"""link devices with alerts, ml_analysis and feedback

Revision ID: 20260804_0002
Revises: 20260804_0001
Create Date: 2026-08-04
"""

from alembic import op


revision = "20260804_0002"
down_revision = "20260804_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_alerts_device_id_devices'
          ) THEN
            ALTER TABLE alerts
            ADD CONSTRAINT fk_alerts_device_id_devices
            FOREIGN KEY (device_id) REFERENCES devices(device_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
            NOT VALID;
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_ml_analysis_device_id_devices'
          ) THEN
            ALTER TABLE ml_analysis
            ADD CONSTRAINT fk_ml_analysis_device_id_devices
            FOREIGN KEY (device_id) REFERENCES devices(device_id)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_ml_alert_feedback_sensor_id_devices'
          ) THEN
            ALTER TABLE ml_alert_feedback
            ADD CONSTRAINT fk_ml_alert_feedback_sensor_id_devices
            FOREIGN KEY (sensor_id) REFERENCES devices(device_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
            NOT VALID;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ml_alert_feedback DROP CONSTRAINT IF EXISTS fk_ml_alert_feedback_sensor_id_devices")
    op.execute("ALTER TABLE ml_analysis DROP CONSTRAINT IF EXISTS fk_ml_analysis_device_id_devices")
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS fk_alerts_device_id_devices")
