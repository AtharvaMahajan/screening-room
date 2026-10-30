# ADR-0002: PostgreSQL is the only stateful dependency; no Redis, Celery or microservices in the MVP

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Project owner
- **Related:** [ADR-0001](0001-modular-monolith.md) · [ADR-0005](0005-catalog-ingestion-cli.md) · [future-considerations](../architecture/future-considerations.md#infrastructure-and-operations)

## Context

Typical web stacks add Redis (cache, sessions, rate limiting) and a task queue (Celery with a broker) early. Each one adds a service to run, monitor and secure, and each adds failure modes. The MVP's needs are modest:
- metadata caching, which the local catalog with sync timestamps already provides
- session storage, a single indexed lookup
- background catalog work, which is an idempotent batch job that can run manually ([ADR-0005](0005-catalog-ingestion-cli.md))

## Decision

- **PostgreSQL** is the only stateful infrastructure component. It holds all application data, the metadata cache (catalog rows plus `*_synced_at`) and sessions.
- **No Redis** in the MVP. If an in-process TTL cache is ever needed (e.g. for repeated search queries), it's acceptable while there's a single API instance.
- **No Celery or message broker.** Catalog work runs as CLI commands. Scheduling is added later by running the same command from a scheduler.
- **No microservices** ([ADR-0001](0001-modular-monolith.md)).
- Local development needs only Docker Compose for PostgreSQL, alongside the app processes.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Redis for sessions and caching | Saves one indexed query per request, which isn't a bottleneck at this scale. Adds a service and a second source of truth |
| Celery + Redis/RabbitMQ for ingestion | A broker and worker fleet for a job that's naturally a resumable batch command |
| FastAPI `BackgroundTasks` for catalog work | Work is lost on restart and competes with request threads. Acceptable later for tiny best-effort tasks, but not as the ingestion mechanism |
| Postgres-backed job queue (e.g. `SELECT … FOR UPDATE SKIP LOCKED`) | A reasonable first step *when* durable async work appears. Not needed yet |

## Consequences

**Positive**
- Minimal operational surface. One backup target. Simple local setup.
- Every piece of state can be queried and is transactional.

**Negative / accepted costs**
- In-process limits and caches assume a single API instance.
- No durable async work. Anything user-triggered must be synchronous or best-effort until a queue exists.

## Revisit when

- More than one API instance needs shared rate limiting or caching.
- A user-triggered task must run reliably in the background (e.g. sending email).
- Measured database load from sessions or caching becomes significant.
