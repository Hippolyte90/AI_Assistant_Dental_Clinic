# ARCHITECTURE — AI Assistant for a Dental Clinic

> How the system is built. *What* to build and progress tracking live in [SPEC.md](SPEC.md).
> If you change a design decision, update this file and add a line to the decision log (§10).

---

## 1. Overview

```
┌──────────────────────────── Browser (React + TS, Vite) ─────────────────────────────┐
│  Recorder 🎤 ─► Transcript editor ─► [Build plan] ─► Plan view + PDF viewer          │
│                                       ▲                    │                         │
│                                       │                    ▼                         │
│                         [Confirm] ◄── Questions panel (click / text / 🎤 voice)       │
└───────────────────────────────┬─────────────────────────────────────────────────────┘
                                │ REST JSON + multipart audio  (/api/*)
┌───────────────────────────────▼──────────────── FastAPI backend (Python 3.12) ───────┐
│  api/            routes: sessions, audio, plan, revise, confirm, catalog, pdf        │
│  services/                                                                            │
│    stt.py        faster-whisper (local)            audio ─► transcript               │
│    planner.py    orchestrates build / revise       transcript ─► TreatmentPlan        │
│    llm.py        local LLM (Ollama), JSON schema   text ─► procedures / choices       │
│    matcher.py    fuzzy + synonyms shortlist        procedure ─► top-5 catalog items   │
│    catalog.py    price list xlsx ─► catalog                                            │
│    pricing.py    validation + Decimal pricing      PlanDraft ─► priced TreatmentPlan  │
│    pdf.py        ReportLab                         TreatmentPlan ─► PDF               │
│  rules/          clinic_rules.yaml (intervals, auto-add) · synonyms.yaml              │
│  store.py        JSON-file storage: sessions, transcripts, plan versions              │
└───────────┬──────────────────────────────┬───────────────────────────────────────────┘
            │                              │
     storage/ (git-ignored)         Ollama server, localhost:11434
     sessions/{id}/session.json,    (default model qwen3:4b, thinking off, CPU)
       audio/, plans/v{n}.json|pdf
```

**Everything runs on the clinic machine.** **Everything is in English** (dictation, prompts, questions, UI, PDF). No cloud AI service is called: speech-to-text (faster-whisper) and the LLM (Ollama) are both local.

**Core principle:** the LLM understands language and *chooses services from a shortlist of catalog items*.
**Code** owns everything that must be exact: catalog shortlists, prices, totals, IDs, versions, the PDF.

---

## 2. Technology choices

| Concern | Choice | Why |
|---------|--------|-----|
| Backend | **FastAPI** + Uvicorn, Python 3.12 (conda env in `.venv/`) | Async, typed with Pydantic, auto OpenAPI docs at `/docs` |
| Validation / schemas | **Pydantic v2** | Same models for API, LLM structured output, and storage |
| LLM | **Local LLM via Ollama** (`ollama` Python package), default `qwen3:4b` with `think=False`, configurable | Fully offline and private, free to run, easy install on Windows, JSON-schema constrained output (`format=`) |
| Catalog matching | **rapidfuzz** + `synonyms.yaml` | Gives the small local model a short candidate list instead of 209 items |
| Speech-to-text | **faster-whisper** (local, CPU `small` by default) | Patient audio stays on the clinic machine; language fixed to English; no system ffmpeg needed (PyAV bundled) |
| PDF | **ReportLab** | Pure Python, reliable on Windows (WeasyPrint needs GTK) |
| Price list | **openpyxl** reads `.xlsx` | The PDF version truncates long service names |
| Persistence | **JSON files** in `storage/sessions/{id}/` (written atomically: temp file + rename) | Simplest option, human-readable, enough for one clinic |
| Frontend | **React + TypeScript + Vite**, Tailwind CSS | Fast dev loop; `MediaRecorder` for audio; `<iframe>` PDF preview |
| Text-to-speech (optional) | Browser `speechSynthesis` | No backend cost |
| Tests | pytest (+ httpx TestClient), Vitest for UI (optional) | |
| Lint/format | ruff (Python), ESLint + Prettier (TS) | |

