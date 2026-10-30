# Architecture Decision Records

An ADR records one **meaningful architectural decision**: its context, the options considered, what we chose, and the consequences we accept.

## What gets an ADR

A decision gets an ADR when at least one of these is true:
- It's hard or expensive to reverse (persistence model, transaction model, auth model).
- It shapes several modules or the whole system (architecture style, infrastructure).
- A reasonable engineer could have chosen differently, and the reasoning is worth keeping.

What does **not** get an ADR:
- **Conventions** (naming, PK types, enum representation, folder layout, library choices within an accepted stack). These live in [project-structure.md](../architecture/project-structure.md) and [data-model.md](../architecture/data-model.md).
- **Tunable parameters** (weights, quotas, TTLs). These live in configuration and are documented in the relevant architecture doc.
- **Ideas that aren't decided.** These go in [future-considerations.md](../architecture/future-considerations.md) or [open-questions.md](../architecture/open-questions.md).

## Process

- Copy [template.md](template.md) to `NNNN-short-title.md`, using the next number.
- A new ADR starts as **Proposed** and becomes **Accepted** once the project owner confirms it.
- Accepted ADRs aren't rewritten. To change a decision, write a new ADR that **supersedes** the old one, and set the old one's status to `Superseded by ADR-NNNN`. Fixing typos and links is fine.
- Each ADR has a **Revisit when** section naming the evidence that would reopen the decision.

## Index

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith with enforced module boundaries | Accepted |
| [0002](0002-postgresql-only-infrastructure.md) | PostgreSQL is the only stateful dependency; no Redis, Celery or microservices in the MVP | Accepted |
| [0003](0003-local-candidate-pool.md) | Local seeded candidate pool; the recommendation path is local-only | Accepted |
| [0004](0004-tmdb-provider-adapter.md) | TMDB behind a provider adapter, with a normalized catalog and internal genre taxonomy | Accepted |
| [0005](0005-catalog-ingestion-cli.md) | Idempotent two-phase catalog ingestion via a manually run CLI | Accepted |
| [0006](0006-sync-sqlalchemy-handler-owned-transactions.md) | Synchronous SQLAlchemy 2.0 with handler-owned transactions | Accepted |
| [0007](0007-session-auth-and-csrf.md) | Server-side sessions in HttpOnly cookies with signed double-submit CSRF | Accepted |
| [0008](0008-separate-user-title-relationship-tables.md) | Separate tables per user–title relationship | Accepted |
| [0009](0009-ratings-and-not-for-me.md) | 1–5 whole-star ratings and a separate `not_for_me` action | Accepted |
| [0010](0010-staged-deterministic-recommendation-pipeline.md) | Staged, deterministic recommendation pipeline with signal-derived explanations | Accepted |
