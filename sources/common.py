"""Shared plumbing for every event source: HTTP, the canonical record shape,
SF geography, and cross-source dedup.

Every source module exposes `collect(now, horizon) -> list[record]` and raises
nothing: `sources.collect()` isolates failures per source so one broken scraper
degrades the report instead of killing the run.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Richest data first. When the same event shows up on two platforms, the record
# from the higher-priority source wins and the others land in `also_on`.
SOURCE_PRIORITY = ["yc", "luma", "devpost", "eventbrite", "meetup"]


# Minimum seconds between requests to the same host. Eventbrite starts serving
# 429s well before you would expect it to, and a weekly job has no reason to be
# in a hurry -- politeness here is what keeps the source alive.
HOST_DELAY = {
    "www.eventbrite.com": 2.5,
    "www.meetup.com": 2.0,
    "devpost.com": 1.0,
    "www.ycombinator.com": 1.0,
    "api.luma.com": 0.15,
}
DEFAULT_DELAY = 0.5
_last_hit: dict[str, float] = {}


def _throttle(host: str) -> None:
    gap = HOST_DELAY.get(host, DEFAULT_DELAY)
    wait = gap - (time.monotonic() - _last_hit.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()


class EgressBlocked(RuntimeError):
    """The sandbox's egress proxy refused to open a tunnel to this host.

    Cloud routines run behind a policy-enforcing proxy that answers 403 to
    CONNECT for hosts outside the environment's allowlist. That is a network
    policy decision, not a transient error and not something headers or retries
    can fix -- so fail fast and loudly instead of burning the retry budget and
    reporting an empty result that looks like 'no events found'.
    """


def _is_egress_block(err: Exception) -> bool:
    text = str(err)
    return "Tunnel connection failed" in text or "CONNECT tunnel failed" in text


def http_get(url: str, *, headers: dict | None = None, tries: int = 3,
             timeout: int = 30) -> bytes:
    """GET with a browser UA, per-host throttling, and backoff."""
    hdrs = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    hdrs.update(headers or {})
    host = urllib.parse.urlsplit(url).netloc
    last: Exception | None = None
    for attempt in range(tries):
        _throttle(host)
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - network flakiness, retry
            last = e
            if _is_egress_block(e):
                raise EgressBlocked(
                    f"egress proxy refused a tunnel to {host} (403 on CONNECT). "
                    f"Add {host} to this environment's allowed domains.") from e
            if isinstance(e, urllib.error.HTTPError):
                if e.code in (400, 404):
                    break  # not transient
                if e.code == 429:
                    retry_after = e.headers.get("Retry-After") if e.headers else None
                    try:
                        delay = min(float(retry_after), 60.0)
                    except (TypeError, ValueError):
                        delay = 10.0 * (attempt + 1)
                    time.sleep(delay)
                    continue
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}\n{last}")


def http_json(url: str, **kw) -> dict:
    return json.loads(http_get(url, **kw))


# --- canonical record ------------------------------------------------------
# Keys mirror what enrich.py already produces for Luma, so notify/report/rank
# stay source-agnostic. Non-Luma sources fill what they can and leave the rest
# None; the ranker tolerates missing fields.

RECORD_KEYS = (
    "event_id", "source", "name", "url", "start_at", "end_at", "when_local",
    "address", "city_state", "address_hidden", "guest_count", "is_free",
    "price_display", "is_sold_out", "is_near_capacity", "spots_remaining",
    "waitlist_active", "categories", "hosts", "description", "also_on",
    # sf_proximity: 'sf' | 'near' | None. forced_tier: set by hackathon-only
    # sources so the ranker cannot demote a hackathon out of tier 1.
    "sf_proximity", "forced_tier",
    # Genuine registration deadlines, where a source publishes one (YC does;
    # Luma mostly does not). The report gives these their own line, because
    # "needs registering for in advance" is the thing a weekly digest hides.
    "application_closes_at", "registration_closes_at",
)


def blank_record(**kw) -> dict:
    rec = {k: None for k in RECORD_KEYS}
    rec.update({
        "categories": [], "hosts": [], "also_on": [],
        "is_free": False, "is_sold_out": False, "is_near_capacity": False,
        "waitlist_active": False, "address_hidden": False,
    })
    rec.update(kw)
    return rec


# --- JSON-LD ---------------------------------------------------------------
# Eventbrite and Meetup both ship schema.org Event objects in <script
# type="application/ld+json">. Eventbrite nests them inside an ItemList, Meetup
# puts them at the top level, so walk the whole tree rather than guessing.

_LD_SCRIPT = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I)


def iter_jsonld_events(html: str):
    """Yield every schema.org Event dict embedded anywhere in the page."""
    for raw in _LD_SCRIPT.findall(html):
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                t = node.get("@type")
                types = t if isinstance(t, list) else [t]
                if "Event" in types or any(
                        isinstance(x, str) and x.endswith("Event") for x in types):
                    yield node
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)


def ld_location(ev: dict) -> tuple[str | None, str | None]:
    """(street-ish address, 'City, ST') from a schema.org Event."""
    loc = ev.get("location")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return (loc if isinstance(loc, str) else None), None
    addr = loc.get("address")
    if isinstance(addr, list):
        addr = addr[0] if addr else None
    if isinstance(addr, str):
        return addr, None
    if not isinstance(addr, dict):
        return loc.get("name"), None
    street = " ".join(x for x in (loc.get("name"), addr.get("streetAddress")) if x) or None
    city = ", ".join(x for x in (addr.get("addressLocality"), addr.get("addressRegion")) if x) or None
    return street, city


def ld_is_online(ev: dict) -> bool:
    """Ben wants in-person only. Luma flags this cleanly; for JSON-LD we check
    the attendance mode, a VirtualLocation, and finally the title."""
    mode = ev.get("eventAttendanceMode")
    if isinstance(mode, str) and "onlineevent" in mode.lower().replace("/", ""):
        return True
    loc = ev.get("location")
    for node in (loc if isinstance(loc, list) else [loc]):
        if isinstance(node, dict) and node.get("@type") == "VirtualLocation":
            return True
    return bool(re.search(r"\b(virtual|online|webinar|livestream|zoom)\b",
                          ev.get("name") or "", re.I))


def ld_is_free(ev: dict) -> tuple[bool, str | None]:
    offers = ev.get("offers")
    if isinstance(offers, dict):
        offers = [offers]
    if not isinstance(offers, list) or not offers:
        return False, None
    prices = []
    for o in offers:
        if not isinstance(o, dict):
            continue
        p = o.get("price", o.get("lowPrice"))
        try:
            prices.append(float(str(p).replace("$", "").replace(",", "")))
        except (TypeError, ValueError):
            continue
    if not prices:
        return False, None
    lo = min(prices)
    if lo == 0:
        return True, "Free"
    return False, f"${lo:.0f}" + ("+" if len(set(prices)) > 1 else "")


def fmt_local(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PT)
    return dt.astimezone(PT).strftime("%a %b %-d, %-I:%M %p")


def parse_dt(iso: str | None) -> datetime | None:
    """Parse an ISO-ish timestamp; naive values are assumed Pacific."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(iso[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt.replace(tzinfo=PT) if dt.tzinfo is None else dt


