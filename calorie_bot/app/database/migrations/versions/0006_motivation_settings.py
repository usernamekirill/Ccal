"""Add motivation_messages_enabled to user_settings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_motivation_settings"
down_revision: str | None = "0005_add_meal_change_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable per-user opt-out for motivation messages (default on)."""
    with op.batch_alter_table("user_settings") as batch:
        batch.add_column(
            sa.Column(
                "motivation_messages_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )


def downgrade() -> None:
    """Remove motivation preference column."""
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_column("motivation_messages_enabled")
