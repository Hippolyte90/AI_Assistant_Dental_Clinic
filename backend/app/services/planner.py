"""Builds and revises treatment plans: extract -> match -> map -> assemble -> price."""

from collections.abc import Callable
from decimal import Decimal

from app.config import PROMPTS_DIR
from app.models.schemas import (
    Answer,
    ClarifyingQuestion,
    Extraction,
    Interval,
    MapResult,
    PlanDiff,
    PlanDraft,
    PlanItemDraft,
    PlanState,
    Procedure,
    QuestionOption,
    ReviseResult,
    StageDraft,
    TrackedProcedure,
    TreatmentPlan,
)
from app.services.catalog import Catalog
from app.services.llm import LLMClient
from app.services.matcher import SEDATION_HOURS, Matcher, Resolution, parse_interval
from app.services.pricing import money, price_plan
from app.services.rules import Rules

Progress = Callable[[str], None]
MAX_QUESTIONS = 7
EXCLUDE = "exclude"
ADJUNCT_PREFERENCE = ["surgery", "implant", "endodontic", "restorative", "periodontal"]


def clean_transcript(text: str) -> str:
    """Drop the synthetic-note label so it is never sent to the model."""
    lines = [line for line in text.splitlines() if "SYNTHETIC PRACTICE NOTE" not in line]
    return "\n".join(lines).strip()


def _days(interval: Interval) -> str:
    low, high = interval.min_days, interval.max_days
    unit, size = ("days", 1)
    if low >= 60 and low % 30 == 0 and high % 30 == 0:
        unit, size = ("months", 30)
    elif low >= 7 and low % 7 == 0 and high % 7 == 0:
        unit, size = ("weeks", 7)
    span = f"{low // size}" if low == high else f"{low // size}–{high // size}"
    return f"{span} {unit}"


