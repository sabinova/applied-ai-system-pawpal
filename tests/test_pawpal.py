"""
PawPal+ — Automated Test Suite
Run with: python -m pytest
"""

import sys
import os

# Add project root to path so we can import pawpal_system
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pawpal_system import Task, Pet, Owner, Scheduler


def test_task_completion():
    """Verify that calling mark_complete() changes the task's status to True."""
    task = Task(
        description="Morning walk",
        time="07:00",
        duration_minutes=30,
        priority="high",
    )
    # Task should start as incomplete
    assert task.is_complete is False

    # After marking complete, status should flip to True
    task.mark_complete()
    assert task.is_complete is True


def test_task_addition():
    """Verify that adding a task to a Pet increases that pet's task count."""
    pet = Pet(name="Mochi", species="dog", age=3)

    # Pet starts with zero tasks
    assert len(pet.get_tasks()) == 0

    # Adding one task should increase count to 1
    pet.add_task(Task(
        description="Morning walk",
        time="07:00",
        duration_minutes=30,
        priority="high",
    ))
    assert len(pet.get_tasks()) == 1

    # Adding a second task should increase count to 2
    pet.add_task(Task(
        description="Feeding",
        time="08:00",
        duration_minutes=10,
        priority="high",
    ))
    assert len(pet.get_tasks()) == 2