# ADR-0006: Use synchronous SQLAlchemy 2.0 with handler-owned transactions

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Project owner
- **Related:** [project-structure §5](../architecture/project-structure.md#5-request-handling-and-transaction-boundary) · [catalog-ingestion §10–11](../architecture/catalog-ingestion.md#10-failure-handling-rate-limiting-and-concurrency) · [ADR-0007](0007-session-auth-and-csrf.md)

## Context

FastAPI supports both sync and async handlers, and SQLAlchemy 2.0 supports both sync and async sessions. The workload is mostly small database queries, plus occasional TMDB calls on detail and search paths. The recommendation engine is CPU-bound Python.

Transaction ownership needs an explicit rule. A SQLAlchemy 2.0 Session **autobegins** a transaction on first use. The authentication dependency queries `user_sessions` before the handler runs, so a service that later calls `session.begin()` fails with "a transaction is already begun". Services calling other services would hit the same conflict.

External calls are a separate risk. Holding a transaction, and with it a pooled connection, open while waiting seconds for TMDB would tie up connections and keep transactions open needlessly.

## Decision

**Database access style**
- Use **synchronous SQLAlchemy 2.0**. The driver (psycopg 3 is the default proposal) is confirmed in M1.
- Every route that touches the database or TMDB is declared with **`def`**, so FastAPI runs it in its thread pool. **No synchronous database operations inside `async def` handlers.** A test fails if a non-allowlisted endpoint is a coroutine function.
- Size the connection pool explicitly relative to the thread pool (initial values: `pool_size=10`, `max_overflow=10`, against AnyIO's 40 threads).

**Transaction boundary: the request handler owns the transaction**
1. **One Session per request** (`get_session` dependency). It's yielded **without** `begin()`, and `close()` runs in `finally`.
2. Autobegin starts the transaction on first use. **Authentication dependencies and services share that session and transaction.**
3. **Services never call `begin()`, `commit()` or `rollback()`.** They may `flush()`.
4. **Write handlers call `session.commit()` exactly once,** after the service call succeeds and before returning the response.
5. **Read requests don't commit.**
6. **Uncommitted changes are rolled back when the session closes.**
7. The auth dependency is read-only: **no sliding expiry and no activity-based `last_seen_at` updates** in the MVP ([ADR-0007](0007-session-auth-and-csrf.md)).

**No transaction or connection held across external requests**
- Before calling TMDB, the handler (or the handler-level helper `catalog/read_through.py`) calls `end_read_transaction(session)`. This asserts there are no pending changes and ends the read-only transaction, which returns the connection to the pool.
- Data needed afterwards is converted to DTOs first. `current_user` returns a DTO, not an ORM object.
- After the external call, the write happens in a **short transaction** that commits immediately.
- The ingestion CLI follows the same rule. HTTP runs in worker threads. The main thread writes one short transaction per title and commits before it waits on the next result.

**Who may end transactions:** route handlers, `catalog/read_through.py` (called only from handlers), and the CLI and ingestion entrypoints. A source-scanning test enforces this.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Async SQLAlchemy + asyncpg, `async def` handlers | Better I/O concurrency, but it brings implicit-IO pitfalls (lazy loading errors), harder testing and session handling, and async infection of every layer. Our concurrency needs are modest, and the engine is CPU-bound |
| Mixed sync and async handlers | Easy to block the event loop by accident with a sync DB call. A single rule is safer |
| Services own transactions (`with session.begin()` in each service) | Conflicts with autobegin after the auth lookup, and nested service calls conflict |
| Commit in the session dependency's teardown | Teardown timing relative to sending the response has varied across FastAPI versions. A failed commit after a sent `200` would lose writes silently |
| A separate session per service or per module | Breaks atomic cross-module writes and duplicates connections per request |
| Keep the request transaction open while calling TMDB | Ties a pooled connection to network latency, so pool exhaustion appears under modest load |

## Consequences

**Positive**
- One clear rule: commits are visible in handlers, and cross-module service calls compose inside one transaction.
- Commit errors surface as error responses.
- Connections are only held for short database work.

**Negative / accepted costs**
- Each write handler must remember its commit. The transaction-location test catches misplaced commits, and integration tests catch missing ones (the data isn't there).
- Read-through handlers run up to three short transactions per request, which is slightly more code in `read_through.py`.
- Threads waiting on TMDB still occupy a worker thread, though not a DB connection. That's acceptable at MVP scale.

## Revisit when

Measured load saturates the thread pool, or a feature needs many concurrent external calls per request. At that point consider async for specific endpoints, behind a superseding ADR.
