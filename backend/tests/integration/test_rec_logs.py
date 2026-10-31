"""Recommendation logs: constraints and deletion rules (data-model.md §3.4, §6)."""

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from screening_room.modules.catalog.models import Title
from screening_room.modules.discovery.models import RecRequest, RecResult
from screening_room.modules.identity.models import User
from tests.integration.helpers import add_candidate


def make_user(db_session: Session, email: str = "logs@example.com") -> int:
    user = User(email=email, password_hash="not-a-real-hash")
    db_session.add(user)
    db_session.flush()
    return user.id


def make_request(db_session: Session, user_id: int) -> int:
    request = RecRequest(
        user_id=user_id,
        context={"media_type": "any", "genre_ids": [], "excluded": 0},
        engine_version="1.0.0",
        config_hash="abc123",
        pool_size=10,
        candidate_count=10,
        eligible_count=8,
        anchor_count=1,
        anchors_without_neighbors=0,
        cold_start=False,
        diversity_relaxed=False,
        latency_ms=12,
    )
    db_session.add(request)
    db_session.flush()
    return request.id


def result(request_id: int, title_id: int, rank: int) -> RecResult:
    return RecResult(
        request_id=request_id,
        title_id=title_id,
        rank=rank,
        score=0.5,
        score_breakdown={"affinity": {"value": 1.0, "weighted": 0.45}},
        reasons=[{"type": "genre_affinity", "text": "Matches genres you like: Drama"}],
    )


def test_a_request_and_its_results_round_trip(db_session: Session) -> None:
    request_id = make_request(db_session, make_user(db_session))
    title_id = add_candidate(db_session, "Logged")
    db_session.add(result(request_id, title_id, 1))
    db_session.flush()

    stored = db_session.scalars(select(RecResult).where(RecResult.request_id == request_id)).one()

    assert stored.reasons[0]["text"] == "Matches genres you like: Drama"
    assert stored.score_breakdown["affinity"]["weighted"] == 0.45


@pytest.mark.parametrize(
    ("second", "constraint"),
    [
        ((2, 1), "uq_rec_results_request_id_rank"),  # another title, same rank
        ((1, 2), "uq_rec_results_request_id_title_id"),  # same title, another rank
    ],
)
def test_one_title_per_rank_and_no_repeats(
    db_session: Session, second: tuple[int, int], constraint: str
) -> None:
    request_id = make_request(db_session, make_user(db_session))
    titles = [add_candidate(db_session, f"Dup {n}") for n in (1, 2)]
    db_session.add(result(request_id, titles[0], 1))
    db_session.flush()
    title_index, rank = second

    db_session.add(result(request_id, titles[title_index - 1], rank))
    with pytest.raises(IntegrityError, match=constraint):
        db_session.flush()


def test_rank_starts_at_one(db_session: Session) -> None:
    request_id = make_request(db_session, make_user(db_session))
    db_session.add(result(request_id, add_candidate(db_session, "Rank zero"), 0))

    with pytest.raises(IntegrityError, match="ck_rec_results_rank_positive"):
        db_session.flush()


def test_deleting_a_user_deletes_their_logs(db_session: Session) -> None:
    user_id = make_user(db_session)
    request_id = make_request(db_session, user_id)
    db_session.add(result(request_id, add_candidate(db_session, "Gone with user"), 1))
    db_session.flush()

    db_session.execute(delete(User).where(User.id == user_id))

    for model, column in [(RecRequest, RecRequest.id), (RecResult, RecResult.request_id)]:
        count = db_session.scalar(
            select(func.count()).select_from(model).where(column == request_id)
        )
        assert count == 0, model.__tablename__


def test_a_recommended_title_cannot_be_deleted(db_session: Session) -> None:
    request_id = make_request(db_session, make_user(db_session))
    title_id = add_candidate(db_session, "Referenced")
    db_session.add(result(request_id, title_id, 1))
    db_session.flush()

    with pytest.raises(IntegrityError, match="fk_rec_results_title_id_titles"):
        db_session.execute(delete(Title).where(Title.id == title_id))
