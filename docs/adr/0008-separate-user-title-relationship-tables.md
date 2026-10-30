# ADR-0008: Model each user–title relationship in its own table

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Project owner
- **Related:** [data-model §3.3–3.5, §5](../architecture/data-model.md#5-usertitle-state-rules-m3m4) · [ADR-0009](0009-ratings-and-not-for-me.md)

## Context

A user can relate to a title in several ways: favorite, saved to the watchlist, watched (possibly several times), rated, or marked `not_for_me`. PRD §10 warns against collapsing these into one ambiguous status field without evaluating the tradeoffs. The relationships aren't mutually exclusive (a watched title can be rated and later marked `not_for_me`). They also have different cardinalities (rewatches) and different lifecycles.

## Decision

Use separate tables, each with its own keys and constraints:

| Table | Key | Notes |
|---|---|---|
| `user_favorite_titles` (profile) | PK (user_id, title_id) | Up to 10, enforced by the service |
| `watchlist_items` | PK (user_id, title_id) | Prevents duplicates (FR-05) |
| `viewing_events` | Surrogate id | Multiple per title (rewatches). Optional `watched_on` |
| `ratings` | PK (user_id, title_id) | One current rating. `CHECK 1..5` ([ADR-0009](0009-ratings-and-not-for-me.md)) |
| `title_feedback` | PK (user_id, title_id) | `kind IN ('not_for_me')`, extensible |

Cross-table rules live in services and run in one handler-owned transaction:
- marking watched removes the watchlist entry
- rating an unwatched title creates a viewing event
- every action can be undone

A single service query assembles "my state for this title" for the UI.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| One `user_titles` row with a `status` enum | Can't represent combinations or rewatches. Status transitions become ambiguous |
| One `user_titles` row with nullable columns (`in_watchlist`, `watched_at`, `rating`, `dismissed_at`) | A sparse "nullable soup" that mixes lifecycles. Rewatch history is lost. Constraints get awkward |
| Generic event log as the only store (state derived from events) | Flexible, but every read becomes an aggregation. Too heavy for the MVP. `rec_result_events` already covers analytics |

## Consequences

**Positive**
- Each relationship has precise constraints and clear semantics. History is kept where it matters (viewing events).
- The engine treats each relationship as its own signal.

**Negative / accepted costs**
- Showing a title's full user state needs several lookups (cheap, indexed by `(user_id, title_id)`).
- Rules that span tables are enforced in services, not the database.

## Revisit when

A new relationship type appears that doesn't fit this pattern, or the multi-table "my state" query shows up in latency measurements.
