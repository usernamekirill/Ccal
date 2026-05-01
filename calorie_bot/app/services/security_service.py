from pathlib import Path
from uuid import uuid4

from aiogram import Bot
from aiogram.types import File


class SecurityService:
    """Handle file limits and temporary media storage."""

    def __init__(self, tmp_dir: Path) -> None:
        self._tmp_dir = tmp_dir
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    def ensure_file_size(self, file_size: int | None, max_bytes: int) -> None:
        """Raise ``ValidationError`` if a Telegram file exceeds the limit."""
        from calorie_bot.app.exceptions import ErrorCode, ValidationError

        if file_size is not None and file_size > max_bytes:
            raise ValidationError(ErrorCode.FILE_TOO_LARGE, log_hint="telegram_file_bytes")

    async def download_temporary(self, bot: Bot, file: File, suffix: str) -> Path:
        """Download a Telegram file to a temporary path."""
        path = self._tmp_dir / f"{uuid4().hex}{suffix}"
        await bot.download_file(file.file_path, destination=path)
        return path

    def cleanup(self, path: Path | None) -> None:
        """Delete a temporary file if it exists."""
        if path and path.exists():
            path.unlink()
