#!/usr/bin/env python3
"""luma-scout orchestrator -- weekly SF event report.

Local (ranks via headless `claude -p`):
  python run.py                 # full run: collect -> rank -> report -> push
  python run.py --dry-run       # everything except push (still writes docs/)
  python run.py --test-notify   # send one canned teaser to your topic
  python run.py --limit N       # only enrich the first N Luma candidates (fast test)

Cloud routine (ranks in the agent's own turn -- no nested claude):
  python run.py --prepare       # collect -> candidates.json + rank_prompt.txt
  <agent reads rank_prompt.txt, writes ranked.json>
  python run.py --deliver       # ranked.json -> docs/ + ntfy push + seen.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import notify
import rank as rank_mod
import report as report_mod
import sources
import state

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = os.path.join(HERE, "candidates.json")
RANK_PROMPT = os.path.join(HERE, "rank_prompt.txt")
RANKED = os.path.join(HERE, "ranked.json")
STATUS = os.path.join(HERE, "source_status.json")

TIER_ORDER = {"hackathon": 0, "bigfree": 1, "food": 2}
DROP_TIERS = {"none", "excluded"}
DEFAULT_REPORT_URL = "https://benjaminholderbein.github.io/luma-scout/"


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


def gather(window: int, hack_window: int, limit: int = 0) -> tuple[list[dict], dict]:
    """Collect from every source, then annotate against seen-state.

    Note what this deliberately does NOT do: filter out events Ben has already
    been told about. This is a weekly report of the coming week, not a diff --
    an event surfaced three weeks early must still appear the week it happens.
    `seen.json` only decides whether something is badged NEW.
    """
    now = datetime.now(timezone.utc)
    log("Collecting from all sources...")
    records, status = sources.collect(now, window, hack_window, log=log, limit=limit)

    seen = state.load()
    for rec in records:
        rec["_is_new"] = rec["event_id"] not in seen
        rec["is_hackathon_hint"] = sources.looks_like_hackathon(rec)
    log(f"  {sum(1 for r in records if r['_is_new'])} of {len(records)} are new since last report")
    return records, status


def deliver(records: list[dict], ranked: list[dict], env: dict, dry: bool,
            keep_seen: bool, status: dict | None = None) -> int:
    """Select -> render report -> push teaser -> persist state."""
    now = datetime.now(timezone.utc)
    seen = state.load()
    cap = int(env.get("MAX_PER_REPORT", "40"))
    topic = env.get("NTFY_TOPIC")
    server = env.get("NTFY_SERVER", "https://ntfy.sh")
    report_url = env.get("REPORT_URL", DEFAULT_REPORT_URL)

    by_id = {r["event_id"]: r for r in records}
    selected = [rk for rk in ranked
                if rk.get("tier") not in DROP_TIERS and rk.get("event_id") in by_id]
    selected.sort(key=lambda r: (TIER_ORDER.get(r.get("tier"), 9), -int(r.get("score") or 0)))

    # Hackathons are never capped away -- exhaustive coverage is the point.
    hacks = [rk for rk in selected if rk.get("tier") == "hackathon"]
    rest = [rk for rk in selected if rk.get("tier") != "hackathon"]
    to_show = hacks + rest[:max(0, cap - len(hacks))]
    extra = len(selected) - len(to_show)

    pairs = [(by_id[rk["event_id"]], rk) for rk in to_show]
    counts: dict[str, int] = {}
    for _, rk in pairs:
        counts[rk["tier"]] = counts.get(rk["tier"], 0) + 1
    log(f"\nReport: {len(to_show)} events {counts} ({len(ranked)} classified, {extra} over cap)")

    html_text = report_mod.build(pairs, now, status=status, extra_count=extra)
    index, archive = report_mod.write(html_text, now)
    log(f"Wrote {os.path.relpath(index, HERE)} and {os.path.relpath(archive, HERE)}")

    title, message, tags = notify.build_teaser(pairs, report_url)
    log("\n=== teaser preview ===")
    log(title)
    log(message)

    if dry:
        log("\n--dry-run: not pushing, not updating seen.json.")
        return 0
    if not to_show:
        log("\nNothing qualifies; not pushing.")
        return 0
    if not topic:
        log("NTFY_TOPIC not set; cannot push.")
        return 2

    priority = 4 if any(rk.get("tier") == "hackathon" or rk.get("urgency") == "filling"
                        for rk in to_show) else 3
    log(f"\nPushing teaser to {server}/{topic} ...")
    try:
        notify.publish_roundup(title, message, tags, topic, server,
                               priority=priority, click=report_url)
    except Exception as e:  # noqa: BLE001
        log(f"push failed, not marking seen (will retry next run): {e}")
        return 1

    for rk in to_show:  # only mark seen after a successful push
        r = by_id[rk["event_id"]]
        # Prune by whichever end of the event is later: a Devpost submission
        # window can start months before it closes, and pruning on the start
        # would forget a still-open hackathon and re-badge it NEW every week.
        dates = [d for d in (r.get("start_at"), r.get("end_at")) if d]
        seen.setdefault(rk["event_id"], {
            "first_notified": now.isoformat(),
            "event_date": max(dates) if dates else None,
            "tier": rk.get("tier"),
        })
    log(f"Pushed teaser ({len(to_show)} events in the report).")
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
    ap.add_argument("--prepare", action="store_true",
                    help="cloud stage 1: write candidates.json + rank_prompt.txt")
    ap.add_argument("--deliver", action="store_true",
                    help="cloud stage 2: read ranked.json, render report + push")
    args = ap.parse_args()

    env = load_env()
    window = int(env.get("WINDOW_DAYS", "7"))
    hack_window = int(env.get("HACKATHON_WINDOW_DAYS", "30"))

    if args.test_notify:
        if not env.get("NTFY_TOPIC"):
            log("NTFY_TOPIC not set."); return 2
        notify.send_test(env["NTFY_TOPIC"], env.get("NTFY_SERVER", "https://ntfy.sh"),
                         env.get("REPORT_URL", DEFAULT_REPORT_URL))
        log("Sent test teaser.")
        return 0

    # --- Cloud stage 1: prepare candidates for the agent to rank ---
    if args.prepare:
        records, status = gather(window, hack_window, args.limit)
        with open(CANDIDATES, "w") as f:
            json.dump(records, f)
        with open(STATUS, "w") as f:
            json.dump(status, f)
        if records:
            with open(RANK_PROMPT, "w") as f:
                f.write(rank_mod.build_prompt(records))
        log(f"\nPrepared {len(records)} candidates -> candidates.json"
            + (", rank_prompt.txt" if records else " (nothing found; skip ranking + deliver)"))
        return 0

    # --- Cloud stage 2: deliver using the agent-produced ranked.json ---
    if args.deliver:
        with open(CANDIDATES) as f:
            records = json.load(f)
        if not records:
            log("No candidates; nothing to deliver."); return 0
        with open(RANKED) as f:
            ranked = json.load(f)
        status = {}
        if os.path.exists(STATUS):
            with open(STATUS) as f:
                status = json.load(f)
        return deliver(records, ranked, env, dry=False,
                       keep_seen=args.keep_seen, status=status)

    # --- Local path: gather -> rank via claude -p -> deliver ---
    records, status = gather(window, hack_window, args.limit)
    if not records:
        log("Nothing found. Done."); return 0
    log(f"\nRanking {len(records)} candidates with claude ({env.get('RANK_MODEL', 'sonnet')})...")
    ranked = rank_mod.rank(records, model=env.get("RANK_MODEL", "sonnet"))
    return deliver(records, ranked, env, dry=args.dry_run,
                   keep_seen=args.keep_seen, status=status)


if __name__ == "__main__":
    raise SystemExit(main())
