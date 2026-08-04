"""Hack Club source -- student (high-school) hackathons, which list here and
often nowhere else: Hyphen-Hacks (SF) and FireHacks (Mountain View) appear on
this API and on none of the other sources. Everything on it is by definition a
hackathon, so records are force-tiered; eligibility (many are teens-only) is
usually in the name or site, and the ranker's score can reflect that.
"""
from __future__ import annotations

from . import common

API = "https://hackathons.hackclub.com/api/events/upcoming"


def collect(log=lambda _m: None) -> list[dict]:
    events = common.http_json(API)

    out: list[dict] = []
    for e in events:
        if e.get("virtual"):
            continue
        country = (e.get("country") or "").strip().upper()
        if country and country not in ("US", "USA", "UNITED STATES"):
            continue
        name = (e.get("name") or "").strip()
        if not name:
            continue
        city, st = (e.get("city") or "").strip(), (e.get("state") or "").strip()
        city_state = ", ".join(x for x in (city, st) if x)
        where = common.sf_match(city_state, city)
        if not where:
            continue
        start = e.get("start")
        out.append(common.blank_record(
            event_id=f"hackclub-{e.get('id')}",
            source="hackclub",
            name=name,
            url=e.get("website"),
            start_at=start,
            end_at=e.get("end"),
            when_local=common.fmt_local(start),
            city_state=city_state,
            is_free=True,
            price_display="Free",
            description=f"Student hackathon in {city_state or 'the Bay'}, "
                        "listed on Hack Club. Often high-school-aged only -- "
                        "check eligibility on the site.",
            sf_proximity=where,
            forced_tier="hackathon",
        ))
    log(f"  hackclub: {len(events)} upcoming -> {len(out)} in-person in the Bay")
    return out
