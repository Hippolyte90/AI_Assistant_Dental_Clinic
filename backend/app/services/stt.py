"""Local speech-to-text with faster-whisper. Audio never leaves the machine."""

import logging
import os
import threading
from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.models.schemas import Transcript

logger = logging.getLogger(__name__)

DENTAL_PROMPT = (
    "Dental treatment dictation. Tooth numbers in FDI notation such as 11, 26, 36, 46. "
    "Root canal, core build-up, two-surface filling, zirconia crown, healing abutment, "
    "implant, Osstem, Megagen, Straumann, Nobel, Neodent, MTA, endodontic re-treatment, "
    "scaling and root planing, periodontal charting, socket preservation, sinus lift, "
    "All-on-4, All-on-6, rubber dam, local anaesthesia, sedation, fluoride varnish."
)


class STTError(RuntimeError):
    """A transcription failure with a message for the dentist."""


class Transcriber(Protocol):
    """Anything able to turn an audio file into text."""

    def transcribe(self, path: Path, prompt: str | None = None) -> Transcript:
        """Transcribe one audio file."""
        ...


class WhisperTranscriber:
    """faster-whisper on CPU, English only. The model is loaded once, on first use."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                # Keep model files inside the app's storage, whatever HF_HOME says on this machine.
                cache = self.settings.storage_path / "models"
                os.environ["HF_HOME"] = str(cache / "huggingface")
                os.environ["HF_XET_CACHE"] = str(cache / "huggingface" / "xet")
                from faster_whisper import WhisperModel

                logger.info("Loading Whisper model %s", self.settings.whisper_model)
                self._model = WhisperModel(
                    self.settings.whisper_model,
                    device=self.settings.whisper_device,
                    compute_type="int8",
                    download_root=str(self.settings.storage_path / "models" / "whisper"),
                )
        return self._model

    def transcribe(self, path: Path, prompt: str | None = None) -> Transcript:
        """Transcribe in English with a dental vocabulary hint."""
        try:
            segments, _info = self._load().transcribe(
                str(path),
                language="en",
                initial_prompt=prompt or DENTAL_PROMPT,
                vad_filter=True,
            )
            rows = [
                {
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text.strip(),
                }
                for s in segments
            ]
        except Exception as exc:
            logger.exception("Transcription failed")
            raise STTError("The recording could not be transcribed.") from exc
        return Transcript(text=" ".join(row["text"] for row in rows).strip(), segments=rows)
