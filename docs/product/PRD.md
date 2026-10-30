# Screening Room — Product Requirements Document

**Version:** 0.1  
**Date:** October 30, 2026  
**Status:** Draft for product and architecture discovery  
**Working tagline:** Less scrolling. Better watching.

## 1. Product summary

Screening Room is a personalized movie and TV discovery application designed to help people decide what to watch with less browsing. It combines a lightweight taste profile, viewing history, explicit feedback, and the context of the current viewing session to produce a short, explainable list of relevant titles.

The initial product is a responsive web application. It is not intended to be a streaming service, a social network, or a general-purpose film database. Its primary job is to turn the question “What should I watch?” into a small set of good options.

## 2. Problem statement

People have access to a large and fragmented catalog of movies and TV shows. The abundance of options can make choosing difficult: users browse across services, encounter repetitive recommendations, and often spend more time deciding than they want to.

Existing viewing history and preferences are useful signals, but a person's intent also changes from one session to another. Someone may usually enjoy science fiction but want a light comedy tonight, or may have only 90 minutes available. Screening Room should combine longer-term taste with current context.

**Problem to solve:** Help a user reach a relevant, actionable shortlist quickly, with enough explanation to understand why each title was recommended.

## 3. Product vision and positioning

**Vision:** A personal discovery companion that gets better at helping someone choose their next movie or show as it learns from their tastes and viewing behavior.

**Core promise:** A short, relevant shortlist instead of an endless catalog.

**Initial differentiation hypothesis:** Recommendations should reflect both evolving viewing preferences and the user's current intent (mood, available time, movie vs. TV, and similar constraints). This is a hypothesis to validate with users, not a claim of proven market differentiation.

## 4. Goals and non-goals

### Goals

1. Help a user get to a useful shortlist in a few interactions.
2. Personalize recommendations using onboarding preferences, watched titles, ratings, saves, and negative feedback.
3. Support both movies and TV shows in the discovery experience.
4. Make recommendations understandable by showing concise reasons for each result.
5. Let users record viewing activity and use it to improve future recommendations.
6. Build a maintainable foundation that can be extended without prematurely adopting distributed architecture.

### Non-goals for the MVP

- Streaming, hosting, or playing video content.
- Social feeds, following, comments, public profiles, and group voting.
- Native iOS or Android applications (responsive web first; PWA can be considered later).
- An LLM-powered chatbot or agent as the recommendation engine.
- Collaborative filtering or machine-learning ranking in the first release.
- Episode-level TV tracking; TV shows are tracked at the show level initially.
- Guaranteed streaming availability or subscription-aware deep links.
- Full catalog ingestion. Movie and show metadata is fetched and persisted selectively as needed.

## 5. Target users and primary jobs

### Primary user: The overwhelmed viewer

Watches movies or shows regularly, has access to multiple catalogs, and wants to spend less time browsing.

**Job to be done:** “When I want to watch something, help me quickly find a title that fits my taste and what I feel like watching right now.”

### Secondary user: The intentional viewer

Enjoys tracking what they have watched, rating titles, and maintaining a watchlist. They are willing to provide feedback if it improves future recommendations.

**Job to be done:** “Help me remember what I watched and use that history to make better suggestions.”

## 6. Core user journeys

### Journey A — First-time onboarding

1. User creates an account.
2. User selects a manageable number of favorite titles and/or genres, and optionally identifies genres or content they tend to avoid.
3. The application creates an initial taste profile.
4. User lands on discovery and can immediately request recommendations.

Onboarding must not require a lengthy questionnaire. Users can skip optional preference questions and improve recommendations through later feedback.

### Journey B — Find something to watch now

1. User opens the “Find something” experience.
2. User optionally sets current context: movie or TV, mood/genre, available runtime, and other simple filters selected for the MVP.
3. The system generates a ranked shortlist of approximately 3–5 titles.
4. Each result provides a poster, title, type, release year, brief overview, and a concise explanation of why it matches.
5. User can open details, save to watchlist, mark as watched, or dismiss / indicate “not for me.”

The user should be able to get recommendations without completing every context field.

### Journey C — Record viewing activity

