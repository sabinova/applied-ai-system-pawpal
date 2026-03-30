"""
PawPal+ — Automated Test Suite (Phase 5)
Covers: sorting correctness, recurrence logic, conflict detection,
        task-pet linking, and edge cases.
Run with: python -m pytest tests/test_pawpal.py -v
"""

import sys
import os
from datetime import date, timedelta

# Add project root to path so we can import pawpal_system
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pawpal_system import Task, Pet, Owner, Scheduler


# ============================================================
# Helper: quickly build a test environment with owner + pets
# ============================================================
def create_test_setup():
    """Create a fresh Owner, two Pets, and a Scheduler for testing."""
    owner = Owner(name="TestOwner")
    dog = Pet(name="Buddy", species="dog", age=3)
    cat = Pet(name="Whiskers", species="cat", age=5)
    owner.add_pet(dog)
    owner.add_pet(cat)
    scheduler = Scheduler(owner=owner)
    return owner, dog, cat, scheduler


# ============================================================
# TEST GROUP 1: Task Basics
# ============================================================

def test_task_completion():
    """Verify that mark_complete() flips is_complete from False to True."""
    task = Task(description="Walk", time="07:00", duration_minutes=30, priority="high")

    # Task should start as incomplete
    assert task.is_complete is False

    task.mark_complete()

    # After marking, it should be True
    assert task.is_complete is True


def test_task_default_date():
    """Verify that a Task auto-sets today's date if none is provided."""
    task = Task(description="Feed", time="08:00", duration_minutes=10, priority="high")

    # The __post_init__ method should stamp today's date
    assert task.date == date.today().isoformat()


def test_task_end_time():
    """Verify get_end_time() correctly calculates start + duration."""
    task = Task(description="Walk", time="07:00", duration_minutes=45, priority="high")

    # 07:00 + 45 minutes = 07:45
    assert task.get_end_time() == "07:45"


def test_task_end_time_crosses_hour():
    """Verify get_end_time() handles crossing an hour boundary."""
    task = Task(description="Grooming", time="11:45", duration_minutes=30, priority="low")

    # 11:45 + 30 minutes = 12:15
    assert task.get_end_time() == "12:15"


# ============================================================
# TEST GROUP 2: Pet and Task Linking
# ============================================================

def test_task_addition_increases_count():
    """Verify that adding a task to a Pet increases that pet's task count."""
    pet = Pet(name="Buddy", species="dog", age=3)

    assert len(pet.get_tasks()) == 0

    pet.add_task(Task(description="Walk", time="07:00", duration_minutes=30, priority="high"))
    assert len(pet.get_tasks()) == 1

    pet.add_task(Task(description="Feed", time="08:00", duration_minutes=10, priority="high"))
    assert len(pet.get_tasks()) == 2


def test_pet_stamps_name_on_task():
    """Verify that add_task() auto-stamps the pet's name onto the task."""
    pet = Pet(name="Buddy", species="dog", age=3)
    task = Task(description="Walk", time="07:00", duration_minutes=30, priority="high")

    # Before adding, pet_name is empty
    assert task.pet_name == ""

    pet.add_task(task)

    # After adding, pet_name should match the pet
    assert task.pet_name == "Buddy"


def test_owner_get_all_tasks():
    """Verify get_all_tasks() collects tasks from all pets into one list."""
    owner, dog, cat, _ = create_test_setup()

    dog.add_task(Task(description="Walk", time="07:00", duration_minutes=30, priority="high"))
    dog.add_task(Task(description="Feed", time="08:00", duration_minutes=10, priority="high"))
    cat.add_task(Task(description="Groom", time="14:00", duration_minutes=20, priority="low"))

    all_tasks = owner.get_all_tasks()

    # Should have 3 tasks total across both pets
    assert len(all_tasks) == 3


# ============================================================
# TEST GROUP 3: Sorting Correctness
# ============================================================

def test_sort_by_time_chronological():
    """Verify tasks are returned in chronological order regardless of insert order."""
    _, dog, _, scheduler = create_test_setup()

    # Add tasks deliberately out of order
    dog.add_task(Task(description="Evening walk", time="18:00", duration_minutes=30, priority="medium"))
    dog.add_task(Task(description="Morning walk", time="07:00", duration_minutes=30, priority="high"))
    dog.add_task(Task(description="Lunch feed", time="12:00", duration_minutes=10, priority="high"))

    sorted_tasks = scheduler.sort_by_time(dog.get_tasks())

    # Times should be in ascending order
    assert sorted_tasks[0].time == "07:00"
    assert sorted_tasks[1].time == "12:00"
    assert sorted_tasks[2].time == "18:00"


def test_sort_by_priority_tiebreaker():
    """Verify that tasks at the same time are sorted high > medium > low."""
    _, dog, _, scheduler = create_test_setup()

    # Three tasks at the same time with different priorities
    dog.add_task(Task(description="Grooming", time="14:00", duration_minutes=20, priority="low"))
    dog.add_task(Task(description="Medication", time="14:00", duration_minutes=5, priority="high"))
    dog.add_task(Task(description="Play", time="14:00", duration_minutes=15, priority="medium"))

    sorted_tasks = scheduler.sort_by_time(dog.get_tasks())

    # All at 14:00, but high should come first, then medium, then low
    assert sorted_tasks[0].priority == "high"
    assert sorted_tasks[1].priority == "medium"
    assert sorted_tasks[2].priority == "low"


# ============================================================
# TEST GROUP 4: Recurrence Logic
# ============================================================

