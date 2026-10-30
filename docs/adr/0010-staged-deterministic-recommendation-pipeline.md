# ADR-0010: Build recommendations as a staged, deterministic pipeline with signal-derived explanations

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Project owner
- **Related:** [recommendation-engine](../architecture/recommendation-engine.md) · [ADR-0003](0003-local-candidate-pool.md) · [ADR-0009](0009-ratings-and-not-for-me.md)

## Context

The PRD requires a conventional, transparent recommender (no ML or LLM ranking in the MVP). It must be deterministic for fixed inputs (PRD §16 #8) and give at least one truthful, system-derived reason per result (FR-10). Weights must be configurable and tested rather than scattered across modules (PRD §8). The project owner asked for:
- separate retrieval, eligibility, scoring and ranking components
- deterministic generation
- an incremental build: advanced techniques (similarity scoring, MMR, impression fatigue, collaborative filtering) are enhancements, not initial requirements
- **title-level signals from M3**, via favorites and stored TMDB recommendation relationships

## Decision

**Structure**
- Five stages with typed inputs and outputs: **retrieval → eligibility → scoring → ranking/diversity → explanation**, plus a pure taste-profile builder.
- **Retrieval is the only stage that does I/O, and it reads only the local database.** Every stage after it is **pure**: no database, no clock (`as_of` is injected), no randomness.
- Stages are plain functions in ordered lists. There's no plugin framework.

**v1 behaviour** (details and initial values in [recommendation-engine.md](../architecture/recommendation-engine.md))
- **Retrieval:** a whole-pool scan (≤2k titles), plus the neighbor index for the user's anchors, **resolved to candidate-pool titles only**.
- **Eligibility:** hard rules re-checked in the pure core. Rejections are returned with reasons.
- **Scoring:** a weighted sum, `0.45·affinity + 0.25·favorite_neighbor + 0.20·quality + 0.10·popularity`.
  - `favorite_neighbor` is a **supporting** title-level signal built from TMDB recommendation lists stored during hydration. Anchors are favorites in M3, plus 4–5★ ratings in M4.
  - If an anchor has no usable neighbors, the signal simply contributes 0 and the other signals rank as usual.
  - Its source (anchor, provider, provider rank) is recorded in every result's score breakdown for explanation and evaluation.
- **Ranking:** a stable sort `(-round(score, 6), title_id)` with simple diversity rules that **consider all of a title's genres**: ≤3 results per genre (context-selected genres exempt), ≤1 per identical genre set, relaxed and logged when they can't be met.
- **Explanations:** generated only from signals that contributed (thresholded), with ≥1 reason guaranteed through a truthful fallback (the pool source). Wording never claims relationships we didn't compute.
- **Configuration:** one versioned `EngineConfig`. `ENGINE_VERSION` and `config_hash` are stored with every request.
- **Evaluation:** fixture catalog and personas, invariant tests (eligibility, reason truthfulness, diversity, shuffle-determinism) and golden tests, updated only with a version bump.

**Deferred, in an explicit enhancement ladder:** time decay, content similarity, mood presets, MMR and franchise caps, impression fatigue, persisted `not_now`, IDF and rating normalization, multi-source retrieval, pool expansion, collaborative filtering, learning-to-rank, LLM mood parsing. Each has a stated trigger.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| A monolithic scoring function with SQL-embedded logic | Hard to test, explain or evolve. Determinism depends on query details |
| TMDB recommendations as the primary strategy | Opaque and provider-dependent. It can't use our genre preferences or context, and it fails silently when lists are missing. Kept as one supporting signal instead |
| Full content-similarity scoring in v1 | Needs keywords and credits modelling first. TMDB lists give a title-level signal at almost no cost |
| MMR diversity in v1 | Needs a similarity measure we don't have yet. The genre caps are simple and explainable |
| "Primary genre = first TMDB genre" for diversity | TMDB doesn't define order as primacy. Counting all genres avoids the assumption |
| Collaborative filtering or ML ranking | No interaction data yet, and out of MVP scope per the PRD |
| LLM-generated explanations | Risk of untruthful claims, cost and latency. Template reasons from actual signals are verifiable |

## Consequences

**Positive**
- Each stage can be unit-tested, results are reproducible, and explanations are truthful by construction.
- Clear extension points for the enhancements.
- Logged breakdowns enable offline evaluation (e.g. whether `favorite_neighbor`-led results get saved more often).

**Negative / accepted costs**
- Genre-level affinity is coarse. Broad genres such as Drama can dominate until E7.
- `favorite_neighbor` quality depends on TMDB's undocumented lists and on pool coverage, so it's monitored through `report` and `anchors_without_neighbors`.
- Golden tests need deliberate updates whenever behaviour changes.

## Revisit when

Evaluation data (action, save, positive-watch and `not_for_me` rates) shows v1 plateauing, the pool outgrows whole-pool retrieval, or enough interaction data exists for collaborative methods.
