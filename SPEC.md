# SPEC — AI Assistant for a Dental Clinic

> **Living document.** This is the single source of truth for *what* we build and *how far along we are*.
> Every agent (Claude, Codex, …) and every human **must update the status of a task in this file in the same commit that completes it.**

- **Created:** 2026-11-16
- **Stack:** Python 3.12 (FastAPI backend) · React + TypeScript + Vite (frontend) · **local LLM via Ollama** (plan reasoning) · faster-whisper (speech-to-text, local) · ReportLab (PDF) · JSON files for storage
- **Fully local:** no cloud AI service is used. Audio, transcripts and plans never leave the clinic machine.
- **Language: English everywhere.** The dictation, transcript, LLM prompts, clarifying questions, UI and PDF are all in English.
- **Related docs:** [ARCHITECTURE.md](ARCHITECTURE.md) (how it is built) · [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) (rules for AI agents)

---

## 1. Goal

The dentist **dictates** the work to be done for a patient. The assistant:

1. **Understands the voice** (speech → text).
2. **Builds a treatment plan**: stages, intervals between stages, and prices taken from the clinic price list.
3. **Generates a PDF** treatment plan and returns it to the dentist.
4. **Asks clarifying questions** where the dictation leaves options open (e.g. implant brand, crown type, number of surfaces, wisdom-tooth grade).
5. **Regenerates the PDF** with the answers and any corrections, until the dentist **confirms** the final version.

### Acceptance criteria (from the challenge brief)

| # | Criterion | Covered by tasks | Status |
|---|-----------|------------------|--------|
| AC1 | Understands voice | T2.1 – T2.4 | ✅ |
| AC2 | Generates a PDF | T3.1 – T3.6, T4.1 – T4.3 | ✅ |
| AC3 | Asks clarifying questions | T5.1 – T5.2 | ✅ |
| AC4 | Regenerates the PDF (with answers + corrections, then confirmation) | T6.1, T6.3 | ✅ |

### Inputs

| Input | Location | Status |
|-------|----------|--------|
| Clinic price list (EUR) | `Dental_Price_List_EUR.xlsx` / `.pdf` (repo root → moved to `data/price_list/` in T0.3). 1 sheet, columns Service/Code/Price, 8 sections, 208 services | ✅ received |
| Sample dentist notes | Not received from the instructor. **Decision (2026-11-16): work with what we have.** We write our own *synthetic practice notes* (T0.2) and replace or extend them if real notes arrive | ✅ 4 synthetic notes written (T0.2) |
| Challenge brief screenshot | `Screenshot 2026-11-16 at 3.53.44 PM.png` | ✅ received |

### Out of scope

- Making clinical decisions. The assistant **structures what the dentist says**; it never invents treatments.
- Patient accounts, billing/payment, insurance, calendar booking.
- Languages other than English.
- Multi-user authentication (stretch goal only, T8.1).

---

## 2. Status legend & progress tracker

`⬜ Todo` · `🟡 In progress` · `✅ Done` · `⛔ Blocked` (write the reason next to it)
Tasks marked **(optional)** are nice-to-have: do them only after all required tasks of the same phase are done.

| Phase | Name | Tasks (required + optional) | Done | Status |
|-------|------|-----------------------------|------|--------|
| 0 | Project setup | 6 | 5 (T0.3 waits for a commit) | 🟡 |
| 1 | Price catalog | 2 + 1 optional | 3 | ✅ |
| 2 | Voice input (speech-to-text) | 4 | 4 | ✅ |
| 3 | Treatment-plan builder (rules + matching + pricing + local LLM) | 6 | 6 | ✅ |
| 4 | PDF generation | 3 | 3 | ✅ |
| 5 | Clarifying questions | 2 + 1 optional | 3 | ✅ |
| 6 | Revision, regeneration & confirmation | 2 + 1 optional | 3 | ✅ |
| 7 | Quality, tests & demo | 4 | 3 (T7.4 needs a classmate) | 🟡 |
| 8 | Stretch goals | 4 optional | 0 | ⬜ not started |

### Remaining actions (status checked 2026-11-23)

