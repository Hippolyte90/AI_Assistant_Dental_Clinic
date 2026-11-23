"""Clinic price list: xlsx parsing and the in-memory catalog."""

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from openpyxl import load_workbook

from app.config import CATALOG_PATH
from app.models.schemas import CatalogItem

SECTION_PREFIXES = {
    "Restorative dentistry (treatment)": "rest",
    "Periodontics": "perio",
    "Endodontics": "endo",
    "Surgery": "surg",
    "Surgery (Dr. R.A.)": "surgra",
    "Implantology": "impl",
    "Implant prosthetics": "pros",
    "Sedation with anaesthesiologist – adults": "sed",
}


def normalize_code(raw: object) -> str | None:
    """Strip whitespace and the trailing dot; keep duplicates as they are."""
    if raw is None:
        return None
    code = str(raw).strip().rstrip(".")
    return code or None


def parse_price_list(path: Path) -> list[CatalogItem]:
    """Read the xlsx; rows with a name but no price are section headers."""
    sheet = load_workbook(path, read_only=True, data_only=True)["Price list (EUR)"]
    items: list[CatalogItem] = []
    section: str | None = None
    counters: dict[str, int] = {}
    for row in sheet.iter_rows(min_row=2, max_col=3, values_only=True):
        name, code, price = row
        if name is None:
            continue
        name = str(name).strip()
        if price is None:
            if name not in SECTION_PREFIXES:
                raise ValueError(f"Unknown section header: {name!r}")
            section = name
            continue
        if section is None:
            raise ValueError(f"Service before any section: {name!r}")
        prefix = SECTION_PREFIXES[section]
        counters[prefix] = counters.get(prefix, 0) + 1
        items.append(
            CatalogItem(
                id=f"{prefix}-{counters[prefix]:03d}",
                code=normalize_code(code),
                section=section,
                name=name,
                price_eur=Decimal(str(price)).quantize(Decimal("0.01"), ROUND_HALF_UP),
            )
        )
    return items


class Catalog:
    """Lookup over the price list. Items are keyed by internal id, never by code."""

    def __init__(self, items: list[CatalogItem]) -> None:
        self.items = items
        self.by_id = {item.id: item for item in items}
        self._by_ref = {(item.id.split("-")[0], item.name): item for item in items}

    def get(self, catalog_id: str) -> CatalogItem | None:
        """Return an item by internal id."""
        return self.by_id.get(catalog_id)

    def ref(self, reference: str) -> CatalogItem:
        """Resolve a rules reference such as ``endo|Rubber dam placement``."""
        prefix, name = reference.split("|", 1)
        try:
            return self._by_ref[(prefix, name)]
        except KeyError as exc:
            raise KeyError(f"Unknown catalog reference: {reference}") from exc

    def same_name(self, name: str) -> list[CatalogItem]:
        """Return every section's item with this exact name."""
        return [item for item in self.items if item.name == name]


def save_catalog(items: list[CatalogItem], path: Path = CATALOG_PATH) -> None:
    """Write the generated catalog as reviewable JSON."""
    data = [item.model_dump(mode="json") for item in items]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    """Load the generated catalog."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return Catalog([CatalogItem.model_validate(row) for row in data])
