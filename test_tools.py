"""Quick smoke test for agent.tools.validate_schedule.

Run with:  python test_validate_schedule.py

Feeds the function two hand-built schedules - one with an overlap and one
clean - and prints the returned dicts so we can eyeball the behaviour.
"""

from __future__ import annotations

import json

from agent.tools import validate_schedule
from agent.tools import get_species_guidelines, calculate_schedule_quality


def _show(label: str, tasks: list[dict]) -> None:
    """Run validate_schedule and pretty-print the result under a header."""
    print(f"\n=== {label} ===")
    print("Input tasks:")
    for t in tasks:
        print(f"  - {t['time']} ({t['duration_minutes']}m) "
              f"{t['description']} [{t['priority']}] for {t['pet_name']}")
    result = validate_schedule(tasks)
    print("Result:")
    # ensure_ascii=True so the ⚠ character in conflict strings prints fine
    # on Windows consoles that default to cp1252.
    print(json.dumps(result, indent=2))


# Module-level fixtures so both main() and the trailing smoke tests
# (calculate_schedule_quality, etc.) can reuse them.
overlapping_tasks: list[dict] = [
    {
        "description": "Morning walk",
        "time": "08:00",
        "duration_minutes": 30,
        "priority": "high",
        "pet_name": "Buddy",
    },
    {
        "description": "Vet phone call",
        "time": "11:30",
        "duration_minutes": 60,  # ends at 12:30 -> overlaps next task
        "priority": "medium",
        "pet_name": "Buddy",
    },
    {
        "description": "Lunch feeding",
        "time": "12:00",
        "duration_minutes": 15,
        "priority": "high",
        "pet_name": "Buddy",
    },
]

clean_tasks: list[dict] = [
    {
        "description": "Morning walk",
        "time": "08:00",
        "duration_minutes": 30,
        "priority": "high",
        "pet_name": "Buddy",
    },
    {
        "description": "Lunch feeding",
        "time": "12:00",
        "duration_minutes": 15,
        "priority": "high",
        "pet_name": "Buddy",
    },
    {
        "description": "Evening play",
        "time": "18:00",
        "duration_minutes": 20,
        "priority": "medium",
        "pet_name": "Buddy",
    },
]


def main() -> None:
    _show("Case 1: overlapping schedule (expect has_conflicts=True)", overlapping_tasks)
    _show("Case 2: clean schedule (expect has_conflicts=False)", clean_tasks)


print("\n=== get_species_guidelines smoke test ===")
print("Adult dog:", get_species_guidelines("dog", 3))
print("Puppy (case-insensitive):", get_species_guidelines("DOG", 0))
print("Unknown species:", get_species_guidelines("hamster", 2))

print("\n=== calculate_schedule_quality (well-spaced, mixed priorities) ===")
print(json.dumps(calculate_schedule_quality(clean_tasks), indent=2))

print("\n=== calculate_schedule_quality (clustered, single priority) ===")
clustered = [
    {"description": f"Task {i}", "time": f"14:{i*2:02d}",
     "duration_minutes": 5, "priority": "high", "pet_name": "Buddy"}
    for i in range(5)
]
print(json.dumps(calculate_schedule_quality(clustered), indent=2))

if __name__ == "__main__":
    main()
