"""Portion accuracy: meal_items macros ranges, meal totals range, daily approx flag."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_portion_accuracy"
down_revision: str | None = "0007_user_settings_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add honest portion / calorie range fields."""
    with op.batch_alter_table("meal_items") as batch:
        batch.add_column(sa.Column("grams_min", sa.Float(), nullable=True))
        batch.add_column(sa.Column("grams_max", sa.Float(), nullable=True))
        batch.add_column(sa.Column("grams_source", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("calories_min", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("calories_max", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("calories_per_100g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("protein_per_100g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("fat_per_100g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("carbs_per_100g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("protein_g_min", sa.Float(), nullable=True))
        batch.add_column(sa.Column("protein_g_max", sa.Float(), nullable=True))
        batch.add_column(sa.Column("fat_g_min", sa.Float(), nullable=True))
        batch.add_column(sa.Column("fat_g_max", sa.Float(), nullable=True))
        batch.add_column(sa.Column("carbs_g_min", sa.Float(), nullable=True))
        batch.add_column(sa.Column("carbs_g_max", sa.Float(), nullable=True))
        batch.add_column(sa.Column("food_confidence", sa.Float(), nullable=True))
        batch.add_column(sa.Column("portion_confidence", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column(
                "needs_portion_clarification",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        batch.add_column(
            sa.Column(
                "is_estimated",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    with op.batch_alter_table("meal_items") as batch:
        batch.alter_column("calories", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("meals") as batch:
        batch.add_column(sa.Column("total_calories_min", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("total_calories_max", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "has_estimated_items",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    """Remove portion accuracy columns."""
    with op.batch_alter_table("meals") as batch:
        batch.drop_column("has_estimated_items")
        batch.drop_column("total_calories_max")
        batch.drop_column("total_calories_min")

    with op.batch_alter_table("meal_items") as batch:
        batch.alter_column("calories", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("is_estimated")
        batch.drop_column("needs_portion_clarification")
        batch.drop_column("portion_confidence")
        batch.drop_column("food_confidence")
        batch.drop_column("carbs_g_max")
        batch.drop_column("carbs_g_min")
        batch.drop_column("fat_g_max")
        batch.drop_column("fat_g_min")
        batch.drop_column("protein_g_max")
        batch.drop_column("protein_g_min")
        batch.drop_column("carbs_per_100g")
        batch.drop_column("fat_per_100g")
        batch.drop_column("protein_per_100g")
        batch.drop_column("calories_per_100g")
        batch.drop_column("calories_max")
        batch.drop_column("calories_min")
        batch.drop_column("grams_source")
        batch.drop_column("grams_max")
        batch.drop_column("grams_min")
