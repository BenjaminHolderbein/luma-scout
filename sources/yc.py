"""Y Combinator events source.

ycombinator.com/events is a client-rendered Inertia.js app -- the HTML body is
literally just "Y Combinator", so there is no JSON-LD and no server-rendered
list to scrape. The page data lives in the `data-page` attribute on the root
div, which is clean structured JSON. (Requesting it with `X-Inertia: true`
returns 409 on a version mismatch, so parse the attribute instead.)

Worth its own module rather than leaning on the Luma calendar crawl: YC tags
events with an explicit `event_type` of "hackathon", and YC-hosted hackathons
are frequently not listed on Luma at all. The Luma calendar at luma.com/ycombinator
resolves but has no future items, so it is not a substitute.
"""
from __future__ import annotations

import html as htmllib
import json
import re

from . import common

INDEX = "https://www.ycombinator.com/events"
DETAIL = "https://www.ycombinator.com/events/{slug}"
_DATA_PAGE = re.compile(r'data-page="([^"]+)"')
_TAGS = re.compile(r"<[^>]+>")


def _page_props(page_html: str) -> dict:
    m = _DATA_PAGE.search(page_html)
    if not m:
        raise RuntimeError("no Inertia data-page attribute (page structure changed)")
    return json.loads(htmllib.unescape(m.group(1))).get("props") or {}


def _clean(text: str | None, limit: int = 1600) -> str:
    if not text:
        return ""
    txt = htmllib.unescape(_TAGS.sub(" ", text))
    txt = txt.replace("\\", " ")  # YC stores markdown hard-breaks as stray backslashes
    return " ".join(txt.split())[:limit]


def _detail(slug: str) -> dict:
    """Full event record, for the description. Missing/private ones degrade to {}."""
    try:
        page = common.http_get(DETAIL.format(slug=slug)).decode("utf-8", "ignore")
        return _page_props(page).get("meetup") or {}
    except common.EgressBlocked:
        raise
    except Exception:  # noqa: BLE001 - a missing detail page is not fatal
        return {}


def collect(log=lambda _m: None) -> list[dict]:
    page = common.http_get(INDEX).decode("utf-8", "ignore")
    events = _page_props(page).get("events") or []

    out: list[dict] = []
    for e in events:
        where = common.sf_match(e.get("city"), e.get("public_location"))
        if not where:
            continue
        slug = e.get("slug")
        d = _detail(slug) if slug else {}
        if d.get("cancelled"):
            continue

        etype = (d.get("event_type") or e.get("event_type_label") or "").strip().lower()
        bits = [b for b in (
            _clean(d.get("description")),
            f"Capacity {d['capacity']}." if d.get("capacity") else None,
            f"Applications close {d['application_closes_at'][:10]}."
            if d.get("application_closes_at") else None,
            "US citizens only." if d.get("us_citizen_only") else None,
        ) if b]

        start = e.get("starts_at") or d.get("starts_at")
        out.append(common.blank_record(
            event_id=f"yc-{e.get('id')}",
            source="yc",
            name=(e.get("title") or d.get("title") or "").strip(),
            url=DETAIL.format(slug=slug) if slug else INDEX,
            start_at=start,
            end_at=e.get("ends_at") or d.get("ends_at"),
            when_local=common.fmt_local(start),
            address=e.get("public_location"),
            city_state=e.get("city"),
            guest_count=d.get("capacity"),
            # YC events are application-based, never ticketed.
            is_free=True,
            price_display="Free (application)",
            categories=[e["event_type_label"]] if e.get("event_type_label") else [],
            hosts=["Y Combinator"],
            description=" ".join(bits),
            sf_proximity=where,
            forced_tier="hackathon" if etype == "hackathon" else None,
            # Real deadlines, which the report surfaces as their own line -- YC
            # is one of the few sources that publishes them.
            application_closes_at=d.get("application_closes_at"),
            registration_closes_at=d.get("registration_closes_at"),
        ))

    log(f"  yc: {len(events)} listed -> {len(out)} in the Bay")
    return out
