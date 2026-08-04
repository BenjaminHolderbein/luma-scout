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
from sources import common as geo

PT = ZoneInfo("America/Los_Angeles")
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")

TIER_EMOJI = {"hackathon": "🛠️", "bigfree": "⭐", "food": "🍕"}
# Chip tint per tier, so a selected filter is colour-coded to what it selects.
ACCENT_BY_TIER = {"hackathon": "#c2691a", "bigfree": "#8a4fd0", "food": "#2f8f4e"}
TIER_WORD = {"hackathon": "Hackathon", "bigfree": "Big & free", "food": "Free food"}
SOURCE_LABEL = {"luma": "Luma", "devpost": "Devpost", "yc": "Y Combinator",
                "eventbrite": "Eventbrite", "meetup": "Meetup",
                "cerebralvalley": "Cerebral Valley", "agihouse": "AGI House",
                "hackclub": "Hack Club", "mlh": "MLH"}
URGENCY = {
    "filling": ("⚡", "Filling up"),
    "waitlist": ("⏳", "Waitlist"),
    "sold_out": ("🚫", "Sold out"),
}

# Tapping a tier isolates it; tapping the active one again returns to All.
# Day headings, section headers and the whole later-this-month zone collapse
# when a filter empties them, so the page never leaves stranded furniture
# above nothing. Section tallies recount live.
FILTER_JS = """
(function(){
  var bar=document.getElementById('filters');
  if(!bar) return;
  bar.hidden=false;
  var GROUPS=['tier','rarity','source','new'];
  var btns=[].slice.call(bar.querySelectorAll('.fbtn'));
  var cards=[].slice.call(document.querySelectorAll('.card'));
  var none=document.getElementById('noresults');
  var active={tier:'all',rarity:'all',source:'all','new':'all'};

  // A card survives only if it satisfies every group at once. `ignore` lets the
  // facet counts ask "how many would this chip give me?" without counting its
  // own group against itself. Attributes are space-separated token lists so a
  // card can carry several tags in one group (a big-free event that also has
  // free food matches both category chips).
  function matches(card, state, ignore){
    for(var i=0;i<GROUPS.length;i++){
      var g=GROUPS[i];
      if(g===ignore) continue;
      if(state[g]==='all') continue;
      var attr=' '+(card.getAttribute('data-'+g)||'')+' ';
      if(attr.indexOf(' '+state[g]+' ')===-1) return false;
    }
    return true;
  }

  function visibleAfter(el, stopSel){
    var n=0, cur=el.nextElementSibling;
    while(cur && !cur.matches(stopSel)){
      if(cur.classList.contains('card') && !cur.hidden) n++;
      cur=cur.nextElementSibling;
    }
    return n;
  }

  function apply(){
    cards.forEach(function(c){ c.hidden = !matches(c, active); });

    [].slice.call(document.querySelectorAll('.day')).forEach(function(d){
      d.hidden = visibleAfter(d, '.day,.sect,.sectgap') === 0;
    });
    [].slice.call(document.querySelectorAll('.sect')).forEach(function(s){
      var n=visibleAfter(s, '.sect');
      var t=s.querySelector('.tally');
      if(t) t.textContent = n + ' event' + (n===1?'':'s');
      s.hidden = n===0;
    });
    var zone=document.querySelector('.zone');
    if(zone) zone.hidden = zone.querySelectorAll('.card:not([hidden])').length===0;
    if(none) none.hidden = document.querySelectorAll('.card:not([hidden])').length>0;

    // Live facet counts: each chip shows what it would actually yield given the
    // other groups, and dead ends disable themselves instead of lying.
    btns.forEach(function(b){
      var g=b.getAttribute('data-group'), v=b.getAttribute('data-val');
      var probe={}; GROUPS.forEach(function(k){ probe[k]=active[k]; }); probe[g]=v;
      var n=0;
      cards.forEach(function(c){ if(matches(c, probe)) n++; });
      var el=b.querySelector('.n');
      if(el) el.textContent=n;
      b.disabled = (n===0 && v!=='all');
      b.setAttribute('aria-pressed', String(active[g]===v));
    });
  }

  btns.forEach(function(b){
    b.addEventListener('click', function(){
      var g=b.getAttribute('data-group'), v=b.getAttribute('data-val');
      active[g] = (v===active[g] && v!=='all') ? 'all' : v;
      apply();
    });
  });
  apply();
})();
"""

