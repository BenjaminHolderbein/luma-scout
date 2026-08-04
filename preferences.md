# Ben's event preferences

Ben Holderbein is an MSDS grad student at USF, based in San Francisco, with
fully open availability. This is a WEEKLY Monday-morning report: it should let
him plan the whole week in one sitting.

## Priority tiers (STRICT, highest first)

An event maps to the **highest** tier it matches. Every event in a higher tier
ranks above every event in a lower tier.

### 1. 🛠️ Hackathon — *be exhaustive*

Hackathons, buildathons, build weekends, hack nights, jams, datathons, sprints —
anything where people build and ship something, usually competitively, usually
with prizes.

**This tier is about coverage, not taste.** Ben wants to know about EVERY
hackathon happening in San Francisco, without exception. Do not drop one because
it looks small, unpolished, off-topic, paid, or unappealing. If it is a
hackathon in or near SF, it goes in the report. Score it low if it's weak — but
list it. A missed hackathon is the single worst failure this report can have.

Hackathons run on a 60-day horizon (the rest of the report is 7 days) because
they need registration lead time. Include them every week until they happen.

### 2. ⭐ Big & free

**Large events that are free to attend.** Both halves matter:

- *Free* — no ticket cost. Free-with-registration and free-with-approval count.
  A paid event does NOT belong in this tier no matter how big it is.
- *Big* — real scale or real draw. Signals: high guest count, a well-known host
  (frontier AI lab, major company, big-name accelerator or VC), a named speaker
  people would recognize, or conference/summit/demo-day/launch framing.

**And it must be Ben's world**: tech, AI/ML, data, startups/founders, or
engineering. General city culture — street fairs, block parties, food/music
festivals, concerts, museum nights, civic celebrations — is `none` no matter
how big and free it is. "Downtown First Thursdays" is the canonical wrong
answer here: huge, free, and not this report's job.

The idea is the events Ben would kick himself for missing — a big room in his
field he can walk into for nothing. A twelve-person meetup is not this tier,
however nice. If it's free but small, it belongs in tier 3 (if food is
provided) or nowhere.

### 3. 🍕 Free food & drink

Food and/or drink is **provided free** at an event that is **free to attend**:
dinner served, open bar, bites/apps, catered lunch, complimentary happy-hour
drinks. See the food rubric below. Both halves required — a paid ticket with
free canapés is not a free meal.

**No field-relevance requirement.** Unlike tier 2, this tier is about the free
meal, not the room. A non-tech event qualifies as long as attending costs
nothing and the food or drink is genuinely provided — so a big city event
that fails tier 2's tech scoping still lands HERE if it feeds you for free.
Only events that are neither in Ben's field nor feeding him are `none`.

An event matching **none** of these three → **drop it** (`"tier": "none"`).

## Hard exclude

- **Defense / military / weapons** events → always drop (`"tier": "excluded"`),
  even if it is a hackathon. This is the one thing that overrides tier 1.
  Dual-use / grey-area tech (general robotics, security research, gov-adjacent
  civic tech) is fine.

## Ranking signals within a tier (soft, in priority order)

1. **Free admission beats paid** (applies to tier 1 — tiers 2 and 3 are free
   by definition).
2. **Relevance to Ben's field** — AI/ML, LLMs, agents, evals, data science,
   analytics, MLOps, startups/founders, applied engineering.
3. **Signal of a good room** — notable hosts, companies, or speakers; a real
   crowd; substance over a giant impersonal mixer.
4. **RSVP urgency** — near-capacity, filling fast, or waitlist-forming events get
   a nudge so Ben can act in time.
5. **SF proper beats the wider Bay Area.** Peninsula/East Bay events are only
   worth the trip for hackathons.

## Food rubric (for tier 3 — the fuzziest call)

- COUNTS: "dinner provided", "open bar", "drinks & bites", "food and drinks
  served", "catered", "happy hour" (drinks implied free), "pizza/snacks
  provided", "breakfast/lunch included".
- Does NOT count: "cash bar", "drinks available for purchase", "food trucks on
  site" (pay), "no-host bar", or an event that merely happens at a bar or
  restaurant with no sign anything is provided.
- If genuinely ambiguous, do NOT put it in the food tier.

## Data quality notes

Events come from Luma, Cerebral Valley, Devpost, Y Combinator, AGI House,
Hack Club, MLH, Eventbrite, and Meetup, so quality varies:

- **Descriptions may be missing or truncated**, especially from Eventbrite and
  Meetup. Judge on what you have; don't invent details.
- **Devpost lists a submission period, not a start time.** Treat its dates as a
  range, and never call such an event "sold out" or "filling".
- Some listings are recruiting spam or paid workshops dressed up as networking
  ("1 Day Training", "Bootcamp", pitch events charging admission). These are
  tier `none` unless they genuinely fit a tier.

## Tone for summaries

Terse and useful. Lead with the concrete hook Ben cares about (the free dinner,
the prize pool, who's in the room), then one line on what it is. No hype.
