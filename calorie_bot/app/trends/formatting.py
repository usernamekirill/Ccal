"""Plain-text formatting for rolling trend reports (mini ASCII bars)."""

from calorie_bot.app.domain import TrendReport


def format_trend_report(report: TrendReport, *, bar_width: int = 8) -> str:
    """Render calories-by-day mini chart and summary blocks for Telegram."""
    lines: list[str] = []

    target_line = (
        f"Ориентир по калориям: {report.calorie_target} ккал/день"
        if report.calorie_target
        else "Ориентир по калориям не задан в профиле."
    )
    lines.append(target_line)
    lines.append("")
    lines.append("Калории по дням:")
    scale = _scale_max(report)
    for point in report.daily_points:
        filled = 0
        if scale > 0 and point.calories > 0:
            filled = max(1, int(round(bar_width * point.calories / scale)))
        filled = min(bar_width, filled)
        bar = "█" * filled
        lines.append(f"{point.day_label} {bar} {point.calories}")

    lines.append("")
    avg_line = (
        f"Среднее за день (все {report.window_days} дн. окна): "
        f"{report.avg_calories_per_calendar_day:.0f} ккал"
    )
    lines.append(avg_line)

    if report.previous_window_avg is not None:
        if report.avg_change_vs_prev_percent is not None:
            sign = report.avg_change_vs_prev_percent
            lines.append(
                f"К прошлому отрезку: {sign:+.1f}% к среднему "
                f"(было ~{report.previous_window_avg:.0f} ккал/день)."
            )
        else:
            lines.append(f"Прошлый отрезок: ~{report.previous_window_avg:.0f} ккал/день в среднем.")
    else:
        lines.append("Прошлого отрезка для сравнения почти не было.")

    lines.append("")
    reg_bar = _tiny_regularity_bar(report.regularity_percent)
    lines.append(
        f"Регулярность записей: {report.regularity_percent:.0f}% {reg_bar} "
        f"({report.days_with_logs} дн. с записями, {report.days_without_logs} без)."
    )

    if report.goal_relaxed_match_days and report.days_with_logs:
        lines.append(
            f"Мягкое попадание в ориентир: {report.goal_relaxed_match_days} "
            f"дн. с записями из {report.days_with_logs}."
        )

    if report.top_products:
        lines.append("")
        lines.append("Частые продукты:")
        for p in report.top_products:
            lines.append(f"• {p.display_name} — {p.times_seen}×")

    if report.source_slices:
        lines.append("")
        lines.append("Как добавляли приёмы:")
        for s in report.source_slices:
            lines.append(f"• {s.display_label}: {s.percent:.0f}% ({s.meal_count})")

    if report.empty_day_labels and len(report.empty_day_labels) <= 7:
        lines.append("")
        lines.append("Дни без записей: " + ", ".join(report.empty_day_labels))
    elif report.days_without_logs:
        lines.append("")
        lines.append(f"Дней без записей в окне: {report.days_without_logs}.")

    if report.interpretation_lines:
        lines.append("")
        lines.append("Коротко:")
        for t in report.interpretation_lines:
            lines.append(f"— {t}")

    return "\n".join(lines)


def _scale_max(report: TrendReport) -> int:
    """Pick bar scale from tall day or target so bars stay readable."""
    peak = max((p.calories for p in report.daily_points), default=0)
    target = report.calorie_target or 0
    return max(peak, int(target * 1.05), 1)


def _tiny_regularity_bar(percent: float) -> str:
    """3-block hint for regularity."""
    if percent >= 66:
        return "[███]"
    if percent >= 33:
        return "[██░]"
    return "[█░░]"