| # | Action | Who | How | Done when | Closes | Status |
|---|--------|-----|-----|-----------|--------|--------|
| A1 | Commit the work | Project owner, or an agent when asked | Review `git status`, then commit. `storage/`, `.env` and `node_modules/` are already ignored | `git status` is clean and the last commit contains `backend/`, `frontend/` and `data/` | T0.3 | ⬜ Not done: all work since `4655dc7` is uncommitted |
| A2 | Test with a real voice | Project owner | Start the app, click **Start dictation**, read `data/sample_notes/note_01.txt` aloud (without its first line), then build the plan | Brands, tooth numbers and procedure names are transcribed correctly, or corrected in the text box, and the total is **975.76 €** | Open item in §4 | ⬜ Not done: only Windows TTS with a simulated microphone was tested |
| A3 | Have a classmate follow the README | A classmate | Follow [README.md](README.md) on another computer, without help, through the 3-minute demo. Record any blocked step here | The app runs and the demo reaches the final PDF | T7.4 | ⬜ Not done |

Also needed before any use on real patients: a dentist reviews `backend/app/rules/clinic_rules.yaml` and fills in `validated_by` and `validated_on`. Phase 8 is optional.

---

## 3. Tasks, one by one

Each task has: **Goal**, **Steps**, **Done when** (acceptance test), **Status**.
**Tasks are numbered in the order they must be done.** A task only depends on tasks with a lower number, unless it says it can run in parallel.

---

### Phase 0 — Project setup

#### T0.1 Planning documents — ✅ Done (2026-11-16)
- **Goal:** Write `SPEC.md`, `ARCHITECTURE.md`, `CLAUDE.md`, `AGENTS.md`.
- **Done when:** The four files exist at the repo root and are committed.

#### T0.2 Synthetic practice notes — ✅ Done (2026-11-23)
- **Goal:** Have realistic test dictations now, without waiting for the instructor's samples.
- **Steps:**
  1. Write 4 English dictations in a dentist's spoken style, each using real services from the price list, saved as `data/sample_notes/note_01.txt` … `note_04.txt`. Start every file with the line `SYNTHETIC PRACTICE NOTE – not from the instructor`. Cover:
     - **note_01 – implant case:** extraction + socket preservation, implant later, crown on implant, **brand not specified** (to trigger a question).
     - **note_02 – endodontics + restorations:** root canal on a molar, core build-up, fillings on anterior teeth with **number of surfaces missing** for one of them.
     - **note_03 – periodontics:** periodontal charting, scaling and root planing per jaw, follow-up examination after 3–6 months.
     - **note_04 – mixed / surgery:** wisdom tooth extraction (**grade not specified**), sedation, fluoride varnish.
  2. For each note, write the expected plan by hand in `data/sample_notes/note_XX.expected.json` (stages, catalog item names, teeth, quantities, the questions expected, total for the provisional defaults). The catalog ids are filled in after T1.1.
  3. Optional: record yourself reading 1–2 notes → `data/sample_notes/note_XX.webm` to test speech-to-text (T2.3).
  4. If the instructor's real notes arrive later, add them as `note_1X.txt` and keep the synthetic ones.
- **Done when:** 4 notes and 4 expected plans exist in `data/sample_notes/`, each note clearly labelled synthetic.