# --- geography -------------------------------------------------------------
# Ben asked for San Francisco. SF proper is the target; the near-Bay towns are
# included only for hackathons (priority 1 — a miss costs more than a
# false positive) and are tagged so the report can show where they actually are.

SF_TERMS = ("san francisco", "sf,", " sf ", "soma", "mission district")
NEAR_BAY_TERMS = (
    "bay area", "oakland", "berkeley", "palo alto", "mountain view",
    "menlo park", "san jose", "santa clara", "sunnyvale", "redwood city",
    "south san francisco", "emeryville", "burlingame", "san mateo", "cupertino",
    "silicon valley", "stanford",
)


def sf_match(*fields: str | None) -> str | None:
    """Return 'sf', 'near' or None for a set of location-ish strings."""
    blob = " ".join(f.lower() for f in fields if f)
    if not blob:
        return None
    padded = f" {blob} "
    if any(t in padded for t in SF_TERMS):
        return "sf"
    if any(t in padded for t in NEAR_BAY_TERMS):
        return "near"
    return None


# --- dedup -----------------------------------------------------------------

_NOISE = re.compile(
    r"\b(the|a|an|and|of|for|with|at|in|on|by|presented|hosted|featuring"
    r"|hackathon|hack|event|meetup|sf|san francisco|bay area|2026|2027)\b")
_NONWORD = re.compile(r"[^a-z0-9 ]+")


def title_key(name: str | None) -> str:
    """Aggressively normalized title, so 'AI Hackathon SF 2026' and
    'The A.I. Hackathon (San Francisco)' collapse to the same key."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = _NONWORD.sub(" ", s.lower())
    s = _NOISE.sub(" ", s)
    return " ".join(s.split())


def dedup_key(rec: dict) -> tuple:
    dt = parse_dt(rec.get("start_at"))
    day = dt.astimezone(PT).date().isoformat() if dt else ""
    key = title_key(rec.get("name"))
    return (key, day)


def merge(records: list[dict]) -> list[dict]:
    """Collapse cross-source duplicates, keeping the richest record and noting
    the other platforms it also appeared on."""
    rank = {s: i for i, s in enumerate(SOURCE_PRIORITY)}
    best: dict[tuple, dict] = {}
    for rec in records:
        k = dedup_key(rec)
        if not k[0]:  # unusable title -> never merge, always keep
            best[("_uniq", rec.get("event_id") or id(rec))] = rec
            continue
        cur = best.get(k)
        if cur is None:
            best[k] = rec
            continue
        winner, loser = (rec, cur) if rank.get(rec["source"], 9) < rank.get(cur["source"], 9) else (cur, rec)
        also = set(winner.get("also_on") or []) | set(loser.get("also_on") or [])
        also.add(loser["source"])
        also.discard(winner["source"])
        winner["also_on"] = sorted(also)
        # a loser sometimes knows something the winner doesn't
        for field in ("description", "guest_count", "price_display", "address"):
            if not winner.get(field) and loser.get(field):
                winner[field] = loser[field]
        best[k] = winner
    return list(best.values())
