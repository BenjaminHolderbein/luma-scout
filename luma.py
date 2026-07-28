"""Luma discover + event-detail client. Stdlib only."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

API = "https://api.luma.com"
SF_PLACE_ID = "discplace-BDj7GNbGlsF7Cka"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _get(url: str, tries: int = 3) -> dict:
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 - network flakiness, retry
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}\n{last}")


def fetch_discover(place_id: str = SF_PLACE_ID, max_events: int = 300) -> list[dict]:
    """Paginate the discover feed; return raw entries (curated ~71 for SF)."""
    entries: list[dict] = []
    cursor = None
    while len(entries) < max_events:
        q = {"discover_place_api_id": place_id, "pagination_limit": 50}
        if cursor:
            q["pagination_cursor"] = cursor
        data = _get(f"{API}/discover/get-paginated-events?" + urllib.parse.urlencode(q))
        entries.extend(data.get("entries", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return entries


def fetch_detail(event_api_id: str) -> dict:
    """Full event detail (has description_mirror + categories + ticket_types)."""
    return _get(f"{API}/event/get?event_api_id={urllib.parse.quote(event_api_id)}")


def flatten_description(description_mirror) -> str:
    """Flatten Luma's ProseMirror description JSON into plain text."""
    def walk(node) -> str:
        if isinstance(node, dict):
            out = node.get("text", "") or ""
            for child in node.get("content", []) or []:
                out += " " + walk(child)
            return out
        if isinstance(node, list):
            return " ".join(walk(n) for n in node)
        return ""

    return " ".join(walk(description_mirror).split())


def public_url(slug: str) -> str:
    return f"https://luma.com/{slug}" if slug else "https://luma.com"
