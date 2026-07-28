#!/usr/bin/env python3
"""luma-scout orchestrator.

Local (ranks via headless `claude -p`):
  python run.py                 # full run: fetch -> rank -> push -> persist
  python run.py --dry-run       # everything except push
  python run.py --test-notify   # send one canned roundup to your topic
  python run.py --limit N       # only enrich the first N new candidates (fast test)

Cloud routine (ranks in the agent's own turn -- no nested claude):
  python run.py --prepare       # fetch/filter/dedup/enrich -> candidates.json + rank_prompt.txt
  <agent reads rank_prompt.txt, writes ranked.json>
  python run.py --deliver       # read ranked.json -> push roundup + update seen.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import enrich as enrich_mod
import filters
import luma
import notify
import rank as rank_mod
import state

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = os.path.join(HERE, "candidates.json")
RANK_PROMPT = os.path.join(HERE, "rank_prompt.txt")
RANKED = os.path.join(HERE, "ranked.json")

TIER_ORDER = {"hackathon": 0, "food": 1, "networking": 2, "seminar": 3}
DROP_TIERS = {"none", "excluded"}


def load_env() -> dict:
    env = dict(os.environ)
    dotenv = os.path.join(HERE, ".env")
    if os.path.exists(dotenv):
        for line in open(dotenv):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def gather(window: int, limit: int = 0) -> list[dict]:
    """Fetch -> prefilter -> dedup vs seen -> enrich. Returns enriched records."""
    now = datetime.now(timezone.utc)
    log("Fetching Luma SF discover feed...")
    entries = luma.fetch_discover()
    kept, reasons = filters.prefilter(entries, now, window)
    log(f"  {len(entries)} fetched -> {reasons['kept']} pass prefilter "
        f"(dropped: {reasons['virtual']} virtual, {reasons['past_or_far']} out-of-window, "
        f"{reasons['sold_out_no_waitlist']} sold-out)")

    seen = state.load()
    new_entries = [e for e in kept if e.get("event", {}).get("api_id") not in seen]
    log(f"  {len(new_entries)} are new{' [FIRST RUN]' if state.is_first_run(seen) else ''}")
    if limit:
        new_entries = new_entries[:limit]
        log(f"  --limit: enriching first {len(new_entries)}")
    if not new_entries:
        return []
    log("Enriching (fetching descriptions)...")
    return [enrich_mod.enrich(e) for e in new_entries]


def deliver(records: list[dict], ranked: list[dict], env: dict, dry: bool, keep_seen: bool) -> int:
    """Select -> build roundup -> push -> persist. Shared by local and cloud paths."""
    now = datetime.now(timezone.utc)
    seen = state.load()
    first_run = state.is_first_run(seen)
    max_per_run = int(env.get("MAX_PER_RUN", "8"))
    first_cap = int(env.get("FIRST_RUN_CAP", "12"))
    topic = env.get("NTFY_TOPIC")
    server = env.get("NTFY_SERVER", "https://ntfy.sh")

    by_id = {r["event_id"]: r for r in records}
    selected = [rk for rk in ranked
                if rk.get("tier") not in DROP_TIERS and rk.get("event_id") in by_id]
    selected.sort(key=lambda r: (TIER_ORDER.get(r.get("tier"), 9), -int(r.get("score", 0))))

    cap = first_cap if first_run else max_per_run
    to_send = selected[:cap]
    log(f"\n{len(to_send)} to send (of {len(selected)} qualifying, {len(ranked)} classified)")

    pairs = [(by_id[rk["event_id"]], rk) for rk in to_send]
    extra = len(selected) - len(to_send)
    title, message, tags = notify.build_roundup(pairs, extra_count=extra)
    priority = 4 if any(
        rk.get("tier") == "hackathon" or rk.get("urgency") == "filling" for rk in to_send
    ) else 3

    log("\n=== roundup preview ===")
    log(title)
    log(message)

    if dry:
        log("\n--dry-run: not sending, not updating seen.json.")
        return 0
    if not to_send:
        log("\nNothing to send; leaving seen.json unchanged.")
        return 0
    if not topic:
        log("NTFY_TOPIC not set; cannot push.")
        return 2

    log(f"\nPushing roundup to {server}/{topic} ...")
    try:
        notify.publish_roundup(title, message, tags, topic, server, priority=priority)
    except Exception as e:  # noqa: BLE001
        log(f"push failed, not marking seen (will retry next run): {e}")
        return 1

    for rk in to_send:  # only mark seen after a successful push
        r = by_id[rk["event_id"]]
        seen[rk["event_id"]] = {
            "first_notified": now.isoformat(),
            "event_date": r.get("start_at"),
            "tier": rk.get("tier"),
        }
    log(f"Pushed roundup ({len(to_send)} events).")
    if not keep_seen:
        state.save(state.prune(seen))
        log("Updated seen.json.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-notify", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--keep-seen", action="store_true")
    ap.add_argument("--prepare", action="store_true", help="cloud stage 1: write candidates.json + rank_prompt.txt")
    ap.add_argument("--deliver", action="store_true", help="cloud stage 2: read ranked.json, push + persist")
    args = ap.parse_args()

    env = load_env()
    window = int(env.get("WINDOW_DAYS", "14"))

    if args.test_notify:
        if not env.get("NTFY_TOPIC"):
            log("NTFY_TOPIC not set."); return 2
        notify.send_test(env["NTFY_TOPIC"], env.get("NTFY_SERVER", "https://ntfy.sh"))
        log(f"Sent test roundup to {env['NTFY_SERVER'] if 'NTFY_SERVER' in env else 'https://ntfy.sh'}/{env['NTFY_TOPIC']}")
        return 0

    # --- Cloud stage 1: prepare candidates for the agent to rank ---
    if args.prepare:
        records = gather(window, args.limit)
        with open(CANDIDATES, "w") as f:
            json.dump(records, f)
        if records:
            with open(RANK_PROMPT, "w") as f:
                f.write(rank_mod.build_prompt(records))
        log(f"\nPrepared {len(records)} candidates -> candidates.json"
            + (", rank_prompt.txt" if records else " (nothing new; skip ranking + deliver)"))
        return 0

    # --- Cloud stage 2: deliver using the agent-produced ranked.json ---
    if args.deliver:
        with open(CANDIDATES) as f:
            records = json.load(f)
        if not records:
            log("No candidates; nothing to deliver."); return 0
        with open(RANKED) as f:
            ranked = json.load(f)
        return deliver(records, ranked, env, dry=False, keep_seen=args.keep_seen)

    # --- Local path: gather -> rank via claude -p -> deliver ---
    records = gather(window, args.limit)
    if not records:
        log("Nothing new. Done."); return 0
    log(f"Ranking {len(records)} candidates with claude ({env.get('RANK_MODEL', 'sonnet')})...")
    ranked = rank_mod.rank(records, model=env.get("RANK_MODEL", "sonnet"))
    return deliver(records, ranked, env, dry=args.dry_run, keep_seen=args.keep_seen)


if __name__ == "__main__":
    raise SystemExit(main())