---

## 3. End-to-end flow (sequence)

```
Dentist           Frontend                 Backend                         Ollama (local)
  │ speak  ─────►  MediaRecorder
  │                 │ POST /sessions/{id}/audio ─► stt.transcribe()
  │                 │ ◄─────────────── transcript
  │ edit/approve    │
  │                 │ POST /sessions/{id}/plan ─► planner.build()
  │                 │                              ├─ Step A llm.extract(transcript, rules) ─► procedures[]
  │                 │                              ├─ matcher.shortlist(procedure) → top-5 candidates each
  │                 │                              ├─ Step B llm.map(procedures, candidates) ─► PlanDraft (+ questions)
  │                 │                              ├─ pricing.price(PlanDraft)  → TreatmentPlan v1
  │                 │                              └─ pdf.render(v1)            → v1.pdf (DRAFT)
  │                 │ ◄──────── plan v1 + questions + pdf url
  │ answers (click/text/voice) + corrections
  │                 │ POST /sessions/{id}/revise ─► planner.revise()
  │                 │                              ├─ apply option answers in code
  │                 │                              ├─ llm.revise_plan(plan v1, free-text corrections) (only if needed)
  │                 │                              ├─ pricing.price() → v2 ;  pdf.render(v2)
  │                 │ ◄──────── plan v2 + diff + remaining questions
  │   … loop until no blocking questions …
  │ [Confirm]       │ POST /sessions/{id}/confirm ─► mark FINAL → final.pdf (no watermark, signatures)
```

Session state machine:

```
CREATED ─► TRANSCRIBED ─► DRAFT (needs_clarification) ⇄ DRAFT (revised) ─► CONFIRMED
                                   any edit after CONFIRMED ─► new DRAFT version
```

---

## 4. Repository layout

```
AI_Assistant_Dental_Clinic/
├── SPEC.md  ARCHITECTURE.md  CLAUDE.md  AGENTS.md  README.md
├── .env.example                      # never commit .env
├── data/
│   ├── price_list/Dental_Price_List_EUR.xlsx (+ .pdf)
│   ├── catalog.json                  # generated from the xlsx (T1.1)
│   ├── catalog_report.md             # data-quality anomalies (T1.2)
│   └── sample_notes/                 # note_XX.txt + note_XX.expected.json
├── docs/brief.png
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                   # FastAPI app, CORS, router include, startup (load catalog, whisper)
│   │   ├── config.py                 # Settings (pydantic-settings, .env)
│   │   ├── store.py                  # JSON-file storage for sessions and plan versions
│   │   ├── api/
│   │   │   ├── sessions.py           # sessions, audio, transcript, plan, revise, confirm, pdf
│   │   │   ├── catalog.py
│   │   │   └── transcribe.py         # generic STT for voice answers
│   │   ├── models/schemas.py         # Pydantic domain models (§6)
│   │   ├── services/
│   │   │   ├── stt.py                # Transcriber interface + WhisperTranscriber
│   │   │   ├── llm.py                # LLMClient interface + OllamaClient (JSON schema, validation retries)
│   │   │   ├── matcher.py            # rapidfuzz + synonyms → top-5 catalog candidates
│   │   │   ├── planner.py            # build / revise orchestration, versioning, diff
│   │   │   ├── catalog.py
│   │   │   ├── pricing.py
│   │   │   └── pdf.py
│   │   ├── prompts/
│   │   │   ├── extract_procedures.md # Step A
│   │   │   ├── map_to_catalog.md     # Step B
│   │   │   └── revise_plan.md
│   │   └── rules/
│   │       ├── clinic_rules.yaml     # default intervals, auto-add rules
│   │       └── synonyms.yaml         # dentist wording → catalog wording
│   ├── scripts/
│   │   ├── build_catalog.py          # xlsx → data/catalog.json
│   │   └── eval_samples.py           # T7.2 (runs the local model; slow, on demand)
│   └── tests/
├── frontend/
│   ├── package.json  vite.config.ts  (proxy /api → :8000)
│   └── src/
│       ├── api/client.ts             # typed fetch wrappers
│       ├── components/  Recorder.tsx  TranscriptEditor.tsx  PlanView.tsx
│       │                PdfViewer.tsx  QuestionsPanel.tsx  VersionDiff.tsx
│       ├── pages/SessionPage.tsx
│       └── types.ts                  # mirrors backend schemas
└── storage/                          # git-ignored: sessions/{id}/session.json, audio/, plans/
```