#### T0.3 Repository skeleton — 🟡 Tree done; the "clean after commit" check waits for your commit
- **Steps:**
  1. Create the folders described in [ARCHITECTURE.md §4](ARCHITECTURE.md#4-repository-layout): `backend/`, `frontend/`, `data/`, `docs/`, `storage/` (git-ignored).
  2. Move `Dental_Price_List_EUR.xlsx` and `.pdf` to `data/price_list/` with `git mv`.
  3. Move the screenshot to `docs/brief.png`.
  4. Add `storage/` to `.gitignore`. Check `.env` is already ignored (it is).
- **Done when:** The tree matches ARCHITECTURE §4 and `git status` is clean after the commit.

#### T0.4 Backend scaffold & configuration — ✅ Done (2026-11-23)
- **Steps:**
  1. `backend/requirements.txt`: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`, `python-multipart`, `ollama`, `rapidfuzz`, `faster-whisper`, `openpyxl`, `reportlab`, `pyyaml`, `pytest`, `httpx`, `ruff`.
  2. Install into the existing conda env: `.venv/python.exe -m pip install -r backend/requirements.txt`.
  3. `backend/app/config.py` with `Settings` (pydantic-settings), read from `.env`: `OLLAMA_HOST` (default `http://127.0.0.1:11434`), `LLM_MODEL` (default `qwen3:4b`), `LLM_THINK` (default `false`), `LLM_NUM_CTX` (default `8192`), `LLM_TEMPERATURE` (default `0`), `LLM_TIMEOUT_S` (default `300`), `WHISPER_MODEL` (default `small`), `WHISPER_DEVICE` (`cpu`), `STORAGE_DIR`, `CLINIC_NAME`, `CLINIC_ADDRESS`, `DENTIST_NAME`. No API keys.
  4. `.env.example` committed (no secrets).
  5. `backend/app/main.py`: FastAPI app, CORS for `http://localhost:5173`, `GET /api/health`.
- **Done when:** `.venv/python.exe -m uvicorn app.main:app --reload --app-dir backend` starts and `GET /api/health` returns `{"status":"ok"}`.

#### T0.5 Local LLM runtime (Ollama) — ✅ Done (2026-11-23; optional step 5 not done)
- **Machine (recorded 2026-11-16):** AMD Ryzen 5 5500U (6 cores / 12 threads), 13.8 GB RAM, integrated AMD Radeon (Vega, 2 GB shared memory). No dedicated GPU, so inference runs on the CPU.
- **Steps:**
  1. ✅ Ollama for Windows installed (v0.40.15, an update to 0.40.16 is pending).
  2. ✅ Model `qwen3:4b` (2.5 GB) pulled. It is the **default** model.
  3. ✅ Benchmark via the API (`think=false`, `format=json`, `temperature=0`): procedure extraction from a 1-sentence dictation was **correct**. Load 5.6 s, prompt ~35 tok/s, generation ~8.9 tok/s.
     - ⚠️ qwen3 "thinking" mode must be **off** (`think=False` in the API). With thinking on, the model loops for minutes. The CLI flag `--think=false` did not prevent it in our test, so always use the API parameter.
  4. ✅ `GET /api/health` also reports whether Ollama is reachable and the configured model is pulled (`ollama.list()`).
  5. ⬜ *(optional)* Ollama detects the Radeon iGPU through Vulkan but ignores it by default. Set the user environment variable `OLLAMA_IGPU_ENABLE=1`, restart Ollama, re-run the benchmark, and keep it only if it is faster and stable.
  - Alternative models for T7.2: `qwen3:1.7b`, `llama3.2:3b`, `qwen2.5:3b-instruct`.
- **Done when:** the benchmark answers correctly (✅) and `/api/health` shows `llm: ok` (✅).

#### T0.6 Frontend scaffold — ✅ Done (2026-11-23)
- **Steps:**
  1. `npm create vite@latest frontend -- --template react-ts`.
  2. Add Tailwind CSS (or plain CSS modules, keep it simple).
  3. Vite dev-server proxy: `/api` → `http://localhost:8000`.
  4. Empty layout: header (clinic name), left column "Dictation", right column "Plan / PDF".
- **Done when:** `npm run dev` shows the layout and a health-check badge calling `/api/health` is green.

---

### Phase 1 — Price catalog

#### T1.1 Parse the price list into a catalog — ✅ Done (2026-11-23)
- **Goal:** Turn `Dental_Price_List_EUR.xlsx` into a clean, machine-usable catalog.
- **Steps:**
  1. `backend/app/services/catalog.py`: read the xlsx with `openpyxl` (use the **xlsx**, not the PDF; the PDF cuts off long names).
  2. Detect **section header rows** (rows with a name but no price: "Restorative dentistry (treatment)", "Periodontics", "Endodontics", "Surgery", "Surgery (Dr. R.A.)", "Implantology", "Implant prosthetics", "Sedation with anaesthesiologist – adults").
  3. For each service row build a `CatalogItem`: `id` (stable slug, e.g. `endo-018`, section prefix + row index), `code` (may be `None`), `section`, `name`, `price_eur` (Decimal).
  4. `backend/scripts/build_catalog.py` writes `data/catalog.json` (generated, committed so it can be reviewed).
  5. Fill in the catalog ids in the `data/sample_notes/*.expected.json` files from T0.2.
- **Done when:** A unit test loads the catalog and checks: exactly 208 items in 8 sections (sheet "Price list (EUR)", range A1:C217); "Root canal treatment — molars" = 89.60 €; "Osstem implant placement (Korea)" exists in Implantology; every item has a section and a price > 0.

#### T1.2 Data quality handling — ✅ Done (2026-11-23)
- **Known issues in the source file** (handle them, do not silently "fix" prices):
  - Many rows have **no code**, so the internal `id` is the key, never the code.
  - **Duplicate codes** with different prices (e.g. `6.22` → 51.37 and 50.97).
  - Codes with odd format (`5.8` without trailing dot, `6.22` without dot).
  - **Same service name in several sections** with possibly different prices ("Local anaesthesia", "Single-use hygiene kit", "Additional local anaesthetic cartridge", "Root canal disobturation", "Temporary crown on implant"…).
  - Near-duplicates ("Restoration of a molar, 1 surface" vs "Restoration of a single-surface molar").
- **Steps:**
  1. Normalize codes (strip, trailing dot) and keep duplicates as separate items.
  2. *(optional)* Generate `data/catalog_report.md` listing every anomaly.
- **Done when:** Tests cover the duplicate-code and same-name-different-section cases.

#### T1.3 Catalog API — ✅ Done (2026-11-23) (optional)
- **Steps:** `GET /api/catalog` (full list, grouped by section) and `GET /api/catalog/search?q=` (fuzzy match with `rapidfuzz`).
- **Done when:** `GET /api/catalog/search?q=straumann` returns the Straumann items.

---

### Phase 2 — Voice input (AC1)

#### T2.1 Browser audio recorder — ✅ Done (2026-11-23)
- **Steps:**
  1. React component `<Recorder>` using `navigator.mediaDevices.getUserMedia` + `MediaRecorder` (`audio/webm;codecs=opus`).
  2. Big Record / Stop button, timer, level indicator, "re-record".
  3. Show an error message if microphone permission is denied.
- **Done when:** You can record and play back a 30 s clip in the browser.

#### T2.2 Audio upload endpoint — ✅ Done (2026-11-23)
- **Steps:**
  1. `POST /api/sessions`: create a session (patient label optional) → `{session_id}`. The session is saved as `storage/sessions/{session_id}/session.json`.
  2. `POST /api/sessions/{id}/audio` (multipart): save to `storage/sessions/{session_id}/audio/{n}.webm`, call STT (T2.3), store the transcript in the session, return it.
  3. Limit size (e.g. 25 MB) and duration (e.g. 10 min).
- **Done when:** Uploading a clip returns a transcript JSON `{text, segments}`.

#### T2.3 Speech-to-text service — ✅ Done (2026-11-23)
- **Steps:**
  1. `backend/app/services/stt.py` behind an interface `Transcriber.transcribe(path) -> Transcript`.
  2. Default implementation: **faster-whisper** (local, so patient audio never leaves the machine), CPU with `compute_type="int8"`, model from config (`small`; `base` if `small` is too slow), stored in `storage/models/`.
  3. Language fixed to **English** (`language="en"`). This is faster and more accurate than auto-detection.
  4. Pass an `initial_prompt` with dental vocabulary (implant brands Osstem/Megagen/Straumann/Nobel/Neodent, "zirconia", "MTA", "endodontic", "scaling and root planing", FDI tooth numbers…) to improve recognition.
  5. Load the model once at startup (lazy singleton), not per request.
- **Done when:** A recording of a T0.2 note is transcribed with the key terms correct (brands, tooth numbers, procedure names).

#### T2.4 Editable transcript & text fallback — ✅ Done (2026-11-23)
- **Steps:** Show the transcript in an editable textarea; the dentist can fix words before building the plan. Also allow **typing/pasting** notes directly (needed to test with the T0.2 text notes). `PUT /api/sessions/{id}/transcript`.
- **Done when:** A pasted practice note can go through the whole pipeline without audio.

---

### Phase 3 — Treatment-plan builder

Order inside this phase: the deterministic parts are built first (schemas → rules → matcher → pricing), then the LLM parts (prompts → client and `build_plan`).

#### T3.1 Domain schemas — ✅ Done (2026-11-23)
- **Steps:** Pydantic models in `backend/app/models/schemas.py` (see [ARCHITECTURE.md §6](ARCHITECTURE.md#6-data-model)): `CatalogItem`, `Procedure` (Step A output), `PlanItem`, `Stage`, `Interval`, `ClarifyingQuestion`, `PlanDraft` (Step B output), `TreatmentPlan` (priced, versioned), `Session`.
- **Done when:** Models exist, have docstrings, and round-trip to JSON in a test.

#### T3.2 Clinic rules, default intervals & synonyms — ✅ Done (2026-11-23)
- **Steps:**
  1. `backend/app/rules/clinic_rules.yaml`, editable without code:
     - Default intervals between stages, e.g. extraction → implant: 3–4 months (or immediate if dictated); implant → crown: 3–6 months (osseointegration); root canal → crown: 1–2 weeks; sinus lift → implant: 6–9 months; scaling → periodontal re-evaluation: 3–6 months (matches the catalog item "Periodontal follow-up examination… 3–6 months after treatment").
     - Optional auto-add rules (off by default), e.g. "local anaesthesia per surgical session".
     - ⚠️ **These default intervals are clinical assumptions written by the developers.** The file starts with a `validated_by:` / `validated_on:` header that stays empty until a dentist (or the instructor) has reviewed it. Until then, every default interval is shown in the plan and PDF as an **assumption to confirm**.
  2. `backend/app/rules/synonyms.yaml`: dentist wording → catalog wording (e.g. "RCT" / "root canal" / "endo" → root canal treatment; "filling" → restoration; "cleaning" → professional hygiene; "Korean implant" → Osstem/Megagen; "crown on implant" → zirconia crown on implant).
- **Done when:** Both files load in a test, and the `validated_by` field is reported by `/api/health` (`rules_validated: false` until reviewed).

#### T3.3 Catalog matcher (candidate shortlist) — ✅ Done (2026-11-23)
- **Goal:** Shrink the choice for the local LLM from 208 items to about 5 candidates per procedure.
- **Steps:**
  1. `backend/app/services/matcher.py`: for each procedure, score every catalog item with `rapidfuzz` (token-set ratio on the normalized name), after expanding the dentist's words with `synonyms.yaml` (T3.2).
  2. Use context to filter: tooth type from the FDI number (incisor/canine → "anterior"/"incisors and canines", premolar, molar) and the section hint.
  3. Return the top 5 candidates with scores. If the best score is high and clearly ahead, auto-select it. Otherwise the candidates go to the LLM (Step B, T3.6). If several candidates differ in price, raise a clarifying question.
- **Done when:** Unit tests map at least 15 typical phrases (e.g. "root canal on 36" → *Root canal treatment — molars*; "two-surface filling on 21" → *Two-surface restoration of an anterior tooth*) to the right catalog item, with no LLM call.

#### T3.4 Validation & pricing engine — ✅ Done (2026-11-23)
- **Steps:** `backend/app/services/pricing.py`:
  1. Reject/flag any `catalog_id` not in the catalog (turn it into a question instead of crashing).
  2. `unit_price` comes **only** from the catalog; `line_total = unit_price × quantity`; stage subtotal; grand total. Use `Decimal`, round half-up to 2 decimals.
  3. Sanity checks: tooth numbers valid FDI (11–48, 51–85), quantity ≥ 1, no stage without items.
- **Done when:** Unit tests prove totals are exact (on a hand-built `PlanDraft`) and an unknown id produces a question, not a price.

#### T3.5 Prompt design — ✅ Done (2026-11-23)
- **Context:** small local models do worse with 208 catalog lines in the prompt, so plan building uses **two LLM steps** (see ARCHITECTURE §7):
  - **Step A – Extract:** transcript → list of dictated procedures in the dentist's own words, plus teeth, quantity, stage hints and intervals. No catalog yet.
  - **Step B – Map:** for each procedure, the matcher (T3.3) shortlists the top 5 catalog candidates. The LLM picks one, or flags the item as ambiguous so it becomes a question. It also groups items into stages and writes the questions.
- **Steps:** Write `backend/app/prompts/extract_procedures.md`, `map_to_catalog.md`, `revise_plan.md`, in English. Keep prompts short and explicit, with 1–2 worked examples (few-shot): small models follow examples better than long rules. The prompts must:
  1. Allow only catalog ids from the **candidate list given in the prompt** (Step B).
  2. Require every plan item to reference a `catalog_id`, with `quantity` and `teeth` (FDI notation).
  3. Group work into **stages** in clinically logical order (e.g. hygiene/periodontics, then endodontics/restorations, then surgery/extractions, then implants, then prosthetics), each with a short goal.
  4. Give **intervals** between stages (min/max days or weeks + reason), using what the dentist said, otherwise a default from `clinic_rules.yaml` (T3.2) flagged as an assumption.
  5. **Never invent** a treatment that was not dictated. Consumables (hygiene kit, anaesthesia) are added only if the dentist says so or if a clinic rule says so (T3.2), and then marked `auto_added`.
  6. Produce **clarifying questions** whenever a choice changes the price or the plan (see T5.1), with 2–5 options, each option mapped to catalog ids.
  7. Never output prices or totals; the backend computes them.
  8. Write all text (stage titles, goals, questions) in plain English.
- **Done when:** The prompts are reviewed and stored as files (not hard-coded strings).

#### T3.6 Local LLM client & plan builder — ✅ Done (2026-11-23)
- **Steps:**
  1. `backend/app/services/llm.py`: an `LLMClient` interface with one method, `generate_json(system, user, schema: type[BaseModel]) -> BaseModel`. The default implementation is `OllamaClient`, using the official `ollama` Python package, with `think=False` (qwen3).
  2. **Constrained JSON output:** pass `format=Schema.model_json_schema()` to `ollama.chat` so the output follows the schema. Then validate with Pydantic. If validation fails, retry up to 2 times with the validation error added to the prompt.
  3. Options: `temperature=0` (deterministic), `num_ctx` from config. **Ollama's default context window is small and silently truncates long prompts**, so always set `num_ctx` explicitly.
  4. Timeout and clear errors: "Ollama not running", "model not pulled (`ollama pull …`)", "timeout".
  5. Keep the model loaded between calls (`keep_alive`, e.g. `30m`) to avoid reload delay.
  6. Log duration and prompt/response token counts (`prompt_eval_count`, `eval_count`) per call.
  7. Provider-agnostic: an OpenAI-compatible local server (LM Studio, llama.cpp server, vLLM) can be added later as a second `LLMClient` implementation without touching the planner.
  8. `backend/app/services/planner.py` → `build_plan(transcript)`: Step A (LLM) → matcher (T3.3) → Step B (LLM) → pricing (T3.4) → `TreatmentPlan` v1.
  9. Report progress per step (extract / match / map / price) so the UI can show it.
- **Done when:** `build_plan()` on each T0.2 note returns a valid, priced `TreatmentPlan` with the local model, and a unit test runs `build_plan()` with a mocked `LLMClient`.

---

### Phase 4 — PDF generation (AC2)

#### T4.1 PDF template — ✅ Done (2026-11-23)
- **Steps:** `backend/app/services/pdf.py` with **ReportLab** (pure Python, works on Windows without GTK). All text in English. Content:
  1. Header: clinic name/address, dentist, patient label, date, **plan version**, status badge (`DRAFT – pending answers` / `FINAL – confirmed`).
  2. Summary: number of stages, estimated total duration, **grand total (EUR)**.
  3. One table per stage: code, service, teeth, qty, unit price, line total; stage subtotal; "Next stage after: X–Y weeks (reason)".
  4. Timeline (simple horizontal bar or list).
  5. "Open questions" box (draft only) and "Assumptions" box (including unvalidated default intervals, see T3.2).
  6. Footer: "Estimate based on the clinic price list; prices in EUR", page numbers, signature lines (dentist / patient) on the final version.
  7. Diagonal `DRAFT` watermark on non-final versions.
- **Done when:** A plan built from a T0.2 note renders into a readable 1–3 page PDF; totals in the PDF equal the pricing-engine totals.

#### T4.2 Versioned storage & download — ✅ Done (2026-11-23)
- **Steps:** Save each version as `storage/sessions/{session_id}/plans/v{n}.json` + `v{n}.pdf`. Endpoints: `GET /api/sessions/{id}/plans` (list versions), `GET /api/sessions/{id}/plans/{n}` (JSON), `GET /api/sessions/{id}/plans/{n}/pdf`.
- **Done when:** v1 and v2 are both downloadable after a revision.

#### T4.3 Plan & PDF preview in the UI — ✅ Done (2026-11-23)
- **Steps:** Right panel shows the structured plan (stages, items, totals) plus an embedded PDF viewer (`<iframe>`) and a Download button; version selector; progress indicator while the plan is being built.
- **Done when:** After "Build plan", the dentist sees the PDF without leaving the page.

---

### Phase 5 — Clarifying questions (AC3)

#### T5.1 Question generation rules — ✅ Done (2026-11-23)
- **Ask a question when** (examples from the price list):
  - Several catalog items fit and **the price differs**: implant system (Osstem / Megagen / Straumann BLT / Straumann SLActive / Nobel / zirconia), crown type (ML vs ST zirconia), All-on-4 vs All-on-6, temporary prosthesis type.
  - A **parameter is missing**: number of surfaces for a restoration, tooth number, number of implants, number of canals, wisdom-tooth difficulty grade (1/2, near anatomical structures).
  - **Optional add-ons** are likely: sedation (hours), bone grafting/sinus lift, PRF membranes, surgical guide, rubber dam.
  - The dentist said something **not in the catalog**: ask to map it or exclude it.
  - An **interval** was not specified (confirm the default).
- **Rules:** max ~7 questions per round, most price-relevant first; each question has `id`, `text`, `options[]` (label + catalog ids + price impact), `allow_free_text`, `related_stage`/`related_item`. The plan is still built with a **provisional default** (cheapest or most common option, clearly marked) so a PDF is always produced.
- **Done when:** On each T0.2 note, the expected questions (written in the `.expected.json`) are asked, and no question is about something the dentist already said.

#### T5.2 Questions UI — ✅ Done (2026-11-23)
- **Steps:** Questions panel: each question as a card with option buttons (show the price difference), a free-text field, and a 🎤 button to **answer by voice** (reuses T2.1/T2.3 via `POST /api/transcribe`). A general "Other corrections" box (text or voice), e.g. "replace stage 3 implant with Straumann and remove the radiograph".
- **Done when:** All questions can be answered by click, text, or voice.

#### T5.3 Spoken questions — ✅ Done (2026-11-23) (optional)
- **Steps:** "Read questions aloud" toggle using the browser `speechSynthesis` API with an English voice (no backend needed).
- **Done when:** Questions are spoken aloud in English.

---

### Phase 6 — Revision, regeneration & confirmation (AC4)

#### T6.1 Revise endpoint — ✅ Done (2026-11-23)
- **Steps:** `POST /api/sessions/{id}/revise` with `{answers: [{question_id, option_id | free_text}], corrections: "…"}`:
  1. Deterministic answers (option clicked → catalog ids) are applied **in code** where possible.
  2. Free text / voice corrections go to the LLM with the current plan JSON + `revise_plan.md` prompt → new `PlanDraft`.
  3. Re-price (T3.4) → new version `v{n+1}` → new PDF (T4.1).
  4. New questions may appear only if the corrections created new ambiguity.
- **Done when:** Answering the questions of a T0.2 note produces v2 with updated items and totals and fewer/no open questions.

#### T6.2 Version diff — ✅ Done (2026-11-23) (optional)
- **Steps:** Compute a diff between versions (items added/removed/changed, total before → after) and show it in the UI ("What changed").
- **Done when:** After a revision the dentist sees e.g. "+ Straumann BLT implant (tooth 36) · total 2 140.00 € → 2 510.00 €".

#### T6.3 Confirmation & final PDF — ✅ Done (2026-11-23)
- **Steps:** "Confirm plan" button, enabled only when no blocking questions remain (the dentist can explicitly accept remaining defaults). `POST /api/sessions/{id}/confirm` → final version: status `FINAL`, no watermark, signature lines, frozen (further edits create a new draft version).
- **Done when:** The full loop works: dictate → PDF v1 → answer → PDF v2 → confirm → final PDF.

---

### Phase 7 — Quality, tests & demo

#### T7.1 Unit tests — ✅ Done (2026-11-23)
- Catalog parsing, rules loading, matcher, pricing, FDI validation, PDF renders (file exists, page count, total string present), API routes with the LLM and STT **mocked**.
- **Done when:** `.venv/python.exe -m pytest backend/tests` passes with no network access and without Ollama running.

#### T7.2 End-to-end evaluation on the practice notes — ✅ Done (2026-11-23)
- **Steps:** `backend/scripts/eval_samples.py --model <ollama model>`: run each `data/sample_notes/note_XX.txt` through the local LLM, compare to `note_XX.expected.json` (items found / missing / extra, questions asked, total difference, duration), print a table. Compare `qwen3:4b` with 1–2 alternatives (T0.5) and keep the best as the default `LLM_MODEL`. Run it on demand, not in the unit tests.
- **Done when:** All notes reach ≥ 90 % item recall and no invented items with the chosen default model, and the comparison table is saved in `docs/model_eval.md`.

#### T7.3 Error handling, logging & privacy — ✅ Done (2026-11-23)
- Clear UI errors (mic denied, STT failure, Ollama not running / model missing, LLM timeout, invalid plan); structured logs without patient names; `storage/` git-ignored; button to delete a session (audio + plans).
- **Done when:** Each failure mode shows a useful message and nothing crashes silently.

#### T7.4 README & demo script — 🟡 README written; the "classmate can run it" check needs a real person
- `README.md`: setup (conda env, Ollama + `qwen3:4b`, `.env`, npm), run commands, screenshots, a demo script that walks through AC1 → AC4.
- **Done when:** A classmate can run the project from the README alone.

---

### Phase 8 — Stretch goals (optional, only after Phase 7)

| ID | Task | Status |
|----|------|--------|
| T8.1 | Simple login for dentists (multiple dentists per clinic) | ⬜ |
| T8.2 | Patient-friendly summary page in plain English (no codes, explains each stage) | ⬜ |
| T8.3 | Payment schedule per stage (deposit, instalments) | ⬜ |
| T8.4 | Live streaming transcription while the dentist speaks | ⬜ |

---

## 4. Verification record (2026-11-23)

| Check | Result |
|---|---|
| Unit + API tests (LLM and STT mocked, no network) | 53 passed |
| Real model `qwen3:4b` on the 4 practice notes | 18/18 items, 0 invented, 0.00 € difference, 17–37 s per note |
| Real model `qwen3:1.7b` on the same notes | 18/18 items, 0 invented, 4–15 s per note |
| New dictation, spoken by Windows TTS, through the real UI in headless Edge with a simulated microphone | Transcribed in 10 s; plan, answers, v2 PDF, final PDF all correct (1 019.78 € checked by hand) |
| Free-text correction with the real model | Removed one service and added another correctly |
| Voice answer, read aloud, Ollama down, model missing | Work, with clear messages |

**Not verified:** a real human voice on a real microphone; a dentist's review of the plans and intervals; the instructor's own notes. The practice notes were also used to tune the rules, so their 100 % score is optimistic.

---

## 5. Change log

| Date | Change | By |
|------|--------|----|
| 2026-11-16 | Initial spec, architecture and agent instructions | Claude |
| 2026-11-16 | Checked xlsx: price list only (208 services), no sample notes; T1.1 count fixed | Claude |
| 2026-11-16 | Switched to a **fully local LLM** (Ollama): Ollama setup and catalog matcher tasks added, prompt/LLM/eval tasks rewritten | Claude |
| 2026-11-16 | Hardware recorded (Ryzen 5 5500U, 14 GB RAM, Radeon iGPU). Default model `qwen3:4b` with thinking off; Ollama task set to 🟡 | Claude |
| 2026-11-16 | Review fixes: **renumbered** so the order is the build order (Phase 0: T0.5 Ollama ↔ T0.6 frontend; Phase 3: schemas → rules → matcher → pricing → prompts → LLM client); T0.2 unblocked with synthetic practice notes; T1.2 report, T1.3, T5.3, T6.2 marked optional; SQLite replaced by JSON files; default intervals must be validated by a dentist; **English only** | Claude |
| 2026-11-23 | Built T0.2 → T7.4. Corrected two spec errors: the price list has **208** services (not 209) and root canal on a molar is **89.60 €** (109.51 € is the re-treatment). Stages and questions are built by code from `families.yaml`; the LLM extracts procedures, picks from shortlists and interprets corrections | Claude |
| 2026-11-23 | Added the tracker for the three remaining actions (A1 commit, A2 real voice, A3 classmate); all three checked and still open | Claude |
| 2026-11-23 | UI redesigned as a product named **Cuspia** (placeholder name): logo, favicon, guided steps, Plan/PDF tabs, bundled font. The interface and its error messages no longer mention the model or local processing; technical details go to the server log | Claude |
| 2026-11-23 | Published at `https://cuspia.dmb-site.site` through a Cloudflare Tunnel from the owner's PC. Added password sign-in, signed cookies, login rate limit, FastAPI serving the built UI, and `scripts/setup_tunnel.ps1` + `scripts/start_public.ps1`. Verified over the public link: access control, voice, plan, revision, confirmation, PDF preview | Claude |
| 2026-11-23 | Replaced the shared password with **self-service accounts**: sign up / sign in, scrypt password hashes, signed cookies, attempt limits, and per-user isolation of plans and jobs. No email verification or password reset yet | Claude |
| 2026-11-23 | Added the **My plans** page: per-user list with search and status filters; reopen and continue, download, delete | Claude |