1. User finds a title or opens one from their library.
2. User marks it as watched and can optionally provide a rating and review.
3. The system records the viewing event and updates the user's recommendation signals.
4. The title is excluded from ordinary “unwatched” recommendations by default, but remains discoverable through search and history.

### Journey D — Manage a watchlist

1. User saves a title from discovery or search.
2. User views, removes, or marks saved titles as watched.
3. Saved titles can be used as a signal for future personalization, but saving is not treated as equivalent to liking a title.

## 7. MVP scope and functional requirements

Priority definitions: **P0** = required for first usable release; **P1** = valuable follow-up; **Out** = explicitly excluded from MVP.

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-01 | P0 | Account registration and sign-in | A user can create an account, sign in, sign out, and access only their own private data. |
| FR-02 | P0 | Taste onboarding | A user can select favorite titles and/or genres; optional questions can be skipped. Preferences can be edited later. |
| FR-03 | P0 | Movie and TV catalog search | A user can search for movies and TV shows and open a normalized detail page. |
| FR-04 | P0 | Title details | Detail pages show core metadata such as title, media type, release/first-air year, overview, genres, artwork, and available credits where supplied by the provider. |
| FR-05 | P0 | Watchlist | A user can add and remove movies/shows from a personal watchlist. Duplicate entries are prevented. |
| FR-06 | P0 | Viewing history | A user can mark a movie/show as watched and view their history. The initial version tracks TV at show level, not by episode. |
| FR-07 | P0 | Ratings and feedback | A user can optionally rate a watched title and indicate that a recommendation was not relevant. Feedback is associated with the user and title. |
| FR-08 | P0 | Personalized recommendation shortlist | The system returns a ranked shortlist of approximately 3–5 eligible titles based on the user's available preference and behavior signals. |
| FR-09 | P0 | Session context | A user can optionally specify movie/TV/either, mood or genre direction, and available runtime where applicable. Context changes candidate eligibility or ranking. |
| FR-10 | P0 | Recommendation explanation | Each recommendation includes at least one truthful, system-derived reason, such as genre affinity, similarity to a highly rated title, or fit with the selected session context. |
| FR-11 | P0 | Recommendation actions | A user can open a result, save it, mark it watched, or dismiss it / mark it “not for me.” |
| FR-12 | P0 | Basic library views | A user can view watchlist and watched titles, with basic filtering by media type. |
| FR-13 | P1 | Review text | A user can write, edit, and delete a text review for a title they have watched. |
| FR-14 | P1 | Basic viewing statistics | A user can see simple counts and summaries, such as titles watched by month and most-watched genres. |
| FR-15 | Out | Social graph and activity feed | Not part of the first release. |
| FR-16 | Out | Streaming provider availability | Defer until a suitable data source, region handling, licensing, and freshness strategy are evaluated. |

## 8. Recommendation behavior — MVP definition

The MVP should use a transparent, conventional recommendation approach before introducing machine learning. The initial engine should be deterministic enough to test and explain.

### Candidate generation

Generate a candidate pool from locally stored catalog records and/or provider search/discovery endpoints. Candidate sources may include genre affinity, similarity to positively rated or favorited titles, and broadly popular titles as a fallback for sparse profiles.

### Eligibility filtering

Remove or down-rank titles that:
- The user has already marked as watched (unless the user explicitly asks to revisit watched titles).
- The user has explicitly dismissed or marked “not for me,” subject to a defined re-recommendation policy.
- Conflict with hard session constraints, such as selected media type or maximum runtime when runtime metadata is available.

Missing metadata should not cause the application to fail. For example, a title with unknown runtime can be omitted when a strict maximum runtime filter is selected, or retained with a clear uncertainty policy.

### Ranking signals

The initial ranking model may combine:
- Genre and metadata affinity from onboarding preferences.
- Similarity to titles the user rated highly or marked as favorites.
- Negative signals from low ratings and explicit dismissals.
- Recency of viewing behavior, with a time-decay policy so recent activity has influence without completely overriding long-term taste.
- Session context such as mood, media type, and available runtime.
- Popularity or quality proxies as a fallback / tie-breaker, not as the sole personalization mechanism.

Weights and thresholds should be configurable and covered by tests. They should not be hard-coded across multiple modules.

### Diversity

