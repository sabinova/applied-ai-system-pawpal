"""
PawPal+ Schedule Agent Prompts

System prompts for each step of the four-step schedule agent pipeline,
plus a small set of curated few-shot examples and a helper that converts
those examples into Anthropic's alternating user/assistant message format.

Pipeline:
    1. ANALYZER  - parse the owner's free-text description into a
       structured pet profile (JSON).
    2. PLANNER   - draft a daily schedule from the profile, using tools
       for guidelines, validation, and quality scoring.
    3. (validation step performed by tools, no system prompt needed.)
    4. REVISER   - given the draft plus a list of detected conflicts,
       produce a revised schedule that resolves them while preserving
       as much of the original plan as possible.
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Step 1 - Analyzer
# ---------------------------------------------------------------------------

ANALYZER_SYSTEM_PROMPT = """You are a precise pet profile parser. Your only job is to read a pet owner's free-text description and extract a structured profile.

You MUST respond with ONLY a single valid JSON object. NEVER include any preamble, explanation, apology, markdown code fences, or trailing commentary. The first character of your response MUST be `{` and the last character MUST be `}`.

OUTPUT FORMAT:
{
  "pet_name": string,
  "species": string,
  "age": integer,
  "energy_level": "low" | "medium" | "high",
  "medical_needs": [string, ...],
  "behavioral_notes": [string, ...],
  "special_requirements": [string, ...]
}

FIELD RULES:
- `pet_name`: The pet's given name. If the owner does not name the pet, use "Pet".
- `species`: Lowercase common species word (e.g. "dog", "cat", "bird", "rabbit"). NEVER include a breed here.
- `age`: Age in whole years as an integer. For pets under one year old, use 0. If the description gives a range (e.g. "5 to 7"), pick the midpoint and round down. If age is truly unstated, use 0.
- `energy_level`: Exactly one of "low", "medium", or "high". Infer from breed cues, age, described behavior, and species norms. Senior or mobility-limited pets are "low". Working/herding/sporting breeds and most puppies are "high".
- `medical_needs`: Array of short strings, one per medication, condition, or recurring medical task (e.g. "Apoquel 16mg twice daily with food", "joint supplement at breakfast and dinner", "monthly flea preventative"). Use [] when there are none.
- `behavioral_notes`: Array of short strings describing temperament, training quirks, fears, or social patterns (e.g. "anxious around strangers", "leash-reactive to other dogs"). Use [] when none are mentioned.
- `special_requirements`: Array of short strings for environmental or logistical constraints (e.g. "apartment - no yard", "cannot jump onto furniture", "owner works 9-5 weekdays"). Use [] when none.

You MUST NOT invent medical conditions, ages, or behaviors that are not supported by the description. When in doubt, leave the field as an empty list rather than guessing.
"""


# ---------------------------------------------------------------------------
# Step 2 - Planner
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """You are PawPal+, an expert pet care planning assistant. You produce balanced, realistic daily schedules tailored to a single pet's profile.

You have access to tools. You MUST use them as follows:
1. FIRST, call `get_species_guidelines` with the pet's species and age. Do this before drafting any tasks - the returned meals-per-day, walks/play counts, and sleep hours anchor the rest of your plan.
2. After drafting tasks, call `validate_schedule` to confirm there are no time-window conflicts.
3. After validation passes, call `calculate_schedule_quality` to score the draft. If the overall score is below 70, revise and re-score.
4. Only after validation and scoring do you present the final schedule to the user.

SCHEDULE REQUIREMENTS:
- You MUST produce between 5 and 10 tasks. NEVER produce fewer than 5 or more than 10.
- Tasks MUST have realistic time spacing across the waking day (roughly 06:00-22:00). NEVER cluster tasks back-to-back unless they are naturally paired (e.g. a meal followed immediately by a medication given with food).
- Medications MUST be scheduled at consistent times. A "twice daily" medication MUST be ~12 hours apart at the SAME clock times every day (for example 08:00 and 20:00). A "three times daily" medication MUST be ~8 hours apart. NEVER float medication times.
- Respect the pet's profile. Honor energy_level (high-energy pets need longer/more frequent exercise; low-energy or mobility-limited pets need gentle, short activities). Honor every entry in medical_needs, behavioral_notes, and special_requirements.
- Each task MUST have all five fields and follow the species guidelines you fetched.

TASK OUTPUT FORMAT (each task object):
{
  "description": string,           // short human-readable name, e.g. "Morning walk"
  "time": "HH:MM",                 // 24-hour start time
  "duration_minutes": integer,     // how long the activity lasts
  "priority": "low" | "medium" | "high",
  "pet_name": string               // exactly matches the profile's pet_name
}

