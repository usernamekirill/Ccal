from pathlib import Path

from PIL import Image, UnidentifiedImageError

from calorie_bot.app.exceptions import ErrorCode, ValidationError

SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ImageProcessor:
    """Validate and compress meal photos before AI recognition."""

    def __init__(self, max_side_px: int = 1280, jpeg_quality: int = 85) -> None:
        self._max_side_px = max_side_px
        self._jpeg_quality = jpeg_quality

    def validate_and_compress(self, source_path: Path, output_path: Path) -> Path:
        """Validate image format and write a compressed JPEG copy."""
        try:
            with Image.open(source_path) as image:
                if image.format not in SUPPORTED_FORMATS:
                    raise ValidationError(
                        ErrorCode.UNSUPPORTED_IMAGE_FORMAT,
                        log_hint="pill_format",
                    )
                image = image.convert("RGB")
                image.thumbnail((self._max_side_px, self._max_side_px))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                image.save(output_path, format="JPEG", quality=self._jpeg_quality, optimize=True)
        except UnidentifiedImageError as exc:
            raise ValidationError(
                ErrorCode.UNSUPPORTED_IMAGE_FORMAT,
                log_hint="unidentified",
            ) from exc
        return output_path
