from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_expand_user_meal_privacy_schema"
down_revision: str | None = "0001_initial_mvp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Expand MVP schema with settings, audit, stats, and privacy support."""
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "onboarding_status",
            sa.String(length=32),
            nullable=False,
            server_default="not_started",
        ),
    )

    with op.batch_alter_table("user_profiles") as batch:
        batch.create_index("ix_user_profiles_user_id", ["user_id"], unique=True)
        for column_name, column_type in (
            ("goal", sa.String(length=32)),
            ("sex", sa.String(length=16)),
            ("age", sa.Integer()),
            ("height_cm", sa.Float()),
            ("weight_kg", sa.Float()),
            ("activity_level", sa.String(length=32)),
            ("bmr_calories", sa.Integer()),
            ("tdee_calories", sa.Integer()),
            ("daily_calorie_target", sa.Integer()),
            ("daily_protein_target_g", sa.Integer()),
            ("daily_fat_target_g", sa.Integer()),
            ("daily_carbs_target_g", sa.Integer()),
        ):
            batch.alter_column(column_name, existing_type=column_type, nullable=True)

    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("tone", sa.String(length=32), nullable=False),
        sa.Column("ai_daily_soft_limit", sa.Integer(), nullable=False),
        sa.Column("data_retention_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=True)

    op.add_column("meals", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("meals", sa.Column("total_protein_g", sa.Float(), nullable=True))
    op.add_column("meals", sa.Column("total_fat_g", sa.Float(), nullable=True))
    op.add_column("meals", sa.Column("total_carbs_g", sa.Float(), nullable=True))
    op.create_index("ix_meals_eaten_at", "meals", ["eaten_at"])
    op.create_index("ix_meals_user_eaten_at", "meals", ["user_id", "eaten_at"])
    op.create_index("ix_meals_user_status", "meals", ["user_id", "status"])

    op.create_table(
        "meal_ai_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meal_id", sa.Integer(), sa.ForeignKey("meals.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_type", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("structured_result", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_meal_ai_results_meal_id", "meal_ai_results", ["meal_id"])
    op.create_index("ix_meal_ai_results_user_id", "meal_ai_results", ["user_id"])

    with op.batch_alter_table("meal_items") as batch:
        batch.add_column(sa.Column("ai_result_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_meal_items_ai_result_id",
            "meal_ai_results",
            ["ai_result_id"],
            ["id"],
        )

    op.create_table(
        "meal_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meal_id", sa.Integer(), sa.ForeignKey("meals.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("correction_text", sa.Text(), nullable=True),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_meal_corrections_meal_id", "meal_corrections", ["meal_id"])
    op.create_index("ix_meal_corrections_user_id", "meal_corrections", ["user_id"])

    op.create_table(
        "meal_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meal_id", sa.Integer(), sa.ForeignKey("meals.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_meal_history_meal_id", "meal_history", ["meal_id"])
    op.create_index("ix_meal_history_user_id", "meal_history", ["user_id"])

    op.create_table(
        "daily_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("stat_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_calories", sa.Integer(), nullable=False),
        sa.Column("total_protein_g", sa.Float(), nullable=False),
        sa.Column("total_fat_g", sa.Float(), nullable=False),
        sa.Column("total_carbs_g", sa.Float(), nullable=False),
        sa.Column("meals_count", sa.Integer(), nullable=False),
        sa.Column("calorie_target", sa.Integer(), nullable=True),
        sa.Column("protein_target_g", sa.Integer(), nullable=True),
        sa.Column("fat_target_g", sa.Integer(), nullable=True),
        sa.Column("carbs_target_g", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_daily_stats_user_id", "daily_stats", ["user_id"])
    op.create_index("ix_daily_stats_stat_date", "daily_stats", ["stat_date"])
    op.create_index(
        "ix_daily_stats_user_date",
        "daily_stats",
        ["user_id", "stat_date"],
        unique=True,
    )

    op.create_table(
        "motivation_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_motivation_events_user_id", "motivation_events", ["user_id"])
    op.create_index("ix_motivation_events_event_date", "motivation_events", ["event_date"])

    op.create_table(
        "error_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("error_type", sa.String(length=128), nullable=False),
        sa.Column("handler", sa.String(length=128), nullable=True),
        sa.Column("safe_message", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_error_logs_user_id", "error_logs", ["user_id"])
    op.create_index("ix_error_logs_request_id", "error_logs", ["request_id"])


def downgrade() -> None:
    """Remove expanded schema objects."""
    op.drop_index("ix_error_logs_request_id", table_name="error_logs")
    op.drop_index("ix_error_logs_user_id", table_name="error_logs")
    op.drop_table("error_logs")

    op.drop_index("ix_motivation_events_event_date", table_name="motivation_events")
    op.drop_index("ix_motivation_events_user_id", table_name="motivation_events")
    op.drop_table("motivation_events")

    op.drop_index("ix_daily_stats_user_date", table_name="daily_stats")
    op.drop_index("ix_daily_stats_stat_date", table_name="daily_stats")
    op.drop_index("ix_daily_stats_user_id", table_name="daily_stats")
    op.drop_table("daily_stats")

    op.drop_index("ix_meal_history_user_id", table_name="meal_history")
    op.drop_index("ix_meal_history_meal_id", table_name="meal_history")
    op.drop_table("meal_history")

    op.drop_index("ix_meal_corrections_user_id", table_name="meal_corrections")
    op.drop_index("ix_meal_corrections_meal_id", table_name="meal_corrections")
    op.drop_table("meal_corrections")

    with op.batch_alter_table("meal_items") as batch:
        batch.drop_constraint("fk_meal_items_ai_result_id", type_="foreignkey")
        batch.drop_column("ai_result_id")
    op.drop_index("ix_meal_ai_results_user_id", table_name="meal_ai_results")
    op.drop_index("ix_meal_ai_results_meal_id", table_name="meal_ai_results")
    op.drop_table("meal_ai_results")

    op.drop_index("ix_meals_user_status", table_name="meals")
    op.drop_index("ix_meals_user_eaten_at", table_name="meals")
    op.drop_index("ix_meals_eaten_at", table_name="meals")
    op.drop_column("meals", "total_carbs_g")
    op.drop_column("meals", "total_fat_g")
    op.drop_column("meals", "total_protein_g")
    op.drop_column("meals", "deleted_at")

    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")
    op.drop_column("users", "onboarding_status")
    op.drop_column("users", "deleted_at")
