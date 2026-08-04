"""Rank candidates with Claude (headless `claude -p`, billed to the subscription).

Kept as a single subprocess call so the whole pipeline is one portable code path
whether it runs locally, in a cloud routine, or (with an API key) in CI."""
from __future__ import annotations

import json
import os
import subprocess

HERE = os.path.dirname(__file__)

# Fields the ranker actually needs (keeps the prompt small).
RANK_FIELDS = (
    "event_id", "source", "name", "when_local", "address", "city_state",
    "sf_proximity", "guest_count", "is_free", "price_display", "is_sold_out",
    "is_near_capacity", "spots_remaining", "waitlist_active", "categories",
    "hosts", "description", "also_on", "is_hackathon_hint",
)


def _read(name: str) -> str:
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def build_prompt(records: list[dict]) -> str:
    slim = [{k: r.get(k) for k in RANK_FIELDS} for r in records]
    events_json = json.dumps(slim, ensure_ascii=False, indent=1)
    return (
        _read("prompt.md")
        .replace("{PREFERENCES}", _read("preferences.md"))
        .replace("{EVENTS_JSON}", events_json)
    )


def _extract_array(text: str) -> list:
    text = text.strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON array in model output:\n{text[:500]}")
    return json.loads(text[start : end + 1])


def rank(records: list[dict], model: str = "sonnet", timeout: int = 1200) -> list[dict]:
    """Return list of {event_id, tier, score, urgency, hook, summary_md, why}."""
    prompt = build_prompt(records)
    proc = subprocess.run(
        ["claude", "-p", "--model", model, "--output-format", "json"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed ({proc.returncode}):\n{proc.stderr[:800]}")
    # --output-format json wraps the reply: {"result": "...", ...}
    try:
        result_text = json.loads(proc.stdout)["result"]
    except (json.JSONDecodeError, KeyError):
        result_text = proc.stdout  # fall back to raw
    return _extract_array(result_text)
