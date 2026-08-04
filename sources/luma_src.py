"""Luma source.

Two passes, because Luma's curated SF discover feed is small (~69 events) and
demonstrably misses hackathons, and the public search API needs auth:

  1. the SF discover feed (the original behaviour), and
  2. a calendar crawl -- every event carries `calendar_api_id`, and
     /calendar/get-items?period=future lists that calendar's upcoming events in
     the exact same entry shape. Crawling the calendars behind the discover feed
     (plus a seed list of known SF hackathon hosts) surfaces events that never
     made the curated cut.

Entries from both passes are identical in shape, so filters.py and enrich.py
work on them unchanged.
"""
from __future__ import annotations

import urllib.parse

import enrich as enrich_mod
import luma
from . import common

API = "https://api.luma.com"

# Calendars worth crawling even if nothing of theirs is in the discover feed
# this week. Resolved lazily by slug; unknown/renamed slugs are skipped quietly.
SEED_CALENDAR_SLUGS = (
    "agihouse", "cerebralvalley", "sfai", "buildspace", "hackathons",
    "ycombinator", "founderslive", "sfnewtech",
)

MAX_CALENDARS = 60          # crawl budget: calendars fetched per run
MAX_ITEMS_PER_CALENDAR = 40


def _calendar_items(cal_id: str, limit: int = MAX_ITEMS_PER_CALENDAR) -> list[dict]:
    q = {"calendar_api_id": cal_id, "period": "future", "pagination_limit": min(limit, 50)}
    data = common.http_json(f"{API}/calendar/get-items?" + urllib.parse.urlencode(q))
    return data.get("entries", []) or []


def _resolve_slug(slug: str) -> str | None:
    """Public calendar page -> calendar api id, via any event it lists."""
    try:
        html = common.http_get(f"https://luma.com/{urllib.parse.quote(slug)}").decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return None
    import re
    m = re.search(r"cal-[A-Za-z0-9]{10,}", html)
    return m.group(0) if m else None


def collect_entries(log=lambda _m: None) -> tuple[list[dict], dict]:
    """Return (deduped raw Luma entries, stats)."""
    stats = {"discover": 0, "calendars_crawled": 0, "from_calendars": 0}

    entries = luma.fetch_discover()
    stats["discover"] = len(entries)
    by_id = {e["event"]["api_id"]: e for e in entries if e.get("event", {}).get("api_id")}

    cal_ids: list[str] = []
    seen_cal: set[str] = set()
    for e in by_id.values():
        e["_from_discover"] = True  # SF-scoped by Luma itself; trust its geography
        cid = e.get("calendar_api_id") or (e.get("event") or {}).get("calendar_api_id")
        if cid and cid not in seen_cal:
            seen_cal.add(cid)
            cal_ids.append(cid)
    for slug in SEED_CALENDAR_SLUGS:
        cid = _resolve_slug(slug)
        if cid and cid not in seen_cal:
            seen_cal.add(cid)
            cal_ids.append(cid)

    log(f"  luma: {len(entries)} from discover, crawling {min(len(cal_ids), MAX_CALENDARS)} calendars")
    for cid in cal_ids[:MAX_CALENDARS]:
        try:
            items = _calendar_items(cid)
        except Exception:  # noqa: BLE001 - one bad calendar must not kill the crawl
            continue
        stats["calendars_crawled"] += 1
        for it in items:
            ev = it.get("event") or {}
            eid = ev.get("api_id")
            if eid and eid not in by_id:
                by_id[eid] = it
                stats["from_calendars"] += 1

    log(f"  luma: +{stats['from_calendars']} new events from {stats['calendars_crawled']} calendars"
        f" -> {len(by_id)} total")
    return list(by_id.values()), stats


def to_record(entry: dict) -> dict:
    """Enrich a Luma entry (detail fetch) into the canonical record."""
    rec = enrich_mod.enrich(entry)
    rec["source"] = "luma"
    rec["also_on"] = []
    rec["forced_tier"] = None

    # The discover feed is SF-curated, but the calendar crawl is not: those
    # calendars host events worldwide. Judge geography per event, and only fall
    # back to trusting Luma when the address is hidden behind an RSVP.
    geo = common.sf_match(rec.get("address"), rec.get("city_state"))
    if geo:
        rec["sf_proximity"] = geo
    elif entry.get("_from_discover"):
        rec["sf_proximity"] = "sf"
    elif rec.get("address_hidden") and not rec.get("city_state"):
        rec["sf_proximity"] = None      # unknowable; keep and let the ranker see it
    else:
        rec["sf_proximity"] = "elsewhere"
    return rec
