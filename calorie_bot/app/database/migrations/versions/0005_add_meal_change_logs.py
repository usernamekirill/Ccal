from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_add_meal_change_logs"
down_revision: str | None = "0004_add_food_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create meal change log table."""
    op.create_table(
        "meal_change_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meal_id", sa.Integer(), sa.ForeignKey("meals.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_meal_change_logs_meal_id", "meal_change_logs", ["meal_id"])
    op.create_index("ix_meal_change_logs_user_id", "meal_change_logs", ["user_id"])


def downgrade() -> None:
    """Drop meal change log table."""
    op.drop_index("ix_meal_change_logs_user_id", table_name="meal_change_logs")
    op.drop_index("ix_meal_change_logs_meal_id", table_name="meal_change_logs")
    op.drop_table("meal_change_logs")
