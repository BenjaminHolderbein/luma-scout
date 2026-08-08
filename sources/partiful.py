"""Partiful source.

Partiful grew a public Discover feed in 2025-26 (partiful.com/explore/sf), and
behind the client-rendered page sit Firebase callables on api.partiful.com that
answer *anonymously*: `getDiscoverFeed` (the main feed) and
`getDiscoverSections`/`getDiscoverSection` (curated carousels like "Meet New
People!"). Records are rich -- full description, structured address with
neighborhood, going/interested counts -- and the inventory (street fairs, art
walks, free-food pop-ups, social mixers) overlaps none of the other sources, so
everything here is net-new tier-2/3 recall. It contributes nothing to tier 1:
the SF feed has never shown a hackathon.

Hard ceiling, verified empirically (2026-08): feed cursor pagination returns
FAILED_PRECONDITION for anonymous callers -- even from the page's own origin --
and anonymous Firebase signup is disabled, so what's reachable is exactly what
a logged-out visitor sees: the first feed page (20, server-capped whatever
maxResults says) plus the full section carousels, ~50 unique events of the
~100 Partiful counts for SF. That's Partiful's own curation choosing the half
we get, which is the better half.

No price field anywhere; cost lives in the description text and the ranker
reads it there, like it already does for other sources.
"""
from __future__ import annotations

import json

from . import common

API = "https://api.partiful.com/{fn}"
REGION = "SF"
# The server rejects calls that don't state which layouts the client renders.
FEED_STYLES = ["rows"]
SECTION_STYLES = ["carousel-small", "carousel-medium", "carousel-large", "rows"]


def _call(fn: str, params: dict, paging: dict | None = None) -> dict:
    body: dict = {"params": params}
    if paging:
        body["paging"] = paging
    raw = common.http_get(
        API.format(fn=fn),
        data=json.dumps({"data": body}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(raw).get("result", {}).get("data") or {}


def _to_record(e: dict) -> dict | None:
    name = (e.get("title") or "").strip()
    eid = e.get("id")
    if not name or not eid:
        return None
    if e.get("isPublic") is False or e.get("status") not in (None, "PUBLISHED"):
        return None

    loc = e.get("locationInfo") or {}
    lines = loc.get("displayAddressLines") or (
        (loc.get("mapsInfo") or {}).get("addressLines")) or []
    address = ", ".join(lines[:1] + ([loc["neighborhood"]] if loc.get("neighborhood") else []))
    city_state = (lines[1] if len(lines) > 1 else None) or (
        (loc.get("mapsInfo") or {}).get("approximateLocation"))

    start = e.get("startDate")
    desc = " ".join((e.get("description") or "").split())
    return common.blank_record(
        event_id=f"pf-{eid}",
        source="partiful",
        name=name,
        url=f"https://partiful.com/e/{eid}",
        start_at=start,
        end_at=e.get("endDate"),
        when_local=common.fmt_local(start),
        address=address or None,
        city_state=city_state,
        address_hidden=not lines,
        guest_count=e.get("goingGuestCount"),
        description=desc[:1200],
        sf_proximity=common.sf_match(address, city_state),
    )


def collect(log=lambda _m: None) -> list[dict]:
    events: dict[str, dict] = {}

    feed = _call("getDiscoverFeed",
                 {"region": REGION, "tagId": "DISCOVER_HOME",
                  "allowedFeedPresentationStyles": FEED_STYLES},
                 {"maxResults": 20})
    for item in feed.get("items") or []:
        e = item.get("event") or {}
        if e.get("id"):
            events[e["id"]] = e

    # Section ids rotate with Partiful's curation ("sf-arts" today, who knows
    # next quarter), so enumerate them fresh each run instead of hardcoding.
    # The listing truncates each section's items; the per-section call doesn't.
    listing = _call("getDiscoverSections",
                    {"region": REGION, "tagId": "DISCOVER_HOME",
                     "allowedSectionPresentationStyles": SECTION_STYLES},
                    {"maxResults": 100})
    section_ids = [s["id"] for s in listing.get("sections") or [] if s.get("id")]
    # The trending carousel is a distinct surface the listing never includes.
    section_ids.append(f"{REGION.lower()}-dynamic-trending-events")
    for sid in section_ids:
        sec = _call("getDiscoverSection", {"sectionId": sid})
        for item in (sec.get("section") or sec).get("items") or []:
            e = item.get("event") or {}
            if e.get("id"):
                events.setdefault(e["id"], e)

    out = [r for r in (_to_record(e) for e in events.values()) if r]
    log(f"  partiful: {len(events)} in discover feed+sections -> {len(out)} usable")
    return out
