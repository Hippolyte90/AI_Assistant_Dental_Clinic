"""Loads the YAML clinic rules, synonyms and procedure families."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import RULES_DIR
from app.services.catalog import Catalog


@dataclass(frozen=True)
class Rules:
    """All editable clinic knowledge."""

    clinic: dict
    synonyms: dict[str, str]
    dimensions: dict[str, dict]
    families: list[dict]
    protected_phrases: list[str]
    section_categories: dict[str, str]
    diagnosis_terms: list[str]

    @property
    def validated(self) -> bool:
        """True once a dentist has reviewed the default intervals."""
        return bool(str(self.clinic.get("validated_by") or "").strip())

    @property
    def stage_keys(self) -> list[str]:
        """Stage keys in build order."""
        return [stage["key"] for stage in self.clinic["stages"]]

    def check_references(self, catalog: Catalog) -> None:
        """Fail early if a rule names an item that is not in the price list."""
        for family in self.families:
            for option in family.get("options", []):
                catalog.ref(option["item"])
        for rule in self.clinic.get("auto_add", []):
            catalog.ref(rule["item"])


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_rules(directory: Path = RULES_DIR) -> Rules:
    """Read every rules file."""
    families = _read(directory / "families.yaml")
    return Rules(
        clinic=_read(directory / "clinic_rules.yaml"),
        synonyms=_read(directory / "synonyms.yaml")["synonyms"],
        dimensions=families["dimensions"],
        families=families["families"],
        protected_phrases=families["protected_phrases"],
        section_categories=families["section_categories"],
        diagnosis_terms=families["diagnosis_terms"],
    )
