# CLAUDE.md

Instructions for Claude Code working in this repository. (Other agents such as Codex, Cursor, Copilot and Gemini: see [AGENTS.md](AGENTS.md), which has the same rules.)

## Project

AI assistant for a dental clinic, **running fully locally** (no cloud AI): the dentist **dictates** treatment → we **transcribe** (faster-whisper) → a **local LLM** (Ollama) builds a **treatment plan** (stages, intervals, prices from the clinic price list) → **PDF** → assistant **asks clarifying questions** → dentist answers/corrects → **PDF regenerated** → dentist **confirms**.

- [SPEC.md](SPEC.md): what to build, task list, **status tracker**. Read it first, every session.
- [ARCHITECTURE.md](ARCHITECTURE.md): how it is built (layout, API, data model, LLM design).

## Workflow rules

1. **Work task by task from SPEC.md.** Task numbers are the build order. Pick the first required task that is not `✅` or `⛔`, unless the user names one. Skip tasks marked *(optional)* until the required tasks of that phase are done. Don't start the next task without telling the user.
2. **Update SPEC.md in the same change that completes a task:** set the status (`⬜ → 🟡 → ✅`, with the date), update the phase table and the "Next task" line, and add a change-log row. Use `⛔` + the reason when blocked.
3. A task is `✅` only when its **"Done when"** check has actually been run and passed. Say how you checked it.
4. If you change a design decision, update ARCHITECTURE.md (and its decision log).
5. Commit only when the user asks. Use one commit per task, with the message `T<id>: <summary>`.

## Non-negotiable domain rules

- **Prices come only from the catalog** (`data/catalog.json`, built from the xlsx). The LLM never outputs prices or totals; `services/pricing.py` computes them with `Decimal`.
- Plan items reference **`catalog_id`** (internal stable id), never the clinic `code`. Codes are missing or duplicated in the source.
- The assistant **never invents treatments**. Anything not dictated is either a clarifying question, a clearly marked `auto_added` item from `clinic_rules.yaml`, or an `assumption`.
- When a choice changes the price (implant brand, crown type, surfaces, wisdom-tooth grade…), **ask**. Use a provisional default so a PDF is always produced.
- Tooth numbers use **FDI** notation.
- **English only:** dictation (Whisper `language="en"`), prompts, questions, UI and PDF.
- Storage is **JSON files** in `storage/sessions/{id}/`. There is no database.
- Draft PDFs carry a `DRAFT` watermark; only a confirmed plan is `FINAL`.

## Privacy & secrets

- Never commit `.env`, `storage/`, audio files, or real patient data. Sample notes in `data/sample_notes/` are fine.
- No patient names in logs.
- The public link (`https://cuspia.dmb-site.site`) requires user accounts (`AUTH_REQUIRED=true`). Never start the tunnel with accounts off, never store a password in clear, never bind the app to `0.0.0.0`, and use synthetic notes only.
- **Never add a call to a cloud AI/LLM/STT service** (OpenAI, Anthropic, Google, …) to the app. Everything must work offline once the models are downloaded.

## Commands (Windows; Python is a conda env in `.venv/`)

```bash
# backend
.venv/python.exe -m pip install -r backend/requirements.txt
.venv/python.exe -m uvicorn app.main:app --reload --app-dir backend     # http://localhost:8000/docs
.venv/python.exe -m pytest backend/tests                                  # must pass offline (LLM mocked)
.venv/python.exe -m ruff check backend && .venv/python.exe -m ruff format backend
.venv/python.exe backend/scripts/build_catalog.py                         # xlsx → data/catalog.json
.venv/python.exe backend/scripts/eval_samples.py --model qwen3:4b      # local model, slow: run on demand

# local LLM (Ollama v0.40+ installed; `qwen3:4b` already pulled)
ollama pull qwen3:4b
ollama list                                                               # check the model is present

# frontend
cd frontend && npm install && npm run dev                                 # http://localhost:5173 (proxies /api)
```

## Code conventions

- Python: type hints everywhere, Pydantic v2 models in `app/models/schemas.py`, `pathlib` for paths, services have no FastAPI imports (testable on their own), and routes stay thin.
- Prompts live in `backend/app/prompts/*.md`, not in Python strings. Clinic rules live in `backend/app/rules/clinic_rules.yaml`, synonyms in `backend/app/rules/synonyms.yaml`.
- **The interface never mentions the AI model, Ollama, Whisper or local processing**, including in error messages. Technical details go to the server log.
- Frontend: function components + hooks, typed API client in `src/api/client.ts`, types in `src/types.ts` mirroring the backend schemas.
- Tests: unit tests mock the LLM and the transcriber. Every pricing or catalog change needs a test.

## Local LLM usage (in `backend/app/services/llm.py`)

- Runtime: **Ollama** through the official `ollama` Python package, behind the `LLMClient` interface (`generate_json(system, user, schema)`). Default model **`qwen3:4b`**, configurable through `LLM_MODEL`.
- Hardware is a **Ryzen 5 5500U CPU, 14 GB RAM, integrated Radeon only**: ~9 tok/s generation, about 20–50 s per plan. Every prompt and output token counts: keep prompts short and push deterministic work into code.
- Always pass **`think=False`** (qwen3 otherwise reasons for minutes), `format=<Pydantic>.model_json_schema()`, `temperature=0`, and an **explicit `num_ctx`** (default 8192) (Ollama's default context silently truncates long prompts). Validate with Pydantic and retry up to 2 times with the error added to the prompt.
- Small models need help. Keep the pipeline **extract → match (code) → map → revise** (ARCHITECTURE §7). Don't put the full 208-item catalog in one prompt. Keep prompts short, with few-shot examples.
- Unit tests must mock `LLMClient`; they must not need Ollama running.
- Model comparisons (T7.2) are slow. Run them only when asked.

## Gotchas

- Read the price list from the **xlsx**. The PDF truncates long names.
- The same service name can appear in several sections with different prices ("Local anaesthesia", "Single-use hygiene kit", …). Pick by section context.
- The path contains spaces (`Master2  Info`, two spaces), so always quote paths.
- `Dental_Price_List_EUR.xlsx` holds the price list only (1 sheet, 208 services, 8 sections). The instructor's sample notes were never received, so we use **synthetic practice notes** (SPEC T0.2) in `data/sample_notes/`. Each one must start with `SYNTHETIC PRACTICE NOTE`. Never present them as real instructor or patient data.
- This machine's `HF_HOME` points to a missing `E:\` drive, so `stt.py` keeps Whisper files in `storage/models/`. PyAV is pinned below 16 because newer versions break faster-whisper 1.2.1.
- Procedure families, question wording and diagnosis terms live in `backend/app/rules/families.yaml`.
- Default intervals in `clinic_rules.yaml` are developer-written clinical assumptions. Show them as assumptions until `validated_by` is filled in by a dentist.