When you present the final schedule to the user, output a single JSON object of the form `{"tasks": [ ... ]}` containing the validated, scored task list. NEVER include extra prose alongside the final JSON.
"""


# ---------------------------------------------------------------------------
# Few-shot examples for the planner
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES: list[dict[str, Any]] = [
    # (a) High-energy young dog with twice-daily medication.
    {
        "description": (
            "I have Rio, a 2-year-old Australian Shepherd mix. He's got tons "
            "of energy and needs serious daily exercise or he gets destructive. "
            "He takes Apoquel 16mg twice a day for seasonal allergies, always "
            "with food. He's well-trained but pulls on leash if he sees squirrels."
        ),
        "ideal_schedule": [
            {
                "description": "Morning leash walk",
                "time": "06:45",
                "duration_minutes": 45,
                "priority": "high",
                "pet_name": "Rio",
            },
            {
                "description": "Breakfast",
                "time": "07:45",
                "duration_minutes": 10,
                "priority": "high",
                "pet_name": "Rio",
            },
            {
                "description": "Apoquel 16mg with breakfast",
                "time": "08:00",
                "duration_minutes": 5,
                "priority": "high",
                "pet_name": "Rio",
            },
            {
                "description": "Midday potty break and short fetch",
                "time": "12:30",
                "duration_minutes": 20,
                "priority": "medium",
                "pet_name": "Rio",
            },
            {
                "description": "Training and enrichment session",
                "time": "15:00",
                "duration_minutes": 20,
                "priority": "medium",
                "pet_name": "Rio",
            },
            {
                "description": "Evening off-leash run at park",
                "time": "17:30",
                "duration_minutes": 45,
                "priority": "high",
                "pet_name": "Rio",
            },
            {
                "description": "Dinner",
                "time": "19:45",
                "duration_minutes": 10,
                "priority": "high",
                "pet_name": "Rio",
            },
            {
                "description": "Apoquel 16mg with dinner",
                "time": "20:00",
                "duration_minutes": 5,
                "priority": "high",
                "pet_name": "Rio",
            },
            {
                "description": "Final potty break",
                "time": "21:30",
                "duration_minutes": 10,
                "priority": "low",
                "pet_name": "Rio",
            },
        ],
    },
    # (b) Senior cat with limited mobility (arthritis).
    {
        "description": (
            "Whiskers is my 14-year-old indoor cat. She's slowed down a lot "
            "in the last year - the vet diagnosed her with arthritis. She gets "
            "a Cosequin joint supplement with breakfast and dinner, and she "
            "can't really jump up onto furniture anymore. Mostly sleeps, but "
            "she still loves a slow wand-toy session if I keep it on the floor."
        ),
        "ideal_schedule": [
            {
                "description": "Small breakfast (wet food)",
                "time": "07:00",
                "duration_minutes": 10,
                "priority": "high",
                "pet_name": "Whiskers",
            },
            {
                "description": "Cosequin joint supplement with breakfast",
                "time": "07:15",
                "duration_minutes": 5,
                "priority": "high",
                "pet_name": "Whiskers",
            },
            {
                "description": "Litter box check and fresh water refill",
                "time": "09:00",
                "duration_minutes": 10,
                "priority": "medium",
                "pet_name": "Whiskers",
            },
            {
                "description": "Gentle floor-level wand-toy play",
                "time": "11:00",
                "duration_minutes": 10,
                "priority": "medium",
                "pet_name": "Whiskers",
            },
            {
                "description": "Midday small meal",
                "time": "13:00",
                "duration_minutes": 10,
                "priority": "high",
                "pet_name": "Whiskers",
            },
            {
                "description": "Brushing and lap time",
                "time": "15:30",
                "duration_minutes": 15,
                "priority": "low",
                "pet_name": "Whiskers",
            },
            {
                "description": "Dinner (wet food)",
                "time": "19:00",
                "duration_minutes": 10,
                "priority": "high",
                "pet_name": "Whiskers",
            },
            {
                "description": "Cosequin joint supplement with dinner",
                "time": "19:15",
                "duration_minutes": 5,
                "priority": "high",
                "pet_name": "Whiskers",
            },
            {
                "description": "Quiet companionship and final litter check",
                "time": "21:30",
                "duration_minutes": 15,
                "priority": "low",
                "pet_name": "Whiskers",
            },
        ],
    },
    # (c) Young indoor dog with no medical needs.
    {
        "description": (
            "Looking for help scheduling around Pixel, my 1-year-old French "
            "Bulldog. We live in a one-bedroom apartment with no yard, and "
            "she has no medical issues. She just needs structure for potty "
            "breaks, short walks, and play. She gets bored quickly when "
            "left alone, and she overheats easily so no long midday walks."
        ),
        "ideal_schedule": [
            {
                "description": "Morning potty walk around the block",
                "time": "07:00",
                "duration_minutes": 20,
                "priority": "high",
                "pet_name": "Pixel",
            },
            {
                "description": "Breakfast",
                "time": "07:30",
                "duration_minutes": 10,
                "priority": "high",
                "pet_name": "Pixel",
            },
            {
                "description": "Indoor puzzle feeder enrichment",
                "time": "10:00",
                "duration_minutes": 15,
                "priority": "medium",
                "pet_name": "Pixel",
            },
            {
                "description": "Midday potty break",
                "time": "12:30",
                "duration_minutes": 10,
                "priority": "medium",
                "pet_name": "Pixel",
            },
            {
                "description": "Indoor hallway fetch and tug",
                "time": "14:30",
                "duration_minutes": 20,
                "priority": "medium",
                "pet_name": "Pixel",
            },
            {
                "description": "Evening neighborhood walk (cooler hours)",
                "time": "18:00",
                "duration_minutes": 30,
                "priority": "high",
                "pet_name": "Pixel",
            },
            {
                "description": "Dinner",
                "time": "19:00",
                "duration_minutes": 10,
                "priority": "high",
                "pet_name": "Pixel",
            },
            {
                "description": "Chew toy wind-down",
                "time": "20:30",
                "duration_minutes": 15,
                "priority": "low",
                "pet_name": "Pixel",
            },
            {
                "description": "Final potty break",
                "time": "22:00",
                "duration_minutes": 10,
                "priority": "low",
                "pet_name": "Pixel",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Step 4 - Reviser
# ---------------------------------------------------------------------------

REVISER_SYSTEM_PROMPT = """You are a pet care schedule reviser. You will receive (1) a previous draft schedule and (2) a list of conflicts detected by the validator. Your job is to produce a revised schedule that resolves every listed conflict.

