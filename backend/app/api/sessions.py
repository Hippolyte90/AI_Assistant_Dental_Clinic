"""Session routes: dictation, plan, revision, confirmation, PDF."""

from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.models.schemas import Answer, Session, SessionSummary, Transcript, TreatmentPlan
from app.services.pdf import count_pages, render_page_png
from app.services.workflow import Workflow, WorkflowError
from app.store import PlanNotFound

router = APIRouter(prefix="/api")
MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_SUFFIXES = {".webm", ".wav", ".mp3", ".m4a", ".ogg"}


class SessionCreate(BaseModel):
    """New session request."""

    patient_label: str = Field(default="", max_length=80)


class TranscriptUpdate(BaseModel):
    """Edited transcript."""

    text: str = Field(max_length=20000)


class ReviseRequest(BaseModel):
    """Answers and free-text corrections."""

    answers: list[Answer] = Field(default_factory=list)
    corrections: str | None = Field(default=None, max_length=5000)


class ConfirmRequest(BaseModel):
    """Confirmation request."""

    accept_defaults: bool = False


def workflow(request: Request) -> Workflow:
    """The application's workflow."""
    return request.app.state.workflow


def owner(request: Request) -> str:
    """Id of the signed-in user ('' when accounts are disabled)."""
    return getattr(request.state, "user_id", "")


@router.get("/sessions")
def list_sessions(request: Request) -> list[SessionSummary]:
    """The signed-in user's plans."""
    return workflow(request).store.list_summaries(owner(request))


@router.post("/sessions")
def create_session(body: SessionCreate, request: Request) -> Session:
    """Create a session."""
    return workflow(request).store.create(body.patient_label.strip(), owner(request))


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request) -> Session:
    """Read a session."""
    return workflow(request).store.load(session_id)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request) -> dict:
    """Delete a session with its audio and plans."""
    workflow(request).store.delete(session_id)
    return {"deleted": True}


@router.post("/sessions/{session_id}/audio")
def upload_audio(session_id: str, request: Request, file: UploadFile = File(...)) -> Transcript:
    """Store and transcribe a dictation."""
    suffix = Path(file.filename or "audio.webm").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise WorkflowError("Unsupported audio format.")
    data = file.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise WorkflowError("The recording is too large (25 MB maximum).")
    if not data:
        raise WorkflowError("The recording is empty.")
    return workflow(request).add_audio(session_id, data, suffix)


@router.put("/sessions/{session_id}/transcript")
def update_transcript(session_id: str, body: TranscriptUpdate, request: Request) -> Session:
    """Save the edited transcript."""
    return workflow(request).set_transcript(session_id, body.text)


@router.post("/sessions/{session_id}/plan", status_code=202)
def build_plan(session_id: str, request: Request) -> dict:
    """Start building a plan; poll /jobs/{id}."""
    flow = workflow(request)
    flow.store.load(session_id)
    job_id = flow.submit(lambda progress: flow.build(session_id, progress), owner(request))
    return {"job_id": job_id}


@router.post("/sessions/{session_id}/revise", status_code=202)
def revise_plan(session_id: str, body: ReviseRequest, request: Request) -> dict:
    """Start a revision; poll /jobs/{id}."""
    flow = workflow(request)
    flow.store.load(session_id)
    job_id = flow.submit(
        lambda progress: flow.revise(session_id, body.answers, body.corrections, progress),
        owner(request),
    )
    return {"job_id": job_id}


@router.post("/sessions/{session_id}/confirm")
def confirm_plan(session_id: str, body: ConfirmRequest, request: Request) -> TreatmentPlan:
    """Produce the FINAL version."""
    return workflow(request).confirm(session_id, body.accept_defaults)


@router.get("/sessions/{session_id}/plans")
def list_plans(session_id: str, request: Request) -> list[TreatmentPlan]:
    """All versions of the plan."""
    return workflow(request).store.list_plans(session_id)


@router.get("/sessions/{session_id}/plans/{version}")
def get_plan(session_id: str, version: int, request: Request) -> TreatmentPlan:
    """One version of the plan."""
    return workflow(request).store.load_plan(session_id, version)


@router.get("/sessions/{session_id}/plans/{version}/pdf")
def get_pdf(session_id: str, version: int, request: Request) -> FileResponse:
    """Download a version's PDF."""
    path = workflow(request).store.pdf_path(session_id, version)
    if not path.exists():
        raise PlanNotFound(version)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"treatment_plan_v{version}.pdf",
        content_disposition_type="inline",
    )


@router.get("/sessions/{session_id}/plans/{version}/pdf/pages")
def get_pdf_page_count(session_id: str, version: int, request: Request) -> dict:
    """Number of pages available for the on-screen preview."""
    path = workflow(request).store.pdf_path(session_id, version)
    if not path.exists():
        raise PlanNotFound(version)
    return {"pages": count_pages(path)}


@router.get("/sessions/{session_id}/plans/{version}/pdf/pages/{page}")
def get_pdf_page(session_id: str, version: int, page: int, request: Request) -> Response:
    """One PDF page as an image, for the on-screen preview."""
    path = workflow(request).store.pdf_path(session_id, version)
    if not path.exists():
        raise PlanNotFound(version)
    image = render_page_png(path, page)
    if image is None:
        raise PlanNotFound(page)
    return Response(
        image, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    """Progress of a background job."""
    job = workflow(request).job(job_id)
    if job is None:
        raise PlanNotFound(job_id)
    job.pop("owner_id", None)
    return job


@router.post("/transcribe")
def transcribe(request: Request, file: UploadFile = File(...)) -> Transcript:
    """Transcribe a spoken answer without storing it."""
    suffix = Path(file.filename or "audio.webm").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise WorkflowError("Unsupported audio format.")
    data = file.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES or not data:
        raise WorkflowError("The recording is empty or too large.")
    flow = workflow(request)
    return flow.transcribe_answer(data, suffix, flow.settings.storage_path / "tmp")
