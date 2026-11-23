"""Catalog routes."""

from fastapi import APIRouter, Query, Request
from rapidfuzz import fuzz

from app.models.schemas import CatalogItem

router = APIRouter(prefix="/api/catalog")


@router.get("")
def list_catalog(request: Request) -> dict[str, list[CatalogItem]]:
    """All services grouped by section."""
    grouped: dict[str, list[CatalogItem]] = {}
    for item in request.app.state.workflow.catalog.items:
        grouped.setdefault(item.section, []).append(item)
    return grouped


@router.get("/search")
def search_catalog(request: Request, q: str = Query(min_length=2)) -> list[CatalogItem]:
    """Case-insensitive fuzzy search."""
    query = q.lower()
    scored = [
        (fuzz.partial_ratio(query, item.name.lower()), item)
        for item in request.app.state.workflow.catalog.items
    ]
    hits = [pair for pair in scored if pair[0] >= 85]
    hits.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in hits[:30]]
