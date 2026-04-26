"""
PawPal+ Agent Tools

Python implementations and Anthropic tool-use definitions for the three
tools the schedule agent can call:

    1. validate_schedule         - duration-aware conflict detection
    2. get_species_guidelines    - species/age-based care defaults
    3. calculate_schedule_quality - 0-100 scoring on spacing, balance, density

The TOOL_DEFINITIONS list is what we send to the Anthropic API; the
TOOL_REGISTRY maps tool names back to the Python callables so the agent
loop can dispatch a tool_use block to real code.
"""

from __future__ import annotations

from typing import Any, Callable

from pawpal_system import Owner, Pet, Scheduler, Task


# ---------------------------------------------------------------------------
# Tool 1: validate_schedule
# ---------------------------------------------------------------------------

def validate_schedule(tasks: list[dict]) -> dict:
    """Detect time-window conflicts in a draft schedule.

    Builds temporary domain objects (a one-Pet Owner and a Scheduler) and
    delegates to ``Scheduler.detect_conflicts`` so the agent reuses the
    same overlap logic the rest of the app relies on. A task running from
    11:30 for 60 minutes (ending 12:30) will be flagged as conflicting
    with a task that starts at 12:00.

    Args:
        tasks: A list of dicts with keys ``description``, ``time``
            (``HH:MM`` 24-hour), ``duration_minutes``, ``priority``,
            and ``pet_name``.

    Returns:
        A dict with:
          * ``has_conflicts`` (bool): True if any pair of tasks overlap.
          * ``conflicts`` (list[str]): Human-readable warning strings.
          * ``task_count`` (int): Number of tasks evaluated.
    """
    temp_pet = Pet(name="__draft__", species="unknown", age=0)
    temp_owner = Owner(name="__draft_owner__", pets=[temp_pet])
    scheduler = Scheduler(owner=temp_owner)

    task_objects: list[Task] = []
    for raw in tasks:
        task_objects.append(
            Task(
                description=str(raw.get("description", "")),
                time=str(raw.get("time", "00:00")),
                duration_minutes=int(raw.get("duration_minutes", 0)),
                priority=str(raw.get("priority", "medium")),
                pet_name=str(raw.get("pet_name", temp_pet.name)),
            )
        )

    warnings = scheduler.detect_conflicts(task_objects)

    return {
        "has_conflicts": len(warnings) > 0,
        "conflicts": warnings,
        "task_count": len(task_objects),
    }


# ---------------------------------------------------------------------------
# Tool 2: get_species_guidelines
# ---------------------------------------------------------------------------

def get_species_guidelines(species: str, age: int) -> dict:
    """Return baseline care guidelines for a species at a given age.

    Guidelines are intentionally conservative defaults aimed at healthy
    pets and are not a substitute for veterinary advice. ``age`` is in
    years; pets younger than 1 year are treated as juveniles (puppy /
    kitten / fledgling) and given more frequent meals.

    Supported species: ``dog``, ``cat``, ``bird``. Anything else returns
    a generic ``unknown`` marker so the agent can fall back gracefully.

    Args:
        species: Pet species name (case-insensitive).
        age: Pet age in whole years.

    Returns:
        A dict of guideline values, or
        ``{"species": "unknown", "note": "no specific guidelines"}``.
    """
    s = species.strip().lower()
    is_adult = age >= 1

    if s == "dog":
        return {
            "species": "dog",
            "is_adult": is_adult,
            "meals_per_day": 2 if is_adult else 3,
            "walks_per_day": 2,
            "min_walk_minutes": 30,
            "sleep_hours": "12-14",
            "notes": (
                "Adult dogs do best on two balanced meals; puppies under "
                "1 year need three smaller meals. Provide at least one "
                "longer daily walk plus shorter potty breaks."
            ),
        }

    if s == "cat":
        return {
            "species": "cat",
            "is_adult": is_adult,
            "meals_per_day": 2 if is_adult else 4,
            "play_sessions_per_day": 2,
            "min_play_minutes": 15,
            "sleep_hours": "12-16",
            "notes": (
                "Cats prefer small frequent meals; kittens (<1y) need "
                "more frequent feeding. Daily interactive play prevents "
                "boredom and obesity."
            ),
        }

    if s == "bird":
        return {
            "species": "bird",
            "is_adult": is_adult,
            "meals_per_day": 2,
            "out_of_cage_minutes": 60,
            "sleep_hours": "10-12",
            "notes": (
                "Most companion birds need fresh food twice daily and a "
                "long, dark, quiet sleep period. Out-of-cage time "
                "supports social and physical needs."
            ),
        }

    return {"species": "unknown", "note": "no specific guidelines"}


# ---------------------------------------------------------------------------
# Tool 3: calculate_schedule_quality
# ---------------------------------------------------------------------------

def _time_to_minutes(time_str: str) -> int | None:
    """Parse ``HH:MM`` to minutes-since-midnight, or None on failure."""
    try:
        hh, mm = time_str.split(":")
        return int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        return None


