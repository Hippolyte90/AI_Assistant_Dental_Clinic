"""Accounts and access control for the public link."""

import json
import time

import pytest
from conftest import FakeLLM, FakeTranscriber
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.schemas import Procedure
from app.services.auth import (
    SESSION_SECONDS,
    create_token,
    hash_password,
    verify_password,
    verify_token,
)

PASSWORD = "correct-horse-battery"
ALICE = {"name": "Alice", "email": "alice@example.com", "password": PASSWORD}
BOB = {"name": "Bob", "email": "bob@example.com", "password": "another-long-pass"}


@pytest.fixture
def app(tmp_path):
    llm = FakeLLM()
    llm.extraction = [Procedure(said="root canal", teeth=[36])]
    settings = Settings(storage_dir=tmp_path, auth_required=True, _env_file=None)
    return create_app(settings, llm, FakeTranscriber())


@pytest.fixture
def anonymous(app):
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/health"),
        ("get", "/api/catalog"),
        ("get", "/api/catalog/search?q=implant"),
        ("post", "/api/sessions"),
        ("get", "/api/sessions/0123456789abcdef0123456789abcdef"),
        ("get", "/api/sessions/0123456789abcdef0123456789abcdef/plans/1/pdf"),
        ("get", "/api/sessions/0123456789abcdef0123456789abcdef/plans/1/pdf/pages/1"),
        ("delete", "/api/sessions/0123456789abcdef0123456789abcdef"),
        ("get", "/api/jobs/abc"),
        ("post", "/api/transcribe"),
    ],
)
def test_every_api_route_needs_sign_in(anonymous, method, path):
    assert getattr(anonymous, method)(path).status_code == 401


def test_api_docs_are_hidden(anonymous):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert anonymous.get(path).status_code == 404


def test_sign_up_sign_out_sign_in(anonymous):
    assert anonymous.get("/api/auth/status").json()["authenticated"] is False
    created = anonymous.post("/api/auth/register", json=ALICE)
    assert created.status_code == 201
    cookie = created.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert anonymous.get("/api/auth/status").json()["user"]["name"] == "Alice"
    assert anonymous.get("/api/health").status_code == 200
    anonymous.post("/api/auth/logout")
    assert anonymous.get("/api/health").status_code == 401
    wrong = {"email": ALICE["email"], "password": "not-the-password"}
    assert anonymous.post("/api/auth/login", json=wrong).status_code == 401
    right = {"email": "ALICE@example.com", "password": PASSWORD}
    assert anonymous.post("/api/auth/login", json=right).status_code == 200
    assert anonymous.get("/api/health").status_code == 200


def test_password_is_never_stored_in_clear(anonymous, tmp_path):
    anonymous.post("/api/auth/register", json=ALICE)
    raw = (tmp_path / "users.json").read_text(encoding="utf-8")
    assert PASSWORD not in raw
    assert json.loads(raw)[ALICE["email"]]["password_hash"].startswith("scrypt$")


@pytest.mark.parametrize(
    "form",
    [
        {**ALICE, "password": "1234"},
        {**ALICE, "email": "not-an-email"},
        {**ALICE, "name": "   "},
    ],
)
def test_invalid_sign_up_is_refused(anonymous, form):
    assert anonymous.post("/api/auth/register", json=form).status_code == 400


def test_duplicate_email_is_refused(anonymous):
    assert anonymous.post("/api/auth/register", json=ALICE).status_code == 201
    again = {**ALICE, "email": "Alice@Example.com"}
    assert anonymous.post("/api/auth/register", json=again).status_code == 409


def test_password_guessing_is_limited(anonymous):
    anonymous.post("/api/auth/register", json=ALICE)
    anonymous.post("/api/auth/logout")
    wrong = {"email": ALICE["email"], "password": "wrong-password"}
    for _ in range(5):
        assert anonymous.post("/api/auth/login", json=wrong).status_code == 401
    right = {"email": ALICE["email"], "password": PASSWORD}
    assert anonymous.post("/api/auth/login", json=right).status_code == 429


