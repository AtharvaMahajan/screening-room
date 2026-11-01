# Screening Room

Personalized movie and TV discovery: "What should I watch?" answered with a short, explained shortlist.

Product and architecture decisions live in [`docs/`](docs/README.md). Start with [architecture/overview.md](docs/architecture/overview.md).

| Part | Stack | Location |
|---|---|---|
| API | Python 3.15, FastAPI (sync handlers), SQLAlchemy 2.0, psycopg 3 | [`backend/`](backend/) |
| Web app | React, TypeScript (strict), Vite, React Router, TanStack Query, Tailwind CSS, React Hook Form + Zod | [`frontend/`](frontend/) |
| Database | PostgreSQL 17 via Docker Compose (the only infrastructure, [ADR-0002](docs/adr/0002-postgresql-only-infrastructure.md)) | [`docker-compose.yml`](docker-compose.yml) |

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine with Compose v2)
- Python 3.15
- [uv](https://docs.astral.sh/uv/) for Python dependencies (`pip install uv`). If `uv` isn't on your PATH afterwards, `python -m uv` works the same way.
- Node.js 24 and npm

## First-time setup

```bash
# 1. Local configuration. Edit .env and choose your own database password.
#    DATABASE_URL must use the same user/password/db as the POSTGRES_* values.
cp .env.example .env

# 2. Backend dependencies (creates backend/.venv from uv.lock)
cd backend && uv sync && cd ..

# 3. Frontend dependencies (exactly as in package-lock.json)
cd frontend && npm ci && cd ..

# 4. Start the database and create its schema
docker compose up -d --wait db
cd backend && uv run alembic upgrade head && cd ..
```

## Running locally

Use three terminals, all started from the repository root.

```bash
# 1. PostgreSQL (waits until the database is healthy)
docker compose up -d --wait db

# 2. API on http://127.0.0.1:8000 (reloads on code changes)
#    --reload-dir src matters: without it the reloader polls every .py file in
#    backend/, including ~2,000 in .venv, using most of a CPU core.
cd backend
uv run uvicorn screening_room.main:create_app --factory --reload --reload-dir src

# 3. Web app on http://localhost:5173
cd frontend
npm run dev
```

Open **http://localhost:5173**. You'll be sent to **Sign in**: choose **Create an account**. After registering, a short optional onboarding asks for genres and favorite titles, then you land on **Discover**. The footer of every page shows whether the API and database are up.

**Discover needs a catalog.** A fresh database has no titles, so Discover has nothing to recommend until you've filled the pool with the ingestion job (see [Catalog](#catalog-tmdb-ingestion) below; it needs a TMDB token).

Once you're signed in, the header leads to:
- **Discover**: ask for 3-5 explained recommendations, optionally for movies or TV, a genre or the time you have. Save, mark watched, rate, skip or turn down each one.
- **Search**: any movie or TV show on TMDB (falls back to titles already in the catalog if TMDB can't be reached).
- **Library**: your watchlist, viewing history, ratings and "not for me" list.
- **Your taste**: the genres and favorite titles from onboarding, editable any time.
- **Your name**: your account, including deleting it.

The browser only talks to Vite. Vite forwards every `/api/...` request to FastAPI, so the app runs same-origin with no CORS setup. API docs are at http://localhost:5173/api/docs.

Stop the database with `docker compose stop`. `docker compose down -v` also **deletes** its data volume.

## Checks

These are the same checks CI runs ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

```bash
# Backend (from backend/)
uv run ruff check .          # lint
uv run ruff format --check . # formatting (use `uv run ruff format .` to fix)
uv run mypy                  # strict type checking
uv run lint-imports          # module boundaries (ADR-0001), configured in pyproject.toml
uv run pip-audit --skip-editable  # known vulnerabilities in Python dependencies
uv run pytest                # all tests; integration tests need a running, migrated database
uv run pytest tests/unit     # unit tests only, no database needed
uv run alembic check         # models and migrations are in sync

# Frontend (from frontend/)
npm run lint                 # ESLint, including type-aware rules
npm run typecheck            # tsc
npm test                     # Vitest (npm run test:watch while developing)
npm run build                # production build
npm audit --omit=dev         # known vulnerabilities in shipped dependencies
```

Integration tests use the database in `DATABASE_URL`, but every test runs inside a transaction that is rolled back afterwards, so they never change your data.

## Database migrations

The schema is managed with [Alembic](https://alembic.sqlalchemy.org/). Run these from `backend/`:

```bash
uv run alembic upgrade head          # apply all migrations (after pulling changes)
uv run alembic current               # which migration the database is at

# After changing ORM models: generate a migration, then REVIEW it by hand.
# Autogenerate is a draft and can miss things (data-model.md §1).
uv run alembic revision --autogenerate --rev-id 0002 -m "add users table"

uv run alembic downgrade -1          # undo the latest migration
```

Migration IDs are sequential (`0001`, `0002`, …): pass the next number as `--rev-id`. New migration files are formatted with Ruff automatically.

## API types and errors

The frontend's API types in `frontend/src/api/schema.ts` are **generated** from the backend's OpenAPI schema. Never edit that file by hand. After changing any route, request or response model, regenerate it and commit the result:

```bash
cd backend  && uv run python -m screening_room.openapi ../frontend/openapi.json
cd frontend && npm run api:types     # or `npm run api:check` to only verify
```

CI fails if `schema.ts` is out of date.

Every error response has the same shape, so the frontend can branch on `code` (`ApiError.code`):

```json
{"error": {"code": "validation_failed", "message": "The request is invalid.",
           "details": [{"field": "body.email", "message": "Field required"}]}}
```

`details` appears only on validation errors (422). Backend code signals expected failures by raising `AppError(status, code, message)` from `screening_room.core.errors`. Unexpected exceptions become a generic `500 internal_error`, and the full error is logged.

## Configuration

All configuration comes from environment variables. For local development they're read from the repo-root `.env`, and real environment variables take precedence. `.env` is gitignored, and `.env.example` holds placeholders only.

| Variable | Used by | Purpose |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Docker Compose | Local database credentials and host port |
| `DATABASE_URL` | Backend, migrations | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@127.0.0.1:5432/db` |
| `CSRF_SECRET` | Backend | **Required.** HMAC key for CSRF tokens, at least 32 characters. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ALLOWED_ORIGINS` | Backend | **Required.** JSON list of origins allowed to make unsafe requests, e.g. `["http://localhost:5173"]` |
| `LOG_FORMAT`, `LOG_LEVEL` | Backend, jobs | `text` (default, for people) or `json` (production: one JSON object per line). Level default `INFO` |
| `SESSION_TTL_DAYS` | Backend | Absolute session lifetime. Default `30` |
| `COOKIE_SECURE`, `COOKIE_PREFIX_HOST` | Backend | Default `true` (production). Set both to `false` for local http, where browsers drop `Secure` cookies |
| `LOGIN_ATTEMPTS_PER_IP`, `LOGIN_FAILURES_PER_EMAIL`, `LOGIN_WINDOW_MINUTES`, `REGISTRATIONS_PER_IP`, `REGISTRATION_WINDOW_MINUTES` | Backend | Rate limits (security.md §8). Defaults: 30 login attempts per IP and 10 failed logins per email per 15 minutes; 10 registrations per IP per hour |
| `TMDB_API_TOKEN` | Ingestion, title pages, search | TMDB **API Read Access Token** (themoviedb.org → Settings → API). Never commit it. Without a valid token the app still runs: title pages show what's stored, and search only searches the local catalog |
| `TMDB_RATE_LIMIT_RPS`, `TMDB_MAX_WORKERS` | Ingestion | Requests per second (default `20`) and parallel detail fetches (default `8`) |
| `CATALOG_TTL_DAYS` | Ingestion | Title metadata older than this is stale and re-fetched (default `14`) |

Migrations only need `DATABASE_URL`. The web app refuses to start if a required setting is missing.

## Catalog (TMDB ingestion)

Recommendations draw on a local pool of movies and TV shows, filled from TMDB by a command-line job ([catalog-ingestion.md](docs/architecture/catalog-ingestion.md)). It needs `TMDB_API_TOKEN` in `.env`. Run these from `backend/`:

```bash
uv run python -m screening_room.jobs ingest --dry-run       # the plan; no requests, no writes
uv run python -m screening_room.jobs ingest                 # build or update the pool (~2 min, ~1,500 requests)
uv run python -m screening_room.jobs report                 # what's in the pool (no requests)
uv run python -m screening_room.jobs prune                  # delete old titles outside the pool nobody uses (no requests)
uv run python -m screening_room.jobs refresh                # re-fetch every title older than CATALOG_TTL_DAYS
```

Each title has a page at `http://localhost:5173/titles/<id>`, linked from Discover, Search and your Library. Pool titles are served from the local catalog. Stale ones are refreshed from TMDB, and if TMDB is down the page still works, with a note that some details may be out of date.

TMDB's terms allow caching its data for at most 6 months, so production runs `prune` then `refresh` on a schedule, at least weekly. Every page shows TMDB's required attribution; see [docs/evidence/m5e-tmdb-terms.md](docs/evidence/m5e-tmdb-terms.md).

Every run is safe to repeat and to interrupt: re-running continues where it stopped. `--max-requests N` caps the TMDB requests a run may make. Each run is recorded in the `ingestion_runs` table, and the first real run's report is in [docs/evidence/](docs/evidence/m2-first-ingestion-report.txt).

## Logs and metrics

Every request is logged as one line with a `request_id` (also returned in the `X-Request-ID` response header), the route, status and duration, plus the user's id when signed in. Lines written while handling that request carry the same id. Events are logged with fields too: recommendations served (with `latency_ms`), actions on results, TMDB failures and retries, and rate-limit hits. Never logged: passwords, tokens, cookies, email addresses, query strings or search text (security.md §9). Set `LOG_FORMAT=json` in production.

Recommendation metrics come from the database's own logs, with no metrics server (from `backend/`):

```bash
uv run python -m screening_room.jobs metrics --days 7   # latency p50/p95, cold starts, coverage, action rates
```

To load-test the recommendation endpoint, start an API without `--reload` (e.g. on port 8003) and run `uv run python scripts/load_test.py` from `backend/`. It creates synthetic users in the database, deletes them afterwards, and prints latency per concurrency level. The latest results are in [docs/evidence/m5c-load-test.txt](docs/evidence/m5c-load-test.txt).

## Authentication

Email and password, with server-side sessions in an HttpOnly cookie and signed CSRF tokens ([ADR-0007](docs/adr/0007-session-auth-and-csrf.md), [security.md](docs/architecture/security.md)). The API is under `/api/auth`: `GET session`, `POST register`, `POST login`, `POST logout`. Deleting an account is `DELETE /api/me` with the current password re-entered; it removes all the user's data.

Every POST/PUT/PATCH/DELETE must come from an allowed `Origin` and send the CSRF token from `GET /api/auth/session` in an `X-CSRF-Token` header. Otherwise it gets `403 origin_rejected` or `403 csrf_failed`. Protect a route by adding a `CurrentUserDep` parameter (from `screening_room.modules.identity.dependencies`); it returns `401 unauthenticated` when nobody is signed in.

## Troubleshooting

**Health check says the API can't reach the database.** Run `docker compose ps` to check the database is up and healthy, and check that `DATABASE_URL` matches the `POSTGRES_*` values in `.env`.

**Windows: `An Application Control policy has blocked this file`.** Smart App Control blocks some unsigned native extensions. On the original dev machine it blocked uv-managed Python builds and SQLAlchemy's optional Cython extension. Use a python.org Python, and install SQLAlchemy without its C extensions (it then runs as pure Python):

```powershell
$env:DISABLE_SQLALCHEMY_CEXT = "1"
uv sync --no-binary-package sqlalchemy --reinstall-package sqlalchemy
```

This only affects your local environment. The lockfile and CI are unchanged.
