# ADR-0003: Use a local seeded candidate pool; the recommendation path is local-only

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Project owner
- **Related:** [catalog-ingestion](../architecture/catalog-ingestion.md) · [recommendation-engine](../architecture/recommendation-engine.md) · [ADR-0005](0005-catalog-ingestion-cli.md) · [ADR-0010](0010-staged-deterministic-recommendation-pipeline.md)

## Context

The PRD rules out mirroring the full external catalog and suggests persisting only titles users interact with. But a recommender needs a broad set of candidates. With few users, the set of "touched" titles is too small to recommend from.

The PRD allows candidates to come from live provider endpoints, but live candidates conflict with other requirements:
- **Determinism** (PRD §16 #8): live lists change between calls.
- **Latency** (p95 < 1.5 s): several external calls per request.
- **Reliability:** a provider outage would break discovery.
- **Explainability:** rankings built on opaque live lists are hard to explain truthfully.

## Decision

- Maintain a **local candidate pool** in PostgreSQL, populated by the ingestion process ([ADR-0005](0005-catalog-ingestion-cli.md)) from popular, top-rated, genre, decade and language sources.
- **Start modest: ~1,000–2,000 titles**, with a hard cap (`--max-titles`, default 2,000). Grow based on coverage and recommendation-quality evidence ([catalog-ingestion §5](../architecture/catalog-ingestion.md#5-sizing-and-growth)).
- **Pool membership is explicit.** A title is a candidate only with ≥1 pool membership, full details, active provider status and no adult flag. Titles stored by search or detail views aren't candidates by default.
- **`POST /api/recommendations` reads only PostgreSQL and never calls TMDB.** TMDB recommendation relationships used by the engine are stored during hydration, and only targets inside the pool can be recommended.
- **The latency target, p95 < 1.5 s, applies specifically to this local recommendation endpoint.** TMDB-backed search and detail requests are bounded by timeouts and have no p95 target in the MVP.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Live TMDB discover/recommendations per request | Non-deterministic, slow, fails during outages, hard to explain |
| Hybrid (local first, live top-up when thin) | Inherits both sets of complexity, and determinism holds only sometimes |
| Full catalog mirror | Large ingestion and refresh cost, licensing questions. Unnecessary for a curated shortlist |
| Interacted-titles only (literal PRD reading) | Too few candidates. Cold start would be empty |

## Consequences

**Positive**
- Deterministic, fast and outage-tolerant recommendations, testable against fixed datasets.
- Clear evaluation data: we know exactly what the engine could have chosen.

**Negative / accepted costs**
- Titles outside the pool can't be recommended, so coverage has to be monitored and the pool grown.
- Metadata freshness depends on ingestion runs (TTL 14 days, refresh command).
- An ingestion process to maintain.

## Revisit when

Coverage metrics show persistent gaps that quota increases can't fix, or the pool grows past ~20k titles (retrieval redesign, E8).
