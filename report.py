"""Render the weekly report as a self-contained HTML page for GitHub Pages.

Phone-first: single column, big tap targets, no external assets, respects the
reader's light/dark preference. Stdlib only -- the markup is built by hand
rather than templated so the whole pipeline stays dependency-free.
"""
from __future__ import annotations

import html
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")

TIERS = [
    ("hackathon", "🛠️", "Hackathons", "Every one in SF — next 30 days"),
    ("bigfree", "⭐", "Big & free", "Large events you can walk into for nothing"),
    ("food", "🍕", "Free food & drink", "Your week of free meals"),
]
SOURCE_LABEL = {"luma": "Luma", "devpost": "Devpost",
                "eventbrite": "Eventbrite", "meetup": "Meetup"}
URGENCY = {
    "filling": ("⚡", "Filling up"),
    "waitlist": ("⏳", "Waitlist"),
    "sold_out": ("🚫", "Sold out"),
}

CSS = """
*{box-sizing:border-box}
:root{
  --bg:#fbfaf8; --card:#fff; --ink:#17150f; --muted:#6b6559; --line:#e6e1d7;
  --accent:#b4451f; --chip:#f2ede3;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#14130f; --card:#1c1b16; --ink:#f0ece3; --muted:#9d968a; --line:#2e2c25;
  --accent:#ff9d6e; --chip:#26241d;
}}
:root[data-theme=dark]{
  --bg:#14130f; --card:#1c1b16; --ink:#f0ece3; --muted:#9d968a; --line:#2e2c25;
  --accent:#ff9d6e; --chip:#26241d;
}
:root[data-theme=light]{
  --bg:#fbfaf8; --card:#fff; --ink:#17150f; --muted:#6b6559; --line:#e6e1d7;
  --accent:#b4451f; --chip:#f2ede3;
}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.5 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  -webkit-text-size-adjust:100%}
.wrap{max-width:44rem;margin:0 auto;padding:1.5rem 1rem 4rem}
header{padding:.5rem 0 1.25rem;border-bottom:1px solid var(--line);margin-bottom:1.5rem}
h1{margin:0 0 .3rem;font-size:1.6rem;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:.9rem;margin:0}
.counts{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.9rem}
.count{background:var(--chip);border-radius:999px;padding:.25rem .7rem;font-size:.82rem;
  font-variant-numeric:tabular-nums;white-space:nowrap}
h2{font-size:1.15rem;margin:2rem 0 .15rem;letter-spacing:-.01em}
.tiersub{color:var(--muted);font-size:.83rem;margin:0 0 .85rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:.85rem .95rem;margin-bottom:.6rem}
.card a.title{color:var(--ink);font-weight:650;text-decoration:none;font-size:1.03rem;
  display:inline-block;line-height:1.35}
.card a.title:hover{color:var(--accent)}
.hook{color:var(--accent);font-size:.9rem;margin:.28rem 0 0;font-weight:550}
.summary{font-size:.9rem;color:var(--ink);margin:.4rem 0 0;opacity:.85}
.meta{display:flex;flex-wrap:wrap;gap:.35rem .55rem;margin-top:.55rem;
  font-size:.8rem;color:var(--muted);align-items:center}
.meta .when{font-weight:600;color:var(--ink)}
.tag{background:var(--chip);border-radius:5px;padding:.1rem .42rem;font-size:.75rem}
.new{background:var(--accent);color:#fff;border-radius:5px;padding:.1rem .42rem;
  font-size:.72rem;font-weight:700;letter-spacing:.02em}
.empty{color:var(--muted);font-size:.9rem;font-style:italic;
  border:1px dashed var(--line);border-radius:12px;padding:1rem;text-align:center}
footer{margin-top:3rem;padding-top:1.1rem;border-top:1px solid var(--line);
  color:var(--muted);font-size:.78rem}
footer a{color:var(--muted)}
.warn{background:var(--chip);border-left:3px solid var(--accent);border-radius:6px;
  padding:.6rem .8rem;font-size:.82rem;margin-bottom:1.2rem}
"""


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _when(rec: dict, now: datetime) -> tuple[str, str]:
    """(absolute label, relative label)."""
    iso = rec.get("start_at")
    if not iso:
        return rec.get("when_local") or "Date TBA", ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PT)
    except ValueError:
        return rec.get("when_local") or "Date TBA", ""
    label = dt.strftime("%a %b %-d, %-I:%M %p").replace(":00 ", " ")
    if rec.get("source") == "devpost":  # a submission window, not a start time
        label = dt.strftime("%a %b %-d")
        end_iso = rec.get("end_at")
        if end_iso and dt.date() <= now.astimezone(PT).date():
            # already open -- what matters is how long is left to enter
            try:
                end = datetime.fromisoformat(end_iso.replace("Z", "+00:00")).astimezone(PT)
                left = (end.date() - now.astimezone(PT).date()).days
                return f"Open now · closes {end.strftime('%b %-d')}", (
                    f"{left} days left" if left > 0 else "closes today")
            except ValueError:
                pass
    days = (dt.date() - now.astimezone(PT).date()).days
    rel = ("Today" if days == 0 else "Tomorrow" if days == 1
           else f"in {days} days" if 1 < days <= 30 else "")
    return label, rel