def calculate_schedule_quality(tasks: list[dict]) -> dict:
    """Score a draft schedule on three independent dimensions (0-100).

    Dimensions:
      * ``activity_spacing`` — rewards activities spread across the day.
        If the gap between the earliest and latest task start is under
        4 hours, the score scales linearly down to 0.
      * ``priority_balance`` — rewards a mix of ``high``, ``medium``, and
        ``low`` priorities. One distinct level scores ~33, two ~66, all
        three 100.
      * ``realistic_density`` — rewards 1-12 tasks per day; 0 tasks scores
        0, and each task above 12 deducts 15 points (floored at 0).

    Args:
        tasks: List of task dicts with at least ``time`` and ``priority``.

    Returns:
        A dict with ``overall_score`` (rounded average), per-dimension
        ``breakdown``, and a ``feedback`` list of revision suggestions.
    """
    feedback: list[str] = []
    n = len(tasks)

    # --- realistic_density --------------------------------------------------
    if n == 0:
        density_score = 0
        feedback.append("Schedule is empty - add at least one task.")
    elif n > 12:
        density_score = max(0, 100 - (n - 12) * 15)
        feedback.append(
            f"{n} tasks is unrealistic for a single day; aim for 12 or fewer."
        )
    else:
        density_score = 100

    # --- priority_balance ---------------------------------------------------
    if n == 0:
        priority_score = 0
    else:
        counts = {"high": 0, "medium": 0, "low": 0}
        for t in tasks:
            p = str(t.get("priority", "medium")).lower()
            if p in counts:
                counts[p] += 1
        present = sum(1 for v in counts.values() if v > 0)
        priority_score = round((present / 3) * 100)
        if present == 1:
            feedback.append(
                "All tasks share one priority level - vary high/medium/low."
            )
        elif present == 2:
            feedback.append(
                "Consider adding the missing priority tier for better balance."
            )

    # --- activity_spacing ---------------------------------------------------
    if n == 0:
        spacing_score = 0
    elif n == 1:
        # A single task has nothing to space against; don't punish it.
        spacing_score = 100
    else:
        minutes = [m for m in (_time_to_minutes(str(t.get("time", ""))) for t in tasks) if m is not None]
        if len(minutes) < 2:
            spacing_score = 0
            feedback.append("Could not parse task times; check the HH:MM format.")
        else:
            span_hours = (max(minutes) - min(minutes)) / 60.0
            if span_hours < 4:
                spacing_score = round((span_hours / 4) * 100)
                feedback.append(
                    f"Activities cluster within {span_hours:.1f}h - spread "
                    "them across the day for the pet's wellbeing."
                )
            else:
                spacing_score = 100

    breakdown = {
        "activity_spacing": int(spacing_score),
        "priority_balance": int(priority_score),
        "realistic_density": int(density_score),
    }
    overall_score = round(sum(breakdown.values()) / 3, 1)

    if not feedback:
        feedback.append("Schedule looks well-balanced.")

    return {
        "overall_score": overall_score,
        "breakdown": breakdown,
        "feedback": feedback,
    }


# ---------------------------------------------------------------------------
# Anthropic tool-use definitions
# ---------------------------------------------------------------------------

# Reused JSON Schema for a single task object so the three tools stay in sync.
_TASK_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": "Short human-readable name of the activity, e.g. 'Morning walk'.",
        },
        "time": {
            "type": "string",
            "description": "Start time in 24-hour HH:MM format (e.g. '07:30').",
        },
        "duration_minutes": {
            "type": "integer",
            "description": "How long the activity lasts, in minutes.",
        },
        "priority": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Urgency tier of the task.",
        },
        "pet_name": {
            "type": "string",
            "description": "Name of the pet this task belongs to.",
        },
    },
    "required": [
        "description",
        "time",
        "duration_minutes",
        "priority",
        "pet_name",
    ],
}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "validate_schedule",
        "description": (
            "Use this to verify a draft schedule has no time conflicts. "
            "Call this AFTER drafting tasks but BEFORE finalizing or "
            "presenting the day's plan. It runs duration-aware overlap "
            "detection (an 11:30 task lasting 60 minutes conflicts with "
            "a 12:00 task) and returns a list of warning strings you "
            "should use to revise overlapping tasks. Returns "
            "has_conflicts=False when the draft is safe to present."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "Draft list of pet care tasks to validate.",
                    "items": _TASK_ITEM_SCHEMA,
                }
            },
            "required": ["tasks"],
        },
    },
    {
        "name": "get_species_guidelines",
        "description": (
            "Use this BEFORE drafting a schedule to look up species- and "
            "age-appropriate care defaults (meals per day, walks, sleep "
            "hours, etc.). Call once per pet so the schedule reflects "
            "the pet's actual biological needs instead of guessing. "
            "Supports 'dog', 'cat', and 'bird'; other species return a "
            "generic 'unknown' marker so you can ask the user for "
            "clarification."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "species": {
                    "type": "string",
                    "description": "Pet species name, e.g. 'dog', 'cat', 'bird'.",
                },
                "age": {
                    "type": "integer",
                    "description": "Pet age in whole years (use 0 for under one year old).",
                    "minimum": 0,
                },
            },
            "required": ["species", "age"],
        },
    },
    {
        "name": "calculate_schedule_quality",
        "description": (
            "Use this AFTER validate_schedule passes to score the draft "
            "0-100 on activity spacing, priority balance, and realistic "
            "density. Read the returned 'feedback' list and revise the "
            "plan when overall_score is below ~70 before presenting it "
            "to the user. Do NOT call this on an empty schedule - draft "
            "tasks first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "Draft list of pet care tasks to score.",
                    "items": _TASK_ITEM_SCHEMA,
                }
            },
            "required": ["tasks"],
        },
    },
]


# Maps tool names (as the LLM sees them) to the actual Python callables.
# The agent loop uses this to dispatch a tool_use block to real code.
TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "validate_schedule": validate_schedule,
    "get_species_guidelines": get_species_guidelines,
    "calculate_schedule_quality": calculate_schedule_quality,
}
