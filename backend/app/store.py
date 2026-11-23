"""JSON-file storage for sessions and plan versions."""

import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from app.models.schemas import Session, SessionSummary, TreatmentPlan

logger = logging.getLogger(__name__)
PREVIEW_LENGTH = 110


class SessionNotFound(KeyError):
    """The session does not exist."""


class PlanNotFound(KeyError):
    """The plan version does not exist."""


class Store:
    """Keeps one folder per session under storage/sessions."""

    def __init__(self, root: Path) -> None:
        self.root = root / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, session_id: str) -> Path:
        """Folder of a session; rejects anything that is not a generated id."""
        try:
            normalized = uuid.UUID(hex=session_id).hex
        except ValueError as exc:
            raise SessionNotFound(session_id) from exc
        if normalized != session_id:
            raise SessionNotFound(session_id)
        return self.root / session_id

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temp, path)

    def create(self, patient_label: str = "", owner_id: str = "") -> Session:
        """Create a new session."""
        session = Session(id=uuid.uuid4().hex, owner_id=owner_id, patient_label=patient_label)
        self.save(session)
        return session

    def owned_by(self, session_id: str, owner_id: str) -> bool:
        """True if this session exists and belongs to this user."""
        try:
            return self.load(session_id).owner_id == owner_id
        except SessionNotFound:
            return False

    def list_summaries(self, owner_id: str) -> list[SessionSummary]:
        """This user's plans and started notes, most recently updated first."""
        summaries: list[SessionSummary] = []
        for path in self.root.glob("*/session.json"):
            try:
                session = Session.model_validate_json(path.read_text(encoding="utf-8"))
                if session.owner_id != owner_id:
                    continue
                version = session.current_version
                plan = self.load_plan(session.id, version) if version else None
            except (ValueError, OSError, PlanNotFound):
                logger.warning("Skipping an unreadable session folder: %s", path.parent.name)
                continue
            notes = " ".join(session.transcript.split())
            if plan is None and not notes:
                continue
            preview = notes
            if len(notes) > PREVIEW_LENGTH:
                preview = notes[:PREVIEW_LENGTH].rstrip() + "…"
            summaries.append(
                SessionSummary(
                    id=session.id,
                    patient_label=session.patient_label,
                    state=session.state,
                    status=plan.status if plan else None,
                    current_version=version,
                    total_eur=plan.total_eur if plan else None,
                    stage_count=len(plan.stages) if plan else 0,
                    preview=preview,
                    created_at=session.created_at,
                    updated_at=plan.created_at if plan else session.created_at,
                )
            )
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return summaries

    def save(self, session: Session) -> None:
        """Persist a session atomically."""
        path = self.directory(session.id) / "session.json"
        self._write(path, session.model_dump_json(indent=1))

    def load(self, session_id: str) -> Session:
        """Read a session."""
        path = self.directory(session_id) / "session.json"
        if not path.exists():
            raise SessionNotFound(session_id)
        return Session.model_validate_json(path.read_text(encoding="utf-8"))

    def audio_path(self, session_id: str, number: int, suffix: str) -> Path:
        """Path of a stored recording."""
        path = self.directory(session_id) / "audio" / f"{number}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def pdf_path(self, session_id: str, version: int) -> Path:
        """Path of a version's PDF."""
        return self.directory(session_id) / "plans" / f"v{version}.pdf"

    def save_plan(self, plan: TreatmentPlan) -> None:
        """Persist a plan version."""
        path = self.directory(plan.session_id) / "plans" / f"v{plan.version}.json"
        self._write(path, plan.model_dump_json(indent=1))

    def load_plan(self, session_id: str, version: int) -> TreatmentPlan:
        """Read a plan version."""
        path = self.directory(session_id) / "plans" / f"v{version}.json"
        if not path.exists():
            raise PlanNotFound(version)
        return TreatmentPlan.model_validate_json(path.read_text(encoding="utf-8"))

    def list_plans(self, session_id: str) -> list[TreatmentPlan]:
        """All versions, oldest first."""
        self.load(session_id)
        folder = self.directory(session_id) / "plans"
        if not folder.exists():
            return []
        versions = sorted(int(path.stem[1:]) for path in folder.glob("v*.json"))
        return [self.load_plan(session_id, version) for version in versions]

    def delete(self, session_id: str) -> None:
        """Delete a session with its audio and plans."""
        self.load(session_id)
        shutil.rmtree(self.directory(session_id))
