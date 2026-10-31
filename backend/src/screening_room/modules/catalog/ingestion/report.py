"""`jobs report`: what's in the pool and how healthy it is (catalog-ingestion.md §5, §12).

Read-only, no provider calls. Uses the same in_candidate_pool() rule as the rest
of the app, so the numbers match what recommendations will actually see.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from screening_room.modules.catalog import service
from screening_room.modules.catalog.ingestion.seed_plan import SEEDED_GENRES
from screening_room.modules.catalog.models import (
    CandidatePoolMembership,
    Genre,
    IngestionRun,
    ProviderGenreMap,
    ProviderTitleRecommendation,
    Title,
    TitleGenre,
)
from screening_room.modules.catalog.providers.base import MediaType

THIN_CELL = 30  # a media type x genre/decade cell below this is "thin" (§5)
TOP_LANGUAGES = 10


def build_report(session: Session, *, now: datetime, ttl_days: int) -> str:
    lines = [f"Screening Room catalog report ({now:%Y-%m-%d %H:%M} UTC)", ""]
    lines += _latest_run(session)
    lines += _pool_and_health(session, now - timedelta(days=ttl_days), ttl_days)
    lines += _by_genre(session)
    lines += _by_decade(session)
    lines += _by_language(session)
    lines += _recommendation_coverage(session)
    lines += _unseen_memberships(session)
    return "\n".join(lines) + "\n"


def _latest_run(session: Session) -> list[str]:
    run = session.scalars(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(1)).first()
    if run is None:
        return ["No ingestion runs yet.", ""]
    counts = ", ".join(f"{k}={v}" for k, v in sorted(run.counts.items()))
    return [
        f"Latest run: #{run.id} {run.command} ({run.seed_plan_version or '-'}), {run.status}",
        f"  started {run.started_at:%Y-%m-%d %H:%M}, finished {run.finished_at:%Y-%m-%d %H:%M}"
        if run.finished_at
        else "  still running",
        f"  counts: {counts}",
        *([f"  note: {run.error_summary}"] if run.error_summary else []),
        "",
    ]


def _pool_and_health(session: Session, stale_before: datetime, ttl_days: int) -> list[str]:
    candidates = dict(
        session.execute(
            select(Title.media_type, func.count())
            .where(service.in_candidate_pool())
            .group_by(Title.media_type)
        ).all()
    )
    members = service.has_pool_membership()
    detail_levels = dict(
        session.execute(
            select(Title.detail_level, func.count()).where(members).group_by(Title.detail_level)
        ).all()
    )

    def count(*conditions: ColumnElement[bool]) -> int:
        return (
            session.scalar(select(func.count()).select_from(Title).where(members, *conditions)) or 0
        )

    stale = count(Title.details_synced_at < stale_before)
    return [
        f"Candidate pool: {sum(candidates.values())} titles "
        f"(movie {candidates.get('movie', 0)}, tv {candidates.get('tv', 0)})",
        f"  pool members by detail level: full {detail_levels.get('full', 0)}, "
        f"summary only {detail_levels.get('summary', 0)}",
        f"  stale (details older than {ttl_days} days): {stale}",
        f"  missing at provider: {count(Title.provider_status == 'missing')}",
        f"  with sync errors: {count(Title.sync_error_count > 0)}",
        "",
    ]


def _table(title: str, rows: dict[str, Counter[str]], flag_thin: set[tuple[str, str]]) -> list[str]:
    lines = [title, f"  {'':<22}{'movie':>7}{'tv':>7}"]
    for name in sorted(rows):
        cells = []
        for media in ("movie", "tv"):
            n = rows[name][media]
            cells.append(f"{n}{'!' if (name, media) in flag_thin and n < THIN_CELL else ' '}")
        lines.append(f"  {name:<22}{cells[0]:>7}{cells[1]:>7}")
    lines += [f"  ! = fewer than {THIN_CELL} titles (thin coverage, see §5)", ""]
    return lines


def _by_genre(session: Session) -> list[str]:
    rows: dict[str, Counter[str]] = defaultdict(Counter)
    for slug, media, n in session.execute(
        select(Genre.slug, Title.media_type, func.count())
        .join(TitleGenre, TitleGenre.genre_id == Genre.id)
        .join(Title, Title.id == TitleGenre.title_id)
        .where(service.in_candidate_pool())
        .group_by(Genre.slug, Title.media_type)
    ):
        rows[slug][media] = n
    # Only flag cells the seed plan actually targets (e.g. no "kids" movies exist).
    seeded = {
        (slug, media)
        for slug, media, provider_genre_id in session.execute(
            select(
                Genre.slug, ProviderGenreMap.media_type, ProviderGenreMap.provider_genre_id
            ).join(ProviderGenreMap, ProviderGenreMap.genre_id == Genre.id)
        )
        if provider_genre_id in SEEDED_GENRES.get(cast(MediaType, media), {})
    }
    for slug, media in seeded:
        rows[slug][media] += 0  # show seeded genres even when empty
    return _table("Candidates by genre:", rows, seeded)


def _by_decade(session: Session) -> list[str]:
    # e.g. 1994 -> 1990. NULL release dates stay NULL ("unknown").
    decade: ColumnElement[Any] = func.floor(func.extract("year", Title.release_date) / 10) * 10
    rows: dict[str, Counter[str]] = defaultdict(Counter)
    for start, media, n in session.execute(
        select(decade, Title.media_type, func.count())
        .where(service.in_candidate_pool())
        .group_by(decade, Title.media_type)
    ):
        rows["unknown" if start is None else f"{int(start)}s"][media] = n
    targeted = {(f"{d}s", m) for d in range(1970, 2030, 10) for m in ("movie", "tv")}
    return _table("Candidates by decade (release / first air):", rows, targeted)


def _by_language(session: Session) -> list[str]:
    counts = Counter(
        dict(
            session.execute(
                select(func.coalesce(Title.original_language, "unknown"), func.count())
                .where(service.in_candidate_pool())
                .group_by(Title.original_language)
            ).all()
        )
    )
    top = counts.most_common(TOP_LANGUAGES)
    other = sum(counts.values()) - sum(n for _, n in top)
    parts = [f"{language} {n}" for language, n in top] + ([f"other {other}"] if other else [])
    return ["Candidates by original language:", "  " + ", ".join(parts or ["none"]), ""]


def _recommendation_coverage(session: Session) -> list[str]:
    """How useful the provider recommendation lists are for favorite_neighbor."""
    candidates = {
        (provider, media, provider_id): title_id
        for title_id, provider, media, provider_id in session.execute(
            select(Title.id, Title.provider, Title.media_type, Title.provider_id).where(
                service.in_candidate_pool()
            )
        )
    }
    lists: dict[int, list[bool]] = defaultdict(list)  # source title -> "target is a candidate?"
    for source, provider, media, target_id in session.execute(
        select(
            ProviderTitleRecommendation.source_title_id,
            ProviderTitleRecommendation.provider,
            ProviderTitleRecommendation.target_media_type,
            ProviderTitleRecommendation.target_provider_id,
        )
    ):
        if source in candidates.values():
            lists[source].append((provider, media, target_id) in candidates)
    if not candidates:
        return ["Recommendation lists: no candidates yet.", ""]
    targets = [resolved for entries in lists.values() for resolved in entries]
    resolved_share = sum(targets) / len(targets) if targets else 0.0
    mean_length = len(targets) / len(lists) if lists else 0.0
    dead_ends = sum(1 for entries in lists.values() if not any(entries))
    return [
        "Recommendation lists (for favorite_neighbor):",
        f"  candidates with a stored list: {len(lists)} of {len(candidates)}",
        f"  mean list length: {mean_length:.1f}",
        f"  targets that are themselves candidates: {resolved_share:.0%}",
        f"  candidates whose list has no candidate at all: {dead_ends}",
        "",
    ]


def _unseen_memberships(session: Session) -> list[str]:
    latest = session.scalar(
        select(func.max(IngestionRun.id)).where(
            IngestionRun.command == "ingest", IngestionRun.status != "running"
        )
    )
    if latest is None:
        return []
    unseen = session.scalar(
        select(func.count())
        .select_from(CandidatePoolMembership)
        .where(CandidatePoolMembership.last_seen_run_id != latest)
    )
    return [f"Memberships not seen in the latest ingest run (#{latest}): {unseen}", ""]
