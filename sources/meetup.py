"""Meetup source (scraper).

Meetup's GraphQL API needs OAuth, but the /find/ pages ship their results as
schema.org JSON-LD in the document head. Same caveat as Eventbrite: this is
markup, not a contract, so a zero return is reported as degraded.

Meetup is the weakest of the four for Ben's tiers -- lots of recurring meetups --
but it is where the standing free-pizza tech nights live.
"""
from __future__ import annotations

import html as htmllib
import re
import urllib.parse

from . import common

BASE = "https://www.meetup.com/find/"
LOCATION = "us--ca--San Francisco"

# As with Eventbrite: the query is a net, not a label. Meetup's find pages mix
# in unrelated groups, so tier is decided per-event downstream.
QUERIES = (
    "hackathon", "hack night", "artificial intelligence",
    "machine learning", "startup networking", "tech happy hour",
)
_TAGS = re.compile(r"<[^>]+>")


def _clean(text: str | None, limit: int = 1200) -> str:
    if not text:
        return ""
    return " ".join(htmllib.unescape(_TAGS.sub(" ", text)).split())[:limit]


def _event_id(url: str | None) -> str:
    if not url:
        return ""
    m = re.search(r"/events/(\d+)", url)
    return m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1][:60]


def collect(log=lambda _m: None) -> list[dict]:
    out: dict[str, dict] = {}
    ok_queries = 0
    for keywords in QUERIES:
        q = urllib.parse.urlencode({
            "keywords": keywords, "location": LOCATION, "source": "EVENTS",
        })
        try:
            page_html = common.http_get(f"{BASE}?{q}").decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            continue
        found = 0
        for ev in common.iter_jsonld_events(page_html):
            name = (ev.get("name") or "").strip()
            url_ev = ev.get("url")
            if not name or not url_ev:
                continue
            found += 1
            if common.ld_is_online(ev):
                continue
            street, city = common.ld_location(ev)
            # Meetup's LD often omits the address for online/TBD venues; the
            # search itself is SF-scoped, so an unknown location is kept as 'sf'.
            where = common.sf_match(street, city) or ("sf" if not (street or city) else None)
            if not where:
                continue
            start = ev.get("startDate")
            free, price = common.ld_is_free(ev)
            eid = f"meetup-{_event_id(url_ev)}"
            if eid in out:
                continue
            out[eid] = common.blank_record(
                event_id=eid,
                source="meetup",
                name=name,
                url=url_ev,
                start_at=start,
                end_at=ev.get("endDate"),
                when_local=common.fmt_local(start),
                address=street,
                city_state=city,
                is_free=free,
                price_display=price,
                description=_clean(ev.get("description")),
                sf_proximity=where,
                forced_tier=None,
            )
        if found:
            ok_queries += 1

    log(f"  meetup: {ok_queries}/{len(QUERIES)} queries returned -> {len(out)} SF events")
    return list(out.values())
