# Roadmap

**Status:** Draft for review · **Last updated:** 2026-10-30

## Principles

- **Thin vertical slices.** Each milestone ends with something usable end to end in the browser.
- **Recommendations early.** The first explained shortlist arrives in **M3**, before the full library (M4), and runs on onboarding genres and favorite titles. Later milestones feed it more signals rather than building it last.
- **Incremental abstractions.** Each milestone builds only the tables and abstractions it needs ([project-structure.md §10](architecture/project-structure.md#10-abstractions-deliberately-not-built-yet)).
- **Evidence as we go.** Each milestone leaves behind tests, measurements or reports that can be cited honestly (PRD §17).

## Milestones

### M0: Product and technical definition (current)
- **Scope:** PRD review, architecture overview, data model, ingestion and engine design, security design, ADRs, this roadmap.
- **Done when:** the project owner has reviewed and accepted the documentation in `docs/`.

### M1: Foundation
- **Scope:**
  - Repo tooling. Docker Compose for PostgreSQL.
  - FastAPI app factory, config, `db.py` with the session dependency and `end_read_transaction`, health endpoint.
  - Alembic baseline with the naming convention.
  - React shell: Vite, router, TanStack Query, generated API client, CSRF bootstrap.
  - CI: ruff, mypy, pytest on Postgres, eslint, tsc, vitest, types drift check.
  - The transaction-location and sync-handler guard tests.
  - **Auth:** register, login, logout, `GET /api/auth/session`, CSRF middleware, Origin check. `users` and `user_sessions` tables.
- **Not in scope:** password reset, rate limiting (M5), any catalog work.
- **Done when:**
  - A user can register, sign in and sign out in the browser.
  - CSRF and Origin tests cover anonymous, authenticated, expired-session and cross-origin cases.
  - CI is green on a fresh clone.
  - Local setup is documented in one page.

### M2: Catalog and starter pool
- **Scope:**
  - `CatalogProvider` + TMDB adapter + `FakeProvider`; mapper tests on recorded JSON.
  - Internal genre taxonomy and mapping.
  - Catalog tables, including `provider_title_recommendations`. `ingestion_runs`, pool memberships.
  - `ingest`, `refresh` and `report` commands with the `starter-v1` seed plan.
  - `GET /api/titles/{id}` with read-through (no connection held during TMDB calls). Title detail page.
  - `import-linter` contracts.
- **Not in scope:** TMDB search (M4).
- **Done when:**
  - The pool holds ~1,000–2,000 titles.
  - The idempotency, resumability and read-through tests pass.
  - `report` shows reasonable spread across genres, decades, languages and media types, including recommendation-list coverage. The first real report is saved as evidence.
  - Detail pages for pool titles work with TMDB unreachable.

### M3: First end-to-end recommendations
- **Scope:**
  - **Onboarding** (skippable): liked and avoided genres, plus **up to 10 favorite titles** picked from the local pool via local title search (`GET /api/titles?q=`) and "popular in your genres" suggestions. Preferences editable later (FR-02).
  - `user_genre_preferences`, `user_favorite_titles`, `rec_requests`, `rec_results`.
  - **Engine v1:** taste profile (genres + favorites), whole-pool retrieval, the M3 eligibility rules, scoring with affinity, **`favorite_neighbor`**, quality and popularity, all-genre diversity rules, explanations, cold start.
  - **Discover page:** context controls (movie / TV / either, genre direction, max runtime), 5 result cards with reasons, "show me more", ephemeral skip, open detail.
  - Engine fixtures, personas, invariant, golden and determinism tests.
  - Server-side latency measurement for the recommendation endpoint.
- **Not in scope:** saving, watched, ratings, `not_for_me` (M4). Persisted skip.
- **Done when:**
  - A new user can sign up, pick genres and a couple of favorites, and see 5 explained recommendations **in under 2 minutes** (timed walkthrough).
  - The sci-fi-fan persona shows `favorite_neighbor` reasons, and the no-neighbors persona falls back cleanly.
  - All invariants hold. Output is deterministic under input shuffling.
  - A latency baseline is recorded.

### M4: Library and feedback loop
- **Scope:**
  - TMDB search (`GET /api/search`). Favorites can now include non-pool titles, hydrated on selection.
  - Watchlist, viewing events (incl. rewatch and optional date), 1–5★ ratings, `not_for_me` with an undo list. State rules from [data-model.md §5](architecture/data-model.md#5-usertitle-state-rules-m3m4).
  - Actions on recommendation cards: save, watched, rate, not for me, skip. `rec_result_events` attribution.
  - Library views (watchlist, history, ratings) with a media-type filter (FR-12).
  - The engine consumes library signals: the M4 eligibility rules, the rating, watched, watchlist and `not_for_me` weights, and 4–5★ titles as anchors.
  - Account deletion with password re-entry.
- **Done when:**
  - All PRD §16 acceptance criteria are met (table below).
  - Rating a title and marking another `not_for_me` measurably changes the next shortlist (integration test).
  - Cross-user authorization tests pass for every library endpoint.

### M5: Hardening and first deployment
- **Scope:**
  - Responsive and accessibility pass.
  - Structured logs and metrics (API errors, provider failures and retries, recommendation latency, result actions).
  - Security review, login and registration rate limiting, security headers and CSP.
  - Load test of `POST /api/recommendations` against the p95 target.
  - TMDB attribution page and terms review (gate).
  - Choose a hosting target and deploy. Run ingestion against production.
  - Demo script.
- **Done when:** a measured p95 is recorded, the security checklist is complete, the TMDB terms are confirmed for the intended use, the app is publicly reachable, and the demo walkthrough works.

### M6+: Evidence-driven enhancements
- Enhancements E1–E12 from the [enhancement ladder](architecture/recommendation-engine.md#16-enhancement-ladder), and P1 product features (reviews FR-13, stats FR-14). Each starts only when its trigger is met and is evaluated against the fixtures and logged outcomes.

## PRD §16 acceptance criteria → milestones

| # | Criterion | Milestone |
|---|---|---|
| 1 | Register, sign in, private profile | M1 (account deletion in M4) |
| 2 | Search for and view movie/TV details | Details M2 · Search M4 |
| 3 | Watchlist add/remove, mark watched | M4 |
| 4 | Rate or dismiss a recommendation | M4 (ephemeral skip from M3) |
| 5 | Small shortlist with optional session context | **M3** |
| 6 | Results filtered against watched and dismissed titles by documented rules | Rules and favorites in M3 · Watched and `not_for_me` in M4 |
| 7 | Each recommendation has a truthful reason | **M3** |
| 8 | Deterministic ranking for a fixed fixture | **M3** |
| 9 | Business rules tested; runs locally from docs | M1 onward |
| 10 | Demo from onboarding to selecting and saving a recommendation | M4 (saving needs the watchlist) |

## Sequencing rationale

- **Catalog before recommendations** (M2 → M3): the engine needs a real pool, and the pool needs the adapter and mapper anyway.
- **Recommendations before the library** (M3 → M4): this validates the core promise early, and the favorites and `favorite_neighbor` signals give real title-level personalization without the full library. M4 then adds signals to a working pipeline instead of building the pipeline last.
- **Search moves to M4:** M3's favorites picker uses local pool search, which keeps M3 free of a second TMDB-backed flow.
