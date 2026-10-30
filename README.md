# Screening Room

Personalized movie and TV discovery: "What should I watch?" answered with a short, explained shortlist.

Product and architecture decisions live in [`docs/`](docs/README.md). Start with [architecture/overview.md](docs/architecture/overview.md).

| Part | Stack | Location |
|---|---|---|
| API | Python 3.15, FastAPI (sync handlers), SQLAlchemy 2.0, psycopg 3 | [`backend/`](backend/) |
| Web app | React, TypeScript (strict), Vite, React Router, TanStack Query | [`frontend/`](frontend/) |
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
```

## Running locally

Use three terminals, all started from the repository root.

```bash
# 1. PostgreSQL (waits until the database is healthy)
docker compose up -d --wait db

# 2. API on http://127.0.0.1:8000 (reloads on code changes)
cd backend
uv run uvicorn screening_room.main:create_app --factory --reload

# 3. Web app on http://localhost:5173
cd frontend
npm run dev
```

Open **http://localhost:5173**. The home page calls `GET /api/health` and should say "API and database are up."

The browser only talks to Vite. Vite forwards every `/api/...` request to FastAPI, so the app runs same-origin with no CORS setup. API docs are at http://localhost:5173/api/docs.

Stop the database with `docker compose stop`. `docker compose down -v` also **deletes** its data volume.

## Checks

These are the same checks CI runs ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

```bash
# Backend (from backend/)
uv run ruff check .          # lint
uv run ruff format --check . # formatting (use `uv run ruff format .` to fix)
uv run mypy                  # strict type checking
uv run pytest                # all tests; integration tests need the database running
uv run pytest tests/unit     # unit tests only, no database needed

# Frontend (from frontend/)
npm run lint                 # ESLint, including type-aware rules
npm run typecheck            # tsc
npm test                     # Vitest (npm run test:watch while developing)
npm run build                # production build
```

## Configuration

All configuration comes from environment variables. For local development they're read from the repo-root `.env`, and real environment variables take precedence. `.env` is gitignored, and `.env.example` holds placeholders only.

| Variable | Used by | Purpose |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Docker Compose | Local database credentials and host port |
| `DATABASE_URL` | Backend | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@127.0.0.1:5432/db` |

## Troubleshooting

**Health check says the API can't reach the database.** Run `docker compose ps` to check the database is up and healthy, and check that `DATABASE_URL` matches the `POSTGRES_*` values in `.env`.

**Windows: `An Application Control policy has blocked this file`.** Smart App Control blocks some unsigned native extensions. On the original dev machine it blocked uv-managed Python builds and SQLAlchemy's optional Cython extension. Use a python.org Python, and install SQLAlchemy without its C extensions (it then runs as pure Python):

```powershell
$env:DISABLE_SQLALCHEMY_CEXT = "1"
uv sync --no-binary-package sqlalchemy --reinstall-package sqlalchemy
```

This only affects your local environment. The lockfile and CI are unchanged.