The final shortlist should avoid returning several near-duplicates. A simple diversity step can limit repeated genres, franchises, or highly similar candidates where metadata supports it.

### Explainability

Recommendation explanations must be derived from the signals actually used. Do not invent claims such as “because you loved this director” unless the user history and metadata support that explanation.

### Cold start

When a user has little or no history, use onboarding preferences and a general discovery fallback. The application should explain that recommendations will improve as the user rates, saves, watches, or dismisses titles.

## 9. Data and external integrations

### Initial metadata source

Evaluate TMDB as the initial source for movie and TV metadata. Integrate through a provider adapter so the rest of the application depends on an internal normalized model rather than provider-specific response shapes.

### Local persistence strategy

Do not mirror the entire external catalog. Persist metadata for titles that are viewed, saved, rated, or otherwise needed by the application, plus any deliberately cached discovery candidates. Store the provider's external identifier and track metadata refresh timestamps.

### Resilience requirements

- Apply request timeouts and bounded retries for transient provider failures.
- Respect provider rate limits and retry guidance; do not retry indefinitely.
- Cache suitable metadata and avoid repeated external calls for the same title.
- Handle missing or changed external records gracefully.
- Keep provider credentials on the server; never expose secret API keys in the browser.
- Review provider attribution and licensing requirements before public deployment or monetization.

## 10. Conceptual data domains

The PRD does not prescribe the final schema, but the initial model is expected to cover:

- **Identity:** users and authentication credentials / identities.
- **Catalog:** normalized titles, media type, genres, people/credits where needed, provider identifiers, and metadata refresh information.
- **Taste profile:** explicit preferences and exclusions.
- **Library:** watchlist entries, viewing events, ratings, reviews, and dismissal feedback.
- **Discovery:** recommendation sessions, generated results, ranking/explanation metadata, and user actions on results.

A key modeling distinction: a title being in a watchlist, being watched, being rated, or being dismissed are different user-title relationships and should not be collapsed into one ambiguous status field unless the tradeoffs are explicitly evaluated.

## 11. Non-functional requirements

| Area | Requirement / initial target |
|---|---|
| Performance | For a warm local catalog and ordinary profile size, target recommendation response p95 under 1.5 seconds at initial launch, excluding any slow external metadata fetch performed synchronously. Validate with load tests; revise based on evidence. |
| Reliability | External catalog outages should not make a user's saved library or viewing history unavailable. Discovery should degrade gracefully when live catalog data cannot be fetched. |
| Security | Store password hashes using a recognized password-hashing approach; validate authorization on the server; protect secrets; apply input validation and safe error handling. |
| Privacy | Keep viewing history, ratings, preferences, and library private by default. Collect only data needed for product behavior. Provide a way to delete an account and associated personal data, subject to documented retention requirements. |
| Data integrity | Enforce ownership, uniqueness, and referential constraints in the database. Use transactions for multi-step state changes where required. |
| Accessibility | Build responsive layouts and support keyboard navigation, semantic markup, adequate contrast, and accessible form labels. |
| Maintainability | Use clear module boundaries, typed request/response schemas, migrations, automated tests, and documented architecture decisions. |
| Observability | Record structured application logs and key metrics for API errors, provider failures, recommendation latency, and user actions. Do not log passwords, tokens, or unnecessary personal data. |
| Portability | Local development should be reproducible using documented setup instructions and containerized dependencies where practical. |

## 12. Success measures and validation

These are proposed validation targets, not established baselines.

### Primary product outcome

**Time to useful shortlist:** In moderated usability testing, a new user should be able to reach a shortlist they consider worth considering in approximately two minutes or less, without needing to browse a long catalog.

### Supporting measures

- Recommendation action rate: proportion of recommendation sessions that result in a detail view, save, watched mark, or other meaningful action.
- Positive feedback rate: proportion of recommendations rated positively or later marked watched with a positive rating.
- Dismissal rate: proportion of recommendations marked “not for me”; segment by reason if collected.
- Repeat discovery usage: whether users return for another discovery session.
- Coverage: proportion of users for whom the system can generate a shortlist despite sparse history.
- Latency and reliability: recommendation endpoint latency and provider error rates.

