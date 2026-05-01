from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_add_meal_type"
down_revision: str | None = "0002_expand_privacy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add meal type classification to meals."""
    op.add_column("meals", sa.Column("meal_type", sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Remove meal type classification from meals."""
    op.drop_column("meals", "meal_type")
