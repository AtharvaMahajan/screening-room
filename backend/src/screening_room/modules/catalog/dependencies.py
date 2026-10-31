"""Request dependencies for the catalog module."""

from typing import Annotated

from fastapi import Depends, Request

from screening_room.modules.catalog.providers.base import CatalogProvider


def get_catalog_provider(request: Request) -> CatalogProvider | None:
    """The app's metadata provider, or None when no TMDB token is configured
    (pages then show the data we already have). Tests override this."""
    provider: CatalogProvider | None = request.app.state.catalog_provider
    return provider


CatalogProviderDep = Annotated[CatalogProvider | None, Depends(get_catalog_provider)]