---

## 5. Backend API

All routes are prefixed with `/api`. JSON unless stated.

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/health` | – | `{status}` |
| GET | `/catalog` | – | items grouped by section |
| GET | `/catalog/search?q=` | – | matching items |
| POST | `/sessions` | `{patient_label?}` | `Session` |
| GET | `/sessions/{id}` | – | `Session` (state, transcript, latest version) |
| POST | `/sessions/{id}/audio` | multipart `file` | `Transcript` |
| PUT | `/sessions/{id}/transcript` | `{text}` | `Transcript` |
| POST | `/sessions/{id}/plan` | – | `TreatmentPlan` (v1) |
| POST | `/sessions/{id}/revise` | `{answers[], corrections?}` | `{plan: TreatmentPlan, diff: PlanDiff}` |
| POST | `/sessions/{id}/confirm` | `{accept_defaults: bool}` | `TreatmentPlan` (FINAL) |
| GET | `/sessions/{id}/plans` | – | list of versions |
| GET | `/sessions/{id}/plans/{n}` | – | `TreatmentPlan` |
| GET | `/sessions/{id}/plans/{n}/pdf` | – | `application/pdf` |
| POST | `/transcribe` | multipart `file` | `Transcript` (used for voice answers) |
| DELETE | `/sessions/{id}` | – | deletes audio, plans, DB rows |

---

## 6. Data model

```python
class CatalogItem:          # one row of the price list
    id: str                 # stable internal key, e.g. "impl-012"   ← ALWAYS use this
    code: str | None        # clinic code, may be missing or duplicated
    section: str            # "Implantology", ...
    name: str
    price_eur: Decimal

class Procedure:            # Step A output: what the dentist said, before catalog mapping
    said: str               # dentist's own words, e.g. "root canal"
    teeth: list[int] = []   # FDI
    quantity: int = 1
    stage_hint: str | None
    interval_hint: str | None

class PlanItemDraft:        # produced by Step B (no prices!)
    catalog_id: str
    quantity: int = 1
    teeth: list[int] = []   # FDI notation (11–48, 51–85)
    note: str | None
    provisional: bool       # default chosen while a question is open
    auto_added: bool        # added by a clinic rule, not dictated

class Interval:
    min_days: int
    max_days: int
    reason: str
    assumed: bool           # True = default from clinic_rules, not dictated

class StageDraft:
    number: int
    title: str
    goal: str
    items: list[PlanItemDraft]
    interval_after: Interval | None

class QuestionOption:
    id: str
    label: str
    catalog_ids: list[str]  # what this option maps to

class ClarifyingQuestion:
    id: str
    text: str
    kind: Literal["choice", "missing_param", "add_on", "unknown_service", "interval"]
    options: list[QuestionOption]
    allow_free_text: bool
    related_stage: int | None
    blocking: bool          # must be answered (or defaults accepted) before confirm

class PlanDraft:            # LLM structured-output schema
    stages: list[StageDraft]
    questions: list[ClarifyingQuestion]
    assumptions: list[str]
    unmapped_mentions: list[str]   # things said that match no catalog item

