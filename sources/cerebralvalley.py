"""Cerebral Valley source.

Their /events page is client-rendered, but behind it sits a public JSON API of
curated Bay-Area AI/tech events -- exactly tiers 1-2, with near-zero junk. Most
records carry the underlying luma.com URL, which makes this double as a
recall-repair layer for the Luma crawl: an event whose host calendar the crawl
never found still arrives here, and cross-source dedup collapses the overlap
(SOURCE_PRIORITY puts CV below luma so the Luma-native record wins).

API quirk, verified empirically: `startDateTime`/`endDateTime` are UTC but
carry no timezone marker ("2026-08-04 00:45:00"), and the query's
startDateTime parameter must be strict ISO with a trailing Z.
"""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

from . import common

API = ("https://api.cerebralvalley.ai/v1/public/event/pull"
       "?approved=true&startDateTime={start}&locations=BAY_AREA"
       "&limit=50&offset={offset}")
MAX_PAGES = 6


def _iso_utc(naive: str | None) -> str | None:
    if not naive:
        return None
    try:
        dt = datetime.strptime(naive[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat()


def collect(log=lambda _m: None) -> list[dict]:
    start = urllib.parse.quote(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    out: list[dict] = []
    total = None
    for page in range(MAX_PAGES):
        data = common.http_json(API.format(start=start, offset=page * 50))
        events = data.get("events") or []
        total = data.get("totalCount", total)
        if not events:
            break
        for e in events:
            name = (e.get("name") or "").strip()
            if not name:
                continue
            where = common.sf_match(e.get("venue"), e.get("location"))
            if not where:
                continue
            s = _iso_utc(e.get("startDateTime"))
            desc = (e.get("descriptionSummary") or e.get("description") or "")
            out.append(common.blank_record(
                event_id=f"cv-{e.get('id')}",
                source="cerebralvalley",
                name=name,
                url=e.get("url") or "https://cerebralvalley.ai/events",
                start_at=s,
                end_at=_iso_utc(e.get("endDateTime")),
                when_local=common.fmt_local(s),
                address=e.get("venue"),
                city_state=e.get("location"),
                description=" ".join(desc.split())[:1200],
                sf_proximity=where,
            ))
        if len(events) < 50:
            break
    log(f"  cerebralvalley: {total} listed -> {len(out)} located in the Bay")
    return out
