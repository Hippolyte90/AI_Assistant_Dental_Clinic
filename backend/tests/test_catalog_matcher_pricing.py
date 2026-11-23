"""Catalog, rules, matcher and pricing tests."""

from decimal import Decimal

import pytest

from app.config import PRICE_LIST_PATH
from app.models.schemas import (
    PlanDraft,
    PlanItemDraft,
    Procedure,
    StageDraft,
    TrackedProcedure,
    TreatmentPlan,
)
from app.services.catalog import normalize_code, parse_price_list
from app.services.matcher import parse_interval, tooth_type
from app.services.pricing import is_valid_fdi, price_plan


def by_name(catalog, name):
    return next(item for item in catalog.items if item.name == name)


def test_catalog_matches_the_source_file(catalog):
    parsed = parse_price_list(PRICE_LIST_PATH)
    assert [i.model_dump() for i in parsed] == [i.model_dump() for i in catalog.items]
    assert len(catalog.items) == 208
    assert len({item.section for item in catalog.items}) == 8
    assert len({item.id for item in catalog.items}) == 208
    assert all(item.section and item.price_eur > 0 for item in catalog.items)
    assert by_name(catalog, "Root canal treatment — molars").price_eur == Decimal("89.60")
    assert by_name(catalog, "Osstem implant placement (Korea)").section == "Implantology"
    assert by_name(catalog, "Scaling").price_eur == Decimal("162.08")


def test_duplicate_code_keeps_both_prices(catalog):
    rows = [item for item in catalog.items if item.code == "6.22"]
    assert {item.price_eur for item in rows} == {Decimal("51.37"), Decimal("50.97")}


def test_same_name_in_several_sections(catalog):
    assert {i.section for i in catalog.same_name("Local anaesthesia")} >= {
        "Endodontics",
        "Surgery",
    }
    assert len(catalog.same_name("Local anaesthesia")) == 4


def test_code_normalization():
    assert normalize_code(" 1.36. ") == "1.36"
    assert normalize_code("5.8") == "5.8"
    assert normalize_code(None) is None


def test_rules_load_and_are_flagged_unvalidated(rules, catalog):
    rules.check_references(catalog)
    assert rules.validated is False


@pytest.mark.parametrize(
    ("said", "teeth", "expected"),
    [
        ("root canal", [36], "Root canal treatment — molars"),
        ("RCT", [14], "Root canal treatment — premolars"),
        ("root canal", [11], "Root canal treatment — anterior teeth (incisors and canines)"),
        ("endodontic re-treatment", [26], "Endodontic re-treatment (molars)"),
        ("two-surface filling", [21], "Two-surface restoration of an anterior tooth"),
        ("two surface filling", [46], "Restoration of a two-surface molar"),
        ("core build-up", [36], "Core build-up of a molar for a prosthetic restoration"),
        ("extraction", [18], "Conventional tooth extraction with socket suturing and antimicrobial sponge placement"),
        ("extraction and socket preservation", [46], "Tooth extraction and socket preservation"),
        ("Straumann implant", [46], "Straumann BLT implant placement (Switzerland)"),
        ("Nobel implant", [11], "Nobel implant placement"),
        ("healing abutment", [46], "Healing abutment placement"),
        ("ST zirconia crown on Megagen implant", [46], "ST zirconia crown on Megagen implant"),
        ("scaling and root planing on the upper jaw", [], "Scaling and root planing (SRP), one jaw"),
        ("scaling and root planing", [31], "Scaling and root planing (SRP), one tooth"),
        ("fluoride varnish", [37], "Fluoride varnish application, 1 tooth"),
        ("grade 2 wisdom tooth extraction", [38], "Extraction of a wisdom tooth (Grade 2 complexity)"),
        ("dental x-ray", [], "Dental radiograph"),
    ],
)  # fmt: skip
def test_matcher_maps_common_phrases_without_llm(matcher, said, teeth, expected):
    procedure = TrackedProcedure(pid=1, said=said, teeth=teeth)
    facts = matcher.detect_facts(said)
    result = matcher.resolve(procedure, facts)
    assert not result.needs_llm
    assert result.lines[0][0].name == expected


def test_missing_brand_is_provisional_and_asks(matcher):
    result = matcher.resolve(TrackedProcedure(pid=1, said="implant", teeth=[46]), {})
    assert result.provisional
    assert result.pending[0].dimension == "brand"
    assert result.lines[0][0].name == "Osstem implant placement (Korea)"


def test_compound_is_split(matcher):
    procedure = Procedure(said="implant at 46 with a healing abutment", teeth=[46])
    assert len(matcher.split_compound(procedure)) == 2
    two_teeth = Procedure(said="two-surface filling on 11 and a filling on 21", teeth=[11, 21])
    parts = matcher.split_compound(two_teeth)
    assert [part.teeth for part in parts] == [[11], [21]]
    assert len(matcher.split_compound(Procedure(said="scaling and root planing"))) == 1