class Planner:
    """Orchestrates the LLM steps; everything exact is done in code."""

    def __init__(self, catalog: Catalog, rules: Rules, llm: LLMClient) -> None:
        self.catalog = catalog
        self.rules = rules
        self.llm = llm
        self.matcher = Matcher(catalog, rules)

    @staticmethod
    def _prompt(name: str) -> str:
        return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")

    # ---------------------------------------------------------------- build

    def build_state(self, transcript: str, progress: Progress | None = None) -> PlanState:
        """Run Step A, the matcher and Step B on a transcript."""
        report = progress or (lambda _step: None)
        text = clean_transcript(transcript)
        report("extract")
        extraction = self.llm.generate_json(self._prompt("extract_procedures"), text, Extraction)
        state = PlanState(facts=self.matcher.detect_facts(text))
        self._add_procedures(state, self.matcher.ground(extraction.procedures, text))
        report("match")
        self.map_open_procedures(state)
        return state

    def _add_procedures(self, state: PlanState, procedures: list[Procedure]) -> None:
        for procedure in procedures:
            for part in self.matcher.split_compound(procedure):
                for single in self.matcher.split_by_tooth_type(part):
                    state.procedures.append(
                        TrackedProcedure(pid=state.next_pid, **single.model_dump())
                    )
                    state.next_pid += 1

    def map_open_procedures(self, state: PlanState) -> None:
        """Step B: ask the LLM only about procedures the rules could not settle."""
        open_items: list[tuple[TrackedProcedure, Resolution]] = []
        for procedure in self._active(state):
            resolution = self.matcher.resolve(procedure, state.facts)
            if resolution.needs_llm and resolution.candidates:
                open_items.append((procedure, resolution))
        if not open_items:
            return
        blocks = []
        for index, (procedure, resolution) in enumerate(open_items):
            lines = [f'[{index}] said: "{procedure.said}"']
            lines += [f" {item.id}: {item.name}" for item in resolution.candidates]
            blocks.append("\n".join(lines))
        result = self.llm.generate_json(
            self._prompt("map_to_catalog"), "\n".join(blocks), MapResult
        )
        for choice in result.choices:
            if not 0 <= choice.index < len(open_items):
                continue
            procedure, resolution = open_items[choice.index]
            if choice.catalog_id in {item.id for item in resolution.candidates}:
                procedure.suggested_id = choice.catalog_id

    @staticmethod
    def _active(state: PlanState) -> list[TrackedProcedure]:
        return [procedure for procedure in state.procedures if not procedure.excluded]

    # ------------------------------------------------------------- assemble

    def _context_category(self, state: PlanState, adjunct: TrackedProcedure) -> str | None:
        main: list[tuple[TrackedProcedure, str]] = []
        for procedure in self._active(state):
            family = self.matcher.family_for(procedure.said)
            if family and family["category"] == "adjunct":
                continue
            main.append((procedure, self.matcher.resolve(procedure, state.facts).category))
        if not main:
            return None
        for procedure, category in main:
            if set(procedure.teeth) & set(adjunct.teeth):
                return category
        categories = {category for _, category in main}
        return next((c for c in ADJUNCT_PREFERENCE if c in categories), main[0][1])

    def _resolutions(self, state: PlanState) -> list[tuple[TrackedProcedure, Resolution, str]]:
        """Resolve procedures and assign each to a stage key."""
        keys = self.rules.stage_keys
        rows: list[tuple[TrackedProcedure, Resolution, str]] = []
        last_rank = -1
        for procedure in self._active(state):
            family = self.matcher.family_for(procedure.said)
            is_adjunct = bool(family and family["category"] == "adjunct")
            context = self._context_category(state, procedure) if is_adjunct else None
            resolution = self.matcher.resolve(procedure, state.facts, context)
            stage = context or resolution.category
            if stage == "adjunct":
                stage = keys[0]
            if not is_adjunct:
                dictated = parse_interval(procedure.interval_hint or procedure.said)
                if dictated and keys.index(stage) <= last_rank:
                    stage = "maintenance"
                last_rank = max(last_rank, keys.index(stage))
            rows.append((procedure, resolution, stage))
        return rows

    def _interval(
        self,
        state: PlanState,
        before: str,
        after: str,
        before_families: set[str],
        after_rows: list,
    ) -> Interval:
        key = f"{before}>{after}"
        if key in state.interval_overrides:
            return state.interval_overrides[key]
        for procedure, _, _ in after_rows:
            dictated = parse_interval(procedure.interval_hint or procedure.said)
            if dictated:
                return Interval(
                    min_days=dictated[0],
                    max_days=dictated[1],
                    reason="as dictated",
                    assumed=False,
                )
        clinic = self.rules.clinic
        spec = clinic["intervals"].get(key, clinic["default_interval"])
        for family in before_families:
            override = clinic.get("family_intervals", {}).get(f"{family}>{after}")
            if override:
                spec = override
        return Interval(**spec, assumed=not self.rules.validated)

    def assemble(self, state: PlanState) -> PlanDraft:
        """Rebuild the whole plan from its state, with no LLM call."""
        rows = self._resolutions(state)
        draft = PlanDraft()
        stage_defs = {stage["key"]: stage for stage in self.rules.clinic["stages"]}
        used = [key for key in self.rules.stage_keys if any(row[2] == key for row in rows)]
        for number, key in enumerate(used, start=1):
            stage_rows = [row for row in rows if row[2] == key]
            items = [
                PlanItemDraft(
                    catalog_id=item.id,
                    quantity=quantity,
                    teeth=list(procedure.teeth),
                    note=procedure.said,
                    provisional=resolution.provisional,
                )
                for procedure, resolution, _ in stage_rows
                for item, quantity in resolution.lines
            ]
            for rule in self.rules.clinic.get("auto_add", []):
                auto = self.catalog.ref(rule["item"])
                already_there = any(line.catalog_id == auto.id for line in items)
                if rule.get("enabled") and rule["stage"] == key and not already_there:
                    items.append(PlanItemDraft(catalog_id=auto.id, auto_added=True))
            interval = None
            if number < len(used):
                next_key = used[number]
                families = {row[1].family for row in stage_rows if row[1].family}
                next_rows = [row for row in rows if row[2] == next_key]
                interval = self._interval(state, key, next_key, families, next_rows)
                if interval.assumed:
                    draft.questions.append(self._interval_question(key, next_key, number, interval))
                    draft.assumptions.append(
                        f"Default interval after stage {number}: {_days(interval)} "
                        f"({interval.reason}). To be confirmed by the dentist."
                    )
            draft.stages.append(
                StageDraft(
                    number=number,
                    title=stage_defs[key]["title"],
                    goal=stage_defs[key]["goal"],
                    items=items,
                    interval_after=interval,
                )
            )
        stage_of = {key: number for number, key in enumerate(used, start=1)}
        choice_questions = self._choice_questions(state, rows, stage_of)
        for procedure, resolution, _ in rows:
            if resolution.unmapped:
                draft.unmapped_mentions.append(procedure.said)
        for question in choice_questions:
            draft.assumptions.insert(0, f"Provisional choice pending: {question.text}")
        draft.questions = (choice_questions + draft.questions)[:MAX_QUESTIONS]
        return draft

    def _lines_total(self, state: PlanState) -> Decimal:
        total = Decimal(0)
        for procedure in self._active(state):
            for item, quantity in self.matcher.resolve(procedure, state.facts).lines:
                total += item.price_eur * quantity
        return money(total)

    def _choice_questions(
        self, state: PlanState, rows: list, stage_of: dict[str, int]
    ) -> list[ClarifyingQuestion]:
        questions: dict[str, ClarifyingQuestion] = {}
        base = self._lines_total(state)
        for procedure, resolution, stage in rows:
            if resolution.unmapped:
                options = [
                    QuestionOption(id=item.id, label=item.name, catalog_ids=[item.id])
                    for item in resolution.candidates
                ]
                options.append(QuestionOption(id=EXCLUDE, label="Leave it out of the plan"))
                questions[f"p{procedure.pid}:item"] = ClarifyingQuestion(
                    id=f"p{procedure.pid}:item",
                    text=f"'{procedure.said}' is not in the price list. "
                    "Which service is it, or should it be left out?",
                    kind="unknown_service",
                    options=options,
                )
                continue
            for pending in resolution.pending:
                question = self._question_for(procedure, pending, stage_of.get(stage))
                if question.id not in questions:
                    questions[question.id] = question
                else:
                    known = {option.id for option in questions[question.id].options}
                    questions[question.id].options += [
                        option for option in question.options if option.id not in known
                    ]
        for question in questions.values():
            for option in question.options:
                trial = state.model_copy(deep=True)
                self._apply_option(trial, question.id, option.id)
                option.price_delta_eur = money(self._lines_total(trial) - base)
        return list(questions.values())

    def _question_for(self, procedure, pending, stage: int | None) -> ClarifyingQuestion:
        teeth = ", ".join(str(tooth) for tooth in procedure.teeth) or "?"
        if pending.dimension == "item":
            options = []
            for catalog_id in pending.values:
                item = self.catalog.get(catalog_id)
                options.append(QuestionOption(id=item.id, label=item.name, catalog_ids=[item.id]))
            return ClarifyingQuestion(
                id=f"p{procedure.pid}:item",
                text=f"Which price-list service matches '{procedure.said}' (tooth {teeth})?",
                kind="choice",
                topic="item",
                options=options,
                related_stage=stage,
            )
        if pending.dimension == "sedation_hours":
            options = [QuestionOption(id=k, label=v) for k, v in SEDATION_HOURS.items()]
            return ClarifyingQuestion(
                id=f"p{procedure.pid}:sedation_hours",
                text="How many hours of sedation?",
                kind="missing_param",
                topic="sedation_hours",
                options=options,
                related_stage=stage,
            )
        spec = self.rules.dimensions[pending.dimension]
        options = [
            QuestionOption(id=value, label=spec["values"][value]["label"])
            for value in pending.values
        ]
        is_global = spec["scope"] == "global"
        return ClarifyingQuestion(
            id=f"dim:{pending.dimension}" if is_global else f"p{procedure.pid}:{pending.dimension}",
            text=spec["question"].format(teeth=teeth),
            kind="choice" if is_global else "missing_param",
            topic=pending.dimension,
            options=options,
            related_stage=stage,
        )

    @staticmethod
    def _interval_question(
        before: str, after: str, number: int, interval: Interval
    ) -> ClarifyingQuestion:
        return ClarifyingQuestion(
            id=f"interval:{before}>{after}",
            text=f"Confirm the wait after stage {number}: {_days(interval)} ({interval.reason})? "
            "Or type another delay, e.g. '2 weeks'.",
            kind="interval",
            topic="interval",
            options=[QuestionOption(id="keep", label=f"Keep {_days(interval)}")],
            related_stage=number,
            blocking=False,
        )

    # --------------------------------------------------------------- revise

    def _apply_option(self, state: PlanState, question_id: str, option_id: str) -> None:
        if question_id.startswith("dim:"):
            state.facts[question_id[4:]] = option_id
            return
        if question_id.startswith("p"):
            pid_text, _, dimension = question_id[1:].partition(":")
            procedure = next((p for p in state.procedures if p.pid == int(pid_text)), None)
            if procedure is None:
                return
            if dimension == "item":
                if option_id == EXCLUDE:
                    procedure.excluded = True
                else:
                    procedure.catalog_id = option_id
            else:
                procedure.facts[dimension] = option_id

    def _apply_interval(self, state: PlanState, question: ClarifyingQuestion, answer: Answer):
        key = question.id.split(":", 1)[1]
        if answer.free_text:
            parsed = parse_interval(answer.free_text)
            if parsed is None:
                return False
            state.interval_overrides[key] = Interval(
                min_days=parsed[0],
                max_days=parsed[1],
                reason="set by dentist",
                assumed=False,
            )
            return True
        before, after = key.split(">")
        rows = self._resolutions(state)
        families = {row[1].family for row in rows if row[2] == before and row[1].family}
        current = self._interval(state, before, after, families, [])
        state.interval_overrides[key] = current.model_copy(update={"assumed": False})
        return True

    def apply_answers(
        self,
        state: PlanState,
        questions: list[ClarifyingQuestion],
        answers: list[Answer],
    ) -> list[str]:
        """Apply answers in code. Returns free text that still needs the LLM."""
        by_id = {question.id: question for question in questions}
        leftovers: list[str] = []
        for answer in answers:
            question = by_id.get(answer.question_id)
            if question is None:
                continue
            if question.kind == "interval":
                if not self._apply_interval(state, question, answer) and answer.free_text:
                    leftovers.append(answer.free_text)
                continue
            if answer.option_id and any(o.id == answer.option_id for o in question.options):
                self._apply_option(state, question.id, answer.option_id)
                continue
            if answer.free_text:
                value = self.matcher.detect_value(question.topic, answer.free_text)
                valid = {option.id for option in question.options}
                if value in valid:
                    self._apply_option(state, question.id, value)
                else:
                    leftovers.append(f"About '{question.text}': {answer.free_text}")
        return leftovers

    def apply_corrections(self, state: PlanState, corrections: str) -> None:
        """Turn a free-text correction into edits with the LLM."""
        state.facts.update(self.matcher.detect_facts(corrections))
        active = self._active(state)
        listing = "\n".join(
            f"[{index}] {procedure.said}, teeth {procedure.teeth}"
            for index, procedure in enumerate(active)
        )
        user = f"Procedure list:\n{listing}\n\nCorrection: {corrections}"
        result = self.llm.generate_json(self._prompt("revise_plan"), user, ReviseResult)
        additions: list[Procedure] = []
        for op in result.ops:
            if op.op == "add" and op.said:
                additions.append(
                    Procedure(said=op.said, teeth=op.teeth or [], quantity=op.quantity or 1)
                )
                continue
            if op.index is None or not 0 <= op.index < len(active):
                continue
            target = active[op.index]
            if op.op == "remove":
                target.excluded = True
            elif op.op == "change":
                if op.said:
                    target.said = op.said
                    target.catalog_id = None
                    target.suggested_id = None
                    target.facts = {}
                if op.teeth is not None:
                    target.teeth = op.teeth
                if op.quantity:
                    target.quantity = op.quantity
        self._add_procedures(state, additions)
        self.map_open_procedures(state)

    def revise_state(
        self,
        state: PlanState,
        questions: list[ClarifyingQuestion],
        answers: list[Answer],
        corrections: str | None,
        progress: Progress | None = None,
    ) -> PlanState:
        """Return a new state with answers and corrections applied."""
        report = progress or (lambda _step: None)
        updated = state.model_copy(deep=True)
        report("apply")
        leftovers = self.apply_answers(updated, questions, answers)
        text = " ".join(part for part in [*leftovers, corrections or ""] if part.strip())
        if text:
            report("revise")
            self.apply_corrections(updated, text)
        return updated

    def to_plan(self, state: PlanState, session_id: str, version: int) -> TreatmentPlan:
        """Assemble and price."""
        return price_plan(self.assemble(state), self.catalog, session_id, version)


def diff_plans(before: TreatmentPlan, after: TreatmentPlan) -> PlanDiff:
    """Compare two versions line by line."""

    def lines(plan: TreatmentPlan) -> dict[tuple, str]:
        result: dict[tuple, str] = {}
        for stage in plan.stages:
            for item in stage.items:
                teeth = ", ".join(str(tooth) for tooth in item.teeth)
                label = f"{item.name}" + (f" (tooth {teeth})" if teeth else "")
                result[(item.catalog_id, tuple(item.teeth))] = f"{label} × {item.quantity}"
        return result

    old, new = lines(before), lines(after)
    return PlanDiff(
        added=[new[key] for key in new if key not in old],
        removed=[old[key] for key in old if key not in new],
        changed=[f"{old[key]} → {new[key]}" for key in new if key in old and old[key] != new[key]],
        total_before=before.total_eur,
        total_after=after.total_eur,
    )