Do not optimize solely for clicks. A click is not proof that a recommendation was useful. Where feasible, validate whether a recommendation led to a satisfying watch.

## 13. Release plan

### Milestone 0 — Product and technical definition

- Validate the problem with a small number of target users.
- Finalize the MVP scope and key user journeys.
- Compare major architecture options and record ADRs.
- Design an initial relational model and API contract.
- Confirm metadata provider constraints and attribution requirements.

### Milestone 1 — End-to-end foundation

- Repository and local development environment.
- FastAPI application, React application, PostgreSQL, migrations, and CI checks.
- Authentication and basic user profile.
- Provider adapter and basic movie/TV search/detail flow.

### Milestone 2 — Personal library

- Watchlist, watched history, ratings, and feedback.
- User-specific library views.
- Database constraints and tests for state transitions.

### Milestone 3 — Recommendation MVP

- Candidate generation, filtering, ranking, and diversity pass.
- Session context controls.
- Explainable recommendation results.
- Recommendation event capture and evaluation fixtures.

### Milestone 4 — Polish and deployment

- Responsive UI and accessibility pass.
- Error handling, observability, security review, and performance testing.
- Public deployment and a concise product demonstration.

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Recommendations feel generic | Use multiple signals, expose feedback controls, and evaluate with realistic user profiles and test cases. |
| Cold-start recommendations are weak | Allow lightweight onboarding and provide a useful fallback; make preference editing easy. |
| Metadata provider is unavailable or restrictive | Use an adapter, cache appropriately, review licensing, and avoid coupling business logic to provider responses. |
| Scope grows into a social network or streaming guide | Keep the MVP focused on personal discovery and defer social features and availability aggregation. |
| Sparse or inaccurate metadata weakens ranking | Define missing-data behavior and avoid pretending uncertain attributes are known. |
| Users do not provide ratings | Treat passive and lightweight signals (watchlist, watched, dismiss) as useful but distinct evidence. |
| Recommendation metrics are misleading | Combine offline ranking tests, usability sessions, explicit feedback, and downstream watch outcomes. |

## 15. Open questions for product and architecture discovery

1. Should onboarding start with favorite titles, genres, or a mix of both?
2. What does “recently watched” mean for recommendation purposes: last few titles, a time window, or a decayed signal?
3. Should users be able to distinguish “watched and liked,” “watched but did not like,” and “watched but unrated” explicitly?
4. Which session controls are genuinely useful without making the discovery flow feel like a form?
5. Should a TV show be treated as watched when the user finishes a season, finishes the series, or simply marks the show as watched? MVP assumption: show-level tracking only, explicitly controlled by the user.
6. What catalog metadata and image usage are permitted under the selected provider's current terms?
7. Is streaming availability essential to the first public release, or can the product initially focus on choosing a title?
8. How should dismissed titles re-enter recommendations, if at all?

## 16. Initial acceptance criteria for the MVP

The MVP is ready for an initial user test when:

1. A user can register, sign in, and maintain a private profile.
2. A user can search for and view movie and TV title details.
3. A user can add and remove titles from a watchlist and mark titles as watched.
4. A user can provide a rating or dismiss a recommendation.
5. A user can request a small recommendation shortlist with optional session context.
6. Results are filtered against watched and dismissed titles according to documented rules.
7. Each recommendation has a truthful reason tied to profile, history, or session context.
8. Recommendation ranking is deterministic for a fixed catalog/profile/context fixture, subject to explicitly documented external metadata updates.
9. Important business rules have automated tests, and the application can be run locally using the documented setup.
10. The team can demonstrate the primary journey from onboarding to selecting and saving a recommendation.

## 17. Interview and engineering evidence

The project should produce real artifacts that make the engineering work easy to explain: the PRD and user journeys, system context and component diagrams, ADRs with alternatives and tradeoffs, database ER diagram and migration history, API specification and integration error-handling strategy, recommendation algorithm documentation and evaluation fixtures, automated tests and CI pipeline, plus deployment and measured performance evidence.

Interview claims should reflect what was actually implemented and measured. Do not describe planned features as completed, claim unmeasured scale, or invent performance improvements.

---

**Document owner:** Project owner  
**Next step:** Review the open questions, validate the core problem with a few potential users, then create the system architecture and initial data model.
