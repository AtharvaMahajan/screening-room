# ADR-0009: Use 1–5 whole-star ratings and a separate `not_for_me` action

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Project owner
- **Related:** [recommendation-engine §4, §6](../architecture/recommendation-engine.md#4-stage-0-taste-profile) · [ADR-0008](0008-separate-user-title-relationship-tables.md)

## Context

The PRD leaves the rating scale open and merges "dismiss" with "not for me" (Journey B, FR-11). The two choices shape the schema, the UI and the engine's signals:
- A rating says how much a user liked something they **watched**.
- A "not for me" on a recommendation says the user doesn't want this title, without having watched it.
- A "skip" means "not right now" and carries no taste information.

Merging them would either pollute the taste profile or make temporary skips permanent.

## Decision

**Ratings**
- Optional **1–5 whole stars**, stored as `ratings.value smallint CHECK (value BETWEEN 1 AND 5)`, one current rating per user and title.
- Rating implies the user has seen the title, so rating an unwatched title also records a viewing event.
- Engine genre weights (*initial values*): **5★ +1.0, 4★ +0.5, 3★ 0, 2★ −0.5, 1★ −1.0**. 5★ and 4★ titles are also `favorite_neighbor` anchors (weights 1.0 and 0.6).

**`not_for_me`: a separate negative feedback action** (`title_feedback.kind = 'not_for_me'`)
- **The specific title is excluded** from recommendations until the user undoes it (from a "Not for me" list).
- **Its attributes contribute negatively to the taste profile:** each of the title's genres gets **−0.3** (*initial value*).
  - That's weaker than a 2★ rating, because the user hasn't watched it.
  - It's bounded, so one dismissal can't cancel a liked genre.
- It's independent of ratings. Both can exist for the same title.

**Skip** is ephemeral: the client excludes the title from the current discovery flow (`exclude_title_ids`) and logs a `skipped` result event. It **doesn't** change preferences. A persisted "not now" cooldown is deferred (E6).

## Alternatives considered

| Option | Why not chosen |
|---|---|
| 3-level dislike / like / love | Less effort, but less resolution than intentional viewers expect (Letterboxd-style habits) |
| Half-star or 10-point scales | More resolution than the engine uses, and noisier, inconsistent use across users |
| Low rating as the only negative signal | Requires watching. Can't capture "I don't want this" on a recommendation |
| A single "dismiss" that's both temporary and negative | Conflates two intents, and corrupts either the profile or the exclusion policy |
| `not_for_me` with no taste effect (exclusion only) | Throws away an explicit preference signal the user gave us |

## Consequences

**Positive**
- A familiar rating UI. Clear semantics for each action. Explicit negative feedback improves future shortlists.

**Negative / accepted costs**
- Users apply star scales differently (harsh vs generous raters). Per-user mean-centering is deferred (E7).
- Two negative-ish UI actions (skip, not for me) must be clearly labelled.

## Revisit when

Rating response rates are low (consider a lighter-weight input), dismissal data shows users want "not now" to persist (E6), or evaluation shows the −0.3 weight is too strong or too weak.
