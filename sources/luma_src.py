"""Luma source.

Two passes, because Luma's curated SF discover feed is small (~69 events) and
demonstrably misses hackathons, and the public search API needs auth:

  1. the SF discover feed (the original behaviour), and
  2. a calendar crawl -- every event carries `calendar_api_id`, and
     /calendar/get-items?period=future lists that calendar's upcoming events in
     the exact same entry shape.

The crawl's calendar set comes from four places, in priority order (the crawl
budget cuts from the back, and discover calendars have already contributed at
least one event each via the feed itself):

  seeds     -- hand-picked known hackathon hosts, resolved via /url (below)
  learned   -- calendars that previously hosted a hackathon-named event
               (state/luma_calendars.json, so coverage compounds week over week)
  featured  -- cal ids embedded in the luma.com/sf page HTML, which rotate with
               Luma's own curation and aren't all in the API feed
  discover  -- the calendar behind every event in this week's feed

Seeds are resolved with `GET /url?url=<slug>`, which states whether a slug is a
calendar or an event and returns the true calendar api_id. The old approach
regex-grabbed the first `cal-` id out of the page HTML -- on an event page that
silently returns the *poster's personal calendar*, which is how more than half
the original seed list rotted without anyone noticing. Seeds that fail to
resolve are reported in stats as `dead_seeds` and surfaced in the report.

Entries from both passes are identical in shape, so filters.py and enrich.py
work on them unchanged.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timezone

import enrich as enrich_mod
import luma
from . import common

API = "https://api.luma.com"

# Verified live (Aug 2026). `hackathon_collections` is a community-run
# aggregator ("SF Hackathon Collection") that alone carried 8 upcoming
# hackathons, 5 of which the old crawl missed.
SEED_CALENDAR_SLUGS = (
    "hackathon_collections",  # SF Hackathon Collection -- the highest-value seed
    "agihouse",               # AGI House (their API source covers the rest)
    "fdotinc",                # Founders, Inc -- NOT "foundersinc", which is unrelated
    "frontiertower",
    "mox",                    # Mox -- hosted Apart's AI Control hackathon
    "apartresearch",          # Apart Research -- AIxBio / AI-Control hackathons
    "bayaicircle",            # AGI Summit hackathon host
    "lablab.ai",              # global calendar; per-event geo filter handles that
    "genlab",
)

MAX_CALENDARS = 90          # crawl budget: calendars fetched per run
MAX_ITEMS_PER_CALENDAR = 40
MAX_LEARNED = 40            # cap on the self-widening store

LEARNED_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "state", "luma_calendars.json")


def _calendar_items(cal_id: str, limit: int = MAX_ITEMS_PER_CALENDAR) -> list[dict]:
    q = {"calendar_api_id": cal_id, "period": "future", "pagination_limit": min(limit, 50)}
    data = common.http_json(f"{API}/calendar/get-items?" + urllib.parse.urlencode(q))
    return data.get("entries", []) or []


def _resolve_slug(slug: str) -> str | None:
    """Public slug -> calendar api id, or None if dead or not a calendar."""
    try:
        data = common.http_json(f"{API}/url?url=" + urllib.parse.quote(slug))
    except Exception:  # noqa: BLE001
        return None
    if data.get("kind") != "calendar":
        return None
    return ((data.get("data") or {}).get("calendar") or {}).get("api_id")


def _featured_calendar_ids() -> list[str]:
    """Cal ids embedded in the luma.com/sf page (~20, not all in the API feed)."""
    try:
        html = common.http_get("https://luma.com/sf").decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return []
    return list(dict.fromkeys(re.findall(r"cal-[A-Za-z0-9]{10,}", html)))


def _load_learned() -> dict:
    try:
        with open(LEARNED_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_learned(learned: dict) -> None:
    if len(learned) > MAX_LEARNED:  # keep the most recently active
        keep = sorted(learned.items(), key=lambda kv: kv[1].get("last_seen", ""),
                      reverse=True)[:MAX_LEARNED]
        learned = dict(keep)
    os.makedirs(os.path.dirname(LEARNED_PATH), exist_ok=True)
    with open(LEARNED_PATH, "w") as f:
        json.dump(learned, f, indent=1, sort_keys=True)


def collect_entries(log=lambda _m: None) -> tuple[list[dict], dict]:
    """Return (deduped raw Luma entries, stats)."""
    stats = {"discover": 0, "calendars_crawled": 0, "from_calendars": 0,
             "dead_seeds": [], "learned": 0}

    entries = luma.fetch_discover()
    stats["discover"] = len(entries)
    by_id = {e["event"]["api_id"]: e for e in entries if e.get("event", {}).get("api_id")}

    discover_cals: list[str] = []
    seen_cal: set[str] = set()
    for e in by_id.values():
        e["_from_discover"] = True  # SF-scoped by Luma itself; trust its geography
        cid = e.get("calendar_api_id") or (e.get("event") or {}).get("calendar_api_id")
        if cid and cid not in seen_cal:
            seen_cal.add(cid)
            discover_cals.append(cid)

    # Seeds first (and track the dead ones so the list can't rot silently again),
    # then learned, then featured, then discover -- the budget cuts from the back.
    ordered: list[str] = []
    added: set[str] = set()

    def _push(cid: str | None) -> None:
        if cid and cid not in added:
            added.add(cid)
            ordered.append(cid)

    for slug in SEED_CALENDAR_SLUGS:
        cid = _resolve_slug(slug)
        if cid:
            _push(cid)
        else:
            stats["dead_seeds"].append(slug)

    learned = _load_learned()
    for cid in learned:
        _push(cid)
    for cid in _featured_calendar_ids():
        _push(cid)
    for cid in discover_cals:
        _push(cid)

    if stats["dead_seeds"]:
        log(f"  luma: {len(stats['dead_seeds'])} seed slugs failed to resolve: "
            + ", ".join(stats["dead_seeds"]))

    log(f"  luma: {len(entries)} from discover, crawling "
        f"{min(len(ordered), MAX_CALENDARS)} calendars "
        f"({len(learned)} learned)")
    for cid in ordered[:MAX_CALENDARS]:
        try:
            items = _calendar_items(cid)
        except Exception:  # noqa: BLE001 - one bad calendar must not kill the crawl
            continue
        stats["calendars_crawled"] += 1
        for it in items:
            ev = it.get("event") or {}
            eid = ev.get("api_id")
            if eid and eid not in by_id:
                it["_calendar_api_id"] = cid
                by_id[eid] = it
                stats["from_calendars"] += 1

    # Self-widening: any calendar that hosted a hackathon-named event is worth
    # crawling next week even if nothing of its makes the discover feed then.
    today = datetime.now(timezone.utc).date().isoformat()
    for e in by_id.values():
        name = (e.get("event") or {}).get("name") or ""
        if not common.hackathon_name_hint(name):
            continue
        cid = (e.get("_calendar_api_id") or e.get("calendar_api_id")
               or (e.get("event") or {}).get("calendar_api_id"))
        if cid:
            entry = learned.setdefault(cid, {"example": name[:60]})
            entry["last_seen"] = today
    _save_learned(learned)
    stats["learned"] = len(learned)

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
