"""Devpost source -- hackathons only, which makes it priority-1 for Ben.

Devpost has a real JSON API. The whole in-person upcoming/open set worldwide is
only ~80 hackathons, so we page through all of it and filter to the Bay locally
rather than trusting their free-text location search (which returns 2 results
for "san francisco" and misses the rest).
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime

from . import common

API = "https://devpost.com/api/hackathons"
HEADERS = {"Accept": "application/json", "Referer": "https://devpost.com/hackathons"}
MAX_PAGES = 15

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_TOKEN = re.compile(r"([A-Za-z]{3})[a-z]*\s+(\d{1,2})")
_YEAR = re.compile(r"(\d{4})")
_TAGS = re.compile(r"<[^>]+>")


def _parse_period(text: str | None) -> tuple[str | None, str | None]:
    """'Jul 23 - Aug 25, 2026' / 'Sep 26 - 27, 2026' -> (start_iso, end_iso).

    Devpost only publishes the submission period, not a start time, so both ends
    are dated at local midnight and the report labels them as a date range.
    """
    if not text:
        return None, None
    years = _YEAR.findall(text)
    if not years:
        return None, None
    end_year = int(years[-1])
    toks = _DATE_TOKEN.findall(text)
    if not toks:
        return None, None

    def iso(mon: str, day: str, year: int) -> str | None:
        m = _MONTHS.get(mon.lower()[:3])
        if not m:
            return None
        try:
            return datetime(year, m, int(day)).replace(tzinfo=common.PT).isoformat()
        except ValueError:
            return None

    if len(toks) == 1:  # 'Sep 26 - 27, 2026' style tail, or a single date
        start = iso(toks[0][0], toks[0][1], end_year)
        return start, start

    smon, sday = toks[0]
    emon, eday = toks[-1]
    start_year = int(years[0]) if len(years) > 1 else end_year
    # 'Dec 30 - Jan 05, 2027' with one year: the start belongs to the prior year
    if len(years) == 1 and _MONTHS.get(smon.lower()[:3], 0) > _MONTHS.get(emon.lower()[:3], 0):
        start_year = end_year - 1
    return iso(smon, sday, start_year), iso(emon, eday, end_year)


def _prize(raw: str | None) -> str | None:
    if not raw:
        return None
    txt = _TAGS.sub("", raw).strip()
    return txt or None


def collect(log=lambda _m: None) -> list[dict]:
    seen_ids: set[int] = set()
    out: list[dict] = []
    scanned = 0

    for page in range(1, MAX_PAGES + 1):
        q = [("challenge_type[]", "in-person"), ("status[]", "upcoming"),
             ("status[]", "open"), ("page", str(page))]
        data = common.http_json(f"{API}?" + urllib.parse.urlencode(q), headers=HEADERS)
        hacks = data.get("hackathons") or []
        if not hacks:
            break
        scanned += len(hacks)
        for h in hacks:
            if h.get("id") in seen_ids:
                continue
            seen_ids.add(h.get("id"))
            loc = (h.get("displayed_location") or {}).get("location")
            where = common.sf_match(loc, h.get("organization_name"))
            if not where:
                continue
            start, end = _parse_period(h.get("submission_period_dates"))
            prize = _prize(h.get("prize_amount"))
            bits = [b for b in (
                f"Prizes: {prize}" if prize else None,
                f"{h.get('registrations_count')} registered" if h.get("registrations_count") else None,
                "Invite only" if h.get("invite_only") else None,
                "Themes: " + ", ".join(t["name"] for t in h.get("themes") or [] if t.get("name"))
                if h.get("themes") else None,
                f"Submission period: {h.get('submission_period_dates')}" if h.get("submission_period_dates") else None,
            ) if b]
            out.append(common.blank_record(
                event_id=f"devpost-{h.get('id')}",
                source="devpost",
                name=h.get("title", "").strip(),
                url=h.get("url"),
                start_at=start,
                end_at=end,
                when_local=common.fmt_local(start),
                address=loc,
                city_state=loc,
                guest_count=h.get("registrations_count"),
                is_free=True,          # Devpost hackathons are effectively free to enter
                price_display="Free",
                categories=[t["name"] for t in h.get("themes") or [] if t.get("name")],
                hosts=[h["organization_name"]] if h.get("organization_name") else [],
                description=" · ".join(bits),
                sf_proximity=where,
                forced_tier="hackathon",   # a Devpost listing IS a hackathon
            ))
        total = (data.get("meta") or {}).get("total_count")
        if total and scanned >= total:
            break

    log(f"  devpost: {scanned} in-person hackathons scanned -> {len(out)} in the Bay")
    return out
