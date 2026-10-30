# ADR-0001: Build a modular monolith with enforced module boundaries

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Project owner
- **Related:** [overview §5](../architecture/overview.md#5-modules) · [project-structure §3–4](../architecture/project-structure.md#3-module-anatomy) · [ADR-0002](0002-postgresql-only-infrastructure.md)

## Context

Screening Room has a small domain (identity, catalog, profile, library, discovery), one developer, and a PRD that explicitly warns against adopting distributed architecture prematurely (Goal 6). Several key operations cross domains and must be atomic. For example, marking a recommended title as watched writes a viewing event, removes a watchlist entry and attributes the action to a recommendation result.

The PRD also asks for maintainability through clear module boundaries. An unstructured monolith tends to erode into a tangle in which every module reaches into every other module's tables.

## Decision

- **One deployable application** (FastAPI) with one database, plus a CLI entrypoint from the same codebase ([ADR-0005](0005-catalog-ingestion-cli.md)).
- **Package-by-feature modules:** `identity`, `catalog`, `profile`, `library`, `discovery`. Each **owns its tables**.
- A module's **public surface** is its `service.py` functions and `schemas.py` DTOs. ORM models and queries are private. Cross-module data moves as DTOs.
- Allowed dependencies: `discovery → {catalog, profile, library}`, `library → catalog`, `profile → catalog`, `* → identity`, `* → core`. No cycles.
- Cross-module calls are in-process and share the request's session and transaction ([ADR-0006](0006-sync-sqlalchemy-handler-owned-transactions.md)).
- **Enforced in CI** with `import-linter` contracts, starting in M2.
- **Stated exception:** `discovery` legitimately needs data owned by three other modules. It gets it through their public query functions, not ad-hoc joins. If performance ever requires a cross-module SQL read model, that will be a new ADR.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Microservices (e.g. catalog, recommendations, users) | Network calls and distributed consistency (sagas, outboxes) for cross-module writes, plus multiplied ops and CI cost. No scaling or team pressure justifies them |
| Layered monolith (`routers/`, `services/`, `models/` at top level) | Simpler on day one, but it hides domain boundaries and drifts into coupling |
| Modular monolith with boundaries by convention only | Conventions erode silently. An automated contract is cheap |

## Consequences

**Positive**
- Atomic cross-module operations with ordinary database transactions.
- One build, one deploy, one place to debug.
- Clear seams if a module ever needs to be extracted.

**Negative / accepted costs**
- Every module scales together. That's acceptable at this scale.
- Discipline is still needed for things the import linter can't see, such as shared table access through raw SQL.

**Follow-ups**
- Add `import-linter` contracts in M2.

## Revisit when

A module needs independent scaling, deployment cadence or ownership (e.g. a separate team), or recommendation computation becomes heavy enough (offline training, E10/E11) to warrant its own process.
