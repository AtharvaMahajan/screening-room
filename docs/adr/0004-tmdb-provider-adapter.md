# ADR-0004: Put TMDB behind a provider adapter, with a normalized catalog and internal genre taxonomy

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Project owner
- **Related:** [catalog-ingestion](../architecture/catalog-ingestion.md) · [data-model §3.2](../architecture/data-model.md#32-catalog-m2)

## Context

TMDB is the initial metadata source. The PRD requires that the application depend on an internal normalized model, not on provider response shapes. Specific TMDB characteristics affect the design:
- IDs are unique **per media type**: a movie and a TV show can share an ID.
- Movie and TV **genre lists differ** (TV merges genres such as "Sci-Fi & Fantasy").
- List endpoints return partial data. Details, credits and recommendation lists need a detail call (combinable with `append_to_response`).
- There are rate limits, attribution requirements, and separate terms for commercial use.

## Decision

- A `CatalogProvider` **Protocol** defines `discover`/list, `get_details` (with credits and recommendations), `search` and `list_genres`, returning provider-neutral DTOs. Implementations: **TMDB**, and a deterministic **`FakeProvider`** for tests.
- **Only the TMDB adapter knows TMDB's JSON.** A mapper converts it into internal DTOs, and recorded JSON fixtures test the mapper.
- **Normalized catalog:** our own surrogate `titles.id` is used everywhere (URLs, FKs). Provider identity is stored as `(provider, media_type, provider_id)` with a **unique constraint**, which is the idempotency key.
- **Internal genre taxonomy** plus `provider_genre_map` (one provider genre can map to several internal genres). Unmapped provider genres fail loudly.
- **Images:** store paths only. Build CDN URLs from configuration. No proxying or storage.
- **Resilience:** client timeouts, bounded retries with backoff and jitter, `Retry-After` honoured, ≤1 retry on user-facing paths.
- **Secrets:** the TMDB token stays on the server.
- **Locale:** `en-US` for the MVP. Adult content is excluded.
- **Attribution:** an attribution page, and a terms review before public deployment.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Use TMDB response models directly in services and UI | Couples the whole app to one provider's shapes and quirks |
| Use TMDB IDs as primary keys | Not unique across media types, and ties our identity to the provider |
| Separate external-ID mapping table now | Supports multi-provider merging we don't need. Our surrogate IDs make adding it later cheap |
| Use TMDB genre IDs directly | Cross-media genre affinity breaks on mismatched lists |
| Proxy or store images | Bandwidth and storage cost. Licensing review needed. No benefit yet |

## Consequences

**Positive**
- Tests and the engine run against stable internal types. Swapping or adding a provider is contained in one package.
- Genre affinity works across movies and TV.

**Negative / accepted costs**
- The mapper and genre mapping must be maintained.
- The taxonomy is a judgement call (e.g. "War & Politics" → `war` + `politics`), reviewed in M2.

## Revisit when

A second metadata provider is added, or TMDB's terms or availability change.
