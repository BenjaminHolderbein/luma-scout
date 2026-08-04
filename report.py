"""Render the weekly report as a self-contained HTML page for GitHub Pages.

Ordered chronologically, because that is how Ben actually plans a week. Priority
is carried by Fortnite-style loot rarity colour instead of by grouping (see
rarity.py) -- one glance down the timeline tells you what is worth your evening.

Phone-first: single column, big tap targets, no external assets, respects the
reader's light/dark preference. Stdlib only -- the markup is built by hand
rather than templated so the whole pipeline stays dependency-free.
"""
from __future__ import annotations

import html
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import rarity

PT = ZoneInfo("America/Los_Angeles")
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")

TIER_EMOJI = {"hackathon": "🛠️", "bigfree": "⭐", "food": "🍕"}
TIER_WORD = {"hackathon": "Hackathon", "bigfree": "Big & free", "food": "Free food"}
SOURCE_LABEL = {"luma": "Luma", "devpost": "Devpost", "yc": "Y Combinator",
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
header{padding:.5rem 0 1.25rem;border-bottom:1px solid var(--line);margin-bottom:1.25rem}
h1{margin:0 0 .3rem;font-size:1.6rem;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:.9rem;margin:0}

/* rarity legend */
.legend{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.9rem}
.lg{display:flex;align-items:center;gap:.3rem;font-size:.76rem;color:var(--muted);
  background:var(--chip);border-radius:999px;padding:.2rem .6rem;white-space:nowrap}
.dot{width:.6rem;height:.6rem;border-radius:50%;flex:none}

/* day heading */
.day{display:flex;align-items:baseline;gap:.5rem;margin:1.9rem 0 .7rem}
.day h2{font-size:1.05rem;margin:0;letter-spacing:-.01em}
.day .rel{color:var(--muted);font-size:.8rem}
.day::after{content:"";flex:1;height:1px;background:var(--line)}
.divider{margin:2.4rem 0 .4rem;text-align:center;color:var(--muted);font-size:.78rem;
  text-transform:uppercase;letter-spacing:.08em}

/* event card -- rarity drives the left edge and the chip */
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--rar);
  border-radius:10px;padding:.8rem .9rem;margin-bottom:.55rem}
/* legendary gets a glow -- the only rarity that earns extra attention on a
   scan. Kept to ~3 cards a week by the ladder, so it stays special. */
.card.rar-legendary{
  border-color:rgba(240,160,42,.55);
  box-shadow:0 0 0 1px rgba(240,160,42,.28), 0 0 16px -3px rgba(240,160,42,.5);
}
.card.rar-legendary .rar{box-shadow:0 0 10px -2px rgba(240,160,42,.9)}
@media (prefers-color-scheme:dark){
  .card.rar-legendary{
    box-shadow:0 0 0 1px rgba(240,160,42,.4), 0 0 22px -4px rgba(240,160,42,.75);
  }
}
:root[data-theme=dark] .card.rar-legendary{
  box-shadow:0 0 0 1px rgba(240,160,42,.4), 0 0 22px -4px rgba(240,160,42,.75);
}
:root[data-theme=light] .card.rar-legendary{
  box-shadow:0 0 0 1px rgba(240,160,42,.28), 0 0 16px -3px rgba(240,160,42,.5);
}
.card .top{display:flex;align-items:baseline;gap:.5rem;flex-wrap:wrap}
.time{font-variant-numeric:tabular-nums;font-weight:700;font-size:.86rem;color:var(--ink);
  white-space:nowrap}
.rar{background:var(--rar);color:#fff;border-radius:4px;padding:.08rem .4rem;
  font-size:.68rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase;
  white-space:nowrap}
.card a.title{color:var(--ink);font-weight:650;text-decoration:none;font-size:1.02rem;
  display:inline-block;line-height:1.35;margin-top:.3rem}
.card a.title:hover{color:var(--rar)}
.hook{color:var(--rar);font-size:.88rem;margin:.25rem 0 0;font-weight:600}
.summary{font-size:.88rem;margin:.35rem 0 0;opacity:.85}
.deadline{font-size:.83rem;margin:.4rem 0 0;font-weight:650;color:var(--accent)}
.meta{display:flex;flex-wrap:wrap;gap:.3rem .5rem;margin-top:.5rem;
  font-size:.78rem;color:var(--muted);align-items:center}
.tag{background:var(--chip);border-radius:5px;padding:.08rem .4rem;font-size:.73rem}
.new{background:var(--accent);color:#fff;border-radius:5px;padding:.08rem .4rem;
  font-size:.7rem;font-weight:700}
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


def _dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PT)
    except ValueError:
        return None


def _time_label(rec: dict) -> str:
    dt = _dt(rec.get("start_at"))
    if not dt:
        return "TBA"
    if rec.get("source") == "devpost":   # a submission window, not a start time
        return "all day"
    return dt.strftime("%-I:%M%p").replace(":00", "").lower()


def _deadline_line(rec: dict, now: datetime) -> str:
    """Only shown when a source publishes a real deadline (YC, Devpost).

    Ben's actual problem is events that need registering for in advance, so where
    a genuine deadline exists it gets its own emphasised line rather than being
    buried in the summary.
    """
    for key, verb in (("application_closes_at", "Applications close"),
                      ("registration_closes_at", "Registration closes")):
        iso = rec.get(key)
        dt = _dt(iso)
        if not dt:
            continue
        days = (dt.date() - now.astimezone(PT).date()).days
        if days < 0:
            return f"⚠️ {verb.split()[0]} closed {dt.strftime('%b %-d')}"
        when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        return f"⏳ {verb} {when} ({dt.strftime('%b %-d')})"
    end = _dt(rec.get("end_at"))
    if rec.get("source") == "devpost" and end:
        days = (end.date() - now.astimezone(PT).date()).days
        if days >= 0:
            return f"⏳ Submissions close {end.strftime('%b %-d')} ({days} days)"
    return ""


