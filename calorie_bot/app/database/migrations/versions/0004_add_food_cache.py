from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_food_cache"
down_revision: str | None = "0003_add_meal_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create food nutrition cache table."""
    op.create_table(
        "food_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("normalized_name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("calories_per_100g", sa.Float(), nullable=False),
        sa.Column("protein_per_100g", sa.Float(), nullable=True),
        sa.Column("fat_per_100g", sa.Float(), nullable=True),
        sa.Column("carbs_per_100g", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("is_estimated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_food_cache_normalized_name", "food_cache", ["normalized_name"], unique=True)


def downgrade() -> None:
    """Drop food nutrition cache table."""
    op.drop_index("ix_food_cache_normalized_name", table_name="food_cache")
    op.drop_table("food_cache")
