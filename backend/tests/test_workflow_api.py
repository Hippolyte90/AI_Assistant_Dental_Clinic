"""Full loop through the API with the LLM and the transcriber mocked."""

import json
from decimal import Decimal
from io import BytesIO

from pypdf import PdfReader

from app.config import DATA_DIR
from app.models.schemas import MapChoice, Procedure, ReviseOp
from app.services.llm import LLMError
from app.services.planner import Planner, clean_transcript

NOTE_PROCEDURES = {
    "note_01": [
        Procedure(said="tooth extraction and socket preservation", teeth=[46]),
        Procedure(said="implant with a healing abutment", teeth=[46]),
        Procedure(said="abutment and a zirconia crown on the implant", teeth=[46]),
    ],
    "note_02": [
        Procedure(said="root canal under local anaesthesia with a rubber dam", teeth=[36]),
        Procedure(said="core build-up", teeth=[36], interval_hint="two weeks"),
        Procedure(said="two-surface filling", teeth=[11]),
        Procedure(said="filling", teeth=[21]),
    ],
    "note_03": [
        Procedure(said="periodontal consultation and initial charting"),
        Procedure(said="scaling and root planing on both jaws"),
        Procedure(
            said="periodontal follow-up examination with charting",
            interval_hint="three to six months",
        ),
    ],
    "note_04": [
        Procedure(said="wisdom tooth extraction", teeth=[38]),
        Procedure(said="sedation for two hours"),
        Procedure(said="fluoride varnish", teeth=[37], interval_hint="one week"),
    ],
}


def pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)


def start(client, wait_job, transcript="dictation"):
    session = client.post("/api/sessions", json={"patient_label": "P-001"}).json()
    client.put(f"/api/sessions/{session['id']}/transcript", json={"text": transcript})
    job = client.post(f"/api/sessions/{session['id']}/plan").json()
    result = wait_job(client, job["job_id"])
    assert result["status"] == "done", result
    return session["id"], result["result"]["plan"]


