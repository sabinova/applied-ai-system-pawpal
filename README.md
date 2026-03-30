# 🐾 PawPal+ (Module 2 Project)

**PawPal+** is a smart pet care management system built with Python OOP and Streamlit. It helps busy pet owners stay consistent with daily care routines by tracking tasks, detecting scheduling conflicts, and automatically managing recurring activities.

## 📸 Demo

<img src='/PawPal_demo.gif' title='PawPal App' width='' alt='PawPal App' class='center-block' /></a>

## Features

**Owner and Pet Management** — Register your name, add multiple pets with species and age info, and see a live summary table of all your pets and their task counts.

**Task Scheduling** — Create care tasks (walks, feeding, meds, grooming, enrichment) with a scheduled time, duration, priority level (high/medium/low), and frequency (once/daily/weekly). Tasks are assigned to specific pets and tracked in session memory.

**Priority-Aware Sorting** — The daily schedule sorts tasks by time first, then by priority as a tiebreaker using Python's `sorted()` with a tuple key. When two tasks share a time slot, the high-priority task always surfaces first.

**Duration-Overlap Conflict Detection** — Instead of only matching exact start times, the scheduler calculates each task's full time window (start + duration) and flags overlapping windows. A 60-minute task at 11:30 correctly conflicts with a task at 12:00, even though their start times differ.

**Automatic Recurring Tasks** — When a daily or weekly task is marked complete, the scheduler uses Python's `timedelta` to calculate the next occurrence date and automatically creates a new task instance attached to the correct pet.

**Flexible Filtering** — View tasks for all pets or filter by a specific pet using the dropdown. Tasks can also be filtered by completion status.

**Task Completion with Recurrence** — Mark tasks complete directly from the UI. Daily and weekly tasks automatically regenerate for their next scheduled date, with a confirmation message showing what was created.

**Completed Tasks Log** — A running log of all completed tasks with their pet name, description, scheduled time, and date.

## Smarter Scheduling

PawPal+ uses several algorithms to create intelligent daily plans. Tasks are sorted by scheduled time first, then by priority level (high → medium → low) as a tiebreaker. The conflict detection system calculates each task's full time window and checks whether any two windows overlap, catching conflicts that simple start-time matching would miss. When a daily or weekly task is marked complete, the scheduler uses `timedelta` to calculate the exact next occurrence date (today + 1 day for daily, today + 7 days for weekly) and auto-creates a new task. Tasks can be filtered by completion status or by pet name for focused schedule views.

## Testing PawPal+

The project includes an automated test suite with 19 tests covering all core behaviors.

```bash
python -m pytest tests/test_pawpal.py -v
```

The tests verify task completion and default date assignment, pet-task linking and auto-stamping of `pet_name`, chronological sorting with priority-based tiebreaking, daily and weekly recurrence logic using `timedelta` (confirming correct next-occurrence dates), duration-aware conflict detection (overlapping windows, exact matches, and no false positives), and edge cases like empty schedules, non-existent pet filtering, and completed task exclusion.

**Confidence Level: ⭐⭐⭐⭐ (4/5)** — The suite covers all happy paths and key edge cases. The one area that would benefit from more testing is multi-day scheduling scenarios and tasks that span midnight.

## Getting Started

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

### Run tests

```bash
python -m pytest tests/test_pawpal.py -v
```

## Project Structure

```
pawpal-starter/
├── app.py                  # Streamlit UI (frontend)
├── pawpal_system.py        # Backend logic layer (Owner, Pet, Task, Scheduler)
├── main.py                 # CLI demo script for terminal verification
├── requirements.txt        # Python dependencies
├── reflection.md           # Project reflection and AI collaboration notes
├── uml_final.md            # Final Mermaid.js UML class diagram
├── README.md               # This file
└── tests/
    └── test_pawpal.py      # Automated pytest suite (19 tests)
```