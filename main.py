"""Run the calorie bot locally (entry point at repo root).

Equivalent to: ``python -m calorie_bot.app.main``
"""

from __future__ import annotations

import asyncio

from calorie_bot.app.main import main


if __name__ == "__main__":
    asyncio.run(main())
