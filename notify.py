"""Build and send the weekly ntfy push.

A teaser, not the report: headline rarity counts plus the few highest-rated
picks, linking to the published HTML page. Plain text only (the ntfy iOS app
doesn't render markdown), published via ntfy's JSON API so the title and body
carry full UTF-8."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import rarity
from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")

TIER_DISPLAY = {
    "hackathon": "🛠️ Hackathons",
    "bigfree": "⭐ Big & free",
    "food": "🍕 Free food & drink",
}
TIER_ORDER = {"hackathon": 0, "bigfree": 1, "food": 2}


def _clip(s: str, limit: int) -> str:
    """Word-safe truncation. The model is told the char limits, but a clamp in
    code is what actually guarantees the lock screen never truncates us."""
    s = (s or "").strip()
    if len(s) <= limit:
        return s
    cut = s[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:·-—+&") + "…"


def _short_when(rec: dict) -> str:
    iso = rec.get("start_at")
    if not iso:
        return rec.get("when_local", "")
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PT)
    return dt.strftime("%a %-I:%M%p").replace(":00", "").replace("AM", "am").replace("PM", "pm")


def build_teaser(pairs: list[tuple[dict, dict]], report_url: str,
                 date: datetime | None = None,
                 model_teaser: dict | None = None) -> tuple[str, str, list[str]]:
    """The weekly push: the rarest few picks, in chronological order.

    The full list lives in the HTML report -- a plain-text notification is the
    wrong place for 30 events, and iOS truncates it anyway. This is a doorbell,
    not the report, so it leads with what the ranking actually rates highest
    rather than one item per tier.

    The title is written by the ranking model when available (`model_teaser`,
    the `_teaser` element of ranked.json) -- an email-subject-style headline
    that leads with the week's single most exciting thing. The mechanical
    rarity-count title is the fallback, so a run whose ranker skipped the
    teaser still pushes something sensible.
    """
    date = date or datetime.now(PT)
    counts: dict[str, int] = {}
    for _, rk in pairs:
        r = rarity.of(rk.get("tier"), rk.get("score"))
        counts[r] = counts.get(r, 0) + 1
    headline = ", ".join(f"{counts[n]} {n}" for n in reversed(rarity.ORDER) if counts.get(n))

    # Sized for the collapsed lock-screen chip: iOS gives the title one line
    # (~40 chars) and the body two or three, so every line is clamped, the
    # rarity brackets are gone (the tier emoji carries it), and the URL is not
    # spelled out -- tapping the notification opens the report anyway. No ntfy
    # tag either: its emoji is prepended to the title and steals title width.
    model_title = _clip((model_teaser or {}).get("headline") or "", 40)
    subline = _clip((model_teaser or {}).get("subline") or "", 70)
    if model_title:
        title = model_title
    else:
        title = (f"Week of {date.strftime('%b %-d')} — {headline}" if headline
                 else f"Week of {date.strftime('%b %-d')}")

    # top two by rarity, then shown in the order they actually happen
    best = sorted(pairs, key=lambda p: -rarity.attention(p[1].get("tier"), p[1].get("score")))[:2]
    best.sort(key=lambda p: p[0].get("start_at") or "")

    lines = []
    if subline:
        lines.append(subline)
    for rec, rk in best:
        tier_emoji = TIER_DISPLAY.get(rk.get("tier"), "").split(" ")[0]
        lines.append(f"{tier_emoji} {_clip(rec.get('name') or 'Event', 30)} · {_short_when(rec)}")
    remaining = len(pairs) - len(best)
    if remaining > 0:
        lines.append(f"+{remaining} more — tap for the full report")
    return title, "\n".join(lines), []


def publish_roundup(title: str, message: str, tags: list[str], topic: str,
                    server: str, priority: int = 3, click: str | None = None) -> None:
    payload = {
        "topic": topic,
        "title": title,
        "message": message,
        "tags": tags,
        "priority": priority,
    }
    if click:
        payload["click"] = click  # tapping the notification opens the report
    body = json.dumps(payload).encode("utf-8")

    # Retried, because one unlucky POST used to lose the entire week. The whole
    # pipeline -- ten sources, a 25-minute crawl, a ranked report -- funnels
    # into this single request, and on 2026-08-10 it raised once and the run
    # went silent with a perfectly good report already published. ntfy.sh
    # rate-limits per client IP and a cloud sandbox shares its egress address
    # with strangers, so a 429 here is somebody else's traffic, not ours.
    # 4xx other than 429 is our own bug and retrying cannot fix it.
    last = None
    for attempt in range(4):
        if attempt:
            delay = min(2 ** attempt, 8)
            if isinstance(last, urllib.error.HTTPError):
                try:  # ntfy sends Retry-After on 429; prefer its number
                    delay = max(delay, min(int(last.headers.get("Retry-After", 0)), 30))
                except (TypeError, ValueError):
                    pass
            time.sleep(delay)
        req = urllib.request.Request(
            server.rstrip("/") + "/", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read()
            return
        except urllib.error.HTTPError as e:
            last = e
            if e.code != 429 and e.code < 500:
                raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
    raise last


def send_failure(topic: str, server: str, error_text: str) -> None:
    """Dead-man's switch: a crashed run must still make a sound.

    Per-source failures degrade gracefully into the report, but if the run
    itself dies there is no report -- and a missing Monday push is far too easy
    to not notice. Priority 4 so it stands out from the weekly roundup.

    Blind spot, by construction: this needs NTFY_TOPIC and the ntfy host to
    work, which is exactly what it is trying to report on. On 2026-08-10 the
    run published a good report and went completely silent -- and whatever the
    trigger, the switch could not fire, because a missing topic disables the
    alarm and the alarm's own channel in one stroke. Anything that must survive
    that needs a different channel; the weekly routine's own completion
    notification (email + push, enabled 2026-08-10) is the real backstop."""
    publish_roundup(
        "⚠️ luma-scout run failed",
        f"{error_text}\n\nNo report this week until this is fixed — check the run logs.",
        ["warning"], topic, server, priority=4)


def send_test(topic: str, server: str = "https://ntfy.sh",
              report_url: str = "https://benjaminholderbein.github.io/luma-scout/") -> None:
    sample = [
        ({"name": "Built Different: Auth0 × Stripe Hackathon", "url": "https://luma.com/aaaa",
          "start_at": "2026-07-30T19:00:00.000Z", "address": "SoMa", "price_display": "Free"},
         {"tier": "hackathon", "hook": "$2k prizes + free lunch", "urgency": "none"}),
        ({"name": "Mistral Vibe Hackathon", "url": "https://luma.com/cccc",
          "start_at": "2026-08-23T19:00:00.000Z", "address": "SoMa", "price_display": "Free"},
         {"tier": "hackathon", "hook": "Weekend build, Mistral credits", "urgency": "none"}),
        ({"name": "YC Startup School Afterparty", "url": "https://luma.com/z9teb942",
          "start_at": "2026-07-28T01:00:00.000Z", "address": "Frontier Tower", "price_display": "Free"},
         {"tier": "bigfree", "hook": "Free, 900 founders", "urgency": "filling"}),
        ({"name": "AI Nerd Meet Up", "url": "https://luma.com/bbbb",
          "start_at": "2026-07-29T01:00:00.000Z", "address": "Mission", "price_display": "Free"},
         {"tier": "food", "hook": "Pizza + AI founders", "urgency": "none"}),
    ]
    teaser = {"headline": "2 hackathons + 900-founder afterparty",
              "subline": "Auth0×Stripe builds Thursday; YC afterparty filling fast."}
    title, message, tags = build_teaser(sample, report_url, model_teaser=teaser)
    publish_roundup("🧪 " + title, message, tags, topic, server, priority=4,
                    click=report_url)