def test_daily_recurrence_creates_new_task():
    """Verify marking a daily task complete creates a new task for the next day."""
    _, dog, _, scheduler = create_test_setup()

    dog.add_task(Task(
        description="Morning walk", time="07:00",
        duration_minutes=30, priority="high", frequency="daily",
    ))

    assert len(dog.get_tasks()) == 1

    # Complete the daily task via the scheduler
    original_task = dog.get_tasks()[0]
    scheduler.mark_task_complete(original_task)

    # Should now have 2 tasks: original (completed) + new (pending)
    assert len(dog.get_tasks()) == 2
    assert original_task.is_complete is True
    assert dog.get_tasks()[-1].is_complete is False


def test_daily_recurrence_date_is_tomorrow():
    """Verify the new recurring task's date is exactly one day ahead."""
    _, dog, _, scheduler = create_test_setup()

    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    dog.add_task(Task(
        description="Feed", time="08:00",
        duration_minutes=10, priority="high", frequency="daily",
    ))

    task = dog.get_tasks()[0]
    assert task.date == today

    scheduler.mark_task_complete(task)

    new_task = dog.get_tasks()[-1]
    # New task should be scheduled for tomorrow
    assert new_task.date == tomorrow


def test_weekly_recurrence_date_is_next_week():
    """Verify weekly recurrence adds 7 days to the task date."""
    _, _, cat, scheduler = create_test_setup()

    today = date.today()
    next_week = (today + timedelta(days=7)).isoformat()

    cat.add_task(Task(
        description="Grooming", time="14:00",
        duration_minutes=20, priority="low", frequency="weekly",
    ))

    task = cat.get_tasks()[0]
    scheduler.mark_task_complete(task)

    new_task = cat.get_tasks()[-1]
    assert new_task.date == next_week


def test_once_task_no_recurrence():
    """Verify that completing a one-time task does NOT create a new task."""
    _, dog, _, scheduler = create_test_setup()

    dog.add_task(Task(
        description="Vet visit", time="10:00",
        duration_minutes=60, priority="high", frequency="once",
    ))

    assert len(dog.get_tasks()) == 1

    scheduler.mark_task_complete(dog.get_tasks()[0])

    # Count should still be 1 — no new task created
    assert len(dog.get_tasks()) == 1


# ============================================================
# TEST GROUP 5: Conflict Detection
# ============================================================

def test_detect_exact_time_conflict():
    """Verify two tasks at the exact same time are flagged as a conflict."""
    owner, dog, cat, scheduler = create_test_setup()

    dog.add_task(Task(description="Walk", time="07:00", duration_minutes=30, priority="high"))
    cat.add_task(Task(description="Feed", time="07:00", duration_minutes=10, priority="high"))

    conflicts = scheduler.detect_conflicts(owner.get_all_tasks())

    assert len(conflicts) == 1
    assert "Conflict" in conflicts[0]


def test_detect_duration_overlap_conflict():
    """Verify overlapping time windows are flagged even without matching start times.

    Task A: 11:30 - 12:30 (60 min)
    Task B: 12:00 - 13:00 (60 min)
    These overlap by 30 minutes even though start times differ.
    """
    owner, dog, cat, scheduler = create_test_setup()

    dog.add_task(Task(description="Long feeding", time="11:30", duration_minutes=60, priority="high"))
    cat.add_task(Task(description="Vet visit", time="12:00", duration_minutes=60, priority="high"))

    conflicts = scheduler.detect_conflicts(owner.get_all_tasks())

    assert len(conflicts) == 1
    assert "overlap" in conflicts[0].lower()


def test_no_conflict_when_tasks_dont_overlap():
    """Verify non-overlapping tasks produce zero warnings.

    Task A: 07:00 - 07:30 (30 min)
    Task B: 08:00 - 08:10 (10 min)
    These don't overlap — 30 minute gap between them.
    """
    owner, dog, cat, scheduler = create_test_setup()

    dog.add_task(Task(description="Walk", time="07:00", duration_minutes=30, priority="high"))
    cat.add_task(Task(description="Feed", time="08:00", duration_minutes=10, priority="high"))

    conflicts = scheduler.detect_conflicts(owner.get_all_tasks())

    assert len(conflicts) == 0


# ============================================================
# TEST GROUP 6: Edge Cases
# ============================================================

def test_schedule_with_no_tasks():
    """Verify get_daily_schedule() returns empty list when no tasks exist."""
    _, _, _, scheduler = create_test_setup()

    schedule = scheduler.get_daily_schedule()
    assert schedule == []


def test_filter_by_pet_no_match():
    """Verify filtering by a non-existent pet name returns an empty list."""
    owner, dog, _, scheduler = create_test_setup()

    dog.add_task(Task(description="Walk", time="07:00", duration_minutes=30, priority="high"))

    result = scheduler.filter_by_pet(owner.get_all_tasks(), "NonExistentPet")
    assert result == []


def test_daily_schedule_excludes_completed():
    """Verify get_daily_schedule() only returns incomplete tasks."""
    _, dog, _, scheduler = create_test_setup()

    dog.add_task(Task(description="Walk", time="07:00", duration_minutes=30, priority="high"))
    dog.add_task(Task(description="Feed", time="08:00", duration_minutes=10, priority="high"))

    # Complete one task directly
    dog.get_tasks()[0].mark_complete()

    schedule = scheduler.get_daily_schedule()

    # Only the incomplete task should appear
    assert len(schedule) == 1
    assert schedule[0].description == "Feed"