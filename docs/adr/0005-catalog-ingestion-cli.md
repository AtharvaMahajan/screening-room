# ADR-0005: Populate the catalog with an idempotent two-phase ingestion CLI, run manually

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Project owner
- **Related:** [catalog-ingestion](../architecture/catalog-ingestion.md) · [ADR-0002](0002-postgresql-only-infrastructure.md) · [ADR-0003](0003-local-candidate-pool.md) · [ADR-0006](0006-sync-sqlalchemy-handler-owned-transactions.md)

## Context

The local candidate pool ([ADR-0003](0003-local-candidate-pool.md)) needs a process that pulls titles from TMDB, keeps them up to date, records why each title is in the pool, and can be re-run safely. Scheduling can come later. Requirements: idempotent on TMDB IDs, sync timestamps, metadata updates, a modest start that can grow, and no TMDB calls on the recommendation path.

## Decision

- A CLI in the same codebase: `python -m screening_room.jobs ingest | refresh | report`, **run manually** at first.
- A **declarative, versioned seed plan** (typed Python): sources for popular, top-rated, per-genre, per-decade and per-language lists, for movies and TV, with page quotas and vote-count floors. Growing the pool means editing the plan.
- **Two phases:**
  1. **Discover:** upsert summary rows and `candidate_pool_memberships`, recording which source and run each title came from.
  2. **Hydrate:** fetch details with credits and the **TMDB recommendation list**, then *replace* genres, credits and `provider_title_recommendations` in **one transaction per title**.
- **Idempotency:** every write is an upsert on `(provider, media_type, provider_id)`, or a wholesale replace of a title's child rows.
- **Resumability:** commit per title. Re-running continues with whatever is still summary-only or stale.
- **Tracking:** `ingestion_runs` (params, status, counts). Per-title `first_ingested_at`, `summary_synced_at`, `details_synced_at`, error fields and `provider_status`. One TTL (14 days).
- **Concurrency:** HTTP in a small thread pool behind a token bucket. **Database writes on the main thread only**, and **no transaction held while waiting on HTTP**.
- **Safety flags:** `--dry-run`, `--max-requests`, `--max-titles`.
- **`report`** prints composition by media type, genre, decade and language, plus staleness, errors and recommendation-list coverage.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Celery beat / worker | Needs a broker ([ADR-0002](0002-postgresql-only-infrastructure.md)). A batch job doesn't need a worker fleet |
| Run ingestion inside the API process (startup or background tasks) | Couples batch work to request serving. Lost on restart. Hard to observe |
| Single-phase ingestion (fetch details while paging lists) | Harder to resume and budget. Mixes list and detail concerns |
| TMDB daily ID export files | IDs only, with no metadata. Still needs detail calls, and suits full mirrors, which we don't want |

## Consequences

**Positive**
- Safe to re-run at any time. Easy to schedule later. Auditable runs.
- Recommendation relationships arrive in the same call as details, at no extra API cost.

**Negative / accepted costs**
- Manual runs until scheduling is added.
- A refresh re-fetches everything stale, rather than only changed titles (`/changes` endpoints deferred).

## Revisit when

Manual runs become a burden or production needs freshness guarantees (add scheduling), refresh volume grows (use `/changes`), or user-driven pool expansion (E9) needs on-demand ingestion.
