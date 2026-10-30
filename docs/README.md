# Screening Room Documentation

**Status:** Draft for review · **Last updated:** 2026-10-30

This directory is the source of truth for Screening Room's product and architecture decisions.

## Map

| Document | What it covers |
|---|---|
| [product/PRD.md](product/PRD.md) | Product requirements (v0.1) |
| [architecture/overview.md](architecture/overview.md) | **Start here.** System context, modules, request paths, quality targets, decision summary |
| [architecture/project-structure.md](architecture/project-structure.md) | Code layout, module anatomy, **transaction boundary rules**, API and frontend conventions |
| [architecture/data-model.md](architecture/data-model.md) | Database conventions, ER diagram, tables by milestone, state rules |
| [architecture/catalog-ingestion.md](architecture/catalog-ingestion.md) | TMDB integration, candidate pool, ingestion CLI, read-through |
| [architecture/recommendation-engine.md](architecture/recommendation-engine.md) | Recommendation pipeline v1, signals, explanations, evaluation, enhancement ladder |
| [architecture/security.md](architecture/security.md) | Authentication, sessions, CSRF lifecycle, authorization, privacy |
| [roadmap.md](roadmap.md) | Milestones M0–M6 and how they map to the PRD's acceptance criteria |
| [architecture/future-considerations.md](architecture/future-considerations.md) | Everything deliberately deferred, with revisit triggers |
| [architecture/open-questions.md](architecture/open-questions.md) | PRD questions and review findings, with their status |
| [adr/README.md](adr/README.md) | Architecture Decision Records: index and process |

## Status vocabulary

These labels mean the same thing in every document:

| Label | Meaning |
|---|---|
| **Decided** | Confirmed by the project owner. Change it only through a superseding ADR, or by explicitly editing the relevant doc. |
| **Deferred** | Deliberately not in the current scope. Each item has a revisit trigger in `future-considerations.md`. |
| **Open** | Needs a decision or external input (e.g. licensing terms, user research). |
| **Validate** | Decided for the build, but it's a product hypothesis to be checked with users. |

Numbers marked *initial value* (weights, quotas, thresholds) are tunable configuration. They aren't architectural decisions. They're set in one place in code and adjusted based on evidence.

## How decisions change

1. Significant, cross-cutting or hard-to-reverse decisions go in an ADR (see [adr/README.md](adr/README.md)).
2. Conventions and implementation detail go in the relevant architecture doc.
3. A new idea that isn't decided yet goes in `future-considerations.md` or `open-questions.md`, not in an ADR.
