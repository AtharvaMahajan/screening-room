# Project Structure and Code Conventions

**Status:** Draft for review · **Last updated:** 2026-10-30

This document covers how the code is laid out and the conventions every module follows. It includes the **transaction boundary rules** ([ADR-0006](../adr/0006-sync-sqlalchemy-handler-owned-transactions.md)), which are the conventions with the most impact on correctness.

> Principle: **keep the architecture, build the abstractions only when they're needed.** The layout below is the *initial* shape. Section 10 lists the abstractions we're deliberately not building yet.

## 1. Repository layout

```
screening-room/
  backend/                  # Python / FastAPI (M1)
  frontend/                 # React / TypeScript / Vite (M1)
  docs/                     # This documentation
  docker-compose.yml        # Local PostgreSQL (M1)
  .github/workflows/        # CI (M1)
```

A single repository holds frontend, backend and docs, so one change can update the API, the generated client types and the docs together.

## 2. Backend layout (initial, M1–M3)

```
backend/
  pyproject.toml
  alembic.ini
  alembic/versions/
  src/screening_room/
    main.py                  # app factory, router registration, middleware (CSRF, Origin)
    config.py                # pydantic-settings, env-driven
    db.py                    # engine, SessionLocal, get_session dependency, end_read_transaction()
    jobs.py                  # CLI entrypoint: python -m screening_room.jobs ingest|refresh|report
    core/
      errors.py              # domain error types → HTTP error mapping
      security.py            # password hashing, token generation, HMAC helpers
      logging.py             # structured logging setup
    modules/
      identity/   router.py service.py models.py schemas.py dependencies.py csrf.py
      catalog/    router.py service.py models.py schemas.py genres.py read_through.py
                  providers/ base.py tmdb.py fake.py
                  ingestion/ seed_plan.py discover.py hydrate.py report.py
      profile/    router.py service.py models.py schemas.py                 # M3
      discovery/  router.py service.py models.py schemas.py retrieval.py    # M3
                  engine/ types.py config.py profile.py eligibility.py
                          scoring.py ranking.py explain.py pipeline.py
      library/    router.py service.py models.py schemas.py                 # M4
  tests/
    unit/          # pure engine, mappers, domain rules (no DB)
    integration/   # API and services against real PostgreSQL
    fixtures/      # recorded TMDB JSON, engine fixture catalog and personas
```

**How it grows:** a file is split only when it becomes hard to navigate. For example, `providers/tmdb.py` becomes `providers/tmdb/{client,mapper}.py`, and a large `service.py` gets a private `queries.py` beside it. A new module is created only for a new bounded area of the domain.

## 3. Module anatomy

| File | Visibility | Contents |
|---|---|---|
| `router.py` | Internal | FastAPI routes. HTTP concerns, dependencies, **transaction boundary (commit)**, DTO → response mapping |
| `service.py` | **Public** | Use-case and query functions. Take a `Session` plus typed arguments, return DTOs. Other modules call these |
| `schemas.py` | **Public** | Pydantic DTOs: API request/response models and cross-module data types |
| `models.py` | Private | SQLAlchemy ORM models for this module's tables |
| `dependencies.py` | Internal / public as documented | FastAPI dependencies (e.g. `identity.dependencies.current_user`) |

**No repository layer.** SQLAlchemy 2.0's `Session` already provides the unit of work and identity map. Services use `select()` directly. If query code grows, it moves into a private `queries.py` in the same module.

## 4. Module boundary rules

1. A module may import another module's `service`, `schemas` and documented `dependencies` only, never its `models` or internals.
2. Allowed dependency directions: `discovery → {catalog, profile, library}`, `library → catalog`, `profile → catalog`, `* → identity` (current user), `* → core`. No cycles.
3. Cross-module data crosses the boundary as DTOs, not ORM instances.
4. `import-linter` contracts encode rules 1–2. They're added in M2, once three or more modules exist, and run in CI.

## 5. Request handling and transaction boundary

### 5.1 Rules

These rules prevent a common SQLAlchemy 2.0 failure. The Session **autobegins** a transaction on first use (here, the session-cookie lookup in the auth dependency), so a later `session.begin()` inside a service raises *"A transaction is already begun"*. Services calling other services would conflict in the same way.

