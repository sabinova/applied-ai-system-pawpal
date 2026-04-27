"""
PawPal+ Agent Guardrails

Three-layer guardrail surface for the schedule agent:

    1. INPUT  guardrail - ``validate_user_input`` runs before the agent
       starts. Catches empty / too-short / too-long input, descriptions
       that contain no pet-related vocabulary, and obvious prompt
       injection attempts. Returns a ``(is_valid, message)`` tuple.

    2. TOOL  guardrail - the existing ``validate_schedule`` tool plus
       the revise loop in ``ScheduleAgent``. This module does not own
       that layer, but ``AgentGuardrailLog`` is the shared sink the
       agent uses to record every conflict-driven revise round.

    3. OUTPUT guardrail - the ``TaskOutput`` / ``ScheduleOutput``
       Pydantic models and the ``validate_schedule_output`` helper run
       after the agent finishes and reject any final schedule that
       doesn't conform to the strict schema (HH:MM times, sane
       durations, allowed enums, no duplicate tasks, etc.).

``AgentGuardrailLog`` is a small append-only log that any layer can
write to. The agent surfaces its contents on the result dict as
``guardrail_events`` so UIs / eval harnesses can observe exactly which
guardrails fired during a run.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Union

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


# ---------------------------------------------------------------------------
# Layer 1 - Input guardrail
# ---------------------------------------------------------------------------

# Lowercased keyword set; we accept the description if at least one of
# these appears as a whole word. Stored as a tuple for stable ordering
# in error messages and so callers can introspect what's checked.
#
# The set is intentionally split into three buckets so it's obvious
# what counts as "pet vocabulary":
#
#   * SPECIES_KEYWORDS  - the animal itself ("dog", "cat", ...).
#   * BREED_KEYWORDS    - common dog/cat breeds. Owners frequently say
#                         "Australian Shepherd" or "Labrador" and never
#                         use the bare word "dog", so without these the
#                         guardrail falsely rejects valid descriptions.
#   * PET_CARE_KEYWORDS - vocabulary that strongly correlates with pet
#                         ownership ("leash", "vet", "paw", "kibble"...).
#
# All three are merged into PET_KEYWORDS for backwards compatibility -
# external callers and tests only need to know about the union.
SPECIES_KEYWORDS: tuple[str, ...] = (
    "pet",
    "dog",
    "doggo",
    "doggy",
    "cat",
    "kitty",
    "bird",
    "fish",
    "rabbit",
    "bunny",
    "hamster",
    "gerbil",
    "ferret",
    "guinea",  # "guinea pig" - "pig" alone is too ambiguous
    "lizard",
    "snake",
    "turtle",
    "tortoise",
    "parrot",
    "parakeet",
    "cockatiel",
    "canary",
    "reptile",
    "rodent",
    "feline",
    "canine",
    "animal",
    "puppy",
    "kitten",
)

BREED_KEYWORDS: tuple[str, ...] = (
    # Dog breeds - the most common ones owners actually type.
    "shepherd",
    "retriever",
    "labrador",
    "poodle",
    "terrier",
    "bulldog",
    "corgi",
    "husky",
    "dachshund",
    "beagle",
    "chihuahua",
    "dalmatian",
    "doberman",
    "rottweiler",
    "mastiff",
    "collie",
    "spaniel",
    "pitbull",
    "boxer",
    "pug",
    "shihtzu",
    "maltese",
    "akita",
    "samoyed",
    "pomeranian",
    "schnauzer",
    "greyhound",
    "whippet",
    "aussie",  # short for Australian Shepherd / Aussie
    # Cat breeds.
    "persian",
    "siamese",
    "tabby",
    "ragdoll",
    "bengal",
    "sphynx",
    "burmese",
)

PET_CARE_KEYWORDS: tuple[str, ...] = (
    "leash",
    "collar",
    "kennel",
    "crate",
    "litter",
    "paw",
    "paws",
    "fur",
    "furry",
    "tail",
    "whiskers",
    "feathers",
    "scales",
    "fin",
    "fins",
    "vet",
    "vets",
    "veterinarian",
    "veterinary",
    "groom",
    "grooming",
    "neuter",
    "neutered",
    "spay",
    "spayed",
    "breed",
    "breeds",
    "kibble",
    "chew",
    "chews",
    "fetch",
    "purr",
    "bark",
    "meow",
    "wag",
    "muzzle",
    "harness",
    "treat",
    "treats",
    "obedience",
    # Walks / walking are by far the most common signal in dog
    # descriptions but "walk" alone is generic enough to need the
    # whole-word boundary the matcher already enforces.
    "walk",
    "walks",
    "walking",
)

# Public union, kept as PET_KEYWORDS so existing callers keep working.
PET_KEYWORDS: tuple[str, ...] = (
    SPECIES_KEYWORDS + BREED_KEYWORDS + PET_CARE_KEYWORDS
)

# Lowercased substrings that strongly suggest a prompt-injection attempt.
# Substring (not whole-word) match is intentional - "ignore previous
# instructions" should still trip "ignore previous".
PROMPT_INJECTION_PATTERNS: tuple[str, ...] = (
    "ignore previous",
    "system prompt",
    "you are now",
)

MIN_INPUT_LENGTH = 15
MAX_INPUT_LENGTH = 1500

# Pre-compile a whole-word matcher for the keyword check so we don't
# false-match on substrings like "carpet" containing "pet".
_PET_KEYWORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in PET_KEYWORDS) + r")\b",
    flags=re.IGNORECASE,
)


def validate_user_input(description: str) -> tuple[bool, str]:
    """Validate a free-text pet description before the agent runs.

    Rejects, in order:
      * non-string / empty / whitespace-only input;
      * descriptions shorter than ``MIN_INPUT_LENGTH`` characters;
      * descriptions longer than ``MAX_INPUT_LENGTH`` characters;
      * descriptions that contain none of ``PET_KEYWORDS`` as whole
        words (so "I love carpets" doesn't accidentally pass on "pet");
      * descriptions containing any phrase in
        ``PROMPT_INJECTION_PATTERNS``.

    Args:
        description: The raw user-supplied pet description.

    Returns:
        ``(True, "ok")`` on success, otherwise ``(False, message)``
        with a short, friendly explanation suitable for display.
    """
    if not isinstance(description, str) or not description.strip():
        return (
            False,
            "Please tell me a little about your pet so I can build a schedule.",
        )

    text = description.strip()
    length = len(text)

    if length < MIN_INPUT_LENGTH:
        return (
            False,
            f"That description is a bit too short (need at least "
            f"{MIN_INPUT_LENGTH} characters). Tell me your pet's name, "
            "species, and anything special about them.",
        )

    if length > MAX_INPUT_LENGTH:
        return (
            False,
            f"That description is quite long ({length} characters). "
            f"Please trim it to under {MAX_INPUT_LENGTH} characters and "
            "focus on the most important details.",
        )

    lowered = text.lower()

    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern in lowered:
            return (
                False,
                "I can only help with pet care planning. Please describe "
                "your pet (name, species, age, any medical or behavioral "
                "needs) and I'll build a schedule.",
            )

    if not _PET_KEYWORD_RE.search(lowered):
        return (
            False,
            "I didn't spot any pet-related words in that description. "
            "Try again with details about your dog, cat, bird, or other "
            "pet.",
        )

    return True, "ok"


# ---------------------------------------------------------------------------
# Layer 3 - Output guardrail (Pydantic schemas)
# ---------------------------------------------------------------------------

# 24-hour HH:MM, 00:00 - 23:59. Anchored on both ends so partial
# matches like "7:30am" or "1234" can't slip through.
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class TaskOutput(BaseModel):
    """Strict schema for a single task in the agent's final schedule.

    The agent's planner emits an additional ``pet_name`` field; Pydantic
    silently ignores it (default ``extra='ignore'``) because the output
    guardrail only cares about the canonical, user-facing fields.
    """

    description: str = Field(min_length=1)
    time: str
    duration_minutes: int = Field(ge=1, le=240)
    priority: Literal["low", "medium", "high"]
    # The legacy planner doesn't always emit `frequency`, so we default
    # to "once" rather than rejecting otherwise-valid schedules. The
    # value is still constrained to the literal set when present.
    frequency: Literal["once", "daily", "weekly"] = "once"

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be blank")
        return v

    @field_validator("time")
    @classmethod
    def _time_is_hhmm(cls, v: str) -> str:
        if not isinstance(v, str) or not _HHMM_RE.match(v):
            raise ValueError(
                f"time must be 24-hour HH:MM (00:00-23:59), got {v!r}"
            )
        return v


class ScheduleOutput(BaseModel):
    """Strict schema for a full schedule returned by the agent."""

    pet_name: str = Field(min_length=1)
    tasks: list[TaskOutput] = Field(min_length=1, max_length=15)

    @model_validator(mode="after")
    def _no_duplicate_tasks(self) -> "ScheduleOutput":
        """Reject schedules with two tasks sharing the SAME start time
        AND description (case-insensitive on description, exact on time).

        This is a deliberately narrow duplicate check - genuine overlap
        detection is the job of the tool-based guardrail. Here we only
        catch obvious "the model emitted the same task twice" mistakes.
        """
        seen: set[tuple[str, str]] = set()
        for idx, task in enumerate(self.tasks):
            key = (task.time, task.description.strip().lower())
            if key in seen:
                raise ValueError(
                    f"duplicate task at index {idx}: time={task.time!r} "
                    f"description={task.description!r}"
                )
            seen.add(key)
        return self


def _format_validation_error(exc: ValidationError) -> str:
    """Flatten a pydantic ``ValidationError`` into a single readable string.

    We surface this directly to the model in the revise retry, so a
    clean comma-joined list of "tasks[2].time: time must be 24-hour..."
    style messages works better than the multi-line default repr.
    """
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = err.get("msg", "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) if parts else str(exc)


def validate_schedule_output(
    raw_dict: dict,
) -> tuple[bool, Union[ScheduleOutput, str]]:
    """Validate a final schedule dict against ``ScheduleOutput``.

    Args:
        raw_dict: A dict shaped like
            ``{"pet_name": str, "tasks": [task_dict, ...]}``.

    Returns:
        ``(True, ScheduleOutput)`` on success.
        ``(False, error_message)`` on failure, with ``error_message``
        a single-line string suitable for logging or for feeding back
        into the reviser as a pseudo-conflict.
    """
    if not isinstance(raw_dict, dict):
        return False, f"expected a dict, got {type(raw_dict).__name__}"
    try:
        parsed = ScheduleOutput.model_validate(raw_dict)
    except ValidationError as exc:
        return False, _format_validation_error(exc)
    except (TypeError, ValueError) as exc:
        return False, str(exc)
    return True, parsed


# ---------------------------------------------------------------------------
# Shared guardrail event log (used by all three layers via the agent)
# ---------------------------------------------------------------------------

class AgentGuardrailLog:
    """Append-only record of every guardrail trigger during a run.

    Each event is stored as a plain dict with three keys:

      * ``timestamp`` - ISO-8601 second-resolution string.
      * ``type``      - short slug for the guardrail layer that fired
                        (e.g. ``"input_invalid"``, ``"conflict"``,
                        ``"output_invalid"``, ``"output_invalid_retry"``).
      * ``details``   - layer-specific dict with the trigger payload
                        (the rejection message, the conflict list, the
                        validation error, etc.).

    Plain dicts let the events round-trip through ``json.dumps`` so
    callers can render them in a UI or persist them as part of a trace.
    """

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def record(self, event_type: str, details: dict[str, Any] | None = None) -> None:
        """Append a single guardrail-trigger event to the log."""
        self._events.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "type": event_type,
                "details": dict(details or {}),
            }
        )

    @property
    def events(self) -> list[dict[str, Any]]:
        """Return a shallow copy of the recorded events list."""
        return list(self._events)

    def reset(self) -> None:
        """Clear the log. Called at the start of each agent run."""
        self._events.clear()

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self):
        return iter(self._events)
