"""Turn a kept discover entry into a compact record (with description +
categories from the detail endpoint) for ranking and notification."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import luma

PT = ZoneInfo("America/Los_Angeles")
DESC_CHARS = 1600


def _fmt_local(iso: str | None) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PT)
    return dt.strftime("%a %b %-d, %-I:%M %p")


def _price_display(ticket_info: dict, ticket_types: list) -> str:
    if ticket_info.get("is_free"):
        return "Free"
    prices = []
    for t in ticket_types or []:
        if t.get("is_free"):
            prices.append(0)
        elif isinstance(t.get("cents"), int):
            prices.append(t["cents"])
    if prices:
        lo = min(prices)
        return "Free" if lo == 0 else f"${lo/100:.0f}+" if len(set(prices)) > 1 else f"${lo/100:.0f}"
    if ticket_info.get("require_approval"):
        return "Free (approval)"
    return "Paid"


def enrich(entry: dict) -> dict:
    ev = entry.get("event", {})
    eid = ev.get("api_id")
    detail = {}
    try:
        detail = luma.fetch_detail(eid)
    except Exception:  # noqa: BLE001 - degrade gracefully to list data
        detail = {}

    desc = luma.flatten_description(detail.get("description_mirror"))[:DESC_CHARS]
    cats = [c.get("name") for c in (detail.get("categories") or []) if c.get("name")]
    hosts = [h.get("name") for h in (detail.get("hosts") or entry.get("hosts") or []) if h.get("name")]
    geo = ev.get("geo_address_info") or {}
    ti = entry.get("ticket_info") or {}

    return {
        "event_id": eid,
        "name": ev.get("name"),
        "url": luma.public_url(ev.get("url")),
        "start_at": ev.get("start_at"),
        "end_at": ev.get("end_at"),
        "when_local": _fmt_local(ev.get("start_at")),
        "timezone": ev.get("timezone"),
        "address": geo.get("address"),
        "city_state": geo.get("city_state"),
        "address_hidden": (ev.get("geo_address_visibility") not in (None, "public"))
        or not geo.get("address"),
        "cover_url": ev.get("cover_url"),
        "guest_count": entry.get("guest_count"),
        "is_free": bool(ti.get("is_free")),
        "price_display": _price_display(ti, detail.get("ticket_types") or []),
        "is_sold_out": bool(ti.get("is_sold_out")),
        "is_near_capacity": bool(ti.get("is_near_capacity")),
        "spots_remaining": ti.get("spots_remaining"),
        "waitlist_active": bool(entry.get("waitlist_active")),
        "categories": cats,
        "hosts": hosts[:4],
        "description": desc,
    }
