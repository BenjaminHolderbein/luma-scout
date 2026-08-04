"""Multi-source collection.

`collect()` runs every source, isolates failures, applies the horizon/geography
rules, and merges cross-source duplicates into one list of canonical records.

Two horizons, because Ben's priorities differ in lead time:
  * hackathons  -- long window (you have to register in advance), Bay-wide
  * everything else -- the coming week, San Francisco proper

Tier is decided later by the ranker, so at this stage we keep anything that
*might* be a hackathon and let run.py enforce the short horizon after ranking.
"""
from __future__ import annotations

import re
from datetime import timedelta

from . import common, devpost, eventbrite, luma_src, meetup

HACKATHON_HINT = re.compile(
    r"\b(hack ?a ?thon|hackaton|buildathon|build[- ]?a[- ]?thon|hack night|"
    r"hack day|hack week|code ?jam|game ?jam|datathon|makeathon|sprint weekend)\b",
    re.I)


def looks_like_hackathon(rec: dict) -> bool:
    """Deliberately name-first.

    An earlier version also matched on description, which flooded tier 1 with
    junk: Eventbrite and Meetup put unrelated "you might also like" events on a
    hackathon search page, and their JSON-LD descriptions leak page context. Only
    Luma and Devpost have descriptions trustworthy enough to match on.
    """
    if rec.get("forced_tier") == "hackathon":
        return True
    if HACKATHON_HINT.search(rec.get("name") or ""):
        return True
    if rec.get("source") in ("luma", "devpost"):
        return bool(HACKATHON_HINT.search(rec.get("description") or ""))
    return False


def _in_window(rec: dict, now, window_days: int, hack_window_days: int) -> bool:
    start = common.parse_dt(rec.get("start_at"))
    if start is None:
        # Devpost sometimes gives an unparseable period. Keep hackathons (a
        # missed hackathon is the failure mode Ben cares about), drop the rest.
        return looks_like_hackathon(rec)
    is_hack = looks_like_hackathon(rec)
    if start < now - timedelta(hours=6):
        # Devpost publishes a submission *period*, so a hackathon that opened in
        # April and closes in September has a start date in the past while still
        # being open to join. Judge those on the end date instead.
        end = common.parse_dt(rec.get("end_at"))
        return bool(is_hack and end and end >= now)
    days = hack_window_days if is_hack else window_days
    return start <= now + timedelta(days=days)


def _geo_ok(rec: dict) -> bool:
    prox = rec.get("sf_proximity")
    if prox == "elsewhere":
        return False
    if prox in ("sf", None):    # None = address hidden until RSVP
        return True
    # 'near' (Peninsula/East Bay): hackathons only. Ben asked for SF, but a
    # missed hackathon costs more than a Palo Alto false positive.
    return prox == "near" and looks_like_hackathon(rec)


def collect(now, window_days: int, hack_window_days: int, log=lambda _m: None,
            limit: int = 0) -> tuple[list[dict], dict]:
    """Returns (merged records, per-source status report)."""
    status: dict[str, dict] = {}
    records: list[dict] = []

    # --- Luma: entries need a detail fetch, so filter before enriching ---
    try:
        entries, stats = luma_src.collect_entries(log)
        import filters
        kept, reasons = filters.prefilter(entries, now, hack_window_days)
        log(f"  luma: {reasons['kept']} pass prefilter (dropped {reasons['virtual']} virtual,"
            f" {reasons['past_or_far']} out-of-window, {reasons['sold_out_no_waitlist']} sold-out)")
        if limit:
            kept = kept[:limit]
        log(f"  luma: enriching {len(kept)} (fetching descriptions)...")
        luma_records = []
        for e in kept:
            try:
                luma_records.append(luma_src.to_record(e))
            except Exception:  # noqa: BLE001 - skip a single bad event
                continue
        records += luma_records
        status["luma"] = {"ok": True, "count": len(luma_records), "detail": stats}
    except Exception as e:  # noqa: BLE001
        log(f"  luma: FAILED - {e}")
        status["luma"] = {"ok": False, "count": 0, "error": str(e)[:300]}

    # --- the rest: cheap, already-complete records ---
    for name, mod in (("devpost", devpost), ("eventbrite", eventbrite), ("meetup", meetup)):
        try:
            recs = mod.collect(log)
            records += recs
            status[name] = {"ok": True, "count": len(recs)}
            if not recs:
                status[name]["degraded"] = "returned no events (markup may have changed)"
        except common.EgressBlocked as e:
            log(f"  {name}: BLOCKED - {e}")
            status[name] = {"ok": False, "count": 0, "blocked": True,
                            "error": str(e)[:300]}
        except Exception as e:  # noqa: BLE001 - never let one scraper kill the run
            log(f"  {name}: FAILED - {e}")
            status[name] = {"ok": False, "count": 0, "error": str(e)[:300]}

    before = len(records)
    records = [r for r in records if _in_window(r, now, window_days, hack_window_days) and _geo_ok(r)]
    windowed = len(records)
    records = common.merge(records)
    log(f"\n  {before} collected -> {windowed} in window/area -> {len(records)} after cross-source dedup")
    status["_totals"] = {"collected": before, "in_scope": windowed, "merged": len(records)}
    return records, status
