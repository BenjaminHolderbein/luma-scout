"""seen.json persistence. Committed to the repo so a cloud routine keeps state
across runs. Only holds event ids + dates -- nothing sensitive."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

SEEN_PATH = os.path.join(os.path.dirname(__file__), "state", "seen.json")


def load() -> dict:
    try:
        with open(SEEN_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(seen: dict) -> None:
    os.makedirs(os.path.dirname(SEEN_PATH), exist_ok=True)
    with open(SEEN_PATH, "w") as f:
        json.dump(seen, f, indent=1, sort_keys=True)


def prune(seen: dict, days_grace: int = 3) -> dict:
    """Drop events whose date is more than `days_grace` in the past."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_grace)
    out = {}
    for eid, rec in seen.items():
        ed = rec.get("event_date")
        try:
            if ed and datetime.fromisoformat(ed.replace("Z", "+00:00")) >= cutoff:
                out[eid] = rec
        except ValueError:
            out[eid] = rec  # keep anything unparseable rather than lose it
    return out


def is_first_run(seen: dict) -> bool:
    return len(seen) == 0
