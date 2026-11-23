"""Deterministic mapping from dictated procedures to catalog items.

Known procedure families are resolved by rules. Anything else gets a fuzzy top-5 shortlist,
so the local LLM never has to choose among all the services.
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.models.schemas import CatalogItem, Procedure, TrackedProcedure
from app.services.catalog import Catalog
from app.services.rules import Rules

AUTO_SCORE = 85.0
AUTO_MARGIN = 8.0
MIN_SCORE = 55.0
TOOTH_RE = re.compile(r"(?<![\d.])([1-4][1-8]|[5-8][1-5])(?![\d.])")
SPLIT_RE = re.compile(r"\b(?:and|with|under|then|plus|also)\b|[,;]")
NEGATION_RE = re.compile(
    r"\b(?:no|not|don't|do not|without|avoid|instead|cancel|never|had|already|previous|"
    r"previously|history|last year)\b"
)
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
}  # fmt: skip
UNIT_DAYS = {"day": 1, "week": 7, "month": 30}
CATEGORY_PREFIX = {
    "endodontic": "endo", "restorative": "rest", "periodontal": "perio",
    "surgery": "surg", "implant": "impl", "prosthetic": "impl",
}  # fmt: skip
SEDATION_HOURS = {"1": "1 hour", "2": "2 hours", "3": "3 hours", "4": "4 hours"}


@dataclass
class PendingChoice:
    """A choice that needs the dentist: a dimension value or a catalog item."""

    dimension: str
    values: list[str]
    current: str


@dataclass
class Resolution:
    """How one procedure maps to catalog lines."""

    family: str | None = None
    category: str = "restorative"
    lines: list[tuple[CatalogItem, int]] = field(default_factory=list)
    provisional: bool = False
    pending: list[PendingChoice] = field(default_factory=list)
    candidates: list[CatalogItem] = field(default_factory=list)
    needs_llm: bool = False
    unmapped: bool = False


def normalize(text: str) -> str:
    """Lower-case and unify dashes and spaces."""
    text = text.lower().replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip()


def has_word(text: str, keyword: str) -> bool:
    """True if the keyword starts at a word boundary (so plurals match)."""
    return re.search(r"(?<!\w)" + re.escape(keyword), text) is not None


def tooth_type(tooth: int) -> str:
    """Classify an FDI tooth number."""
    quadrant, position = tooth // 10, tooth % 10
    if position <= 3:
        return "anterior"
    if quadrant >= 5:
        return "molar"
    return "premolar" if position <= 5 else "molar"


def teeth_in(text: str) -> list[int]:
    """Find FDI tooth numbers in free text."""
    return [int(number) for number in TOOTH_RE.findall(text)]


def _number(token: str) -> int | None:
    return int(token) if token.isdigit() else NUMBER_WORDS.get(token)


def parse_interval(text: str | None) -> tuple[int, int] | None:
    """Read a dictated delay such as 'two weeks' or '3-6 months' as days."""
    if not text:
        return None
    text = normalize(text)
    span = re.search(r"(\w+)\s*(?:to|-)\s*(\w+)\s*(day|week|month)", text)
    if span:
        low, high = _number(span[1]), _number(span[2])
        if low is not None and high is not None:
            return low * UNIT_DAYS[span[3]], high * UNIT_DAYS[span[3]]
    single = re.search(r"(\w+)[\s-]*(day|week|month)", text)
    if single:
        value = _number(single[1])
        if value is not None:
            days = value * UNIT_DAYS[single[2]]
            return days, days
    return None


class Matcher:
    """Resolves procedures against the catalog using the clinic rules."""

    def __init__(self, catalog: Catalog, rules: Rules) -> None:
        self.catalog = catalog
        self.rules = rules

    def family_for(self, text: str) -> dict | None:
        """Return the first family whose triggers match the text."""
        text = normalize(text)
        for family in self.rules.families:
            if any(has_word(text, word) for word in family.get("exclude", [])):
                continue
            if any(has_word(text, word) for word in family["triggers"]):
                return family
        return None

    def detect_facts(self, text: str) -> dict[str, str]:
        """Find values of plan-wide dimensions (e.g. implant brand) in free text."""
        text = normalize(text)
        facts: dict[str, str] = {}
        for name, dimension in self.rules.dimensions.items():
            if dimension["scope"] != "global":
                continue
            found = [
                value
                for value, spec in dimension["values"].items()
                if any(has_word(text, word) for word in spec["keywords"])
            ]
            if len(found) == 1:
                facts[name] = found[0]
        return facts

    def detect_value(self, dimension: str, text: str) -> str | None:
        """Find a value of one dimension in free text."""
        text = normalize(text)
        if dimension == "sedation_hours":
            match = re.search(r"(\w+)\s*(?:hour|hr)", text)
            value = _number(match[1]) if match else None
            return str(value) if value else None
        spec = self.rules.dimensions.get(dimension)
        if not spec:
            return None
        for value, details in spec["values"].items():
            if any(has_word(text, word) for word in details["keywords"]):
                return value
        return None

    def ground(self, procedures: list[Procedure], transcript: str) -> list[Procedure]:
        """Check the model's extraction against the dictated sentences.

        Drops diagnoses, merges fragments of one procedure, removes delays that are not in the
        procedure's own sentence, and restores details such as the jaw.
        """
        parts = re.split(r"(?<=[.!?])\s+|\n", transcript)
        sentences = [normalize(part) for part in parts if part.strip()]
        result: list[Procedure] = []
        for original in procedures:
            procedure = original.model_copy(deep=True)
            text = normalize(procedure.said)
            family = self.family_for(text)
            if not family and any(has_word(text, term) for term in self.rules.diagnosis_terms):
                continue
            own_sentences = [s for s in sentences if text in s]
            hint = normalize(procedure.interval_hint or "")
            if own_sentences and hint and not any(hint in s for s in own_sentences):
                procedure.interval_hint = None
            if own_sentences and family:
                for word in family.get("context_words", []):
                    if word in own_sentences[0] and word not in text:
                        procedure.said = f"{procedure.said} on {word}"
                        break
            if result:
                previous = result[-1]
                previous_family = self.family_for(previous.said)
                same_teeth = previous.teeth == procedure.teeth
                if previous_family and same_teeth:
                    absorbed = text in previous_family.get("absorbs", [])
                    duplicate = (
                        family is not None
                        and family["id"] == previous_family["id"]
                        and not family.get("dimensions")
                    )
                    if absorbed or duplicate:
                        previous.interval_hint = previous.interval_hint or procedure.interval_hint
                        continue
            result.append(procedure)
        return self._recover_missed(result, sentences)

    def _recover_missed(self, procedures: list[Procedure], sentences: list[str]) -> list[Procedure]:
        """Add known procedures that were clearly dictated but missed by the model."""

        def position(procedure: Procedure) -> int:
            text = normalize(procedure.said)
            return next((i for i, s in enumerate(sentences) if text in s), len(sentences))

        result = list(procedures)
        for index, sentence in enumerate(sentences):
            if NEGATION_RE.search(sentence):
                continue
            for clause in self._clauses(sentence):
                family = self.family_for(clause)
                if family is None:
                    continue
                teeth = teeth_in(clause) or teeth_in(sentence)
                if any(self._covers(known, family["id"], teeth) for known in result):
                    continue
                insert_at = next(
                    (i for i, known in enumerate(result) if position(known) > index), len(result)
                )
                result.insert(insert_at, Procedure(said=clause, teeth=teeth))
        return result

    def _covers(self, procedure: Procedure, family_id: str, teeth: list[int]) -> bool:
        for part in self.split_compound(procedure):
            family = self.family_for(part.said)
            if family is None or family["id"] != family_id:
                continue
            if not teeth or not part.teeth or set(teeth) & set(part.teeth):
                return True
        return False

    def _clauses(self, text: str) -> list[str]:
        """Split text into clauses, keeping words without a family with the previous clause."""
        text = normalize(text).rstrip(".!?")
        for phrase in self.rules.protected_phrases:
            text = text.replace(phrase, phrase.replace(" ", "_"))
        parts = [part.strip().replace("_", " ") for part in SPLIT_RE.split(text) if part.strip()]
        merged: list[str] = []
        for part in parts:
            if self.family_for(part) or not merged:
                merged.append(part)
            else:
                merged[-1] += f" {part}"
        return merged

    def split_compound(self, procedure: Procedure) -> list[Procedure]:
        """Split 'implant with a healing abutment' style phrases into single procedures."""
        merged = self._clauses(procedure.said)
        with_family = [part for part in merged if self.family_for(part)]
        families = {self.family_for(part)["id"] for part in with_family}
        own_teeth = all(teeth_in(part) for part in with_family)
        if len(with_family) < 2 or (len(families) < 2 and not own_teeth):
            return [procedure]
        result = []
        for part in merged:
            result.append(
                procedure.model_copy(
                    update={
                        "said": part,
                        "teeth": teeth_in(part) or list(procedure.teeth),
                        "quantity": 1,
                        "interval_hint": procedure.interval_hint if not result else None,
                    }
                )
            )
        return result

    def split_by_tooth_type(self, procedure: Procedure) -> list[Procedure]:
        """A family priced by tooth type needs one line per type."""
        family = self.family_for(procedure.said)
        if not family or "tooth_type" not in family.get("dimensions", []):
            return [procedure]
        groups: dict[str, list[int]] = {}
        for tooth in procedure.teeth:
            groups.setdefault(tooth_type(tooth), []).append(tooth)
        if len(groups) < 2:
            return [procedure]
        return [procedure.model_copy(update={"teeth": teeth}) for teeth in groups.values()]

    def shortlist(self, procedure: Procedure, limit: int = 5) -> list[tuple[CatalogItem, float]]:
        """Fuzzy top candidates for a procedure, using synonyms and the tooth type."""
        query = normalize(procedure.said)
        for word, replacement in self.rules.synonyms.items():
            query = re.sub(r"(?<!\w)" + re.escape(word) + r"(?!\w)", replacement, query)
        query = TOOTH_RE.sub(" ", query)
        kinds = {tooth_type(tooth) for tooth in procedure.teeth}
        scored = []
        for item in self.catalog.items:
            name = normalize(item.name)
            score = (fuzz.token_set_ratio(query, name) + fuzz.token_sort_ratio(query, name)) / 2
            if kinds and "molar" in name and "premolar" not in name and "molar" not in kinds:
                score -= 15
            if kinds and "anterior" in name and "anterior" not in kinds:
                score -= 15
            scored.append((item, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:limit]

    def _quantity(self, procedure: Procedure, mode: str | None) -> int:
        if mode == "per_tooth":
            return max(len(procedure.teeth), 1)
        if mode == "jaws":
            text = normalize(procedure.said)
            both = any(has_word(text, word) for word in ("both", "full mouth"))
            return 2 if both or (has_word(text, "upper") and has_word(text, "lower")) else 1
        return max(procedure.quantity, 1)

    def resolve(
        self,
        procedure: TrackedProcedure,
        facts: dict[str, str],
        context: str | None = None,
    ) -> Resolution:
        """Map one procedure to priced-catalog lines, recording what is still open."""
        family = self.family_for(procedure.said)
        if procedure.catalog_id:
            return self._explicit(procedure, family)
        if family and family.get("special") == "sedation":
            return self._sedation(procedure)
        if family and family.get("contextual"):
            return self._contextual(procedure, family, context)
        if family and family.get("options"):
            return self._from_family(procedure, family, facts)
        return self._fuzzy(procedure, family)

    def _explicit(self, procedure: TrackedProcedure, family: dict | None) -> Resolution:
        item = self.catalog.get(procedure.catalog_id or "")
        if item is None:
            return Resolution(unmapped=True)
        mode = None
        if family:
            mode = family.get("quantity")
            for option in family.get("options", []):
                if self.catalog.ref(option["item"]).id == item.id:
                    mode = option.get("quantity", mode)
        return Resolution(
            family=family["id"] if family else None,
            category=family["category"] if family else self._category(item),
            lines=[(item, self._quantity(procedure, mode))],
        )

    def _category(self, item: CatalogItem) -> str:
        return self.rules.section_categories[item.id.split("-")[0]]

    def _sedation(self, procedure: TrackedProcedure) -> Resolution:
        result = Resolution(family="sedation", category="adjunct")
        hours = procedure.facts.get("sedation_hours") or self.detect_value(
            "sedation_hours", procedure.said
        )
        if hours is None:
            hours = "1"
            result.provisional = True
            result.pending.append(PendingChoice("sedation_hours", list(SEDATION_HOURS), "1"))
        result.lines.append((self.catalog.ref("sed|Sedation – first hour"), 1))
        if int(hours) > 1:
            extra = self.catalog.ref("sed|Sedation – each additional hour")
            result.lines.append((extra, int(hours) - 1))
        return result

    def _contextual(
        self, procedure: TrackedProcedure, family: dict, context: str | None
    ) -> Resolution:
        items = self.catalog.same_name(family["contextual"])
        prefix = CATEGORY_PREFIX.get(context or "")
        chosen = next((i for i in items if i.id.startswith(f"{prefix}-")), items[0])
        return Resolution(
            family=family["id"],
            category="adjunct",
            lines=[(chosen, self._quantity(procedure, None))],
        )

    def _from_family(
        self, procedure: TrackedProcedure, family: dict, facts: dict[str, str]
    ) -> Resolution:
        text = normalize(procedure.said)
        options = family["options"]
        required = [
            option
            for option in options
            if any(has_word(text, word) for word in option.get("requires", []))
        ]
        options = required or [option for option in options if not option.get("requires")]
        result = Resolution(family=family["id"], category=family["category"])
        for dimension in family.get("dimensions", []):
            if dimension == "tooth_type":
                if procedure.teeth:
                    kind = tooth_type(procedure.teeth[0])
                    options = [o for o in options if o.get("tooth_type") == kind] or options
                continue
            available = list(dict.fromkeys(o[dimension] for o in options if dimension in o))
            value = procedure.facts.get(dimension) or facts.get(dimension)
            value = value or self.detect_value(dimension, text)
            if dimension == "srp_scope" and value is None and procedure.teeth:
                value = "tooth"
            if value in available:
                options = [o for o in options if o.get(dimension) == value]
            elif len(available) > 1:
                default = self.rules.dimensions[dimension]["default"]
                current = default if default in available else available[0]
                result.pending.append(PendingChoice(dimension, available, current))
                result.provisional = True
                options = [o for o in options if o.get(dimension) == current]
        if len(options) > 1 and not result.pending:
            ids = [self.catalog.ref(option["item"]).id for option in options]
            result.pending.append(PendingChoice("item", ids, ids[0]))
            result.provisional = True
        chosen = options[0]
        mode = chosen.get("quantity", family.get("quantity"))
        result.lines = [(self.catalog.ref(chosen["item"]), self._quantity(procedure, mode))]
        return result

    def _fuzzy(self, procedure: TrackedProcedure, family: dict | None) -> Resolution:
        ranked = self.shortlist(procedure)
        best_item, best = ranked[0]
        second = ranked[1][1]
        category = family["category"] if family else self._category(best_item)
        result = Resolution(family=family["id"] if family else None, category=category)
        result.candidates = [item for item, score in ranked if score >= MIN_SCORE]
        quantity = self._quantity(procedure, None)
        if best < MIN_SCORE:
            result.unmapped = True
            result.candidates = [item for item, _ in ranked]
        elif best >= AUTO_SCORE and best - second >= AUTO_MARGIN:
            result.lines = [(best_item, quantity)]
        else:
            suggested = self.catalog.get(procedure.suggested_id or "")
            if suggested is None:
                result.needs_llm = True
            chosen = suggested or best_item
            if not family:
                result.category = self._category(chosen)
            ids = [item.id for item in result.candidates]
            if chosen.id not in ids:
                ids.insert(0, chosen.id)
            result.lines = [(chosen, quantity)]
            result.provisional = True
            result.pending.append(PendingChoice("item", ids, chosen.id))
        return result