def test_health_reports_rules_not_validated(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["llm"] == "ok"
    assert body["catalog_items"] == 208 and body["rules_validated"] is False


def test_catalog_search(client):
    names = [item["name"] for item in client.get("/api/catalog/search?q=straumann").json()]
    assert "Straumann abutment placement" in names


def test_every_practice_note_matches_its_expected_plan(client, fake_llm, wait_job):
    for note, procedures in NOTE_PROCEDURES.items():
        expected = json.loads(
            (DATA_DIR / "sample_notes" / f"{note}.expected.json").read_text("utf-8")
        )
        fake_llm.extraction = procedures
        _, plan = start(client, wait_job)
        got = sorted(
            (item["catalog_id"], item["quantity"])
            for stage in plan["stages"]
            for item in stage["items"]
        )
        assert got == sorted((row["catalog_id"], row["quantity"]) for row in expected["items"]), (
            note
        )
        assert Decimal(plan["total_eur"]) == Decimal(expected["total_eur"]), note
        topics = {q["topic"] for q in plan["questions"] if q["kind"] != "interval"}
        assert topics == set(expected["expected_questions"]), note


def test_dictated_intervals_are_not_assumptions(client, fake_llm, wait_job):
    fake_llm.extraction = NOTE_PROCEDURES["note_03"]
    _, plan = start(client, wait_job)
    last_gap = plan["stages"][-2]["interval_after"]
    assert (last_gap["min_days"], last_gap["max_days"], last_gap["assumed"]) == (
        90,
        180,
        False,
    )


def test_full_loop_answer_correct_confirm(client, fake_llm, wait_job):
    fake_llm.extraction = NOTE_PROCEDURES["note_01"]
    session_id, v1 = start(client, wait_job)
    assert v1["status"] == "DRAFT" and Decimal(v1["total_eur"]) == Decimal("975.76")
    pdf = client.get(f"/api/sessions/{session_id}/plans/1/pdf")
    assert pdf.headers["content-type"] == "application/pdf"
    assert "975.76" in pdf_text(pdf.content) and "DRAFT" in pdf_text(pdf.content)

    assert client.post(f"/api/sessions/{session_id}/confirm", json={}).status_code == 409

    answers = [
        {"question_id": "dim:brand", "option_id": "straumann"},
        {"question_id": "dim:crown_type", "option_id": "st"},
    ]
    answers += [
        {"question_id": q["id"], "option_id": "keep"}
        for q in v1["questions"]
        if q["kind"] == "interval"
    ]
    job = client.post(f"/api/sessions/{session_id}/revise", json={"answers": answers}).json()
    result = wait_job(client, job["job_id"])["result"]
    v2 = result["plan"]
    # 60 + 830 + 65 + 61.53 + 340
    assert Decimal(v2["total_eur"]) == Decimal("1356.53")
    assert v2["version"] == 2 and v2["questions"] == []
    assert any("Straumann BLT" in line for line in result["diff"]["added"])
    assert "1 356.53" in pdf_text(client.get(f"/api/sessions/{session_id}/plans/2/pdf").content)

    final = client.post(f"/api/sessions/{session_id}/confirm", json={}).json()
    assert final["status"] == "FINAL" and final["version"] == 3
    text = pdf_text(client.get(f"/api/sessions/{session_id}/plans/3/pdf").content)
    assert "FINAL" in text and "DRAFT" not in text and "signature" in text
    assert len(client.get(f"/api/sessions/{session_id}/plans").json()) == 3


def test_free_text_correction_uses_llm_and_reprices(client, fake_llm, wait_job):
    fake_llm.extraction = NOTE_PROCEDURES["note_04"]
    session_id, _v1 = start(client, wait_job)
    fake_llm.ops = [
        ReviseOp(op="remove", index=2),
        ReviseOp(op="add", said="dental radiograph", teeth=[38]),
    ]
    body = {"corrections": "Remove the fluoride and add a radiograph on 38"}
    job = client.post(f"/api/sessions/{session_id}/revise", json=body).json()
    plan = wait_job(client, job["job_id"])["result"]["plan"]
    names = [item["name"] for stage in plan["stages"] for item in stage["items"]]
    assert "Fluoride varnish application, 1 tooth" not in names
    assert "Dental radiograph" in names
    assert Decimal(plan["total_eur"]) == Decimal("345.07") - Decimal("4.18") + Decimal("4.18")


def test_llm_only_chooses_from_shortlist(client, fake_llm, wait_job, catalog):
    fake_llm.extraction = [Procedure(said="bone grafting at the site", teeth=[13])]
    fake_llm.map_choices = [MapChoice(index=0, catalog_id="impl-001")]  # not a candidate
    _, plan = start(client, wait_job)
    assert plan["stages"][0]["items"][0]["catalog_id"] != "impl-001"
    assert any(q["topic"] == "item" for q in plan["questions"])


def test_unknown_service_can_be_left_out(client, fake_llm, wait_job):
    fake_llm.extraction = [
        Procedure(said="root canal", teeth=[36]),
        Procedure(said="xylophone therapy"),
    ]
    session_id, v1 = start(client, wait_job)
    assert v1["unmapped_mentions"] == ["xylophone therapy"]
    question = next(q for q in v1["questions"] if q["kind"] == "unknown_service")
    answers = [{"question_id": question["id"], "option_id": "exclude"}]
    job = client.post(f"/api/sessions/{session_id}/revise", json={"answers": answers}).json()
    plan = wait_job(client, job["job_id"])["result"]["plan"]
    assert plan["unmapped_mentions"] == []
    assert Decimal(plan["total_eur"]) == Decimal("89.60")


def test_voice_upload_and_answer(client):
    session = client.post("/api/sessions", json={}).json()
    files = {"file": ("clip.webm", b"audio", "audio/webm")}
    body = client.post(f"/api/sessions/{session['id']}/audio", files=files).json()
    assert body["text"] == "Root canal on 36."
    assert client.get(f"/api/sessions/{session['id']}").json()["state"] == "TRANSCRIBED"
    assert client.post("/api/transcribe", files=files).json()["text"] == "Root canal on 36."
    bad = {"file": ("clip.exe", b"x", "application/octet-stream")}
    assert client.post("/api/transcribe", files=bad).status_code == 409


def test_errors_and_delete(client, wait_job):
    assert client.get("/api/sessions/../../etc").status_code == 404
    assert client.get("/api/sessions/not-a-session").status_code == 404
    session = client.post("/api/sessions", json={}).json()
    job = client.post(f"/api/sessions/{session['id']}/plan").json()
    assert wait_job(client, job["job_id"])["status"] == "error"
    assert client.delete(f"/api/sessions/{session['id']}").json() == {"deleted": True}
    assert client.get(f"/api/sessions/{session['id']}").status_code == 404


def test_synthetic_label_is_not_sent_to_the_model():
    text = "SYNTHETIC PRACTICE NOTE – not from the instructor\nRoot canal on 36."
    assert clean_transcript(text) == "Root canal on 36."
    assert Planner is not None


def test_confirming_never_claims_unreviewed_intervals_were_accepted(client, fake_llm, wait_job):
    fake_llm.extraction = NOTE_PROCEDURES["note_01"]
    session_id, _ = start(client, wait_job)
    final = client.post(
        f"/api/sessions/{session_id}/confirm", json={"accept_defaults": True}
    ).json()
    assert final["status"] == "FINAL"
    accepted = [a for a in final["assumptions"] if "accepted by the dentist" in a]
    assert len(accepted) == 2 and not any("wait" in a for a in accepted)
    assert any(a.startswith("Default interval") for a in final["assumptions"])
    assert all(s["interval_after"]["assumed"] for s in final["stages"][:-1])


def test_engine_errors_are_not_shown_to_the_dentist(client, fake_llm, wait_job):
    def fail(*_args):
        raise LLMError("Ollama is not running. Start the Ollama app.")

    fake_llm.generate_json = fail
    session = client.post("/api/sessions", json={}).json()
    client.put(f"/api/sessions/{session['id']}/transcript", json={"text": "Root canal on 36"})
    job = client.post(f"/api/sessions/{session['id']}/plan").json()
    result = wait_job(client, job["job_id"])
    assert result["status"] == "error"
    assert "ollama" not in result["error"].lower()


def test_pdf_preview_pages(client, fake_llm, wait_job):
    fake_llm.extraction = NOTE_PROCEDURES["note_01"]
    session_id, _ = start(client, wait_job)
    base = f"/api/sessions/{session_id}/plans/1/pdf/pages"
    pages = client.get(base).json()["pages"]
    assert pages >= 1
    image = client.get(f"{base}/1")
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG")
    assert client.get(f"{base}/{pages + 1}").status_code == 404