1. **One Session per request.** `get_session` creates a Session, yields it **without** calling `begin()`, and calls `close()` in `finally`. Closing rolls back anything that wasn't committed and returns the connection to the pool.
2. **Autobegin is embraced.** The first database use starts the request's transaction. The authentication dependency and all services share the same Session and transaction.
3. **Services never call `begin()`, `commit()` or `rollback()`.** They may `flush()` to get generated IDs or surface `IntegrityError` early, and translate it into a domain error.
4. **Write handlers call `session.commit()` exactly once,** after the service call succeeds and **before** returning. A failed commit then becomes an error response rather than a lost write behind a `200`.
5. **Read handlers don't commit.** Their transaction ends when the session closes.
6. **The authentication dependency is read-only.** There's no `last_seen_at` update and no sliding expiry ([ADR-0007](../adr/0007-session-auth-and-csrf.md)), so read requests never need a commit.
7. **Commit happens in the handler, not in dependency teardown.** Teardown timing relative to sending the response has varied across FastAPI versions, and correctness mustn't depend on it.
8. **Savepoints** (`session.begin_nested()`) are used only where a step must be able to fail without aborting the request's transaction. Expected to be rare.

### 5.2 No transaction or connection held across external calls

A request must never hold an open transaction or a checked-out connection while it waits on TMDB:

- **`end_read_transaction(session)`** (in `db.py`) asserts the session has no pending changes (`new`, `dirty` and `deleted` are empty), then calls `session.rollback()`. That ends the read-only transaction and returns the connection to the pool. The next database use autobegins a fresh transaction.
- **Before releasing, convert what you need into DTOs.** Ending a transaction expires loaded ORM instances. That's why `current_user` returns a `CurrentUser` DTO (id, email, display name), not an ORM object.
- **External calls take plain values** (e.g. `ProviderRef(media_type, provider_id)`), never a Session or ORM objects.
- After the external call, write in a **short transaction** and commit.

### 5.3 Who may end a transaction

| Location | May call `commit()` / `end_read_transaction()` |
|---|---|
| `modules/*/router.py` handlers | Yes. They're the transaction owners |
| `modules/catalog/read_through.py` | Yes. It's a **handler-level helper**: it's called only from handlers (detail, M4 search, M4 non-pool favorites), with a session that has no pending changes, and it encapsulates *read → release → fetch → short write → commit* |
| `jobs.py` and `catalog/ingestion/*` | Yes. The CLI command owns its own sessions and commits per title or per batch |
| Everything else (`service.py`, `engine/*`, `core/*` except `db.py`) | **No** |

A unit test scans the source tree and fails if `.commit(` or `end_read_transaction(` appears outside the allowed locations.

### 5.4 Handler patterns (illustrative)

```python
# Read handler: no commit.
@router.get("/api/me/preferences")
def get_preferences(session: SessionDep, user: CurrentUserDep) -> PreferencesOut:
    return profile_service.get_preferences(session, user.id)

# Write handler: one commit, after the service succeeds, before returning.
@router.put("/api/me/preferences")
def put_preferences(body: PreferencesIn, session: SessionDep, user: CurrentUserDep) -> PreferencesOut:
    result = profile_service.replace_preferences(session, user.id, body)
    session.commit()
    return result

# Read-through handler: delegates to the handler-level helper.
@router.get("/api/titles/{title_id}")
def get_title(title_id: int, session: SessionDep, user: CurrentUserDep) -> TitleDetailOut:
    return read_through.get_title_detail(session, title_id)  # may release, fetch, write, commit
```

### 5.5 Sync handlers only

- Every route that touches the database or TMDB is declared with `def`, so FastAPI runs it in its worker thread pool. `async def` is reserved for handlers with no blocking I/O, and there should be almost none.
- A unit test fails if any route endpoint outside an explicit allowlist is a coroutine function.
- **Sizing:** AnyIO's default thread pool is 40 threads. The SQLAlchemy pool is configured explicitly (initial value: `pool_size=10`, `max_overflow=10`). Because connections are released before external calls (§5.2), a thread waiting on TMDB doesn't hold a connection.

### 5.6 Testing with transactions

Integration tests open a connection, begin an outer transaction, and bind the request Session to it with `join_transaction_mode="create_savepoint"`. Handler commits then release savepoints, and each test rolls back the outer transaction at the end. Tests run against **real PostgreSQL**, not SQLite, because we rely on Postgres constraints, `jsonb` and `ON CONFLICT`.

## 6. Configuration

