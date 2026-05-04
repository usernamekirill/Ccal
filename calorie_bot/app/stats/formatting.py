"""User-facing formatting for statistics messages (Telegram plain text)."""

from calorie_bot.app.domain import StatsMonthView, StatsTodayView, StatsWeekView


def format_progress_bar(percent: float, width: int = 12) -> str:
    """Build a simple block progress bar for Telegram (no external graphics)."""
    ratio = max(0.0, min(100.0, percent)) / 100.0
    filled = int(round(width * ratio))
    filled = min(width, filled)
    return f"[{'█' * filled}{'░' * (width - filled)}] {percent:.0f}%"


_NEAR_GOAL_PCT = 85.0


def _kcal_progress_suffix(*, progress_percent: float | None, remaining_kcal: int | None) -> str:
    if remaining_kcal is not None and remaining_kcal < 0:
        return " 🔴"
    if progress_percent is not None and progress_percent >= _NEAR_GOAL_PCT:
        return " ⚠️"
    return ""


def _macro_row(label: str, current: float, target: int | None, *, width: int = 10) -> str:
    """One macro line: ASCII bar vs daily target when target exists."""
    if target is None or target <= 0:
        bar = format_progress_bar(0.0, width=width)
        return f"{label}: {bar} — {current:.0f} г (цель не задана)"
    pct = min(100.0, max(0.0, 100.0 * current / float(target)))
    bar = format_progress_bar(pct, width=width)
    suf = ""
    if current > target * 1.01:
        suf = " 🔴"
    elif pct >= _NEAR_GOAL_PCT:
        suf = " ⚠️"
    return f"{label}: {bar}{suf} ({current:.0f}/{target} г)"


def format_today_macro_dashboard(view: StatsTodayView) -> str | None:
    """Optional KBJU block for /stats day view (uses sums from ``StatsService`` only)."""
    if view.meals_count == 0:
        return None
    p, f_, c = view.total_protein_g, view.total_fat_g, view.total_carbs_g
    if p is None and f_ is None and c is None:
        return None
    lines = [
        "КБЖУ за день:",
        _macro_row("Белки", float(p or 0), view.protein_target_g),
        _macro_row("Жиры", float(f_ or 0), view.fat_target_g),
        _macro_row("Углеводы", float(c or 0), view.carbs_target_g),
    ]
    return "\n".join(lines)


def format_today_status_line(view: StatsTodayView) -> str:
    """Single-line daily progress for footers, menus, post-save, and quick status."""
    approx = getattr(view, "has_approximate_values", False)
    tilde = "~" if approx else ""
    label = "🔥 Сегодня:"
    if view.calorie_target is not None and view.progress_percent is not None:
        return (
            f"{label} {tilde}{view.total_calories} / {view.calorie_target} ккал "
            f"({view.progress_percent:.0f}%)"
        )
    if view.calorie_target is not None:
        return f"{label} {tilde}{view.total_calories} / {view.calorie_target} ккал"
    return f"{label} {tilde}{view.total_calories} ккал (цель не задана)"


def format_today_stats(view: StatsTodayView) -> str:
    """Render today's calories, goal, progress, meals, and food list."""
    approx = getattr(view, "has_approximate_values", False)
    cmin = getattr(view, "total_calories_min", None)
    cmax = getattr(view, "total_calories_max", None)
    if cmin is not None and cmax is not None:
        eaten_label = f"Съедено: ~{cmin}–{cmax} ккал (диапазон по порциям)"
    elif approx:
        eaten_label = f"Съедено: ~{view.total_calories} ккал"
    else:
        eaten_label = f"Съедено: {view.total_calories} ккал"
    lines = [eaten_label]
    if view.calorie_target is not None:
        lines.append(f"Цель: {view.calorie_target} ккал")
        if view.remaining_kcal is not None:
            if view.remaining_kcal >= 0:
                lines.append(f"Остаток до цели: {view.remaining_kcal} ккал")
            else:
                lines.append(f"Сверх цели на: {abs(view.remaining_kcal)} ккал")
        if view.progress_percent is not None:
            bar = format_progress_bar(view.progress_percent)
            suf = _kcal_progress_suffix(
                progress_percent=view.progress_percent,
                remaining_kcal=view.remaining_kcal,
            )
            lines.append(f"Прогресс: {bar}{suf}")
    else:
        lines.append("Цель по калориям не задана — укажи её в онбординге.")

    macro_lines = format_today_macro_dashboard(view)
    if macro_lines:
        lines.append("")
        lines.append(macro_lines)

    lines.append(f"Приёмов пищи: {view.meals_count}")

    if view.food_sections:
        lines.append("")
        lines.append("Что было:")
        lines.extend(view.food_sections)
    elif view.meals_count == 0:
        lines.append("")
        lines.append("Пока нет записей за сегодня.")

    if getattr(view, "has_approximate_values", False):
        lines.append("")
        lines.append("Часть значений примерная (оценка порции).")
        ratio = getattr(view, "estimated_meals_ratio", None)
        if ratio is not None and 0 < ratio < 1:
            pct = int(round(100 * ratio))
            lines.append(f"Около {pct}% приёмов с оценочными порциями.")

    return "\n".join(lines)


def format_week_stats(view: StatsWeekView) -> str:
    """Render weekly averages and goal adherence hints."""
    lines = []

    if view.avg_calories_per_day is not None:
        lines.append(f"Среднее за день (÷7): {view.avg_calories_per_day:.0f} ккал")
    else:
        lines.append("Среднее за день: нет данных")

    if view.calorie_target is not None:
        above = view.days_above_target
        below = view.days_below_or_equal_target
        lines.append(f"Дней выше цели: {above} — на цели или ниже: {below}")
        logged = view.days_with_logs
        window = view.calendar_days_in_window
        lines.append(f"Дней с записями: {logged} из {window} (календарная неделя)")
    else:
        lines.append("Цель не задана — счёт дней относительно цели недоступен.")
        lines.append(
            f"Дней с записями: {view.days_with_logs} из {view.calendar_days_in_window}"
        )

    has_best = (
        view.best_day_label
        and view.best_day_calories is not None
        and view.calorie_target is not None
    )
    if has_best:
        delta = view.best_day_delta_from_target
        delta_txt = f" (отклонение {delta:+d} ккал)" if delta is not None else ""
        label = view.best_day_label
        kcal = view.best_day_calories
        lines.append(f"Лучший день по близости к цели: {label} — {kcal} ккал{delta_txt}")

    lines.append("")
    lines.append("Графики появятся позже — данные уже собираются.")
    return "\n".join(lines)


def format_month_stats(view: StatsMonthView) -> str:
    """Render monthly aggregates, trend, and logging regularity."""
    lines = []

    if view.avg_calories_per_day is not None:
        lines.append(f"Среднее в день (по дням месяца): {view.avg_calories_per_day:.0f} ккал")
    else:
        lines.append("Среднее в день: нет данных")

    lines.append(f"Тренд по дням с записями: {view.trend_label}")
    dw = view.days_with_data
    de = view.days_elapsed_in_month
    lines.append(f"Дней с записями: {dw} из {de} прошедших в этом месяце")

    if view.regularity_percent is not None:
        reg_bar = format_progress_bar(view.regularity_percent)
        lines.append(f"Регулярность ведения: {reg_bar}")
    else:
        lines.append("Регулярность: нет данных")

    if view.calorie_target is None:
        lines.append("")
        lines.append("Цель по калориям не задана — часть метрик ориентировочная.")

    lines.append("")
    lines.append("График тренда подключим на следующем этапе.")
    return "\n".join(lines)
