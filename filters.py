"""Deterministic pre-filter: cheap rules applied to the discover LIST payload,
before we spend a detail-fetch or a Claude call on anything."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _parse(dt: str) -> datetime:
    # Luma start_at looks like "2026-07-28T01:00:00.000Z"
    return datetime.fromisoformat(dt.replace("Z", "+00:00"))


def prefilter(entries: list[dict], now: datetime, window_days: int) -> tuple[list[dict], dict]:
    """Return (kept_entries, reasons_counter). All SF, no geo sub-filter."""
    horizon = now + timedelta(days=window_days)
    kept: list[dict] = []
    reasons = {"virtual": 0, "past_or_far": 0, "sold_out_no_waitlist": 0, "kept": 0}

    for e in entries:
        ev = e.get("event", {})

        # in-person only
        if ev.get("location_type") != "offline":
            reasons["virtual"] += 1
            continue

        # inside the window [now, now+window]
        start = ev.get("start_at")
        if not start:
            reasons["past_or_far"] += 1
            continue
        s = _parse(start)
        if s < now - timedelta(hours=6) or s > horizon:
            reasons["past_or_far"] += 1
            continue

        # drop fully sold out with no waitlist; keep if a waitlist is open
        ti = e.get("ticket_info") or {}
        if ti.get("is_sold_out") and not e.get("waitlist_active"):
            reasons["sold_out_no_waitlist"] += 1
            continue

        kept.append(e)
        reasons["kept"] += 1

    return kept, reasons


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