def test_users_cannot_see_each_others_plans(app):
    alice, bob = TestClient(app), TestClient(app)
    alice.post("/api/auth/register", json=ALICE)
    bob.post("/api/auth/register", json=BOB)
    session = alice.post("/api/sessions", json={}).json()["id"]
    alice.put(f"/api/sessions/{session}/transcript", json={"text": "Root canal on 36"})
    job = alice.post(f"/api/sessions/{session}/plan").json()["job_id"]
    for _ in range(200):
        result = alice.get(f"/api/jobs/{job}").json()
        if result["status"] in ("done", "error"):
            break
    assert result["status"] == "done"
    assert "owner_id" not in result
    assert alice.get(f"/api/sessions/{session}/plans/1/pdf").status_code == 200

    for method, path in [
        ("get", f"/api/sessions/{session}"),
        ("get", f"/api/sessions/{session}/plans"),
        ("get", f"/api/sessions/{session}/plans/1"),
        ("get", f"/api/sessions/{session}/plans/1/pdf"),
        ("get", f"/api/sessions/{session}/plans/1/pdf/pages/1"),
        ("post", f"/api/sessions/{session}/plan"),
        ("delete", f"/api/sessions/{session}"),
        ("get", f"/api/jobs/{job}"),
    ]:
        assert getattr(bob, method)(path).status_code == 404, path
    assert alice.get(f"/api/sessions/{session}").status_code == 200


def test_password_hashing():
    stored = hash_password(PASSWORD)
    assert PASSWORD not in stored
    assert verify_password(stored, PASSWORD)
    assert not verify_password(stored, "something-else")
    assert hash_password(PASSWORD) != stored


def test_tokens_cannot_be_forged_or_reused_after_expiry():
    secret = b"s" * 32
    token = create_token(secret, "user1", now=1000)
    assert verify_token(secret, token, now=1001) == "user1"
    assert verify_token(secret, token, now=1000 + SESSION_SECONDS + 1) is None
    assert verify_token(b"x" * 32, token, now=1001) is None
    assert verify_token(secret, token[:-1] + ("0" if token[-1] != "0" else "1"), now=1001) is None
    assert verify_token(secret, "garbage", now=1001) is None
    assert verify_token(secret, None) is None


def _build(client, label, notes="Root canal on 36"):
    session = client.post("/api/sessions", json={"patient_label": label}).json()["id"]
    client.put(f"/api/sessions/{session}/transcript", json={"text": notes})
    job = client.post(f"/api/sessions/{session}/plan").json()["job_id"]
    for _ in range(300):
        result = client.get(f"/api/jobs/{job}").json()
        if result["status"] in ("done", "error"):
            break
        time.sleep(0.01)
    assert result["status"] == "done"
    return session


def test_my_plans_lists_only_my_plans(app):
    alice, bob = TestClient(app), TestClient(app)
    alice.post("/api/auth/register", json=ALICE)
    bob.post("/api/auth/register", json=BOB)
    first = _build(alice, "P-1")
    second = _build(alice, "P-2")
    other = _build(bob, "B-1")
    alice.post("/api/sessions", json={"patient_label": "empty"})

    plans = alice.get("/api/sessions").json()
    assert [plan["id"] for plan in plans] == [second, first]
    assert plans[0]["status"] == "DRAFT" and plans[0]["total_eur"] == "89.60"
    assert plans[0]["stage_count"] == 1 and plans[0]["current_version"] == 1
    assert "owner_id" not in plans[0]
    assert [plan["id"] for plan in bob.get("/api/sessions").json()] == [other]

    alice.post("/api/auth/logout")
    assert alice.get("/api/sessions").status_code == 401
    alice.post("/api/auth/login", json={"email": ALICE["email"], "password": PASSWORD})
    assert len(alice.get("/api/sessions").json()) == 2
    assert alice.get(f"/api/sessions/{first}/plans").status_code == 200


def test_my_plans_shows_notes_final_status_and_survives_a_bad_folder(app, tmp_path):
    alice = TestClient(app)
    alice.post("/api/auth/register", json=ALICE)
    session = _build(alice, "P-1")
    alice.post(f"/api/sessions/{session}/confirm", json={"accept_defaults": True})
    notes = alice.post("/api/sessions", json={"patient_label": "P-2"}).json()["id"]
    alice.put(f"/api/sessions/{notes}/transcript", json={"text": "word " * 60})
    broken = tmp_path / "sessions" / ("f" * 32)
    broken.mkdir()
    (broken / "session.json").write_text("{not json", encoding="utf-8")

    plans = {plan["id"]: plan for plan in alice.get("/api/sessions").json()}
    assert set(plans) == {session, notes}
    assert plans[session]["status"] == "FINAL" and plans[session]["current_version"] == 2
    assert plans[notes]["status"] is None and plans[notes]["total_eur"] is None
    assert plans[notes]["preview"].endswith("…")