def _card(rec: dict, rk: dict, now: datetime) -> str:
    when, rel = _when(rec, now)
    bits = [f'<span class="when">{_esc(when)}</span>']
    if rel:
        bits.append(f"<span>{_esc(rel)}</span>")
    where = rec.get("address") or rec.get("city_state")
    if rec.get("address_hidden") and not where:
        where = "SF · address after RSVP"
    if where:
        bits.append(f"<span>{_esc(where[:60])}</span>")
    if rec.get("sf_proximity") == "near":
        bits.append('<span class="tag">Wider Bay Area</span>')
    price = rec.get("price_display")
    if price:
        bits.append(f'<span class="tag">{_esc(price)}</span>')
    urg = URGENCY.get(rk.get("urgency"))
    if urg:
        bits.append(f'<span class="tag">{urg[0]} {urg[1]}</span>')
    src = SOURCE_LABEL.get(rec.get("source"), rec.get("source"))
    also = rec.get("also_on") or []
    src_label = src + (" + " + ", ".join(SOURCE_LABEL.get(s, s) for s in also) if also else "")
    bits.append(f'<span class="tag">{_esc(src_label)}</span>')
    if rec.get("_is_new"):
        bits.append('<span class="new">NEW</span>')

    hook = rk.get("hook") or ""
    name = rec.get("name") or "Event"
    parts = [f'<div class="card">',
             f'<a class="title" href="{_esc(rec.get("url"))}" target="_blank" rel="noopener">{_esc(name)}</a>']
    if hook and hook.lower().strip() not in name.lower():
        parts.append(f'<p class="hook">{_esc(hook)}</p>')
    if rk.get("summary"):
        parts.append(f'<p class="summary">{_esc(rk["summary"])}</p>')
    parts.append(f'<div class="meta">{"".join(bits)}</div></div>')
    return "".join(parts)


def build(pairs: list[tuple[dict, dict]], now: datetime, status: dict | None = None,
          extra_count: int = 0) -> str:
    """pairs = ordered [(record, ranked), ...] across all tiers."""
    now_pt = now.astimezone(PT)
    week_end = now_pt + timedelta(days=6)
    groups: dict[str, list] = {}
    for rec, rk in pairs:
        groups.setdefault(rk.get("tier"), []).append((rec, rk))

    counts = " ".join(
        f'<span class="count">{emoji} {len(groups.get(key, []))} {label.lower()}</span>'
        for key, emoji, label, _ in TIERS)

    body = []
    for key, emoji, label, blurb in TIERS:
        items = groups.get(key, [])
        body.append(f"<h2>{emoji} {label}</h2><p class='tiersub'>{_esc(blurb)}</p>")
        if items:
            body.extend(_card(rec, rk, now) for rec, rk in items)
        elif key == "hackathon":
            body.append('<div class="empty">No hackathons found in the next 30 days. '
                        'That is unusual for SF — worth a manual check.</div>')
        else:
            body.append('<div class="empty">Nothing this week.</div>')

    warn = ""
    degraded = [n for n, s in (status or {}).items()
                if not n.startswith("_") and (not s.get("ok") or s.get("degraded"))]
    if degraded:
        warn = ('<div class="warn"><strong>Partial data.</strong> These sources returned '
                'nothing this run, so coverage may be incomplete: '
                + _esc(", ".join(degraded)) + ".</div>")

    extra = (f'<p class="sub" style="margin-top:1.5rem">+{extra_count} more qualifying events '
             f'not shown (report cap).</p>' if extra_count > 0 else "")

    src_line = ", ".join(
        f"{SOURCE_LABEL.get(n, n)} {s.get('count', 0)}"
        for n, s in sorted((status or {}).items()) if not n.startswith("_"))

    return f"""<title>SF events · week of {now_pt.strftime('%b %-d, %Y')}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<style>{CSS}</style>
<div class="wrap">
<header>
  <h1>Your week in SF</h1>
  <p class="sub">{now_pt.strftime('%A, %B %-d')} &ndash; {week_end.strftime('%B %-d, %Y')}
     · hackathons through {(now_pt + timedelta(days=30)).strftime('%B %-d')}</p>
  <div class="counts">{counts}</div>
</header>
{warn}
{''.join(body)}
{extra}
<footer>
  Built by luma-scout for Benjamin Holderbein ·
  generated {now_pt.strftime('%a %b %-d, %-I:%M %p')} PT<br>
  Sources: {_esc(src_line)} ·
  <a href="https://github.com/BenjaminHolderbein/luma-scout">source</a>
</footer>
</div>"""


def write(html_text: str, now: datetime) -> tuple[str, str]:
    """Write docs/index.html plus a dated archive copy. Returns (paths)."""
    os.makedirs(DOCS, exist_ok=True)
    stamp = now.astimezone(PT).strftime("%Y-%m-%d")
    index = os.path.join(DOCS, "index.html")
    archive = os.path.join(DOCS, f"{stamp}.html")
    for path in (index, archive):
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_text)
    # GitHub Pages would otherwise run these through Jekyll and drop the
    # underscore-free but still fragile raw HTML through a layout.
    nojekyll = os.path.join(DOCS, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()
    return index, archive
