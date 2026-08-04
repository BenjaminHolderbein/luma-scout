"""Eventbrite source (scraper).

Eventbrite retired its public search API, but the SF search pages embed every
result as schema.org JSON-LD. That markup is stable-ish but not a contract --
`sources.collect()` treats a zero-result return as a degraded source and says so
in the report rather than pretending Eventbrite had nothing on.
"""
from __future__ import annotations

import html as htmllib
import re

from . import common

BASE = "https://www.eventbrite.com/d/{city}/{q}/"

# (city, query) pairs chosen to serve Ben's three tiers, in priority order.
# The Bay-city hackathon queries exist because Eventbrite's SF pages don't
# return Oakland/Berkeley/Peninsula hackathons, and hackathons get the wider
# geography anyway; the non-hackathon tiers stay SF-proper.
# NOTE: the query does NOT determine the tier. Eventbrite pads search results
# with unrelated "you might also like" events, so a hit on the hackathon query
# proves nothing about the event itself -- sources.looks_like_hackathon() judges
# each event on its own name.
QUERIES = (
    ("ca--san-francisco", "hackathon"),
    ("ca--san-francisco", "hackathons"),
    ("ca--san-francisco", "free--hackathon"),
    ("ca--san-francisco", "ai-hackathon"),
    ("ca--oakland", "hackathon"),
    ("ca--berkeley", "hackathon"),
    ("ca--palo-alto", "hackathon"),
    ("ca--san-francisco", "free--tech-networking"),
    ("ca--san-francisco", "free--ai"),
    ("ca--san-francisco", "free--food-and-drink"),
)
PAGES_PER_QUERY = 2
_TAGS = re.compile(r"<[^>]+>")


def _clean(text: str | None, limit: int = 1200) -> str:
    if not text:
        return ""
    return " ".join(htmllib.unescape(_TAGS.sub(" ", text)).split())[:limit]


def _slug_id(url: str | None) -> str:
    if not url:
        return ""
    m = re.search(r"-(\d+)(?:\?|$)", url)
    return m.group(1) if m else url.rsplit("/", 1)[-1][:60]


def collect(log=lambda _m: None) -> list[dict]:
    out: dict[str, dict] = {}
    pages = 0
    attempted = 0
    last_error: Exception | None = None
    for city, slug in QUERIES:
        for page in range(1, PAGES_PER_QUERY + 1):
            url = BASE.format(city=city, q=slug) + (f"?page={page}" if page > 1 else "")
            attempted += 1
            try:
                page_html = common.http_get(url).decode("utf-8", "ignore")
            except common.EgressBlocked:
                raise  # a policy block is not a dead query; surface it at once
            except Exception as e:  # noqa: BLE001 - one dead query shouldn't kill the source
                last_error = e
                continue
            pages += 1
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
                where = common.sf_match(street, city, ev.get("name"))
                if not where:
                    continue
                start = ev.get("startDate")
                free, price = common.ld_is_free(ev)
                eid = f"eventbrite-{_slug_id(url_ev)}"
                if eid in out:
                    continue
                out[eid] = common.blank_record(
                    event_id=eid,
                    source="eventbrite",
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
            if found == 0:
                break  # no more result pages for this query

    if pages == 0 and attempted:
        # Every request failed. Returning [] here would be indistinguishable
        # from "Eventbrite has no SF events this week", which is how a total
        # outage once hid behind a clean-looking report.
        raise RuntimeError(
            f"all {attempted} Eventbrite requests failed; last error: {last_error}")

    log(f"  eventbrite: {pages} pages -> {len(out)} SF events")
    return list(out.values())
