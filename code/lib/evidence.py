from __future__ import annotations

import json
import os

EVIDENCE_DIR = os.path.join(os.path.dirname(__file__), "..", "evidence")


def load_image_amounts() -> dict[str, dict]:
    """event_id -> {amount, currency, image_id, ...} extracted from linked images."""
    path = os.path.join(EVIDENCE_DIR, "image_amounts.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("events", {})
