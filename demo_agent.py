"""
End-to-end smoke test for the PawPal+ ScheduleAgent.

Runs the four-step pipeline (analyze -> plan with tools -> validate ->
revise) against a real Anthropic call and prints:

    1. The structured pet profile produced by the analyzer.
    2. Each step recorded on `agent.steps`, formatted with a short
       human-readable summary so you can see the reasoning trace.
    3. The final scored daily schedule.
    4. Iteration counts (planner-loop iterations + revise rounds).

Usage:
    python demo_agent.py
    python demo_agent.py --description "Luna is a 12-year-old indoor cat ..."
    python demo_agent.py --max-iterations 6 --verbose

Requires ANTHROPIC_API_KEY in the environment or a .env file at the
project root.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv

from agent.schedule_agent import ScheduleAgent


DEFAULT_DESCRIPTION = (
    "Mochi is a 3-year-old golden retriever, very high energy. "
    "He needs arthritis medication twice daily. He also needs at least "
    "two 30-minute walks per day."
)


# ---------------------------------------------------------------------------
# Per-step summaries
# ---------------------------------------------------------------------------

def _summarize_step(step: dict[str, Any]) -> str:
    """Return a short one-line summary for a trace step.

    The agent records steps as ``{type, timestamp, details}`` with no
    ``summary`` field, so this function derives a useful headline per
    type (analyze, tool_call, validate, revise, warning, error,
    quality_score, plan).
    """
    step_type = step.get("type", "?")
    details = step.get("details", {}) or {}

    if step_type == "analyze":
        profile = details.get("pet_profile", {})
        return (
            f"parsed profile: {profile.get('pet_name', '?')} "
            f"({profile.get('species', '?')}, "
            f"{profile.get('age', '?')}y, "
            f"energy={profile.get('energy_level', '?')})"
        )

    if step_type == "tool_call":
        tool = details.get("tool", "?")
        is_error = details.get("is_error", False)
        flag = " [ERROR]" if is_error else ""
        return f"called {tool}(...){flag}"

    if step_type == "validate":
        result = details.get("result", {})
        return (
            f"has_conflicts={result.get('has_conflicts')} "
            f"conflicts={len(result.get('conflicts', []))} "
            f"task_count={result.get('task_count')}"
        )

    if step_type == "revise":
        n_conflicts = len(details.get("input_conflicts", []))
        n_revised = len(details.get("revised_tasks", []))
        return f"revised {n_revised} tasks to resolve {n_conflicts} conflicts"

    if step_type == "warning":
        stage = details.get("stage", "?")
        msg = details.get("message") or details.get("error") or ""
        return f"stage={stage} {msg}".strip()

    if step_type == "error":
        stage = details.get("stage", "?")
        return f"stage={stage} error={details.get('error', '?')}"

    if step_type == "quality_score":
        quality = details.get("quality", {})
        return (
            f"overall={quality.get('overall_score')} "
            f"breakdown={quality.get('breakdown')}"
        )

    if step_type == "plan":
        return (
            f"planner_iterations={details.get('planner_iterations')} "
            f"final_tasks={len(details.get('tasks', []))}"
        )

    return ""


def _format_details(details: dict[str, Any], indent: str = "    ") -> str:
    """Pretty-print step details for verbose mode."""
    import json
    return "\n".join(
        f"{indent}{line}"
        for line in json.dumps(details, indent=2, default=str).splitlines()
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the PawPal+ ScheduleAgent against a sample pet description.",
    )
    parser.add_argument(
        "--description",
        default=DEFAULT_DESCRIPTION,
        help="Free-text pet description to feed the agent.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=8,
        help="Cap on planner-loop iterations (default: 8).",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5",
        help="Anthropic model id (default: claude-sonnet-4-5).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Also dump full step details (raw JSON).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Silence the agent's own INFO logs (only show the summary).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY is not set. Add it to your environment "
            "or to a .env file at the project root before running this demo.",
            file=sys.stderr,
        )
        return 1

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=== INPUT ===")
    print(args.description)
    print()

    agent = ScheduleAgent(model=args.model, max_iterations=args.max_iterations)
    try:
        result = agent.generate_schedule(args.description)
    except Exception as exc:
        print(f"\nFATAL: agent.generate_schedule raised: {exc!r}", file=sys.stderr)
        return 2

    pet_profile = result.get("pet_profile", {})
    tasks = result.get("tasks", [])
    steps = result.get("steps", [])
    iterations = result.get("iterations", 0)

    print("\n=== PET PROFILE ===")
    if pet_profile:
        for key, value in pet_profile.items():
            print(f"  {key}: {value}")
    else:
        print("  (analyzer produced no profile - see steps below for the error)")

    print("\n=== AGENT STEPS ===")
    for step in steps:
        summary = _summarize_step(step)
        ts = step.get("timestamp", "")
        line = f"\n[{step.get('type', '?')}] {ts}"
        if summary:
            line += f"  -  {summary}"
        print(line)
        if args.verbose and step.get("details"):
            print(_format_details(step["details"]))

    print("\n=== FINAL SCHEDULE ===")
    if tasks:
        for task in tasks:
            print(
                f"  {task.get('time', '??:??')}  "
                f"{task.get('description', '(no description)'):<45}  "
                f"({task.get('duration_minutes', '?')} min, "
                f"priority={task.get('priority', '?')})"
            )
    else:
        print("  (no tasks produced - see error / warning steps above)")

    print("\n=== SUMMARY ===")
    print(f"  total iterations: {iterations}")
    print(f"  step count:       {len(steps)}")
    print(f"  task count:       {len(tasks)}")

    quality_steps = [s for s in steps if s.get("type") == "quality_score"]
    if quality_steps:
        quality = quality_steps[-1].get("details", {}).get("quality", {})
        print(f"  quality score:    {quality.get('overall_score')}")
        breakdown = quality.get("breakdown")
        if breakdown:
            print(f"  breakdown:        {breakdown}")

    has_errors = any(s.get("type") == "error" for s in steps)
    return 3 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
