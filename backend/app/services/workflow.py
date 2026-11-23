"""Session workflow and background jobs. Free of FastAPI so it can be tested alone."""

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import Settings
from app.models.schemas import Answer, PlanDiff, Session, Transcript, TreatmentPlan
from app.services.catalog import Catalog
from app.services.llm import LLMClient, LLMError
from app.services.pdf import render_plan_pdf
from app.services.planner import Planner, diff_plans
from app.services.rules import Rules
from app.services.stt import STTError, Transcriber
from app.store import Store

logger = logging.getLogger(__name__)
ASSISTANT_UNAVAILABLE = "The assistant is unavailable right now. Please try again."


class WorkflowError(RuntimeError):
    """A request that is not valid in the current session state."""


class Workflow:
    """All session operations. LLM work runs one job at a time in the background."""

    def __init__(
        self,
        settings: Settings,
        catalog: Catalog,
        rules: Rules,
        llm: LLMClient,
        transcriber: Transcriber,
        store: Store,
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.rules = rules
        self.llm = llm
        self.transcriber = transcriber
        self.store = store
        self.planner = Planner(catalog, rules, llm)
        self.jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1)

    # ----------------------------------------------------------------- jobs

    def submit(self, work: Callable[[Callable[[str], None]], dict], owner_id: str = "") -> str:
        """Queue an LLM job and return its id."""
        job_id = uuid.uuid4().hex
        with self._lock:
            self.jobs[job_id] = {
                "id": job_id,
                "owner_id": owner_id,
                "status": "queued",
                "step": "queued",
            }

        def progress(step: str) -> None:
            with self._lock:
                self.jobs[job_id].update(status="running", step=step)

        def run() -> None:
            progress("starting")
            try:
                result = work(progress)
                update = {"status": "done", "step": "done", "result": result}
            except LLMError as exc:
                logger.error("Assistant engine error: %s", exc)
                update = {"status": "error", "step": "error", "error": ASSISTANT_UNAVAILABLE}
            except (STTError, WorkflowError) as exc:
                update = {"status": "error", "step": "error", "error": str(exc)}
            except Exception:
                logger.exception("Job failed")
                update = {
                    "status": "error",
                    "step": "error",
                    "error": "Unexpected error while building the plan.",
                }
            with self._lock:
                self.jobs[job_id].update(update)

        self._executor.submit(run)
        return job_id

    def job(self, job_id: str) -> dict | None:
        """Current state of a job."""
        with self._lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    # ------------------------------------------------------------- sessions

    def add_audio(self, session_id: str, data: bytes, suffix: str) -> Transcript:
        """Store a dictation and transcribe it."""
        session = self.store.load(session_id)
        session.audio_count += 1
        path = self.store.audio_path(session_id, session.audio_count, suffix)
        path.write_bytes(data)
        transcript = self.transcriber.transcribe(path)
        session.transcript = (f"{session.transcript} {transcript.text}").strip()
        if session.state == "CREATED":
            session.state = "TRANSCRIBED"
        self.store.save(session)
        return transcript

    def transcribe_answer(self, data: bytes, suffix: str, temp_dir: Path) -> Transcript:
        """Transcribe a spoken answer; the temporary audio is deleted afterwards."""
        path = temp_dir / f"{uuid.uuid4().hex}{suffix}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        try:
            return self.transcriber.transcribe(path)
        finally:
            path.unlink(missing_ok=True)

    def set_transcript(self, session_id: str, text: str) -> Session:
        """Replace the transcript with the dentist's edited text."""
        session = self.store.load(session_id)
        session.transcript = text.strip()
        if session.state == "CREATED" and session.transcript:
            session.state = "TRANSCRIBED"
        self.store.save(session)
        return session

    def _publish(self, session: Session, plan: TreatmentPlan) -> TreatmentPlan:
        path = self.store.pdf_path(session.id, plan.version)
        render_plan_pdf(plan, path, self.settings, session.patient_label)
        plan.pdf_path = f"/api/sessions/{session.id}/plans/{plan.version}/pdf"
        self.store.save_plan(plan)
        session.current_version = plan.version
        self.store.save(session)
        return plan

    def build(self, session_id: str, progress: Callable[[str], None]) -> dict:
        """Build a new version from the transcript."""
        session = self.store.load(session_id)
        if not session.transcript.strip():
            raise WorkflowError("There is no dictation to build a plan from.")
        session.plan_state = self.planner.build_state(session.transcript, progress)
        if not session.plan_state.procedures:
            raise WorkflowError("No dental procedure was found in the dictation.")
        progress("price")
        plan = self.planner.to_plan(session.plan_state, session.id, session.current_version + 1)
        progress("pdf")
        session.state = "DRAFT"
        plan = self._publish(session, plan)
        return {"plan": plan.model_dump(mode="json"), "diff": None}

    def revise(
        self,
        session_id: str,
        answers: list[Answer],
        corrections: str | None,
        progress: Callable[[str], None],
    ) -> dict:
        """Apply answers and corrections, then publish a new version."""
        session = self.store.load(session_id)
        if session.current_version == 0:
            raise WorkflowError("Build a plan first.")
        if not answers and not (corrections or "").strip():
            raise WorkflowError("There is nothing to apply.")
        previous = self.store.load_plan(session_id, session.current_version)
        session.plan_state = self.planner.revise_state(
            session.plan_state, previous.questions, answers, corrections, progress
        )
        progress("price")
        plan = self.planner.to_plan(session.plan_state, session.id, previous.version + 1)
        plan.answers = [*previous.answers, *answers]
        progress("pdf")
        session.state = "DRAFT"
        plan = self._publish(session, plan)
        diff: PlanDiff = diff_plans(previous, plan)
        return {
            "plan": plan.model_dump(mode="json"),
            "diff": diff.model_dump(mode="json"),
        }

    def confirm(self, session_id: str, accept_defaults: bool) -> TreatmentPlan:
        """Freeze the current version as a FINAL plan."""
        session = self.store.load(session_id)
        if session.current_version == 0:
            raise WorkflowError("Build a plan first.")
        current = self.store.load_plan(session_id, session.current_version)
        if current.status == "FINAL":
            return current
        blocking = [q for q in current.questions if q.blocking]
        if blocking and not accept_defaults:
            raise WorkflowError(
                f"{len(blocking)} question(s) still need an answer, or accept the defaults."
            )
        final = current.model_copy(deep=True)
        final.version = current.version + 1
        final.status = "FINAL"
        accepted = [f"Provisional choice accepted by the dentist: {q.text}" for q in blocking]
        final.assumptions = accepted + [
            a for a in current.assumptions if not a.startswith("Provisional choice pending")
        ]
        final.questions = []
        for stage in final.stages:
            for item in stage.items:
                item.provisional = False
        session.state = "CONFIRMED"
        return self._publish(session, final)
