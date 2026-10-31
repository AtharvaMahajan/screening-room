"""Catalog endpoints. Readable by any signed-in user (security.md §6)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from screening_room.config import SettingsDep
from screening_room.db import SessionDep
from screening_room.modules.catalog import read_through
from screening_room.modules.catalog.dependencies import CatalogProviderDep
from screening_room.modules.catalog.schemas import TitleDetailOut
from screening_room.modules.identity.dependencies import get_current_user

router = APIRouter(prefix="/api/titles", dependencies=[Depends(get_current_user)])

# Our ids are PostgreSQL bigints; anything outside that range can't exist.
TitleId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.get("/{title_id}")
def get_title(
    title_id: TitleId,
    session: SessionDep,
    provider: CatalogProviderDep,
    settings: SettingsDep,
) -> TitleDetailOut:
    # Read-only for fresh titles; the helper owns any refresh transactions.
    return read_through.get_title_detail(session, title_id, provider, settings)
