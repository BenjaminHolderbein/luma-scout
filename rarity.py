"""Fortnite-style loot rarity, used as the single "how much should I care" signal.

The report is ordered chronologically, so tier can no longer carry priority
through grouping. Rarity carries it instead: one colour per event, readable at a
glance while scanning a timeline.

Rarity is computed here in code rather than asked of the model, because the
ranker's `score` is only meaningful WITHIN a tier -- a food event scoring 90 is
not "better" than a hackathon scoring 60 in Ben's ordering. Combining a tier
floor with the score gives one cross-tier number that respects his priorities:

    attention = tier_base + score * SCORE_WEIGHT

    hackathon  25 .. 100
    bigfree    18 ..  93
    food        5 ..  80

The bases encode Ben's priority (a weak hackathon outranks a weak dinner) while
the ceilings stay generous enough that an outstanding event in any tier can
still light up -- an excellent free-dinner night reaching Epic is the point of
having a scale at all.

These numbers are calibrated against a real week of rankings, not guessed. The
model scores hackathons high (65-95) and food moderate (35-75), so an earlier
version with large tier bases and a small score weight made a THIRD of the
report legendary, which drains the colour of any meaning. Letting the score
dominate and demanding 90+ for legendary gives a proper pyramid: about
3 legendary, 10 epic, 7 rare, 11 uncommon out of ~31 events.

If the model's calibration drifts and legendary starts showing up everywhere
again, retune the two constants below -- nothing else needs to change.

Hackathon coverage does NOT depend on this arithmetic: `is_protected()` exempts
them from the cutoff outright, so the guarantee survives any retuning.
"""
from __future__ import annotations

TIER_BASE = {"hackathon": 25, "bigfree": 18, "food": 5}
SCORE_WEIGHT = 0.75

# name, min attention, colour, short blurb
# `junk` is the won't-be-shown bucket: with MIN_RARITY=common (the default),
# commons appear as gray filler cards and junk is what the cutoff hides. It
# exists so "shown but gray" and "not shown" are separate rungs rather than
# one overloaded bottom tier.
LADDER = [
    ("legendary", 90, "#f0a02a", "Drop everything"),
    ("epic",      78, "#a44dd6", "Really worth it"),
    ("rare",      55, "#2f9fe8", "Solid pick"),
    ("uncommon",  30, "#3fb950", "Decent option"),
    ("common",    18, "#8b949e", "Filler"),
    ("junk",       0, "#5f5a52", "Skip it"),
]
ORDER = [name for name, *_ in LADDER][::-1]   # common -> legendary
COLOR = {name: color for name, _, color, _ in LADDER}
BLURB = {name: blurb for name, _, _, blurb in LADDER}


def attention(tier: str | None, score) -> int:
    try:
        s = max(0, min(100, int(score or 0)))
    except (TypeError, ValueError):
        s = 0
    return round(TIER_BASE.get(tier or "", 0) + s * SCORE_WEIGHT)


def of(tier: str | None, score) -> str:
    """Rarity name for a ranked event."""
    a = attention(tier, score)
    for name, floor, _, _ in LADDER:
        if a >= floor:
            return name
    return "junk"


def rank_index(name: str) -> int:
    """0 = common ... 4 = legendary. Handy for sorting and cutoffs."""
    return ORDER.index(name) if name in ORDER else 0


def is_protected(tier: str | None) -> bool:
    """Tiers that must never be dropped by a rarity cutoff.

    Hackathon coverage is meant to be exhaustive; a quality filter must not be
    able to quietly delete one.
    """
    return tier == "hackathon"


def meets(name: str, minimum: str) -> bool:
    return rank_index(name) >= rank_index(minimum)


def max_score_within(tier: str, ceiling: str) -> int:
    """Highest score that keeps `tier` at or below the `ceiling` rarity.
    Derived from the ladder so it survives retuning."""
    return max((s for s in range(101)
                if rank_index(of(tier, s)) <= rank_index(ceiling)), default=0)
