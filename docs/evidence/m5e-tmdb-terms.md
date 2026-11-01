# M5e TMDB terms review

Read 2026-10-31 from TMDB's [API Terms of Use](https://www.themoviedb.org/api-terms-of-use) and
[logos and attribution](https://www.themoviedb.org/about/logos-attribution) pages. Not legal advice;
TMDB may change its terms at any time (§10.H), so re-read them before relying on this.

## Decision (open question O1 / Q6)

**Screening Room is a free, non-commercial portfolio project** (decided by the project owner,
2026-10-31). TMDB's free API license covers non-commercial use only (§2.A). Ads, paid features or
anything else that drives revenue would need a separate written agreement with TMDB first.

## Obligations and status

| Term | What it requires | Status |
|---|---|---|
| §2.A Non-commercial | No ads, payments or revenue | ✅ Decided above. Revisit before any monetization |
| §3 Logo | TMDB's logo identifies our use of TMDB; less prominent than our own branding; no implied endorsement | ✅ Official "Alt short" SVG (downloaded from TMDB with the owner's OK, checked: no scripts) in every page's footer at 12 px and on `/about`, linking to themoviedb.org. The "Screening Room" name in the header is larger |
| §3 Notice | Prominently: "This website uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB." | ✅ Verbatim in every page's footer and on `/about`. A test compares it against the terms' wording |
| §1.C Caching | Don't cache anything from TMDB for longer than 6 months | ✅ in code, needs scheduling: `refresh` now covers every stored title (it was pool titles only; titles from search could go stale indefinitely), and the new `prune` deletes old titles outside the pool that nobody uses. **Run `prune` then `refresh` at least weekly in production (M5f)**. With the 14-day TTL, data is then at most about 3 weeks old |
| §1.C Images | Don't use TMDB as image hosting for banner ads | ✅ Posters are shown only next to their titles |
| §1.C Bandwidth | No excessive use or impairing TMDB's service | ✅ Client-side rate limiting (20 requests/s for ingestion), retries with backoff, search debounced, results cached for 5 minutes in the browser |
| §2.A AI/ML | Don't use TMDB data to train machine learning or AI systems | ✅ The recommender is rules-based (ADR-0010) and trains nothing |
| §2.A Datasets | Don't share cached TMDB data with others | ✅ The database isn't shared or exported |
| §1.D, §5 Termination | On termination, stop using the API and delete all TMDB content | ⚠️ No automated "delete everything" step. If it's ever needed: `docker compose down -v` locally; in production, drop the catalog tables (user data references titles, so in practice the whole database) |

## Edge case noted, not solved

A title TMDB no longer has (404, `provider_status = missing`) that a user still references can't be
refreshed or deleted. Its old data stays. Rare; revisit if it ever matters (e.g. clear its
TMDB-derived fields after 6 months).
