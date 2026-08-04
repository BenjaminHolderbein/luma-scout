"""AGI House source.

The archetypal announce-on-Discord/X host: their hackathons -- renamed "X Build
Day / Build Weekend" since 2025 -- mostly never reach Luma, and the old
`agihouse` Luma seed calendar resolves but lists zero future events.
app.agihouse.org is a SPA over an open API that returns every public event
with an explicit `type` field ("hackathon"), which beats any name heuristic.

Caveat: the endpoint is an opaque AWS API-Gateway hostname that could rotate on
their next deploy. If it does, this module raises, sources.collect() marks the
source failed, and the report says so -- the desired loud failure.
"""
from __future__ import annotations

from . import common

API = "https://jtwthn6xog.execute-api.us-east-1.amazonaws.com/events"


def collect(log=lambda _m: None) -> list[dict]:
    events = common.http_json(API)
    if isinstance(events, dict):
        events = events.get("events") or []

    out: list[dict] = []
    for e in events:
        if e.get("privacy") not in (None, "public"):
            continue
        if e.get("status") not in (None, "published"):
            continue
        if e.get("dateTbd"):
            continue
        loc = e.get("location") or {}
        if loc.get("isVirtual"):
            continue
        title = (e.get("title") or "").strip()
        slug = e.get("slug")
        if not title or not slug:
            continue
        where = common.sf_match(loc.get("address"), loc.get("city"), loc.get("name"))
        if not where:
            continue
        etype = (e.get("type") or "").strip().lower()
        is_hack = etype == "hackathon" or common.hackathon_name_hint(title)
        start = e.get("startTime")
        confirmed = e.get("confirmedCount") or 0
        out.append(common.blank_record(
            event_id=f"agihouse-{slug}",
            source="agihouse",
            name=title,
            url=f"https://app.agihouse.org/events/{slug}",
            start_at=start,
            end_at=e.get("endTime"),
            when_local=common.fmt_local(start),
            address=", ".join(x for x in (loc.get("name"), loc.get("address"),
                                          loc.get("city")) if x),
            city_state=loc.get("city"),
            guest_count=confirmed or None,
            # AGI House events are application-gated, not ticketed.
            is_free=True,
            price_display="Free (application)",
            hosts=["AGI House"],
            description=(f"AGI House {etype or 'event'}."
                         + (f" {confirmed} confirmed." if confirmed else "")),
            sf_proximity=where,
            forced_tier="hackathon" if is_hack else None,
        ))
    log(f"  agihouse: {len(events)} listed -> {len(out)} public in-person in the Bay")
    return out
