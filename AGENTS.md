# AGENTS.md

Instructions for AI coding agents (OpenAI Codex, Cursor, GitHub Copilot agent, Gemini CLI, Jules, Aider, …) working in this repository.
Claude Code reads [CLAUDE.md](CLAUDE.md), which has the same rules. **If you change a rule here, change it there too.**

## Read first

1. [SPEC.md](SPEC.md): the task list and **status tracker** (source of truth for progress).
2. [ARCHITECTURE.md](ARCHITECTURE.md): layout, API, data model, LLM/STT/PDF design.

## Project in one paragraph

**Everything runs locally; no cloud AI service.** A dentist dictates treatment by voice. The backend transcribes it with local faster-whisper. A **local LLM served by Ollama** (default `qwen3:4b` with thinking off, JSON-schema output, CPU-only target machine: Ryzen 5 5500U, 14 GB RAM, ~9 tok/s) extracts the procedures. A fuzzy matcher shortlists catalog candidates, and the LLM maps them to **catalog items** grouped into **stages with intervals**. The plan is priced **in code** from the clinic price list, renders a **PDF** (ReportLab), asks **clarifying questions**, applies the answers/corrections, regenerates the PDF, and produces a **final confirmed** version. Stack: Python 3.12 + FastAPI backend, React + TypeScript + Vite frontend.

## How to work

- Do **one SPEC task at a time**, in numeric order (numbers are the build order), unless told otherwise. Tasks marked *(optional)* come after the required tasks of their phase.
- When a task's "Done when" check passes, set it to `✅ Done (YYYY-MM-DD)` in SPEC.md, update the phase table, the "Next task" line and the change log, **in the same commit**. Use `🟡` while working and `⛔ + reason` when blocked.
- Never mark a task done without running its check.
- Design changes go in ARCHITECTURE.md (with a decision-log line).
- Commit message format: `T<id>: <summary>`. Don't push or open PRs unless asked.

## Hard rules

- Prices and totals are computed **only** by `backend/app/services/pricing.py` from `data/catalog.json`, using `Decimal`. The LLM never produces prices.
- Plan items reference the internal `catalog_id`, not the clinic code (codes are missing or duplicated).
- Never invent treatments. Unclear or price-relevant choices become **clarifying questions** with a provisional default.
- FDI tooth numbering. `DRAFT` watermark on drafts, `FINAL` only after confirmation.
- Never commit `.env`, `storage/`, audio, or real patient data. No patient names in logs.
- **English only** (Whisper `language="en"`, prompts, questions, UI, PDF). Storage is JSON files in `storage/sessions/{id}/`, with no database.
- Test notes in `data/sample_notes/` are **synthetic practice notes** (SPEC T0.2) and must stay labelled `SYNTHETIC PRACTICE NOTE`. Never present them as real instructor or patient data.
- Procedure families, question wording and diagnosis terms live in `backend/app/rules/families.yaml`. Whisper files stay in `storage/models/`; PyAV is pinned below 16.
- Default intervals in `clinic_rules.yaml` are shown as assumptions until a dentist fills in `validated_by`.
- The public link (`https://cuspia.dmb-site.site`) requires user accounts (`AUTH_REQUIRED=true`). Never start the tunnel with accounts off, never store a password in clear, never bind the app to `0.0.0.0`, and use synthetic notes only.
- **Local only:** never add calls to cloud AI/LLM/STT services (OpenAI, Anthropic, Google, …). The LLM goes through the `LLMClient` interface (`backend/app/services/llm.py`), implemented with the `ollama` Python package.
- Ollama calls always set `think=False`, `format=<schema>`, `temperature=0` and an explicit `num_ctx` (8192) (the default context silently truncates). Validate the output with Pydantic and retry on failure.
- Keep the pipeline extract → match (code) → map → revise. Don't send the whole 208-item catalog to the model in one prompt.
- Unit tests mock the LLM and STT and must pass without Ollama running. `backend/scripts/eval_samples.py` is slow: run it only when asked.

## Setup & commands (Windows, conda env in `.venv/`)

```bash
.venv/python.exe -m pip install -r backend/requirements.txt
cp .env.example .env            # no API keys; set LLM_MODEL / OLLAMA_HOST if needed
ollama pull qwen3:4b            # Ollama for Windows must be installed and running
.venv/python.exe -m uvicorn app.main:app --reload --app-dir backend
.venv/python.exe -m pytest backend/tests          # offline; LLM + STT mocked, Ollama not needed
.venv/python.exe -m ruff check backend
cd frontend && npm install && npm run dev
```

The repo path contains spaces, so quote it.

## Conventions

- Python: type hints, Pydantic v2, `pathlib`, services free of FastAPI imports, thin routes, prompts in `backend/app/prompts/*.md`, clinic rules in `backend/app/rules/clinic_rules.yaml`.
- **The interface never mentions the AI model, Ollama, Whisper or local processing**, including in error messages. Technical details go to the server log.
- TypeScript: function components + hooks, API client in `frontend/src/api/client.ts`, shared types in `frontend/src/types.ts`.
- Add or adjust tests with every change to catalog parsing, pricing, or plan revision.
