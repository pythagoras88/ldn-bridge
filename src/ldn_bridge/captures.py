from __future__ import annotations

import json
import time
from pathlib import Path

from .config import PROJECT_ROOT


def save_capture(kind: str, obj) -> Path:
    """Write a JSON capture under captures/. Never pass keys or passphrases in obj."""
    d = PROJECT_ROOT / "captures"
    d.mkdir(exist_ok=True)
    path = d / f"{kind}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(obj, indent=2))
    return path
