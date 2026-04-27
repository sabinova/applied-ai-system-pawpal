"""
PawPal+ Evaluation Harness

Integration eval that runs ``ScheduleAgent.generate_schedule`` against
every case in ``evaluation.eval_cases.EVAL_CASES`` and scores the
output against the ``expected`` criteria attached to each case.

This is NOT a unit test - it's an end-to-end behavioural eval. Each
case kicks off real LLM calls through the agent's four-step pipeline
(analyze -> plan-with-tools -> validate -> revise), so a full run takes
a few minutes. A tqdm progress bar is shown while we work.

Usage::

    python -m evaluation.run_evaluation                    # default
    python -m evaluation.run_evaluation --max-iterations 6
    python -m evaluation.run_evaluation --only case_07_adversarial_too_short

Side effects:
    * Prints a summary table to stdout with one row per case
      (Case ID, Pass/Fail, Quality Score, Iterations Used, Tools
      Called Count) plus a final ``X / N cases passed`` line.
    * Writes a detailed JSON report to
      ``evaluation/results_<YYYYMMDD_HHMMSS>.json`` containing the
      case input, the full agent output, the scoring breakdown, and
      the agent's step trace. One file per run.

Each case is wrapped in a try/except so a single failure doesn't kill
the whole run. ``InvalidInputError`` is treated as the agent correctly
rejecting the input (used by the adversarial cases).

Requires ``ANTHROPIC_API_KEY`` in the environment (or a ``.env`` at the
project root) and the ``tqdm`` package (see ``requirements.txt``).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from tqdm import tqdm

from agent.schedule_agent import InvalidInputError, ScheduleAgent
from agent.tools import validate_schedule
from evaluation.eval_cases import EVAL_CASES


logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _last_quality_score(steps: list[dict[str, Any]]) -> float | None:
    """Return ``overall_score`` from the most recent ``quality_score`` step.

    The agent records one quality_score step per run (after the final
    revise pass); we still scan from the end so this keeps working if
    that ever changes.
    """
    for step in reversed(steps or []):
        if step.get("type") == "quality_score":
            quality = (step.get("details") or {}).get("quality") or {}
            score = quality.get("overall_score")
            if isinstance(score, (int, float)):
                return float(score)
    return None


def _tools_called_count(steps: list[dict[str, Any]]) -> int:
    """Count ``tool_call`` steps emitted by the planner agentic loop."""
    return sum(1 for s in (steps or []) if s.get("type") == "tool_call")


def _medication_task_count(tasks: list[dict[str, Any]]) -> int:
    """Count tasks whose description mentions medication.

    Substring-matches ``medic`` (case-insensitive) so it covers
    "medication", "medicine", and "medicate" without false-matching
    on unrelated words like "food" or "meal".
    """
    return sum(
        1
        for t in tasks
        if "medic" in str(t.get("description", "")).lower()
    )


def _keywords_present(
    tasks: list[dict[str, Any]],
    keywords: list[Any],
) -> tuple[bool, list[Any]]:
    """Check that EVERY required concept appears in at least one task.

    Each entry in ``keywords`` is either:

      * a string  - that exact substring must appear in some task
        description (case-insensitive);
      * a list/tuple of strings - ANY ONE of these synonyms must
        appear (case-insensitive). Use this for concepts that
        owners can phrase multiple ways - e.g. "feeding" might
        legitimately surface as "Breakfast" or "Dinner" in the
        schedule, so the synonym group ``["feed", "meal",
        "breakfast", "dinner"]`` accepts any of them.

    Returns ``(all_present, missing)`` where ``missing`` is the list
    of original keyword entries (string or list) that weren't
    satisfied, so notes can echo them back verbatim for debugging.
    """
    descriptions = [str(t.get("description", "")).lower() for t in tasks]

    def _any_in(needle: str) -> bool:
        n = needle.lower()
        return any(n in d for d in descriptions)

    missing: list[Any] = []
    for entry in keywords:
        if isinstance(entry, (list, tuple)):
            if not any(_any_in(syn) for syn in entry):
                missing.append(list(entry))
        else:
            if not _any_in(str(entry)):
                missing.append(entry)
    return (not missing), missing


def score_case(
    case: dict[str, Any],
    agent_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Score a single eval case against its ``expected`` criteria.

    ``agent_result`` is the dict returned by
    ``ScheduleAgent.generate_schedule``, with two harness-specific
    extensions added by ``_run_one``:

      * ``rejected`` (bool): True iff the input guardrail raised
        ``InvalidInputError`` (so the agent never produced tasks).
      * ``error`` (str): only present on agent-side exceptions or
        rejections; carries the human-readable rejection / error
        message for inclusion in the JSON report.

    Pass ``None`` to indicate the harness itself never got a result
    back (catastrophic exception). That always fails the case.

    Returns ``{"passed": bool, "checks": {<criterion>: bool}, "notes": [str]}``.
    A case passes only when every criterion present in ``expected``
    evaluates to True. Notes are short human-readable explanations for
    each failed check, suitable for printing or storing in JSON.
    """
    expected = case.get("expected") or {}
    checks: dict[str, bool] = {}
    notes: list[str] = []

    expects_rejection = bool(expected.get("should_be_rejected", False))
    rejected = bool(agent_result and agent_result.get("rejected"))

    # ---- adversarial cases -------------------------------------------------
    # When the case is supposed to be rejected, the only criterion we
    # care about is whether the input guardrail actually fired. Other
    # criteria (min_tasks, keywords, ...) don't apply and are skipped.
    if expects_rejection:
        checks["should_be_rejected"] = rejected
        if not rejected:
            if agent_result is None:
                notes.append(
                    "expected input rejection but the harness raised an "
                    "unhandled exception"
                )
            else:
                notes.append(
                    "expected input rejection but the agent ran to "
                    "completion (input guardrail did not fire)"
                )
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "notes": notes,
        }

    # ---- happy-path cases --------------------------------------------------
    # An unexpected rejection or exception here fails the case
    # immediately - we don't bother running the rest of the criteria
    # because there's no schedule to score.
    if agent_result is None:
        checks["agent_ran"] = False
        notes.append("harness exception before agent_result was produced")
        return {"passed": False, "checks": checks, "notes": notes}

    if rejected:
        checks["agent_ran"] = False
        notes.append(
            f"input guardrail unexpectedly rejected this case: "
            f"{agent_result.get('error', '<no message>')}"
        )
        return {"passed": False, "checks": checks, "notes": notes}

    if not agent_result.get("success", False):
        checks["agent_succeeded"] = False
        notes.append(
            f"agent reported success=False: "
            f"{agent_result.get('error', '<no error message>')}"
        )
        # We still run the remaining checks below so the JSON report
        # captures every signal, but the case is already failing.

    tasks: list[dict[str, Any]] = agent_result.get("tasks") or []

    if "min_tasks" in expected:
        min_t = int(expected["min_tasks"])
        ok = len(tasks) >= min_t
        checks["min_tasks"] = ok
        if not ok:
            notes.append(
                f"expected at least {min_t} tasks, got {len(tasks)}"
            )

    if "max_tasks" in expected:
        max_t = int(expected["max_tasks"])
        ok = len(tasks) <= max_t
        checks["max_tasks"] = ok
        if not ok:
            notes.append(
                f"expected at most {max_t} tasks, got {len(tasks)}"
            )

    if "must_include_keywords" in expected:
        keywords = list(expected["must_include_keywords"] or [])
        ok, missing = _keywords_present(tasks, keywords)
        checks["must_include_keywords"] = ok
        if not ok:
            notes.append(
                f"missing required keyword(s) in task descriptions: "
                f"{missing}"
            )

    if "medication_count" in expected:
        target = int(expected["medication_count"])
        actual = _medication_task_count(tasks)
        ok = actual == target
        checks["medication_count"] = ok
        if not ok:
            notes.append(
                f"expected {target} medication task(s), found {actual}"
            )

    if expected.get("should_have_no_conflicts"):
        # Re-run validate_schedule directly against the final task list
        # rather than trusting the agent's last validate step - this
        # guarantees we score the exact tasks the user would see.
        try:
            v = validate_schedule(tasks)
            ok = not v.get("has_conflicts", False)
            checks["should_have_no_conflicts"] = ok
            if not ok:
                notes.append(
                    f"validate_schedule still reports conflicts: "
                    f"{v.get('conflicts', [])}"
                )
        except Exception as exc:
            checks["should_have_no_conflicts"] = False
            notes.append(f"validate_schedule raised: {exc!r}")

    return {
        "passed": all(checks.values()) if checks else False,
        "checks": checks,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Per-case execution
# ---------------------------------------------------------------------------

def _run_one(
    agent: ScheduleAgent,
    case: dict[str, Any],
) -> dict[str, Any]:
    """Run the agent on a single case and normalise the result envelope.

    Catches everything so the rest of the suite always runs:
      * ``InvalidInputError`` -> rejected=True with the rejection message.
      * Any other ``Exception`` -> rejected=False, success=False, error
        is the formatted traceback.

    Returns a dict shaped like a normal ``generate_schedule`` result
    plus the harness-only fields ``rejected`` and (on errors) ``error``.
    Always includes ``tasks``, ``steps``, ``iterations``, and
    ``guardrail_events`` so downstream code can rely on the shape.
    """
    try:
        result = agent.generate_schedule(case["description"])
        result.setdefault("rejected", False)
        return result
    except InvalidInputError as exc:
        # The input guardrail rejected the description. Adversarial
        # cases are supposed to land here - happy-path cases fail.
        return {
            "rejected": True,
            "success": False,
            "error": str(exc),
            "tasks": [],
            "steps": list(getattr(agent, "steps", []) or []),
            "iterations": 0,
            "guardrail_events": list(
                getattr(agent.guardrail_log, "events", []) or []
            ),
            "pet_profile": {},
        }
    except Exception as exc:
        logger.exception("Agent raised on case %s: %s", case.get("id"), exc)
        return {
            "rejected": False,
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "tasks": [],
            "steps": list(getattr(agent, "steps", []) or []),
            "iterations": 0,
            "guardrail_events": list(
                getattr(agent.guardrail_log, "events", []) or []
            ),
            "pet_profile": {},
        }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _format_summary_table(rows: list[dict[str, Any]]) -> str:
    """Format the per-case summary table that prints after the run.

    Columns: Case ID | Pass/Fail | Quality | Iters | Tools.
    Widths flex to the longest case id so very long ids still line
    up. Quality is shown as ``-`` when the case never produced a
    schedule (rejected or errored before quality scoring).
    """
    headers = ["Case ID", "Result", "Quality", "Iters", "Tools"]
    table = [headers]
    for row in rows:
        quality = row.get("quality_score")
        quality_str = f"{quality:.1f}" if isinstance(quality, (int, float)) else "-"
        table.append([
            row["id"],
            "PASS" if row["passed"] else "FAIL",
            quality_str,
            str(row.get("iterations", 0)),
            str(row.get("tools_called", 0)),
        ])

    widths = [
        max(len(str(table[r][c])) for r in range(len(table)))
        for c in range(len(headers))
    ]

    def _fmt_row(cells: list[str]) -> str:
        return "  ".join(
            str(cells[c]).ljust(widths[c]) for c in range(len(headers))
        )

    sep = "  ".join("-" * w for w in widths)
    lines = [_fmt_row(table[0]), sep]
    lines.extend(_fmt_row(r) for r in table[1:])
    return "\n".join(lines)


def _results_path(now: datetime | None = None) -> Path:
    """Build the timestamped path for this run's JSON report."""
    ts = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return RESULTS_DIR / f"results_{ts}.json"


# ---------------------------------------------------------------------------
# run_all entry point
# ---------------------------------------------------------------------------

def run_all(
    cases: list[dict[str, Any]] | None = None,
    *,
    model: str = "claude-sonnet-4-5",
    max_iterations: int = 8,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the full eval suite end-to-end.

    Loops over ``cases`` (defaults to ``EVAL_CASES``), runs each one
    through a fresh ``ScheduleAgent`` invocation, scores it, and
    accumulates summary rows + a detailed JSON report. Per-case
    exceptions are caught inside ``_run_one`` so one failing case
    never aborts the whole run.

    Side effects:
      * Renders a tqdm progress bar (one tick per case).
      * Prints the summary table and the ``X / N cases passed`` line.
      * Writes the JSON report to ``output_path`` (defaults to
        ``evaluation/results_<timestamp>.json``).

    Returns a dict with::

        {
            "passed":        int,   # count of cases that passed
            "total":         int,   # total cases run
            "summary_rows":  list[dict],  # one row per case
            "results":       list[dict],  # detailed per-case reports
            "output_path":   str,   # location of the JSON dump
        }

    so callers (like CI) can act on the totals without re-parsing
    the JSON file.
    """
    cases = list(cases if cases is not None else EVAL_CASES)
    output_path = output_path or _results_path()

    agent = ScheduleAgent(model=model, max_iterations=max_iterations)

    summary_rows: list[dict[str, Any]] = []
    detailed_results: list[dict[str, Any]] = []

    bar = tqdm(cases, desc="Evaluating", unit="case", dynamic_ncols=True)
    for case in bar:
        case_id = case.get("id", "<unknown>")
        bar.set_postfix_str(case_id, refresh=False)

        try:
            agent_result = _run_one(agent, case)
        except Exception as exc:
            # _run_one already swallows everything, so this is paranoia
            # for the unlikely case (e.g. ScheduleAgent ctor side-effect)
            # where it itself blows up.
            logger.exception(
                "harness crash on case %s: %s", case_id, exc,
            )
            agent_result = None

        score = score_case(case, agent_result)

        steps = (agent_result or {}).get("steps") or []
        row = {
            "id": case_id,
            "passed": score["passed"],
            "quality_score": _last_quality_score(steps),
            "iterations": (agent_result or {}).get("iterations", 0),
            "tools_called": _tools_called_count(steps),
        }
        summary_rows.append(row)

        detailed_results.append(
            {
                "id": case_id,
                "description": case.get("description"),
                "expected": case.get("expected"),
                "agent_result": agent_result,
                "score": score,
                "summary_row": row,
            }
        )

    passed = sum(1 for r in summary_rows if r["passed"])
    total = len(summary_rows)

    print()
    print("=== EVAL RESULTS ===")
    print(_format_summary_table(summary_rows))
    print()
    print(f"{passed} / {total} cases passed")

    report = {
        "run_started_at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "max_iterations": max_iterations,
        "passed": passed,
        "total": total,
        "summary_rows": summary_rows,
        "results": detailed_results,
    }

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
        print(f"\nDetailed results written to {output_path}")
    except OSError as exc:
        logger.error("Failed to write results JSON to %s: %s", output_path, exc)

    return {
        "passed": passed,
        "total": total,
        "summary_rows": summary_rows,
        "results": detailed_results,
        "output_path": str(output_path),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the PawPal+ evaluation harness.",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5",
        help="Anthropic model id (default: claude-sonnet-4-5).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=8,
        help="Cap on planner-loop iterations per case (default: 8).",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help=(
            "Only run cases whose id matches this value. May be passed "
            "multiple times to run a subset."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress agent INFO logs (only print eval output).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY is not set. Add it to your "
            "environment or to a .env file at the project root.",
            file=sys.stderr,
        )
        return 1

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cases = EVAL_CASES
    if args.only:
        wanted = set(args.only)
        cases = [c for c in EVAL_CASES if c.get("id") in wanted]
        if not cases:
            print(
                f"ERROR: no cases matched --only {sorted(wanted)!r}",
                file=sys.stderr,
            )
            return 1

    summary = run_all(
        cases=cases,
        model=args.model,
        max_iterations=args.max_iterations,
    )

    return 0 if summary["passed"] == summary["total"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
