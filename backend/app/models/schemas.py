"""Pydantic domain models shared by the API, the LLM layer and storage."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    """One priced row of the clinic price list."""

    id: str
    code: str | None = None
    section: str
    name: str
    price_eur: Decimal


class Procedure(BaseModel):
    """A procedure as dictated (Step A output), before catalog mapping."""

    said: str
    teeth: list[int] = Field(default_factory=list)
    quantity: int = 1
    stage_hint: str | None = None
    interval_hint: str | None = None


class Extraction(BaseModel):
    """Step A LLM output."""

    procedures: list[Procedure]


class MapChoice(BaseModel):
    """Step B choice for one procedure; null means ambiguous."""

    index: int
    catalog_id: str | None = None


class MapResult(BaseModel):
    """Step B LLM output."""

    choices: list[MapChoice]


class ReviseOp(BaseModel):
    """One edit requested by a free-text correction."""

    op: Literal["add", "remove", "change"]
    index: int | None = None
    said: str | None = None
    teeth: list[int] | None = None
    quantity: int | None = None


class ReviseResult(BaseModel):
    """Revision LLM output."""

    ops: list[ReviseOp]


class TrackedProcedure(Procedure):
    """A procedure plus the decisions taken on it during the session."""

    pid: int
    facts: dict[str, str] = Field(default_factory=dict)
    catalog_id: str | None = None
    suggested_id: str | None = None
    excluded: bool = False


class Interval(BaseModel):
    """Waiting time before the next stage."""

    min_days: int
    max_days: int
    reason: str
    assumed: bool = True


class PlanState(BaseModel):
    """Editable source of a plan; every version is rebuilt from it by code."""

    procedures: list[TrackedProcedure] = Field(default_factory=list)
    facts: dict[str, str] = Field(default_factory=dict)
    interval_overrides: dict[str, Interval] = Field(default_factory=dict)
    next_pid: int = 1


class QuestionOption(BaseModel):
    """A possible answer to a clarifying question."""

    id: str
    label: str
    catalog_ids: list[str] = Field(default_factory=list)
    price_delta_eur: Decimal | None = None


class ClarifyingQuestion(BaseModel):
    """A question for the dentist."""

    id: str
    text: str
    kind: Literal["choice", "missing_param", "add_on", "unknown_service", "interval"]
    topic: str = ""
    options: list[QuestionOption] = Field(default_factory=list)
    allow_free_text: bool = True
    related_stage: int | None = None
    blocking: bool = True


class Answer(BaseModel):
    """The dentist's answer to one question."""

    question_id: str
    option_id: str | None = None
    free_text: str | None = None


class PlanItemDraft(BaseModel):
    """A plan line without price."""

    catalog_id: str
    quantity: int = 1
    teeth: list[int] = Field(default_factory=list)
    note: str | None = None
    provisional: bool = False
    auto_added: bool = False


class StageDraft(BaseModel):
    """A stage without prices."""

    number: int
    title: str
    goal: str
    items: list[PlanItemDraft]
    interval_after: Interval | None = None


class PlanDraft(BaseModel):
    """A complete plan before pricing."""

    stages: list[StageDraft] = Field(default_factory=list)
    questions: list[ClarifyingQuestion] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unmapped_mentions: list[str] = Field(default_factory=list)


class PlanItem(PlanItemDraft):
    """A priced plan line."""

    code: str | None = None
    section: str
    name: str
    unit_price: Decimal
    line_total: Decimal


class Stage(BaseModel):
    """A priced stage."""

    number: int
    title: str
    goal: str
    items: list[PlanItem]
    subtotal: Decimal
    interval_after: Interval | None = None


class TreatmentPlan(BaseModel):
    """A priced, versioned treatment plan."""

    session_id: str
    version: int
    status: Literal["DRAFT", "FINAL"] = "DRAFT"
    stages: list[Stage] = Field(default_factory=list)
    total_eur: Decimal = Decimal("0.00")
    estimated_duration_days: tuple[int, int] = (0, 0)
    questions: list[ClarifyingQuestion] = Field(default_factory=list)
    answers: list[Answer] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unmapped_mentions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    pdf_path: str = ""


class Transcript(BaseModel):
    """Speech-to-text result."""

    text: str
    segments: list[dict] = Field(default_factory=list)


class PlanDiff(BaseModel):
    """What changed between two plan versions."""

    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    total_before: Decimal
    total_after: Decimal


class Session(BaseModel):
    """A dictation session."""

    id: str
    patient_label: str = ""
    state: Literal["CREATED", "TRANSCRIBED", "DRAFT", "CONFIRMED"] = "CREATED"
    transcript: str = ""
    audio_count: int = 0
    current_version: int = 0
    plan_state: PlanState = Field(default_factory=PlanState)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
