from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled) if bundled else Path(__file__).resolve().parent.parent


def user_data_root() -> Path:
    if not getattr(sys, "frozen", False):
        return resource_root()
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "VictorPriceChecker"
