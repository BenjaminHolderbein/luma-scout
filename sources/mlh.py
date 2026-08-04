"""MLH source -- the canonical registry for student flagship hackathons
(Cal Hacks, SF Hacks class), which are announced here months out and often skip
Devpost and Luma entirely.

No API and no JSON-LD, but each season page embeds the full event list as
consecutive JSON objects in the HTML; find each object start and raw_decode it.
That extraction is the most fragile pattern of any source here, so a season
page that stops yielding events degrades loudly via sources.collect()'s
zero-count check. MLH seasons straddle calendar years (the 2027 season starts
fall 2026), so both the current and next year's pages are fetched.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import common

URL = "https://mlh.io/seasons/{year}/events"
_MARK = '{"id":"01'


def _embedded_events(html: str) -> list[dict]:
    dec = json.JSONDecoder()
    out, i = [], 0
    while True:
        i = html.find(_MARK, i)
        if i == -1:
            break
        try:
            obj, span = dec.raw_decode(html[i:i + 6000])
        except ValueError:
            i += len(_MARK)
            continue
        if isinstance(obj, dict) and obj.get("name") and obj.get("startsAt"):
            out.append(obj)
            i += span
        else:
            i += len(_MARK)
    return out


def collect(log=lambda _m: None) -> list[dict]:
    year = datetime.now(timezone.utc).year
    events: dict[str, dict] = {}
    fetched = 0
    for season in (year, year + 1):
        try:
            html = common.http_get(URL.format(year=season)).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001 - next season's page may not exist yet
            continue
        fetched += 1
        for e in _embedded_events(html):
            events.setdefault(e.get("id") or e["name"], e)
    if not fetched:
        raise RuntimeError("no MLH season page could be fetched")

    def _text(v) -> str | None:
        # older season pages embed location as a dict; current ones as a string
        if isinstance(v, dict):
            v = ", ".join(x for x in v.values() if isinstance(x, str))
        return v if isinstance(v, str) and v else None

    out: list[dict] = []
    for e in events.values():
        fmt = (e.get("formatType") or "").lower()
        if fmt == "digital":
            continue
        loc, venue = _text(e.get("location")), _text(e.get("venueAddress"))
        where = common.sf_match(loc, venue)
        if not where:
            continue
        start = e.get("startsAt")
        rel = e.get("url") or ""
        out.append(common.blank_record(
            event_id=f"mlh-{e.get('id') or e.get('slug')}",
            source="mlh",
            name=e["name"].strip(),
            url=e.get("websiteUrl")
                or (f"https://mlh.io{rel}" if rel.startswith("/") else rel)
                or URL.format(year=year + 1),
            start_at=start,
            end_at=e.get("endsAt"),
            when_local=common.fmt_local(start),
            address=venue,
            city_state=loc,
            is_free=True,
            price_display="Free",
            description=f"MLH {e.get('formatType') or ''} student hackathon "
                        f"({loc or 'location TBA'}).",
            sf_proximity=where,
            forced_tier="hackathon",
        ))
    log(f"  mlh: {len(events)} season events scanned -> {len(out)} in the Bay")
    return out
