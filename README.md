# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Smarter Scheduling

PawPal+ uses several algorithms to create intelligent daily plans:

**Priority-aware sorting** — Tasks are sorted by scheduled time first, then by priority level (high → medium → low) as a tiebreaker using Python's `sorted()` with a tuple key. This ensures that when two tasks share a time slot, the more urgent task always appears first.

**Duration-overlap conflict detection** — Instead of only flagging tasks with matching start times, the scheduler calculates each task's full time window (start + duration) and checks whether any two windows overlap. A 60-minute task starting at 11:30 correctly conflicts with a task at 12:00, even though their start times differ.

**Automatic recurring tasks** — When a daily or weekly task is marked complete, the scheduler uses Python's `timedelta` to calculate the next occurrence date (today + 1 day for daily, today + 7 days for weekly) and automatically creates a new task instance attached to the correct pet.

**Flexible filtering** — Tasks can be filtered by completion status or by pet name, allowing the owner to focus on specific views of their schedule.

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run the app

```bash
streamlit run app.py
```

### Run the CLI demo

```bash
python main.py
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.