"""Chart and future image export for statistics (reserved for Phase 2).

Phase 1 does not render graphs. Call sites may request a ``StatsChartSpec`` later
for PNG/SVG generation or Telegram chart widgets without changing service APIs.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class StatsChartSpec:
    """Structured description of a chart to render outside plain-text stats."""

    chart_id: str
    title: str
    x_labels: list[str]
    y_values: list[float]
    y_unit: str


@runtime_checkable
class StatsChartRenderer(Protocol):
    """Protocol for future chart builders (matplotlib, quickchart.io, etc.)."""

    def build_week_calories(
        self,
        user_id: int,
        daily_calories: list[tuple[date, int]],
    ) -> StatsChartSpec | None:
        """Return a weekly calories series spec, or None if charts disabled."""
        ...


class NullStatsChartRenderer:
    """Default renderer: no chart assets in Phase 1."""

    def build_week_calories(
        self,
        user_id: int,
        daily_calories: list[tuple[date, int]],
    ) -> StatsChartSpec | None:
        """Always omit charts until Phase 2."""
        return None