class TreatmentPlan:        # priced + versioned, built by code
    session_id: str
    version: int
    status: Literal["DRAFT", "FINAL"]
    stages: list[Stage]     # Stage = StageDraft + priced PlanItem(unit_price, line_total) + subtotal
    total_eur: Decimal
    estimated_duration_days: tuple[int, int]
    questions: list[ClarifyingQuestion]
    answers: list[Answer]
    assumptions: list[str]
    created_at: datetime
    pdf_path: str
```

Storage (JSON files, no database):

```
storage/sessions/{session_id}/
├── session.json        # Session: state, patient label, transcript(s), current version
├── audio/{n}.webm      # dictation + voice answers
└── plans/
    ├── v1.json  v1.pdf # TreatmentPlan + rendered PDF, one pair per version
    └── v2.json  v2.pdf
```

---

## 7. LLM design (local, Ollama)

- **Runtime:** Ollama on `OLLAMA_HOST` (default `http://127.0.0.1:11434`), official `ollama` Python package.
- **Target hardware:** AMD Ryzen 5 5500U, 13.8 GB RAM, integrated Radeon (Vega) with no dedicated GPU, so **CPU inference**. Ollama sees the iGPU through Vulkan but skips it unless `OLLAMA_IGPU_ENABLE=1` (optional test, SPEC T0.5).
- **Model:** `LLM_MODEL`, default **`qwen3:4b`** (2.5 GB, good at JSON and English instructions). Measured on the target CPU: ~8.9 tok/s generation, ~35 tok/s prompt reading, so **2–4 min per plan**. **Thinking must be disabled** (`think=False`); with thinking on, qwen3 reasons for minutes. Fallbacks for T7.2: `qwen3:1.7b`, `llama3.2:3b`, `qwen2.5:3b-instruct`. 7B+ models only on a stronger machine.
- **Speed budget on this CPU:** every prompt token costs ~30 ms and every output token ~110 ms. So keep system prompts short, send only the shortlisted candidates (never the whole catalog), keep JSON keys short, and let code do everything deterministic (matching, pricing, applying clicked answers).
- **Abstraction:** `LLMClient.generate_json(system, user, schema)`. `OllamaClient` is the only implementation for now. An OpenAI-compatible local server (LM Studio, llama.cpp, vLLM) can be added as a second implementation later.
- **Why two steps instead of one big prompt:** 7–8B models lose accuracy when asked to read a long transcript *and* choose among 209 items at once. So the work is split:
  1. **Step A – Extract** (`extract_procedures.md`): transcript → `procedures[]` = `{said: "root canal", teeth: [36], quantity, stage_hint, interval_hint, options_mentioned}`. No catalog in the prompt.
  2. **Matcher (code, no LLM):** `matcher.py` turns each procedure into the top 5 catalog candidates (rapidfuzz + `synonyms.yaml` + tooth-type filter from the FDI number). A clear winner is auto-selected.
  3. **Step B – Map** (`map_to_catalog.md`): for the remaining procedures, the LLM picks one candidate id or marks it ambiguous. It also groups items into stages, sets intervals, and writes the questions. Output: `PlanDraft`.
  4. **Revise** (`revise_plan.md`): current plan JSON + free-text corrections → updated `PlanDraft`. Answers given by clicking an option are applied in code, with no LLM call.
