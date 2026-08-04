You are building Ben's WEEKLY San Francisco event report, delivered Monday
morning. Follow his preferences file exactly — it defines three strict priority
tiers, a hard exclude, within-tier tie-breakers, and a food rubric.

## Your task

For EACH candidate event below:

1. Decide the single tier it maps to (its HIGHEST-matching tier):
   `hackathon` > `bigfree` > `food`.
   - Matches none of the three → `"tier": "none"` (it will be dropped).
   - Defense/military/weapons → `"tier": "excluded"`.
   - **If the event is a hackathon, the tier is `hackathon`. Always.** Never
     assign a hackathon to another tier or to `none` because it looks small,
     niche, paid, or low-quality — that is the one failure Ben will notice.
     Candidates carry `is_hackathon_hint: true` when the pipeline detected
     hackathon language; treat that as strong evidence, but you may overrule it
     if the event is clearly not one (the hint matches on titles alone and
     occasionally catches things like a "dog-a-thon").
2. Give it a `score` 0–100, used only to order events WITHIN a tier. Apply the
   within-tier nudges: free beats paid, field-relevance, good-room signal, RSVP
   urgency, SF proper over the wider Bay Area.
3. Set `urgency`: `"none"`, `"filling"` (near capacity / limited spots),
   `"waitlist"`, or `"sold_out"`.
4. Write `summary`: 1–2 sentences of plain text that LEAD with the concrete hook
   (free dinner / prize pool / who's in the room), then what it is. No hype.
5. `hook`: a ≤6-word phrase for the headline (e.g. "Free dinner + open bar",
   "24hr hackathon, $5k prizes").
6. `why`: ≤12 words on why it matched (for Ben's debugging).

For tier 2 (`bigfree`), require BOTH halves: it must be free to attend AND
genuinely big or high-draw. A free twelve-person meetup is not tier 2.

Honor the food rubric strictly: `food` only if food or drink is plausibly
PROVIDED FREE. A cash bar or pay-for food does not qualify.

Some candidates come from Eventbrite or Meetup and have thin or missing
descriptions. Judge them on the information present — do not invent details, and
do not promote an event to a tier on the assumption that food or scale is
implied. When there is genuinely nothing to go on, `none` is the right answer
(except for hackathons, which are always included).

## Output format

Return ONLY a JSON array (no prose, no code fence), one object per event, in ANY
order, using exactly these keys:

[
  {"event_id":"evt-...","tier":"food","score":86,"urgency":"filling",
   "hook":"Free dinner + DJ","summary":"Free dinner, open bar and a DJ after YC Startup School Day 1; founder crowd.","why":"free food, YC crowd"}
]

Include every candidate exactly once (even the `none` and `excluded` ones — the
code filters those out). Do not invent events that aren't in the input.

---

## Ben's preferences

{PREFERENCES}

---

## Candidate events (JSON)

{EVENTS_JSON}
