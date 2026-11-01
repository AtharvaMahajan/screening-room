# Open Questions and Review Findings

**Status:** Draft for review · **Last updated:** 2026-10-30

This file tracks the PRD's open questions (§15) and the issues found during the Milestone 0 review, each with its current status. Labels are defined in [docs/README.md](../README.md#status-vocabulary).

## A. PRD §15 open questions

| # | Question | Status | Resolution | Recorded in |
|---|---|---|---|---|
| Q1 | Onboarding: favorite titles, genres or both? | **Decided** | Both, in M3. Liked and avoided genres plus up to 10 favorite titles, all skippable | [roadmap](../roadmap.md), [engine §4](recommendation-engine.md#4-stage-0-taste-profile) |
| Q2 | What does "recently watched" mean? | **Decided** (v1) | No time decay in v1, because a new product's history is all recent. Decay is E1 | [engine §4](recommendation-engine.md#4-stage-0-taste-profile) |
| Q3 | Distinguish liked / disliked / unrated watched? | **Decided** | Optional 1–5★ ratings. Watched-unrated is a weak positive. `not_for_me` is a separate action | [ADR-0009](../adr/0009-ratings-and-not-for-me.md) |
| Q4 | Which session controls are useful without feeling like a form? | **Validate** | v1: media type, genre direction (≤3), max runtime (movies). All optional. Mood presets deferred (E3). Check in usability tests | [engine §3](recommendation-engine.md#3-inputs) |
| Q5 | When is a TV show "watched"? | **Decided** | Show-level, explicitly marked by the user (the PRD's MVP assumption) | PRD |
| Q6 | What metadata and image use does TMDB permit? | **Decided** (M5e) | Non-commercial use under TMDB's free license; logo and verbatim notice on every page; data cached at most 6 months (`prune` + `refresh`). Review: [m5e-tmdb-terms.md](../evidence/m5e-tmdb-terms.md) | [roadmap M5](../roadmap.md#m5-hardening-and-first-deployment) |
| Q7 | Is streaming availability essential for the first public release? | **Open** | Recommendation: make it the **first question in user testing**. It directly affects the "less browsing" promise | [future-considerations](future-considerations.md#catalog) |
| Q8 | How do dismissed titles re-enter recommendations? | **Decided** | `not_for_me`: excluded until the user undoes it. Skip: ephemeral, only for the current discovery flow. Persisted `not_now` is E6 | [ADR-0009](../adr/0009-ratings-and-not-for-me.md) |

## B. Review findings

| # | Finding | Status | Resolution |
|---|---|---|---|
| R1 | Selective persistence can't supply a recommendation candidate pool; live provider candidates conflict with determinism, latency and outage tolerance | **Decided** | Local seeded pool, local-only recommendation path ([ADR-0003](../adr/0003-local-candidate-pool.md)) |
| R2 | "Dismiss" and "not for me" were merged | **Decided** | Separate: `not_for_me` (persisted, negative) and skip (ephemeral) ([ADR-0009](../adr/0009-ratings-and-not-for-me.md)) |
| R3 | "Mood" isn't provider metadata | **Decided** | v1 uses genre direction. Mood presets later as explicit curated mappings (E3) |
| R4 | TV runtime is unreliable | **Decided** | Runtime filter applies to movies only, and the UI says so. Unknown movie runtime is excluded when a max is set |
| R5 | Are onboarding favorites ratings? | **Decided** | No. Separate `user_favorite_titles` profile data, excluded from recommendations, a +1.0 genre signal and an anchor |
| R6 | TMDB movie and TV genre lists differ | **Decided** | Internal genre taxonomy with provider mapping ([ADR-0004](../adr/0004-tmdb-provider-adapter.md)) |
| R7 | The latency target implicitly allowed synchronous provider calls | **Decided** | p95 < 1.5 s applies to `POST /api/recommendations` only, which never calls TMDB |
| R8 | Rating scale unspecified | **Decided** | 1–5 whole stars ([ADR-0009](../adr/0009-ratings-and-not-for-me.md)) |
| R9 | Auth details unspecified | **Decided** | Sessions + HttpOnly cookies + signed double-submit CSRF ([ADR-0007](../adr/0007-session-auth-and-csrf.md)) |
| R10 | Transactions vs SQLAlchemy autobegin | **Decided** | Handler-owned transactions. No connection held across TMDB calls ([ADR-0006](../adr/0006-sync-sqlalchemy-handler-owned-transactions.md)) |
| R11 | "First TMDB genre is primary" was an unsafe assumption | **Decided** | The diversity rules count all genres. `position` is for display only ([engine §8](recommendation-engine.md#8-stage-4-ranking-and-diversity)) |
| R12 | "Show me more" undefined | **Decided** | `exclude_title_ids` (≤100) on the next request |
| R13 | Repetition across sessions | **Deferred** | Impression fatigue (E5) |
| R14 | Undo actions | **Decided** | Every library and profile action can be undone (M4) ([data-model §5](data-model.md#5-usertitle-state-rules-m3m4)) |
| R15 | Watched → watchlist transition | **Decided** | Marking watched removes the watchlist entry in the same transaction |
| R16 | Rewatches and watch dates | **Decided** | Multiple `viewing_events`; optional `watched_on` |
| R17 | Account deletion missing from the FRs | **Decided** | Hard delete with cascade in M4, with password re-entry |
| R18 | Adult content | **Decided** | Always excluded from the pool and from search results |
| R19 | Locale / region | **Decided** | `en-US` metadata for the MVP |
| R20 | Attributing actions to recommendations | **Decided** | `rec_result_id` on library rows plus `rec_result_events` |
| R21 | Raw vote average as a quality proxy | **Decided** | Bayesian average with a vote-count prior |
| R22 | Unreleased titles in popular lists | **Decided** | Pooled, but excluded by eligibility until released |
| R23 | Password reset / email verification | **Deferred** | Needs email infrastructure ([future-considerations](future-considerations.md#security-and-accounts)) |
| R24 | Login rate limiting | **Decided** (M5) | Required before public deployment |
| R25 | TV "News" and "Talk" genres | **Decided** | Not seeded into the pool |

## C. Still open

| # | Question | Needed by | Owner |
|---|---|---|---|
| O1 | TMDB terms for the intended use (Q6) | **Decided** 2026-10-31: free, non-commercial portfolio project | Project owner |
| O2 | Is streaming availability needed for the first public release? (Q7) | First user tests (after M3/M4) | Project owner |
| O4 | Hosting target for deployment | M5 | Project owner |
| O5 | Do the v1 session controls help, or feel like a form? (Q4) | Usability tests after M3 | Project owner |

## D. Resolved

| # | Question | Status | Resolution |
|---|---|---|---|
| O3 | Styling approach: Tailwind (default) or CSS Modules | **Decided** (M1) | Tailwind CSS, via its Vite plugin. Components use utility classes; `src/index.css` holds only the import and page-wide defaults |
