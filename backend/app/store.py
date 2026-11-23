"""JSON-file storage for sessions and plan versions."""

import os
import shutil
import tempfile
import uuid
from pathlib import Path

from app.models.schemas import Session, TreatmentPlan


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

    def create(self, patient_label: str = "") -> Session:
        """Create a new session."""
        session = Session(id=uuid.uuid4().hex, patient_label=patient_label)
        self.save(session)
        return session

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
