"""Validation and pricing. This is the only place where money is computed."""

from decimal import ROUND_HALF_UP, Decimal

from app.models.schemas import (
    ClarifyingQuestion,
    PlanDraft,
    PlanItem,
    Stage,
    TreatmentPlan,
)
from app.services.catalog import Catalog

CENTS = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """Round half-up to two decimals."""
    return value.quantize(CENTS, ROUND_HALF_UP)


def is_valid_fdi(tooth: int) -> bool:
    """True for a permanent (11-48) or primary (51-85) FDI tooth number."""
    quadrant, position = tooth // 10, tooth % 10
    if 1 <= quadrant <= 4:
        return 1 <= position <= 8
    if 5 <= quadrant <= 8:
        return 1 <= position <= 5
    return False


def price_plan(draft: PlanDraft, catalog: Catalog, session_id: str, version: int) -> TreatmentPlan:
    """Turn a draft into a priced plan; invalid lines become questions, never prices."""
    questions = list(draft.questions)
    stages: list[Stage] = []
    for stage in draft.stages:
        items: list[PlanItem] = []
        for line in stage.items:
            item = catalog.get(line.catalog_id)
            if item is None:
                questions.append(
                    ClarifyingQuestion(
                        id=f"unknown:{line.catalog_id}",
                        text=f"A planned service ({line.catalog_id}) is not in the price list. "
                        "What should be done instead?",
                        kind="unknown_service",
                        related_stage=stage.number,
                    )
                )
                continue
            bad_teeth = [tooth for tooth in line.teeth if not is_valid_fdi(tooth)]
            if bad_teeth:
                questions.append(
                    ClarifyingQuestion(
                        id=f"teeth:{item.id}:{bad_teeth[0]}",
                        text=f"Tooth number {bad_teeth[0]} for '{item.name}' is not a valid "
                        "FDI number. Which tooth is it?",
                        kind="missing_param",
                        related_stage=stage.number,
                    )
                )
            quantity = max(line.quantity, 1)
            unit_price = money(item.price_eur)
            data = line.model_dump()
            data.update(
                quantity=quantity,
                teeth=[tooth for tooth in line.teeth if is_valid_fdi(tooth)],
                code=item.code,
                section=item.section,
                name=item.name,
                unit_price=unit_price,
                line_total=money(unit_price * quantity),
            )
            items.append(PlanItem(**data))
        if items:
            stages.append(
                Stage(
                    number=len(stages) + 1,
                    title=stage.title,
                    goal=stage.goal,
                    items=items,
                    subtotal=money(sum((i.line_total for i in items), Decimal(0))),
                    interval_after=stage.interval_after,
                )
            )
    if stages:
        stages[-1].interval_after = None
    low = sum(s.interval_after.min_days for s in stages if s.interval_after)
    high = sum(s.interval_after.max_days for s in stages if s.interval_after)
    return TreatmentPlan(
        session_id=session_id,
        version=version,
        stages=stages,
        total_eur=money(sum((s.subtotal for s in stages), Decimal(0))),
        estimated_duration_days=(low, high),
        questions=questions,
        assumptions=list(draft.assumptions),
        unmapped_mentions=list(draft.unmapped_mentions),
    )
