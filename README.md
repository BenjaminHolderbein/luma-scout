# luma-scout

A weekly scout for San Francisco events. Every Monday morning it sweeps Luma,
Devpost, Eventbrite and Meetup, ranks what it finds against a personal priority
profile using Claude, publishes an HTML report to GitHub Pages, and pushes a
teaser to my phone via [ntfy](https://ntfy.sh).

**Report:** <https://benjaminholderbein.github.io/luma-scout/>

Built by **Benjamin Holderbein**.

## Priorities

The whole thing exists to answer three questions, in this order:

1. **🛠️ What hackathons are happening?** — exhaustively. Every hackathon in SF
   gets listed, on a 30-day horizon, whether or not it looks appealing. Weak ones
   are scored low, never dropped. A missed hackathon is the worst failure mode.
2. **⭐ What big free events shouldn't I miss?** — large or high-draw events that
   cost nothing to attend.
3. **🍕 Where's the free food this week?** — food or drink actually provided free.

Anything matching none of the three is dropped, and defense/military events are
excluded outright — the one rule that overrides even tier 1.

## What it does

```
collect (luma discover + luma calendar crawl + devpost + eventbrite + meetup)
  → window/geo filter → cross-source dedup → rank with Claude against preferences.md
  → render docs/index.html → push ntfy teaser → commit seen.json + docs
```

- **Two horizons:** 7 days for the week's events, 30 for hackathons (they need
  registration lead time).
- **`seen.json` is a badge, not a filter.** Events already reported still appear
  in the coming week's report — they're just not marked NEW. A weekly report is a
  picture of the week, not a diff.
- **Sources are fault-isolated.** A broken scraper reports zero and the report
  says coverage was partial, rather than the run dying or quietly under-reporting.

## Sources

| Source | Method | Notes |
|---|---|---|
| Luma discover | public discover API | SF-curated, ~69 events |
| Luma calendars | `/calendar/get-items` per calendar found in the feed | the big win — ~300 events; Luma's search API needs auth |
| Devpost | public JSON API | hackathons only; publishes a submission period, not a start time |
| Eventbrite | schema.org JSON-LD in search HTML | scraper; rate-limits aggressively, so requests are throttled |
| Meetup | schema.org JSON-LD in `/find/` HTML | scraper |

## Layout

| File | Role |
|------|------|
| `run.py` | orchestrator (`--dry-run`, `--prepare`/`--deliver`, `--test-notify`, `--limit N`) |
| `sources/` | one module per platform + shared HTTP, geo, and dedup (`common.py`) |
| `luma.py` / `filters.py` / `enrich.py` | Luma client, pre-filter, detail → record |
| `rank.py` | ranking via headless `claude -p` |
| `report.py` | HTML report renderer (writes `docs/`) |
| `notify.py` | ntfy teaser builder + publisher |
| `prompt.md` / `preferences.md` | ranking instructions + taste profile (edit freely) |
| `state/seen.json` | NEW-badge state |
| `docs/` | published report + dated archive (GitHub Pages) |

No third-party dependencies — standard library only (Python ≥ 3.11).

## Run it

```bash
cp .env.example .env      # set NTFY_TOPIC etc.
python3 run.py --dry-run  # collect + rank + write docs/, send nothing
python3 run.py            # for real: publish, push, update state
```

The ranking step shells out to `claude -p`, billed to a Claude Pro/Max
subscription (non-interactive credit), not a metered API key.

## Deployment

Runs as a weekly [Claude cloud routine](https://code.claude.com/docs/en/routines.md)
every Monday at 7am PT (`0 14 * * 1` UTC). It clones this repo, runs
`--prepare`, ranks the candidates in its own turn (no nested `claude`), runs
`--deliver`, and commits `docs/` + `seen.json` back to `main`.

A cloud routine is subscription-billed and within Anthropic's terms — unlike
using a subscription OAuth token in third-party CI, which is not.

**Note:** this repo is public, so the published report is public too.
