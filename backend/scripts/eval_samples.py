"""Run the practice notes through the real local model and compare with the expected plans.

Usage: .venv/python.exe backend/scripts/eval_samples.py --model qwen3:4b
"""

import argparse
import json
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR, ROOT_DIR, get_settings
from app.services.catalog import load_catalog
from app.services.llm import LLMError, OllamaClient
from app.services.planner import Planner
from app.services.rules import load_rules


def evaluate(planner: Planner, note: Path) -> dict:
    """Score one note."""
    expected = json.loads(note.with_suffix(".expected.json").read_text(encoding="utf-8"))
    started = time.perf_counter()
    plan = planner.to_plan(planner.build_state(note.read_text(encoding="utf-8")), "eval", 1)
    seconds = time.perf_counter() - started
    want = Counter((row["catalog_id"], row["quantity"]) for row in expected["items"])
    got = Counter((item.catalog_id, item.quantity) for stage in plan.stages for item in stage.items)
    topics = {q.topic for q in plan.questions if q.kind != "interval"}
    return {
        "note": note.stem,
        "found": sum((want & got).values()),
        "expected": sum(want.values()),
        "missing": [key[0] for key in (want - got)],
        "extra": [key[0] for key in (got - want)],
        "questions_ok": set(expected["expected_questions"]) <= topics,
        "unexpected_questions": sorted(topics - set(expected["expected_questions"])),
        "total": plan.total_eur,
        "total_diff": plan.total_eur - Decimal(expected["total_eur"]),
        "seconds": seconds,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None)
    parser.add_argument("--write", action="store_true", help="append to docs/model_eval.md")
    args = parser.parse_args()
    settings = get_settings().model_copy()
    if args.model:
        settings.llm_model = args.model
    planner = Planner(load_catalog(), load_rules(), OllamaClient(settings))
    header = "| Note | Items found | Missing | Extra | Questions OK | Total € | Diff € | Time s |"
    rows = [header, "|---|---|---|---|---|---|---|---|"]
    found = expected = extra = 0
    for note in sorted((DATA_DIR / "sample_notes").glob("note_??.txt")):
        try:
            r = evaluate(planner, note)
        except LLMError as exc:
            print(f"{note.stem}: LLM error: {exc}")
            return 1
        found, expected, extra = (
            found + r["found"],
            expected + r["expected"],
            extra + len(r["extra"]),
        )
        rows.append(
            f"| {r['note']} | {r['found']}/{r['expected']} | {', '.join(r['missing']) or '–'} | "
            f"{', '.join(r['extra']) or '–'} | {'yes' if r['questions_ok'] else 'no'}"
            f"{' (+' + ', '.join(r['unexpected_questions']) + ')' if r['unexpected_questions'] else ''} | "
            f"{r['total']} | {r['total_diff']} | {r['seconds']:.0f} |"
        )
        print(rows[-1], flush=True)
    recall = found / expected if expected else 0
    summary = f"Model `{settings.llm_model}`: item recall {recall:.0%}, extra items {extra}."
    print(summary)
    if args.write:
        path = ROOT_DIR / "docs" / "model_eval.md"
        title = "# Local model evaluation (synthetic practice notes)\n\n"
        previous = path.read_text(encoding="utf-8") if path.exists() else title
        section = f"## {settings.llm_model}\n\n{summary}\n\n" + "\n".join(rows) + "\n\n"
        path.write_text(previous + section, encoding="utf-8")
    return 0 if recall >= 0.9 and extra == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
