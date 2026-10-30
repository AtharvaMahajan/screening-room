# Future Considerations

**Status:** Draft for review · **Last updated:** 2026-10-30

Everything here is **Deferred**: deliberately outside the current scope, with the evidence or condition that should bring it back. Nothing in this file is a decision. When an item is taken up, it gets designed properly, and if it's significant, it gets an ADR.

## Infrastructure and operations

| Item | Why deferred | Revisit when |
|---|---|---|
| Redis (shared cache, rate limits, sessions) | PostgreSQL covers caching and sessions for one instance ([ADR-0002](../adr/0002-postgresql-only-infrastructure.md)) | More than one API instance needs shared rate limits or caches, or measured session-lookup load matters |
| Task queue (Celery / RQ / Dramatiq, or a Postgres-backed queue) | No user-triggered async work. Ingestion is an idempotent CLI | A user action needs reliable background work (e.g. email, large imports), or best-effort follow-ups keep getting lost |
| Scheduled ingestion | Manual runs are enough at this stage | Before public deployment, or when manual runs become a chore |
| Microservice extraction | One developer, one domain, shared transactions ([ADR-0001](../adr/0001-modular-monolith.md)) | A module needs independent scaling, deploy cadence or ownership |
| Read replicas, partitioning | Tiny data volumes | Measured database load |
| Image proxy / own CDN | TMDB's CDN serves images | Licensing or performance requires it |
| Async database access | Sync is simpler and enough ([ADR-0006](../adr/0006-sync-sqlalchemy-handler-owned-transactions.md)) | The thread pool saturates under measured load |

## Catalog

| Item | Revisit when |
|---|---|
| Pool growth beyond 2,000 titles | Coverage triggers in [catalog-ingestion.md §5](catalog-ingestion.md#5-sizing-and-growth) |
| Pool expansion from user anchors and unresolved neighbors (E9) | Neighbor coverage or user-title coverage is low |
| TMDB `/changes`-based incremental refresh | Refresh cost or rate limits become a concern |
| Per-type TTLs | Ongoing TV metadata is noticeably stale |
| Membership pruning | Stale memberships distort the pool |
| Keywords, collections, richer credits | E2, E3, E4 |
| Streaming availability ("where to watch"), FR-16 | **Product question, see [open-questions.md](open-questions.md).** TMDB's watch-provider data is the likely source, and it has its own attribution requirements |
| Localization and regions beyond `en-US` | Non-English or non-US audience |
| Episode or season-level TV tracking | User demand. The PRD says show-level for the MVP |
| Trigram or full-text local search | Pool size makes `ILIKE` slow |

## Recommendations

See the [enhancement ladder](recommendation-engine.md#16-enhancement-ladder): E1 time decay · E2 content similarity · E3 mood presets · E4 MMR and franchise cap · E5 impression fatigue · E6 persisted `not_now` · E7 genre IDF and rating mean-centering · E8 multi-source retrieval · E9 pool expansion · E10 collaborative filtering · E11 learning-to-rank · E12 LLM mood parsing.

Also deferred:
- a "revisit watched titles" context option
- negative anchors (titles similar to 1–2★ ratings)
- a TV episode-length runtime filter
- offline evaluation metrics (hit rate / NDCG on held-out ratings), once there's real data

## Product

| Item | Notes |
|---|---|
| Reviews (FR-13, P1) | `reviews` table; must-have-watched rule in the service |
| Viewing statistics (FR-14, P1) | Derived from `viewing_events` and `ratings` |
| PWA | After responsive web is solid |
| Social features, group voting (FR-15) | Out of scope per the PRD |

## Security and accounts

| Item | Revisit when |
|---|---|
| Password reset and email verification | Email infrastructure exists. Needed before broad public use |
| Sliding or idle session expiry, "log out other devices" | User demand. Needs throttled writes kept out of the read path |
| MFA, OAuth / social login | Product decision |
| Breached-password check | Before public launch, if feasible |

## Data and privacy

| Item | Revisit when |
|---|---|
| Retention window for recommendation logs (e.g. 12 months) | Before public launch. Document the policy either way |
| Personal data export | Requested by users or required by the jurisdiction served |
| Analytics pipeline beyond SQL over `rec_*` tables | SQL queries become insufficient |
