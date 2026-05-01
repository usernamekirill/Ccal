import logging


def configure_logging(level: str) -> None:
    """Configure application logging without exposing sensitive payloads."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
