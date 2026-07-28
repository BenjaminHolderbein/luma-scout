# luma-scout

A daily scout for [Luma](https://luma.com) events in San Francisco. Each morning it
pulls the SF discover feed, filters and ranks events against a personal priority
profile using Claude, and pushes a single well-formatted roundup to my phone via
[ntfy](https://ntfy.sh).

Built by **Benjamin Holderbein**.

## What it does

```
fetch SF discover feed  →  filter (in-person, ≤14 days, not sold-out)
  →  dedup vs seen.json  →  enrich (per-event description + categories)
  →  rank with Claude against preferences.md  →  one ntfy roundup  →  persist seen.json
```

- **Priorities (strict tiers):** 🛠️ Hackathon › 🍕 Free food/drink › 🤝 Networking › 🎓 Seminar.
  Each event maps to its highest-matching tier. Defense/military events are dropped;
  free admission and AI/ML/data/startup relevance break ties within a tier.
- **Delivery:** one daily roundup notification, grouped by tier, each event with a
  tappable Luma link. Plain text (the ntfy iOS app doesn't render markdown).
- **State:** `state/seen.json` (committed) so each event is only surfaced once.

## Layout

| File | Role |
|------|------|
| `run.py` | orchestrator (`--dry-run`, `--test-notify`, `--limit N`) |
| `luma.py` | Luma discover + event-detail client |
| `filters.py` | deterministic pre-filter |
| `enrich.py` | per-event detail → compact record |
| `rank.py` | ranking via headless `claude -p` |
| `notify.py` | ntfy roundup builder + publisher |
| `prompt.md` / `preferences.md` | ranking instructions + taste profile (edit freely) |
| `state/seen.json` | dedup state |

No third-party dependencies — standard library only (Python ≥ 3.11).

## Run it

```bash
cp .env.example .env      # set NTFY_TOPIC etc.
python3 run.py --dry-run  # fetch + rank, print the roundup, send nothing
python3 run.py            # for real: push roundup + update seen.json
```

The ranking step shells out to `claude -p`, billed to a Claude Pro/Max
subscription (non-interactive credit), not a metered API key.

## Deployment

Runs as a daily [Claude cloud routine](https://code.claude.com/docs/en/routines.md)
(~7am PT) that clones this repo, runs the pipeline, and commits `seen.json` back.
A cloud routine is subscription-billed and within Anthropic's terms — unlike using
a subscription OAuth token in third-party CI, which is not.