def _card(rec: dict, rk: dict, now: datetime) -> str:
    rar = rarity.of(rk.get("tier"), rk.get("score"))
    color = rarity.COLOR[rar]
    tier = rk.get("tier")

    bits = []
    where = rec.get("address") or rec.get("city_state")
    if rec.get("address_hidden") and not where:
        where = "address after RSVP"
    if where:
        bits.append(f"<span>{_esc(where[:52])}</span>")
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
    if also:
        src += " + " + ", ".join(SOURCE_LABEL.get(s, s) for s in also)
    bits.append(f'<span class="tag">{_esc(src)}</span>')
    if rec.get("_is_new"):
        bits.append('<span class="new">NEW</span>')

    name = rec.get("name") or "Event"
    hook = rk.get("hook") or ""
    parts = [f'<div class="card rar-{rar}" style="--rar:{color}">',
             '<div class="top">',
             f'<span class="time">{_esc(_time_label(rec))}</span>',
             f'<span class="rar">{_esc(rar)}</span>',
             f'<span class="tag">{TIER_EMOJI.get(tier, "")} {_esc(TIER_WORD.get(tier, tier))}</span>',
             '</div>',
             f'<a class="title" href="{_esc(rec.get("url"))}" target="_blank" rel="noopener">{_esc(name)}</a>']
    if hook and hook.lower().strip() not in name.lower():
        parts.append(f'<p class="hook">{_esc(hook)}</p>')
    if rk.get("summary"):
        parts.append(f'<p class="summary">{_esc(rk["summary"])}</p>')
    deadline = _deadline_line(rec, now)
    if deadline:
        parts.append(f'<p class="deadline">{_esc(deadline)}</p>')
    parts.append(f'<div class="meta">{"".join(bits)}</div></div>')
    return "".join(parts)


def build(pairs: list[tuple[dict, dict]], now: datetime, status: dict | None = None,
          extra_count: int = 0, min_rarity: str = "uncommon") -> str:
    """pairs = [(record, ranked), ...] in any order; this sorts chronologically."""
    now_pt = now.astimezone(PT)
    today = now_pt.date()

    ordered = sorted(
        pairs,
        key=lambda p: (_dt(p[0].get("start_at")) or datetime.max.replace(tzinfo=PT)),
    )

    # group by calendar day, keeping chronological order
    days: list[tuple[object, list]] = []
    for rec, rk in ordered:
        dt = _dt(rec.get("start_at"))
        key = dt.date() if dt else None
        if not days or days[-1][0] != key:
            days.append((key, []))
        days[-1][1].append((rec, rk))

    body = []
    week_end = today + timedelta(days=6)
    split_done = False
    for key, items in days:
        if key and key > week_end and not split_done:
            body.append('<div class="divider">— later this month —</div>')
            split_done = True
        if key is None:
            heading, rel = "Date TBA", ""
        else:
            delta = (key - today).days
            heading = key.strftime("%A, %b %-d")
            rel = ("Today" if delta == 0 else "Tomorrow" if delta == 1
                   else f"in {delta} days" if delta > 1 else "")
        body.append(f'<div class="day"><h2>{_esc(heading)}</h2>'
                    f'<span class="rel">{_esc(rel)}</span></div>')
        body.extend(_card(rec, rk, now) for rec, rk in items)

    if not days:
        body.append('<div class="empty">Nothing cleared the bar this week. '
                    'That is unusual for SF — worth a manual check.</div>')

    counts: dict[str, int] = {}
    for rec, rk in ordered:
        counts[rarity.of(rk.get("tier"), rk.get("score"))] = \
            counts.get(rarity.of(rk.get("tier"), rk.get("score")), 0) + 1
    legend = "".join(
        f'<span class="lg"><span class="dot" style="background:{rarity.COLOR[n]}"></span>'
        f'{counts.get(n, 0)} {n}</span>'
        for n in reversed(rarity.ORDER) if counts.get(n))

    blocked, degraded = [], []
    for n, s in (status or {}).items():
        if n.startswith("_"):
            continue
        if s.get("blocked"):
            blocked.append(n)
        elif not s.get("ok") or s.get("degraded"):
            degraded.append(n)
    warn = ""
    if blocked:
        warn += ('<div class="warn"><strong>Sources blocked.</strong> '
                 + _esc(", ".join(blocked)) + ' could not be reached — the run '
                 'environment\'s egress policy refused the connection. Add these '
                 'domains to the environment\'s allowed list to restore coverage.</div>')
    if degraded:
        warn += ('<div class="warn"><strong>Partial data.</strong> These sources returned '
                 'nothing this run, so coverage may be incomplete: '
                 + _esc(", ".join(degraded)) + ".</div>")

    extra = (f'<p class="sub" style="margin-top:1.5rem">+{extra_count} more below '
             f'{_esc(min_rarity)} not shown.</p>' if extra_count > 0 else "")

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
  <p class="sub">{now_pt.strftime('%A, %B %-d')} onward · hackathons through
     {(now_pt + timedelta(days=30)).strftime('%B %-d')}</p>
  <div class="legend">{legend}</div>
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
    nojekyll = os.path.join(DOCS, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()
    return index, archive