- **Constrained output:** `ollama.chat(..., think=False, format=Schema.model_json_schema(), options={"temperature": 0, "num_ctx": LLM_NUM_CTX}, keep_alive="30m")`, then Pydantic validation. If validation fails, retry (max 2) with the error message added to the prompt, then return a clear error.
- **Context window:** always set `num_ctx` (default 8192, which is enough for the two-step prompts and saves RAM on this machine). Ollama's default is much smaller and **silently truncates** long prompts.
- **Prompt style for small models:** short, numbered rules, 1–2 worked examples (few-shot), the output schema described in plain words, and an explicit instruction to write every text field in plain English.
- **Hard rules in the prompts:** only candidate catalog ids; never invent services; never output prices; FDI tooth numbers; ask instead of guessing when price-relevant; keep the dentist's wording in `note`.
- **Post-validation in code** (`pricing.py`): unknown ids → question; impossible teeth → question; empty stages removed.
- **Latency:** about 2–4 min per plan on the target CPU. The backend runs plan building as a background job and the UI polls or streams per-step progress (extract → match → map → PDF). The model is kept loaded (`keep_alive`) to skip the ~6 s load. Log duration and `prompt_eval_count` / `eval_count` per call.
- **Privacy:** fully local, so no transcript, audio or plan leaves the machine. Patient *label* only, no full identity in prompts or logs.

---

## 8. Speech-to-text design

- Interface `Transcriber.transcribe(path: Path, prompt: str | None) -> Transcript(text, segments)`.
- `WhisperTranscriber` (faster-whisper, `compute_type="int8"` on CPU), loaded once at startup.
- `initial_prompt` = dental glossary (brands Osstem, Megagen, Straumann, Nobel, Neodent; zirconia, MTA, endodontic, apexification, sinus lift, All-on-4/6, FDI numbers…).
- Language fixed to English (`language="en"`), which is faster and more accurate than auto-detection.
- Swappable later (e.g. a cloud STT) without touching the planner.

---

## 9. PDF design

ReportLab `SimpleDocTemplate`, A4:
header (clinic, dentist, patient label, date, version, status) → summary box (stages, duration, total) → one table per stage (code · service · teeth · qty · unit · total) + "next stage after …" → timeline → open questions & assumptions (draft only) → footer (price-list disclaimer, page x/y) → signature block (final only). `DRAFT` diagonal watermark on drafts. Currency format `1 234.56 €`.

---

## 10. Cross-cutting concerns

| Concern | Decision |
|---------|----------|
| Secrets | No API keys needed (all local). Config in `.env` (git-ignored), `.env.example` committed |
| Offline | The app must work without internet once models are downloaded (Ollama model + Whisper model) |
| Patient data | `storage/` git-ignored; no patient names in logs; delete-session endpoint |
| Money | `Decimal` everywhere, round half-up at 2 decimals, never floats |
| Errors | FastAPI exception handlers → `{error_code, message}`; UI shows message |
| Config | Everything tunable in `.env` or `clinic_rules.yaml`, not in code |
| Windows | Use `.venv/python.exe`; paths via `pathlib`; no shell-specific scripts required |

---

## 11. Decision log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-11-16 | LLM picks catalog ids, code computes prices | Prices must be exact and auditable |
| 2026-11-16 | Local faster-whisper for STT | Privacy of patient audio, no extra API |
| 2026-11-16 | ReportLab instead of WeasyPrint | Windows compatibility |
| 2026-11-16 | Fixed workflow (extract → match → map → revise), no agent loop | Predictable, easy to test |
| 2026-11-16 | Internal catalog `id` instead of clinic code | Codes are missing/duplicated in the price list |
| 2026-11-16 | **Local LLM (Ollama) instead of a cloud LLM API** | Project requirement: everything local, private, no API cost |
| 2026-11-16 | Two-step LLM + fuzzy matcher instead of full catalog in one prompt | Small local models are less accurate with 209 options and long prompts |
| 2026-11-16 | JSON files instead of SQLite | Simpler; one clinic, few sessions; files are easy to inspect |
| 2026-11-16 | English only (STT `language="en"`, prompts, UI, PDF) | Project requirement; faster and more accurate STT |
| 2026-11-16 | Default intervals in `clinic_rules.yaml` shown as assumptions until a dentist validates them | They are clinical judgements written by developers |
| 2026-11-16 | Default model `qwen3:4b`, thinking off, CPU | Target is a Ryzen 5 5500U with 14 GB RAM and only an iGPU; measured 8.9 tok/s, output correct |
