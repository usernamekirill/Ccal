"""Guard layers: pure nutrition math, formatters, and documented service Telegram coupling.

These tests do not require moving the whole codebase to a hexagonal layout; they freeze
current safe boundaries and fail if new code deepens illegal dependencies.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "calorie_bot" / "app"


def _module_imports(py_path: Path) -> set[str]:
    """Top-level imported module roots and full ``from`` targets (as strings)."""
    tree = ast.parse(py_path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_nutrition_calculator_has_no_storage_or_telegram_deps() -> None:
    """Nutrition math must stay testable without DB / Telegram."""
    path = _APP / "services" / "nutrition_calculator.py"
    imports = _module_imports(path)
    blocked = {"aiogram", "sqlalchemy", "calorie_bot.app.database"}
    for prefix in blocked:
        assert not any(imp == prefix or imp.startswith(prefix + ".") for imp in imports), (
            f"nutrition_calculator must not depend on {prefix}, got: {sorted(imports)}"
        )


@pytest.mark.parametrize(
    "rel_path",
    [
        "utils/nutrition_formatter.py",
        "utils/ux_formatter.py",
        "stats/formatting.py",
        "trends/formatting.py",
    ],
)
def test_presentation_formatters_avoid_persistence_layer(rel_path: str) -> None:
    """Formatters only turn structured data into strings; no ORM/SQLAlchemy."""
    path = _APP / rel_path
    imports = _module_imports(path)
    assert not any(
        imp.startswith("sqlalchemy") or imp.startswith("calorie_bot.app.database") for imp in imports
    ), f"{rel_path} must not import DB layer: {sorted(imports)}"


# Services that legitimately wrap Telegram transport today (roadmap: move to adapters).
_SERVICES_ALLOWED_AIOGRAM: frozenset[str] = frozenset(
    {
        "services/input_router_service.py",
        "services/security_service.py",
        "services/user_service.py",
    }
)


def test_only_allowlisted_application_services_import_aiogram() -> None:
    """New business services must not take a dependency on aiogram."""
    services_dir = _APP / "services"
    violations: list[str] = []
    for path in sorted(services_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        rel = str(path.relative_to(_APP))
        imports = _module_imports(path)
        uses_aiogram = any(imp == "aiogram" or imp.startswith("aiogram.") for imp in imports)
        if uses_aiogram and rel not in _SERVICES_ALLOWED_AIOGRAM:
            violations.append(rel)
    assert not violations, (
        "Services should not import aiogram (use handlers/adapters). Offenders:\n"
        + "\n".join(violations)
        + "\nAdd to _SERVICES_ALLOWED_AIOGRAM only with architect approval."
    )


def test_handlers_orm_imports_baseline() -> None:
    """Handlers should use repositories; ORM models in handlers are a documented smell.

    Fail if *new* handler files start importing ``database.models`` (regression gate).
    """
    handlers_dir = _APP / "handlers"
    with_models: list[str] = []
    for path in sorted(handlers_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        imports = _module_imports(path)
        if any(imp.startswith("calorie_bot.app.database.models") for imp in imports):
            with_models.append(str(path.relative_to(_APP)))
    # Baseline (2026-04): tighten by removing entries when refactored.
    assert set(with_models) <= {
        "handlers/settings_handler.py",
        "handlers/today.py",
    }, (
        "Handlers must not import ORM models directly; use DTOs/repositories. "
        f"Got: {with_models}"
    )
