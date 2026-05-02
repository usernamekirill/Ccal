"""Meal items: quantity-based portion metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_meal_items_quantity_fields"
down_revision: str | None = "0008_portion_accuracy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add optional countable-portion columns."""
    with op.batch_alter_table("meal_items") as batch:
        batch.add_column(sa.Column("quantity", sa.Float(), nullable=True))
        batch.add_column(sa.Column("unit_type", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("unit_weight_grams", sa.Float(), nullable=True))
        batch.add_column(sa.Column("size_modifier", sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Remove quantity metadata."""
    with op.batch_alter_table("meal_items") as batch:
        batch.drop_column("size_modifier")
        batch.drop_column("unit_weight_grams")
        batch.drop_column("unit_type")
        batch.drop_column("quantity")