CSS = """
*{box-sizing:border-box}
/* the filter toggles the `hidden` attribute, and an author `display` rule beats
   the UA stylesheet's [hidden]{display:none} -- .day is flex, so empty day
   headings survived a filter until this landed */
[hidden]{display:none!important}
:root{
  --bg:#fbfaf8; --card:#fff; --ink:#17150f; --muted:#6b6559; --line:#e6e1d7;
  --accent:#b4451f; --chip:#f2ede3; --zone:#f8f6f1;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#14130f; --card:#1c1b16; --ink:#f0ece3; --muted:#9d968a; --line:#2e2c25;
  --accent:#ff9d6e; --chip:#26241d; --zone:#201e17;
}}
:root[data-theme=dark]{
  --bg:#14130f; --card:#1c1b16; --ink:#f0ece3; --muted:#9d968a; --line:#2e2c25;
  --accent:#ff9d6e; --chip:#26241d; --zone:#201e17;
}
:root[data-theme=light]{
  --bg:#fbfaf8; --card:#fff; --ink:#17150f; --muted:#6b6559; --line:#e6e1d7;
  --accent:#b4451f; --chip:#f2ede3; --zone:#f8f6f1;
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

/* filters -- revealed by script, so they never sit there dead without JS.
   The rarity row doubles as the legend it replaced: same counts, now clickable. */
.filters{margin-top:1rem}
.filters[hidden]{display:none}
.frow{display:flex;flex-wrap:wrap;align-items:center;gap:.35rem;margin-top:.45rem}
.flab{font-size:.7rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
  color:var(--muted);width:100%;margin-bottom:.05rem}
.fbtn{font:inherit;font-size:.8rem;font-weight:600;color:var(--ink);cursor:pointer;
  background:var(--card);border:1.5px solid var(--line);border-radius:999px;
  padding:.28rem .68rem;display:flex;align-items:center;gap:.3rem;
  -webkit-tap-highlight-color:transparent}
.fbtn .n{color:var(--muted);font-weight:600;font-variant-numeric:tabular-nums}
.fbtn .dot{width:.55rem;height:.55rem}
.fbtn[aria-pressed=true]{border-color:var(--fc,var(--accent));
  background:color-mix(in srgb, var(--fc,var(--accent)) 12%, transparent)}
.fbtn[aria-pressed=true] .n{color:var(--fc,var(--accent))}
.fbtn:disabled{opacity:.38;cursor:default}
.noresults{color:var(--muted);font-size:.9rem;font-style:italic;
  border:1px dashed var(--line);border-radius:12px;padding:1.2rem;text-align:center;
  margin-top:1.2rem}

/* day heading */
.day{display:flex;align-items:baseline;gap:.5rem;margin:1.9rem 0 .7rem}
.day h2{font-size:1.05rem;margin:0;letter-spacing:-.01em}
.day .rel{color:var(--muted);font-size:.8rem}
.day::after{content:"";flex:1;height:1px;background:var(--line)}
/* section break -- typographic, not another box. It used to be a filled panel
   with a chunky accent bar, which competed with the cards and borrowed the
   warning callout's visual language. The weight now comes from type size, a
   rule, and whitespace; the tinted zone below marks the second half. */
.sect{margin:.2rem 0 1.2rem;padding:0 0 .75rem;border-bottom:2px solid var(--line)}
.sect .row{display:flex;align-items:baseline;justify-content:space-between;gap:.75rem}
.sect h2{margin:0;font-size:1.45rem;letter-spacing:-.025em;line-height:1.15}
.sect .tally{color:var(--muted);font-size:.8rem;font-weight:600;white-space:nowrap;
  font-variant-numeric:tabular-nums}
.sect .range{display:block;color:var(--muted);font-size:.85rem;margin-top:.3rem}
.sect + .day{margin-top:1.2rem}
.sectgap{height:2.6rem}

/* everything beyond this week sits in its own tinted zone, so the two halves
   of the report read as separate places rather than one continuous scroll */
.zone{background:var(--zone);border:1px solid var(--line);border-radius:16px;
  padding:1.5rem 1.15rem 1.7rem;margin-top:2.9rem}
.zone .sectgap{display:none}
.zone .sect{margin-top:0}
.zone .day{margin-top:1.8rem}
.zone .day h2{font-size:1rem}
.zone .card{margin-bottom:.7rem}
.zone .card:last-child{margin-bottom:0}

/* event card -- rarity drives the whole outline and the chip.
   A uniform border, deliberately: an earlier version used a heavy 4px tab on
   the left only, which read as a lopsided edge next to the legendary glow. */
.card{background:var(--card);border:1.5px solid var(--rar);
  border-radius:10px;padding:.8rem .9rem;margin-bottom:.55rem}
/* legendary gets a glow -- the only rarity that earns extra attention on a
   scan. Kept to ~2-3 cards a week by the ladder, so it stays special. The
   border is already uniform, so the halo sits evenly around the whole card. */
/* common is filler by definition -- shown, but visually receded so the scan
   still lands on the colours that matter. junk only renders if the cutoff is
   dropped below the default, and recedes further. */
.card.rar-common{opacity:.72}
.card.rar-junk{opacity:.55}
.card.rar-legendary{box-shadow:0 0 17px -3px rgba(240,160,42,.55)}
.card.rar-legendary .rar{box-shadow:0 0 10px -2px rgba(240,160,42,.9)}
@media (prefers-color-scheme:dark){
  .card.rar-legendary{box-shadow:0 0 24px -4px rgba(240,160,42,.8)}
}
:root[data-theme=dark] .card.rar-legendary{box-shadow:0 0 24px -4px rgba(240,160,42,.8)}
:root[data-theme=light] .card.rar-legendary{box-shadow:0 0 17px -3px rgba(240,160,42,.55)}
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
/* the location chip only turns loud -- red -- when the event is NOT in SF.
   Everything here is implicitly "in SF" except those, so the exception must
   not whisper. Same radius as the neighbouring tags, deliberately. */
.loc{background:var(--chip);border-radius:5px;padding:.08rem .45rem;font-size:.73rem}
.loc.offsf{background:#e5231b;color:#fff;font-weight:800;letter-spacing:.01em}
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


def _tags_of(rk: dict) -> list[str]:
    """Primary tier first, then any extra tiers the ranker says it also
    satisfies. Primary drives rarity and ordering; the rest are tags."""
    tags = [rk.get("tier")]
    tags += [t for t in (rk.get("also") or []) if t in TIER_WORD]
    return list(dict.fromkeys(t for t in tags if t))


def _near_label(rec: dict) -> str:
    """Name the actual town for a not-SF event. 'Wider Bay Area' flattens a
    real gradient -- Oakland is 20 BART minutes, Santa Clara is an hour-plus --
    so show the specific place whenever the record names one."""
    blob = " ".join(f for f in (rec.get("city_state"), rec.get("address")) if f).lower()
    for term in geo.NEAR_BAY_TERMS:
        town = term.split(",")[0]
        if town in ("bay area", "silicon valley") or town not in blob:
            continue
        return town.title()
    return "Wider Bay Area"


def _card(rec: dict, rk: dict, now: datetime) -> str:
    rar = rarity.of(rk.get("tier"), rk.get("score"))
    color = rarity.COLOR[rar]
    tier = rk.get("tier")
    tags = _tags_of(rk)

    bits = []
    where = rec.get("address") or rec.get("city_state")
    if rec.get("address_hidden") and not where:
        where = "address after RSVP"
    near = rec.get("sf_proximity") == "near"
    if near and not where:
        where = _near_label(rec)
    if where:
        cls = "loc offsf" if near else "loc"
        bits.append(f'<span class="{cls}">{_esc(where[:52])}</span>')
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
    parts = [f'<div class="card rar-{rar}" data-tier="{_esc(" ".join(tags))}" data-rarity="{rar}" '
             f'data-source="{_esc(rec.get("source"))}" '
             f'data-new="{"yes" if rec.get("_is_new") else "no"}" style="--rar:{color}">',
             '<div class="top">',
             f'<span class="time">{_esc(_time_label(rec))}</span>',
             f'<span class="rar">{_esc(rar)}</span>',
             *(f'<span class="tag">{TIER_EMOJI.get(t, "")} {_esc(TIER_WORD.get(t, t))}</span>'
               for t in tags),
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
          extra_count: int = 0, min_rarity: str = "uncommon",
          hack_window_days: int = 60) -> str:
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

    week_end = today + timedelta(days=6)

    def _is_later(key) -> bool:
        return bool(key and key > week_end)

    n_week = sum(len(i) for k, i in days if not _is_later(k))
    n_later = sum(len(i) for k, i in days if _is_later(k))
    horizon = today + timedelta(days=hack_window_days)

    def _section(title: str, rng: str, tally: str, first: bool) -> str:
        gap = "" if first else '<div class="sectgap"></div>'
        return (f'{gap}<div class="sect">'
                f'<div class="row"><h2>{_esc(title)}</h2>'
                f'<span class="tally">{_esc(tally)}</span></div>'
                f'<span class="range">{_esc(rng)}</span></div>')

    body = []
    opened_week = opened_later = False
    for key, items in days:
        later = _is_later(key)
        if later and not opened_later:
            body.append('<section class="zone">')
            body.append(_section(
                "Beyond this week",
                f"{(week_end + timedelta(days=1)).strftime('%b %-d')} – "
                f"{horizon.strftime('%b %-d')} · worth registering for now",
                f"{n_later} event{'s' if n_later != 1 else ''}",
                first=not opened_week))
            opened_later = True
        elif not later and not opened_week:
            body.append(_section(
                "This week",
                f"{today.strftime('%a %b %-d')} – {week_end.strftime('%a %b %-d')}",
                f"{n_week} event{'s' if n_week != 1 else ''}",
                first=True))
            opened_week = True
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

    if opened_later:
        body.append("</section>")

    if not days:
        body.append('<div class="empty">Nothing cleared the bar this week. '
                    'That is unusual for SF — worth a manual check.</div>')

    counts: dict[str, int] = {}
    for rec, rk in ordered:
        counts[rarity.of(rk.get("tier"), rk.get("score"))] = \
            counts.get(rarity.of(rk.get("tier"), rk.get("score")), 0) + 1
    tier_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for rec, rk in ordered:
        for t in _tags_of(rk):
            tier_counts[t] = tier_counts.get(t, 0) + 1
        source_counts[rec.get("source")] = source_counts.get(rec.get("source"), 0) + 1

    def _chip(group: str, val: str, label: str, n: int, fc: str | None = None,
              dot: str | None = None) -> str:
        style = f' style="--fc:{fc}"' if fc else ""
        swatch = f'<span class="dot" style="background:{dot}"></span>' if dot else ""
        return (f'<button class="fbtn" type="button" data-group="{group}" data-val="{val}"'
                f' aria-pressed="{"true" if val == "all" else "false"}"{style}>'
                f'{swatch}{label} <span class="n">{n}</span></button>')

    rows = []
    # Category
    cat = [_chip("tier", "all", "All", len(ordered))]
    cat += [_chip("tier", k, f"{TIER_EMOJI[k]} {_esc(TIER_WORD[k])}", tier_counts[k],
                  ACCENT_BY_TIER[k])
            for k in ("hackathon", "bigfree", "food") if tier_counts.get(k)]
    rows.append('<div class="frow"><span class="flab">Category</span>' + "".join(cat) + "</div>")
    # Rarity -- this row replaces the old static legend
    rar = [_chip("rarity", "all", "All", len(ordered))]
    rar += [_chip("rarity", n, n.capitalize(), counts[n], rarity.COLOR[n], rarity.COLOR[n])
            for n in reversed(rarity.ORDER) if counts.get(n)]
    rows.append('<div class="frow"><span class="flab">Rarity</span>' + "".join(rar) + "</div>")
    # Source
    src = [_chip("source", "all", "All", len(ordered))]
    src += [_chip("source", s, _esc(SOURCE_LABEL.get(s, s)), n)
            for s, n in sorted(source_counts.items(), key=lambda kv: -kv[1]) if s]
    rows.append('<div class="frow"><span class="flab">Source</span>' + "".join(src) + "</div>")
    # New -- only offered when the report actually distinguishes (first runs
    # and cleared-state weeks mark everything NEW, where the chip is noise)
    n_new = sum(1 for rec, _ in ordered if rec.get("_is_new"))
    if 0 < n_new < len(ordered):
        new_row = [_chip("new", "all", "All", len(ordered)),
                   _chip("new", "yes", "NEW this week", n_new, "#b4451f")]
        rows.append('<div class="frow"><span class="flab">New</span>' + "".join(new_row) + "</div>")

    filters = f'<div class="filters" id="filters" hidden>{"".join(rows)}</div>'

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
    dead_seeds = ((((status or {}).get("luma") or {}).get("detail") or {})
                  .get("dead_seeds") or [])
    if dead_seeds:
        warn += ('<div class="warn"><strong>Luma seeds unresolved.</strong> These '
                 'seed calendars no longer resolve and contributed nothing — the '
                 'list in sources/luma_src.py needs pruning: '
                 + _esc(", ".join(dead_seeds)) + ".</div>")
    gaps = (status or {}).get("_rank_gaps") or []
    if gaps:
        warn += ('<div class="warn"><strong>Ranking gap.</strong> The ranker skipped '
                 + ("this hackathon-looking event, so it is" if len(gaps) == 1
                    else "these hackathon-looking events, so they are")
                 + ' listed with a default rating: ' + _esc(", ".join(gaps)) + ".</div>")

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
     {(now_pt + timedelta(days=hack_window_days)).strftime('%B %-d')}</p>
  {filters}
</header>
{warn}
{''.join(body)}
<div class="noresults" id="noresults" hidden>Nothing in that category this time.</div>
{extra}
<footer>
  Built by luma-scout for Benjamin Holderbein ·
  generated {now_pt.strftime('%a %b %-d, %-I:%M %p')} PT<br>
  Sources: {_esc(src_line)} ·
  <a href="https://github.com/BenjaminHolderbein/luma-scout">source</a>
</footer>
</div>
<script>{FILTER_JS}</script>"""


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
