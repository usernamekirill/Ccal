from datetime import datetime
from zoneinfo import ZoneInfo


def now_in_timezone(timezone: str) -> datetime:
    """Return current datetime in the configured timezone."""
    return datetime.now(ZoneInfo(timezone))
