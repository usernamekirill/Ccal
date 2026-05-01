from pathlib import Path


def safe_unlink(path: Path | None) -> None:
    """Delete a file if it exists."""
    if path and path.exists():
        path.unlink()
