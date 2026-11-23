"""Shared fixtures. Nothing here needs Ollama, Whisper or the network."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.config import Settings
from app.models.schemas import (
    Extraction,
    MapChoice,
    MapResult,
    Procedure,
    ReviseOp,
    ReviseResult,
    Transcript,
)
from app.services.catalog import load_catalog
from app.services.matcher import Matcher
from app.services.rules import load_rules


class FakeLLM:
    """Returns canned structured answers."""

    def __init__(self) -> None:
        self.extraction: list[Procedure] = []
        self.ops: list[ReviseOp] = []
        self.map_choices: list[MapChoice] = []
        self.calls: list[str] = []

    def generate_json(self, _system, _user, schema):
        self.calls.append(schema.__name__)
        if schema is Extraction:
            return Extraction(procedures=self.extraction)
        if schema is MapResult:
            return MapResult(choices=self.map_choices)
        if schema is ReviseResult:
            return ReviseResult(ops=self.ops)
        raise AssertionError(schema)


class FakeTranscriber:
    """Returns a fixed transcript."""

    def transcribe(self, _path, _prompt=None) -> Transcript:
        return Transcript(text="Root canal on 36.", segments=[])


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()


@pytest.fixture(scope="session")
def rules():
    return load_rules()


@pytest.fixture(scope="session")
def matcher(catalog, rules):
    return Matcher(catalog, rules)


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def client(tmp_path, fake_llm):
    from app.main import create_app

    settings = Settings(storage_dir=tmp_path, auth_required=False, _env_file=None)
    return TestClient(create_app(settings, fake_llm, FakeTranscriber()))


@pytest.fixture
def wait_job():
    def _wait(client, job_id):
        for _ in range(200):
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in ("done", "error"):
                return job
            time.sleep(0.02)
        raise AssertionError("job did not finish")

    return _wait