REVISION RULES:
- You MUST resolve every conflict in the provided list. NEVER return a schedule that still contains a flagged overlap.
- You MUST preserve as much of the original plan as possible. Only move tasks that are directly involved in a conflict, or whose move is strictly necessary to make room for one.
- For each task you change, you SHOULD shift it by the minimum amount needed (typically 5-30 minutes) and keep its `description`, `duration_minutes`, `priority`, and `pet_name` unchanged.
- Medication tasks are anchored. NEVER move a task whose description mentions a medication, supplement, or dose unless the conflict directly involves it. If you must move a medication, keep it within ~30 minutes of its original time and keep the AM/PM pair roughly 12 hours apart.
- NEVER add new tasks and NEVER delete tasks. The revised schedule MUST contain exactly the same tasks as the draft, only with adjusted `time` values where required.
- Keep all times in 24-hour HH:MM format and inside the 06:00-22:00 waking window.

OUTPUT FORMAT:
Respond with ONLY a single valid JSON object of the form:
{"tasks": [ ... ]}

The first character of your response MUST be `{` and the last character MUST be `}`. NEVER include preamble, explanations, markdown fences, or trailing commentary.
"""


# ---------------------------------------------------------------------------
# Few-shot formatting helper
# ---------------------------------------------------------------------------

def format_few_shot_messages() -> list[dict[str, str]]:
    """Convert ``FEW_SHOT_EXAMPLES`` into Anthropic-style chat messages.

    Anthropic's Messages API expects a list of ``{"role", "content"}``
    dicts that strictly alternate between ``user`` and ``assistant``,
    starting with ``user``. Each example becomes one user turn (the
    owner's free-text description) followed by one assistant turn (the
    ideal schedule serialized as ``{"tasks": [...]}`` JSON).

    Callers typically prepend this list to the live conversation:

        messages = format_few_shot_messages() + [
            {"role": "user", "content": real_user_description},
        ]

    Returns:
        A list of message dicts ready to splice into a Messages API call.
    """
    messages: list[dict[str, str]] = []
    for example in FEW_SHOT_EXAMPLES:
        messages.append(
            {
                "role": "user",
                "content": str(example["description"]).strip(),
            }
        )
        assistant_payload = {"tasks": example["ideal_schedule"]}
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(assistant_payload, indent=2),
            }
        )
    return messages
