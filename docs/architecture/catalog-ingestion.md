# Catalog and Ingestion

**Status:** Draft for review · **Last updated:** 2026-10-30
**Decisions:** [ADR-0003](../adr/0003-local-candidate-pool.md) (local pool) · [ADR-0004](../adr/0004-tmdb-provider-adapter.md) (provider adapter) · [ADR-0005](../adr/0005-catalog-ingestion-cli.md) (ingestion CLI) · [ADR-0006](../adr/0006-sync-sqlalchemy-handler-owned-transactions.md) (transactions)

## 1. Goals and constraints

- Maintain a **local candidate pool** of movie and TV titles in PostgreSQL, populated from TMDB by a separate ingestion process.
- Cover popular, top-rated and genre-specific titles, with reasonable diversity across **genres, release periods, original languages and media types**.
- **Idempotent:** re-running produces the same state, keyed on TMDB IDs (per media type).
- **Track synchronization** and support metadata updates.
- **Keep TMDB out of the recommendation path.**
- Start **modest (~1,000–2,000 titles)**, run **manually**, and design for growth.
- Store TMDB's per-title **recommendation lists**, with their source information, for the `favorite_neighbor` signal.

## 2. Concepts

| Term | Meaning |
|---|---|
| **Catalog** | All rows in `titles`, from any path: ingestion, detail read-through or search |
| **Candidate pool** | Catalog titles with ≥1 pool membership, `detail_level='full'`, `provider_status='active'` and `adult=false` ([data-model.md §4](data-model.md#4-the-candidate-pool-predicate)). Only these can be recommended |
| **Seed source** | One provider list (e.g. top-rated movies, or Korean-language TV) with a page quota and filters |
| **Summary vs full** | A summary row has list-level fields only. A full row has been hydrated with details, credits and recommendation lists |
| **Provider ref** | `(provider, media_type, provider_id)`, the idempotency key |

## 3. Commands

Run manually for now. Scheduling is added later without code changes, because every command is idempotent.

```
python -m screening_room.jobs ingest  [--plan starter-v1] [--media movie|tv|all]
                                      [--max-titles 2000] [--max-requests N] [--dry-run]
python -m screening_room.jobs refresh [--older-than-days 14] [--limit N] [--max-requests N]
python -m screening_room.jobs report
```

| Command | What it does |
|---|---|
| `ingest` | Runs **discover** for every source in the seed plan, then **hydrate** for pool titles that are summary-only or stale |
| `refresh` | Runs **hydrate** only, for pool titles whose `details_synced_at` is older than the TTL |
| `report` | Prints pool composition, staleness, errors and recommendation-list coverage (§12). Makes no API calls |
| `--dry-run` | Prints the planned requests and quotas. No API calls, no writes |
| `--max-requests` | A hard budget on TMDB calls for the run, for safe experimentation |
| `--max-titles` | Caps the pool size. Discover stops adding *new* pool titles once the cap is reached (default 2,000) |

Each run writes an `ingestion_runs` row with its parameters, status and counts.

## 4. Seed plan

The seed plan is a **typed, declarative Python list** in `catalog/ingestion/seed_plan.py`, so mypy checks it and no YAML parser is needed. It's versioned as `SEED_PLAN_VERSION`. Each `SeedSource` has a stable `key`, media type, endpoint, parameters and page quota. **Growing the pool means editing this list** (adding sources or raising quotas). No code changes are needed.

### 4.1 `starter-v1` (initial values)

Each row applies to **both movie and TV** unless noted. One page holds 20 results.

| Diversity axis | Source | Pages | Notes |
|---|---|---|---|
| Popularity | `popular` | 3 | Recency-weighted popularity |
| Quality | `top_rated` | 3 | |
| Genre | `discover` with `with_genres=<g>`, `sort_by=vote_count.desc` | 2 per genre | Every provider genre except movie "TV Movie" and TV "News" and "Talk" (poor fits for a "what to watch" shortlist) |
| Release period | `discover` per decade, 1970s–2020s, `sort_by=vote_count.desc` | 1 per decade | Uses release date for movies and first-air date for TV |
| Language | `discover` with `with_original_language=<l>` for ko, ja, fr, es, hi, de, it, zh | 1 per language | Lower vote floor (below) |

**Quality floors (initial values):** `vote_count.gte` of 200 for movies and 100 for TV, and 50 / 30 for the language sources. These keep obscure titles with too few votes out.

**Expected size:**

| | Raw hits | |
|---|---|---|
| Movies | ~1,120 | 60 + 60 + 18 genres × 40 + 6 decades × 20 + 8 languages × 20 |
| TV | ~960 | 60 + 60 + 14 genres × 40 + 120 + 160 |
| **Total** | **~2,080** | **~1,300–1,600 unique titles** after de-duplication |

Hydration costs about one request per unique title. The real numbers are checked with `report` after the first run, and quotas are tuned to stay within 1,000–2,000.

Unreleased titles (which can appear in `popular`) are stored and pooled, but the engine excludes them until their release date ([recommendation-engine.md §6](recommendation-engine.md#6-stage-2-eligibility)).

### 4.2 Internal genre taxonomy

TMDB's movie and TV genre lists differ. TV merges some genres, e.g. "Action & Adventure". We map both onto one internal taxonomy so that genre affinity works across media types.

| Provider genre(s) | Internal genre(s) |
|---|---|
| Movie: Action · TV: Action & Adventure | `action` (+ `adventure` for the TV genre) |
| Movie: Adventure | `adventure` |
| Movie: Science Fiction · TV: Sci-Fi & Fantasy | `science-fiction` (+ `fantasy` for the TV genre) |
| Movie: Fantasy | `fantasy` |
| TV: War & Politics · Movie: War | `war` (+ `politics` for the TV genre) |
| Movie: Family · TV: Kids, Family | `family` / `kids` (kept separate) |
| Same name in both lists (Animation, Comedy, Crime, Documentary, Drama, Mystery, Western) | One internal genre each |
| Movie-only (History, Horror, Music, Romance, Thriller, TV Movie) | One internal genre each |
| TV-only (Reality, Soap, News, Talk) | One internal genre each (News and Talk aren't seeded) |

The taxonomy and mapping are reference data, loaded by a migration and reviewed in M2. The adapter fetches the provider genre lists and **fails loudly** if a provider genre has no mapping, rather than silently dropping it.

TMDB genre IDs are one shared ID space across its movie and TV lists, and titles are sometimes tagged with a genre only the other list offers. The first real ingestion found a TV show tagged 10749 "Romance", a movie-only genre. Such a genre uses the other media type's mapping. Ingestion still stops on an ID that neither list knows. *(Decided in M2.)*

## 5. Sizing and growth

Start with ~1,000–2,000 titles, and **grow only on evidence**. `report` and the recommendation logs make each trigger measurable:

| Trigger | Signal | Typical response |
|---|---|---|
| Thin genre or decade coverage | Any media type × internal genre cell, or media type × decade cell, with < 30 pool titles | Add pages to that source |
| Thin candidate sets | More than 5% of recommendation requests with < 25 eligible candidates, or < 5 results | Raise quotas for the most-requested context combinations |
| Users' titles outside the pool | High share of favorites (and in M4, saved or rated titles) that aren't pool members | Add sources, or (E9) pool expansion from user anchors |
| Weak neighbor coverage | Low share of anchors' recommendation targets that resolve to pool titles | Add sources, or (E9) ingest the unresolved targets |

Growing the pool changes recommendation inputs, so it's a documented dataset change for determinism purposes ([ADR-0010](../adr/0010-staged-deterministic-recommendation-pipeline.md)). Retrieval is designed to stay a whole-pool scan up to roughly 20k titles. Beyond that, see E8.

## 6. Phase 1: discover

For each seed source, in plan order, for each page up to its quota:

1. **Fetch** the page from TMDB with no database transaction open.
2. In **one short transaction**:
   - upsert each result into `titles` with `INSERT … ON CONFLICT (provider, media_type, provider_id) DO UPDATE`, writing **summary fields only** and never downgrading `detail_level` from `full` to `summary`
   - set `summary_synced_at`
   - set `first_ingested_at` on insert only
   - upsert `candidate_pool_memberships (title_id, source_key)` with `source_rank` and `last_seen_run_id`, setting `first_seen_run_id` on insert only
3. **Commit**, then fetch the next page.

The same title appearing in five sources is still one `titles` row, with five membership rows.

## 7. Phase 2: hydrate

1. In a short read transaction, select the provider refs of pool titles where `detail_level = 'summary'` or `details_synced_at < now() − TTL`, **ordered by `titles.id`**. Convert them to plain values, then end the transaction.
2. Fetch details through a thread pool (§10). Each call uses `append_to_response=credits,recommendations`, so one request per title returns details, credits and page 1 of the recommendation list (≤20 entries).
3. On the **main thread**, for each result **in submission order**, open one transaction per title and:
   - update the title's detail fields, and set `detail_level='full'`, `details_synced_at`, `sync_error_count = 0`
   - **replace** `title_genres` and `title_credits` (delete + insert)
   - **replace** `provider_title_recommendations` for this source title with `provider='tmdb'`, `provider_rank`, `fetched_at` and `ingestion_run_id`. Targets are stored as provider refs even if they aren't in our catalog.
4. **Commit** that title's transaction before waiting on the next fetch result.

## 8. Idempotency and resumability

| Guarantee | How |
|---|---|
| Re-running `ingest` creates no duplicates | The unique provider-ref key, plus `ON CONFLICT` upserts for titles, memberships, genres and people |
| Child collections converge | Genres, credits and recommendation lists are replaced wholesale per title inside one transaction |
| Interrupted runs lose ≤1 title of work | Hydrate commits per title. Re-running selects whatever is still summary-only or stale |
| Runs are auditable | `ingestion_runs` stores params, counts and status, and memberships record first and last seen runs |
| Re-running with identical provider data gives an identical end state | Verified by an integration test with `FakeProvider` (§12) |

## 9. Sync tracking and refresh

| Field | Meaning |
|---|---|
| `first_ingested_at` | First time we stored the title by any path |
| `summary_synced_at` | Last time summary fields were written (discover, search) |
| `details_synced_at` | Last successful hydration. Drives staleness |
| `sync_error_count`, `last_sync_error`, `last_sync_error_at` | Consecutive hydration failures. Reset on success |
| `provider_status` | `missing` after a provider 404. The row is kept and excluded from the pool |

A single TTL (initial value: 14 days) applies to all titles in the MVP. `refresh` re-hydrates stale pool titles.

**Deferred:**
- per-type TTLs (e.g. shorter for ongoing TV)
- TMDB's `/changes` endpoints, to refresh only titles that changed
- pruning memberships not seen for N runs (`report` lists them, but nothing is pruned automatically)

## 10. Failure handling, rate limiting and concurrency

| Condition | Behaviour |
|---|---|
| Timeout, connection error, HTTP 5xx | Retry with exponential backoff and jitter, at most 3 attempts in the CLI (≤1 retry on API user-facing paths). Then record the sync error and continue |
| HTTP 429 | Honour `Retry-After` and slow the token bucket. Counts toward the attempt limit |
| HTTP 404 on a title | Set `provider_status='missing'`, keep the row, continue |
| HTTP 401/403 | Abort the run (bad credentials) with status `failed` |
| Unmapped provider genre | Abort with a clear error (§4.2) |
| Some titles failed | Run status `partial`, with counts in `ingestion_runs.counts` |

- **Concurrency:** a `ThreadPoolExecutor` (initial value: 8 workers) with a shared sync `httpx.Client` performs the HTTP calls. A token bucket (initial value: 20 requests/s, configurable, kept well below TMDB's published limits) throttles them.
- **Database writes happen only on the main thread,** because a SQLAlchemy Session isn't thread-safe.
- **No transaction or connection is held while waiting on HTTP.** Each write transaction is committed before the main thread blocks on the next result.
- **Secrets:** the TMDB token is sent as a header and never logged. Logs record the endpoint path and status, not full URLs with credentials.

## 11. Read-through paths in the API

The API reuses the same adapter, mapper and upsert functions as ingestion. The flow is implemented once in `catalog/read_through.py`, a handler-level helper ([project-structure.md §5.3](project-structure.md#53-who-may-end-a-transaction)), and **never holds a transaction or a checked-out connection while TMDB is called**.

**Title detail (`GET /api/titles/{id}`, M2)**
1. Load the title as a DTO in the request's autobegun transaction.
2. If it's `full` and fresh, return it (no commit).
3. Otherwise **end the read transaction** (`end_read_transaction`), then call TMDB with a short timeout (connect ~3 s, read ~5 s, ≤1 retry).
4. On success, run a short write transaction that hydrates the title exactly as §7 step 3 does (including its recommendation list, with `ingestion_run_id = NULL`), commit, reload and return it with `metadata_status: "fresh"`.
5. On failure, record the sync error (short transaction, commit) and return the existing data with `metadata_status: "stale"` (full but old) or `"partial"` (summary only).

A detail view doesn't add the title to the candidate pool. Pool membership comes only from seed sources (and, later, E9).

**Local pool search (`GET /api/titles?q=&media_type=`, M3)**: used by the onboarding favorites picker before TMDB search exists. It's a local-only, case-insensitive match on `name` and `original_name` over candidate-pool titles, ordered by quality and then `title_id`. A sequential scan is fine at ≤2,000 rows, and a `pg_trgm` index is added if the pool grows. It never calls TMDB.

**Search (`GET /api/search`, M4)**
1. End the request's read transaction.
2. Call TMDB multi-search, filtered to movies and TV, and excluding adult content.
3. In a short transaction, upsert the results as `summary` rows (stable internal IDs, no pool membership) and commit.
4. Return the results.

Upserting on a GET is a cache fill, not a user-state change, and it's idempotent.

**Non-pool favorites (M4):** once TMDB search exists, users can favorite titles outside the pool. Adding the favorite commits first. If the title isn't `full`, the handler then calls `read_through.hydrate(...)`, so its recommendation list becomes available as an anchor. If hydration fails, the favorite still exists and contributes through genre affinity once hydrated later.

## 12. Verification

**Automated (M2):**
- Mapper tests against recorded TMDB JSON fixtures, for movie, TV, missing fields and unmapped genres.
- **Idempotency test:** ingest the same `FakeProvider` dataset twice, then assert identical row counts and identical content for titles, genres, credits, memberships and recommendation lists.
- **Resumability test:** interrupt hydrate halfway, re-run, assert the same end state as an uninterrupted run.
- **Read-through test:** the provider is called only after the read transaction has ended (assert that no connection is checked out during the fake provider call), and the stale-on-failure response is returned.

**`report` output (manual, after each run):**
- Pool size by media type. Counts by internal genre, by decade and by original language (top 10 + other).
- `detail_level` breakdown, stale count (older than TTL), `missing` count, titles with sync errors.
- **Recommendation-list coverage:** pool titles with a stored list, mean list length, share of targets that resolve to pool titles, and titles whose list resolves to zero pool titles.
- Memberships not seen in the latest run.

The first `report` against the real API is kept as M2 evidence.

## 13. Deferred

| Item | Trigger |
|---|---|
| Scheduled runs (cron container or platform scheduler) | Manual runs become a chore, or before public deployment |
| `/changes`-based incremental refresh | Refresh volume or rate limits become a concern |
| Per-type TTLs | Ongoing TV metadata is noticeably stale |
| Membership pruning | Stale memberships distort the pool |
| Pool expansion from user anchors and unresolved neighbors (E9) | Coverage triggers in §5 |
| Keywords and collections hydration | E2, E3, E4 |
| Streaming availability (watch providers) | Product decision ([open-questions.md](open-questions.md)) |
| Localized metadata (non-`en-US`) | Non-English audience |
