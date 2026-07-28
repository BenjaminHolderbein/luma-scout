#!/usr/bin/env python3
"""luma-scout orchestrator.

  python run.py                 # normal run: fetch -> filter -> rank -> push -> persist
  python run.py --dry-run       # everything except push; prints what WOULD send
  python run.py --test-notify   # send one canned rich notification to your topic
  python run.py --limit N       # only enrich/rank the first N new candidates (fast test)
  python run.py --keep-seen     # dry-run helper: don't write seen.json
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import enrich as enrich_mod
import filters
import luma
import notify
import rank as rank_mod
import state

TIER_ORDER = {"hackathon": 0, "food": 1, "networking": 2, "seminar": 3}
DROP_TIERS = {"none", "excluded"}


def load_env() -> dict:
    env = dict(os.environ)
    dotenv = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(dotenv):
        for line in open(dotenv):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-notify", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--keep-seen", action="store_true")
    args = ap.parse_args()

    env = load_env()
    topic = env.get("NTFY_TOPIC")
    server = env.get("NTFY_SERVER", "https://ntfy.sh")
    model = env.get("RANK_MODEL", "sonnet")
    window = int(env.get("WINDOW_DAYS", "14"))
    max_per_run = int(env.get("MAX_PER_RUN", "8"))
    first_cap = int(env.get("FIRST_RUN_CAP", "12"))

    if args.test_notify:
        if not topic:
            log("NTFY_TOPIC not set (.env).")
            return 2
        notify.send_test(topic, server)
        log(f"Sent test notification to {server}/{topic}")
        return 0

    now = datetime.now(timezone.utc)
    log("Fetching Luma SF discover feed...")
    entries = luma.fetch_discover()
    kept, reasons = filters.prefilter(entries, now, window)
    log(f"  {len(entries)} fetched -> {reasons['kept']} pass prefilter "
        f"(dropped: {reasons['virtual']} virtual, {reasons['past_or_far']} out-of-window, "
        f"{reasons['sold_out_no_waitlist']} sold-out)")

    seen = state.load()
    first_run = state.is_first_run(seen)
    new_entries = [e for e in kept if e.get("event", {}).get("api_id") not in seen]
    log(f"  {len(new_entries)} are new (not in seen.json){' [FIRST RUN]' if first_run else ''}")
    if args.limit:
        new_entries = new_entries[: args.limit]
        log(f"  --limit: enriching first {len(new_entries)}")

    if not new_entries:
        log("Nothing new. Done.")
        return 0

    log("Enriching (fetching descriptions)...")
    records = [enrich_mod.enrich(e) for e in new_entries]
    by_id = {r["event_id"]: r for r in records}

    log(f"Ranking {len(records)} candidates with claude ({model})...")
    ranked = rank_mod.rank(records, model=model)

    # join + order
    selected = []
    for rk in ranked:
        tier = rk.get("tier")
        if tier in DROP_TIERS or rk.get("event_id") not in by_id:
            continue
        selected.append(rk)
    selected.sort(key=lambda r: (TIER_ORDER.get(r.get("tier"), 9), -int(r.get("score", 0))))

    cap = first_cap if first_run else max_per_run
    to_send = selected[:cap]

    log(f"\n=== {len(to_send)} to send (of {len(selected)} qualifying, {len(ranked)} classified) ===")
    for rk in to_send:
        r = by_id[rk["event_id"]]
        log(f"  [{rk['tier']:>10} {rk.get('score'):>3}] {rk.get('urgency',''):<9} "
            f"{r['when_local']:<22} {r.get('price_display',''):<14} {r['name'][:48]}")

    # Build the single daily roundup from the ordered picks.
    pairs = [(by_id[rk["event_id"]], rk) for rk in to_send]
    extra = len(selected) - len(to_send)
    title, message, tags = notify.build_roundup(pairs, extra_count=extra)
    priority = 4 if any(
        rk.get("tier") == "hackathon" or rk.get("urgency") == "filling" for rk in to_send
    ) else 3

    log("\n=== roundup preview ===")
    log(title)
    log(message)

    if args.dry_run:
        log("\n--dry-run: not sending, not updating seen.json.")
        return 0

    if not topic:
        log("NTFY_TOPIC not set (.env); cannot push.")
        return 2

    log(f"\nPushing roundup to {server}/{topic} ...")
    try:
        notify.publish_roundup(title, message, tags, topic, server, priority=priority)
    except Exception as e:  # noqa: BLE001
        log(f"push failed, not marking seen (will retry next run): {e}")
        return 1

    # Only mark seen after a successful push.
    for rk in to_send:
        r = by_id[rk["event_id"]]
        seen[rk["event_id"]] = {
            "first_notified": now.isoformat(),
            "event_date": r.get("start_at"),
            "tier": rk.get("tier"),
        }
    log(f"Pushed roundup ({len(to_send)} events).")

    if not args.keep_seen:
        state.save(state.prune(seen))
        log("Updated seen.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