def test_mixed_tooth_types_are_split(matcher):
    parts = matcher.split_by_tooth_type(Procedure(said="root canal", teeth=[11, 36, 46]))
    assert sorted(part.teeth for part in parts) == [[11], [36, 46]]


def test_ground_cleans_a_weak_extraction(matcher):
    text = (
        "Generalised periodontitis. Start with a periodontal consultation and initial charting. "
        "Then scaling and root planing on both jaws. "
        "Periodontal follow-up examination with charting three to six months after treatment."
    )
    raw = [
        Procedure(said="generalised periodontitis"),
        Procedure(said="periodontal consultation"),
        Procedure(said="initial charting"),
        Procedure(said="scaling and root planing", interval_hint="three to six months"),
        Procedure(said="periodontal follow-up examination"),
        Procedure(said="charting", interval_hint="three to six months"),
    ]
    clean = matcher.ground(raw, text)
    assert [p.said for p in clean] == [
        "periodontal consultation",
        "scaling and root planing on both jaws",
        "periodontal follow-up examination",
    ]
    assert clean[1].interval_hint is None
    assert clean[2].interval_hint == "three to six months"


def test_unknown_service_is_unmapped(matcher):
    result = matcher.resolve(TrackedProcedure(pid=1, said="xylophone therapy"), {})
    assert result.unmapped and not result.lines


@pytest.mark.parametrize(
    ("text", "days"),
    [
        ("two weeks", (14, 14)),
        ("3 to 6 months", (90, 180)),
        ("three to six months after treatment", (90, 180)),
        ("3–6 months", (90, 180)),
        ("one week later", (7, 7)),
        ("no delay", None),
    ],
)
def test_parse_interval(text, days):
    assert parse_interval(text) == days


def test_fdi_and_tooth_type():
    assert is_valid_fdi(11) and is_valid_fdi(48) and is_valid_fdi(85)
    assert not is_valid_fdi(19) and not is_valid_fdi(56) and not is_valid_fdi(99)
    assert tooth_type(13) == "anterior" and tooth_type(25) == "premolar"
    assert tooth_type(36) == "molar" and tooth_type(75) == "molar"


def test_totals_are_exact(catalog):
    molar = by_name(catalog, "Root canal treatment — molars")
    scaling = by_name(catalog, "Scaling")
    draft = PlanDraft(
        stages=[
            StageDraft(number=1, title="A", goal="g", items=[PlanItemDraft(catalog_id=molar.id, quantity=3, teeth=[36, 46, 26])]),
            StageDraft(number=2, title="B", goal="g", items=[PlanItemDraft(catalog_id=scaling.id)]),
        ]
    )  # fmt: skip
    plan: TreatmentPlan = price_plan(draft, catalog, "s", 1)
    assert plan.stages[0].subtotal == Decimal("268.80")
    assert plan.total_eur == Decimal("430.88")


def test_unknown_id_becomes_a_question_not_a_price(catalog):
    draft = PlanDraft(
        stages=[
            StageDraft(
                number=1,
                title="A",
                goal="g",
                items=[PlanItemDraft(catalog_id="nope-1")],
            )
        ]
    )
    plan = price_plan(draft, catalog, "s", 1)
    assert plan.total_eur == Decimal("0.00")
    assert plan.stages == []
    assert plan.questions[0].kind == "unknown_service"


def test_invalid_tooth_becomes_a_question(catalog):
    molar = by_name(catalog, "Root canal treatment — molars")
    draft = PlanDraft(
        stages=[
            StageDraft(
                number=1,
                title="A",
                goal="g",
                items=[PlanItemDraft(catalog_id=molar.id, teeth=[99])],
            )
        ]
    )
    plan = price_plan(draft, catalog, "s", 1)
    assert plan.stages[0].items[0].teeth == []
    assert plan.questions[0].kind == "missing_param"


def test_ground_recovers_a_dictated_procedure_the_model_missed(matcher):
    text = "Root canal on 36. Fluoride varnish on 37 two weeks later."
    clean = matcher.ground([Procedure(said="root canal", teeth=[36])], text)
    assert [p.teeth for p in clean] == [[36], [37]]
    assert "fluoride" in clean[1].said


def test_ground_never_adds_a_negated_or_past_treatment(matcher):
    text = "Root canal on 36. No implant for now. She already had an extraction on 46."
    clean = matcher.ground([Procedure(said="root canal", teeth=[36])], text)
    assert [p.said for p in clean] == ["root canal"]


def test_ground_does_not_duplicate_a_compound_entry(matcher):
    text = "Place an implant at 46 with a healing abutment."
    raw = [Procedure(said="implant with a healing abutment", teeth=[46])]
    assert len(matcher.ground(raw, text)) == 1