Settings come from environment variables via `pydantic-settings`. Secrets are never committed.

| Setting | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection |
| `TMDB_API_TOKEN` | TMDB read access token (server only) |
| `CSRF_SECRET` | HMAC key for CSRF tokens. Rotating it invalidates tokens harmlessly |
| `ALLOWED_ORIGINS` | Origin allowlist for unsafe requests |
| `COOKIE_SECURE`, `COOKIE_PREFIX_HOST` | Production `Secure` and `__Host-` cookie behaviour, relaxed for local http |
| `SESSION_TTL_DAYS` | Absolute session lifetime (initial value: 30) |
| `CATALOG_TTL_DAYS` | Metadata freshness TTL (initial value: 14) |
| `TMDB_RATE_LIMIT_RPS`, `TMDB_MAX_WORKERS` | Ingestion throttling (initial values: 20, 8) |

Recommendation-engine weights and thresholds aren't environment settings. They live in `discovery/engine/config.py` (`EngineConfig`) under version control ([recommendation-engine.md §12](recommendation-engine.md#12-configuration-and-versioning)).

## 7. API conventions

- All routes live under `/api`. User-owned resources live under `/api/me/...`, so user IDs never appear in URLs.
- No URL versioning (`/api/v1`): the API has exactly one client, deployed together with it.
- Request and response bodies are Pydantic models, and mutations accept `application/json` only.
- Error body: `{"error": {"code": "csrf_failed", "message": "…"}}` with a stable, machine-readable `code`.
- List endpoints use limit/offset or cursor pagination, with an upper bound on `limit`.
- Unsafe methods (POST/PUT/PATCH/DELETE) require the CSRF header ([security.md](security.md)). Safe methods don't change user state. The only server-side writes during a GET are catalog cache fills and CSRF cookie issuance.

## 8. Frontend layout and conventions

```
frontend/src/
  app/          # router, providers (QueryClient), layout, auth guard, CSRF bootstrap
  api/          # generated OpenAPI types + thin fetch client (adds X-CSRF-Token, handles csrf_failed)
  features/
    auth/ onboarding/ discover/ titles/ library/ search/
      components/  hooks/  routes.tsx
  components/   # shared UI: PosterCard, Button, Dialog, EmptyState, ReasonChip
  lib/          # formatting, image URL builder, accessibility helpers
  test/
```

| Concern | Convention | Status |
|---|---|---|
| Build tooling | Vite, strict TypeScript | Decided |
| Routing | React Router | Decided |
| Server state | TanStack Query. No global client-state library; the little UI-only state left is local | Decided |
| Forms | React Hook Form + Zod | Decided |
| API types | Generated from FastAPI's OpenAPI schema (`openapi-typescript`). CI fails if the generated types are out of date | Decided |
| Styling | Tailwind CSS by default | **Open** (low stakes; confirm in M1) |
| Dev server | Vite proxies `/api` to FastAPI, giving the same origin and no CORS | Decided |
| Testing | Vitest + Testing Library. Browser end-to-end tests deferred | Decided |

Feature folders mirror backend modules where it makes sense.

## 9. Quality tooling and CI (M1)

| Area | Tools |
|---|---|
| Python | `ruff` (lint + format), `mypy` (strict on `src/`), `pytest` against PostgreSQL in CI |
| Architecture checks | `import-linter` (from M2), the transaction-location test, the sync-handler test |
| Frontend | `eslint`, `tsc --noEmit`, `vitest`, generated-types drift check |
| Migrations | `alembic upgrade head` on a fresh database in CI, plus a downgrade/upgrade round-trip for the latest migration |

## 10. Abstractions deliberately not built yet

| Not built | Instead | Build when |
|---|---|---|
| Repository layer / generic DAO | Services use `Session` and `select()` directly | A real need for an alternative persistence implementation (unlikely) |
| Plugin registry for retrievers, rules or signals | Plain functions in ordered lists inside each stage module | Signals or rules need to be configured at runtime, per experiment |
| Multiple candidate retrievers | One whole-pool retrieval query | Pool > ~20k titles or the latency budget is threatened (E8) |
| Domain events / outbox | Direct in-process service calls in one transaction | A second process must react to changes reliably |
| Background job framework | CLI commands, run manually | Scheduled or user-triggered async work ([future-considerations.md](future-considerations.md)) |
| API versioning | Single `/api` | A second client (e.g. a native app) |
