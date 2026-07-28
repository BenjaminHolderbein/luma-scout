"""Build and send the daily ntfy roundup: one notification, ranked list of picks
grouped by tier, each line with a tappable Luma link.

Plain text only (the ntfy iOS app doesn't render markdown). Published via ntfy's
JSON API so the title/body carry full UTF-8 (emoji), with no attachment."""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")

TIER_DISPLAY = {
    "hackathon": "🛠️ Hackathons",
    "food": "🍕 Free food & drink",
    "networking": "🤝 Networking",
    "seminar": "🎓 Seminars",
}
TIER_ORDER = {"hackathon": 0, "food": 1, "networking": 2, "seminar": 3}
URGENCY_EMOJI = {"filling": "⚡", "waitlist": "⏳", "sold_out": "🚫"}


def _short_when(rec: dict) -> str:
    iso = rec.get("start_at")
    if not iso:
        return rec.get("when_local", "")
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PT)
    return dt.strftime("%a %-I:%M%p").replace(":00", "").replace("AM", "am").replace("PM", "pm")


def _line(rec: dict, ranked: dict) -> str:
    where = rec.get("address") or rec.get("city_state") or "SF"
    if rec.get("address_hidden"):
        where = "SF (addr after RSVP)"
    bits = [_short_when(rec), where]
    price = rec.get("price_display")
    if price and price != "Free":
        bits.append(price)
    urg = URGENCY_EMOJI.get(ranked.get("urgency"))
    if urg:
        bits.append(urg)
    hook = ranked.get("hook")
    head = rec.get("name", "Event")
    line = f"• {head} — {' · '.join(b for b in bits if b)}"
    if hook and hook.lower() not in head.lower():
        line += f"\n   {hook}"
    line += f"\n   {rec['url']}"
    return line


def build_roundup(selected: list[tuple[dict, dict]], date: datetime | None = None,
                  extra_count: int = 0) -> tuple[str, str, list[str]]:
    """selected = ordered [(record, ranked), ...]. Returns (title, message, tags)."""
    date = date or datetime.now(PT)
    n = len(selected)
    title = f"🗓️ {n} SF pick{'s' if n != 1 else ''} · {date.strftime('%a %b %-d')}"

    # group by tier, preserving the incoming (already-sorted) order within a tier
    groups: dict[str, list[tuple[dict, dict]]] = {}
    for rec, rk in selected:
        groups.setdefault(rk.get("tier", "seminar"), []).append((rec, rk))

    blocks = []
    for tier in sorted(groups, key=lambda t: TIER_ORDER.get(t, 9)):
        lines = "\n".join(_line(rec, rk) for rec, rk in groups[tier])
        blocks.append(f"{TIER_DISPLAY.get(tier, tier)}\n{lines}")
    message = "\n\n".join(blocks)
    if extra_count > 0:
        message += f"\n\n+{extra_count} more on luma.com/sf"

    tags = ["calendar"]
    return title, message, tags


def publish_roundup(title: str, message: str, tags: list[str], topic: str,
                    server: str, priority: int = 3) -> None:
    payload = {
        "topic": topic,
        "title": title,
        "message": message,
        "tags": tags,
        "priority": priority,
        # No `click`: tapping the notification body does nothing; the per-event
        # luma.com links inside the message are the only navigation.
    }
    req = urllib.request.Request(
        server.rstrip("/") + "/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def send_test(topic: str, server: str = "https://ntfy.sh") -> None:
    sample = [
        ({"name": "Built Different: Auth0 × Stripe Hackathon", "url": "https://luma.com/aaaa",
          "start_at": "2026-07-30T19:00:00.000Z", "address": "SoMa", "price_display": "Free"},
         {"tier": "hackathon", "hook": "$2k prizes + free lunch", "urgency": "none"}),
        ({"name": "YC Startup School Afterparty", "url": "https://luma.com/z9teb942",
          "start_at": "2026-07-28T01:00:00.000Z", "address": "Frontier Tower", "price_display": "Free"},
         {"tier": "food", "hook": "Free dinner, open bar + DJ", "urgency": "filling"}),
        ({"name": "AI Nerd Meet Up", "url": "https://luma.com/bbbb",
          "start_at": "2026-07-29T01:00:00.000Z", "address": "Mission", "price_display": "Free"},
         {"tier": "food", "hook": "Pizza + invite-only AI founders", "urgency": "none"}),
    ]
    title, message, tags = build_roundup(sample)
    publish_roundup("🧪 " + title, message, tags, topic, server, priority=4)
