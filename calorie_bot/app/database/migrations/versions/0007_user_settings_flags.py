"""Add notifications, AI toggle, and measurement unit to user_settings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_user_settings_flags"
down_revision: str | None = "0006_motivation_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add notification, AI analysis, and measurement unit preferences."""
    with op.batch_alter_table("user_settings") as batch:
        batch.add_column(
            sa.Column(
                "notifications_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
        batch.add_column(
            sa.Column(
                "ai_analysis_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
        batch.add_column(
            sa.Column(
                "measurement_unit",
                sa.String(length=16),
                nullable=False,
                server_default="metric",
            ),
        )


def downgrade() -> None:
    """Remove added preference columns."""
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_column("measurement_unit")
        batch.drop_column("ai_analysis_enabled")
        batch.drop_column("notifications_enabled")
