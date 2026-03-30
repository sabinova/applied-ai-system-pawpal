"""
PawPal+ — Smart Pet Care Management System
Logic layer: all backend classes live here.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Task:
    """Represents a single pet care activity."""
    description: str
    time: str              # Format: "HH:MM" (24-hour)
    duration_minutes: int
    priority: str          # "low", "medium", or "high"
    pet_name: str = ""     # Tracks which pet this task belongs to
    frequency: str = "once"  # "once", "daily", or "weekly"
    is_complete: bool = False

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.is_complete = True


@dataclass
class Pet:
    """Stores pet details and a list of tasks."""
    name: str
    species: str
    age: int
    tasks: list = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Add a task to this pet's task list and stamp it with this pet's name."""
        task.pet_name = self.name
        self.tasks.append(task)

    def get_tasks(self) -> list:
        """Return all tasks for this pet."""
        return self.tasks


@dataclass
class Owner:
    """Manages multiple pets and provides access to all their tasks."""
    name: str
    pets: list = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner's pet list."""
        self.pets.append(pet)

    def get_all_tasks(self) -> list:
        """Retrieve all tasks across all pets."""
        all_tasks = []
        for pet in self.pets:
            all_tasks.extend(pet.get_tasks())
        return all_tasks


class Scheduler:
    """The 'Brain' that retrieves, organizes, and manages tasks across pets."""

    def __init__(self, owner: Owner):
        """Initialize the scheduler with an owner."""
        self.owner = owner

    def get_daily_schedule(self) -> list:
        """Return today's schedule: all incomplete tasks sorted by time."""
        all_tasks = self.owner.get_all_tasks()
        pending = self.filter_by_status(all_tasks, complete=False)
        return self.sort_by_time(pending)

    def sort_by_time(self, tasks: list) -> list:
        """Sort a list of tasks by their scheduled time using HH:MM comparison."""
        return sorted(tasks, key=lambda t: t.time)

    def filter_by_status(self, tasks: list, complete: bool = False) -> list:
        """Filter tasks by completion status."""
        return [t for t in tasks if t.is_complete == complete]

    def filter_by_pet(self, tasks: list, pet_name: str) -> list:
        """Filter tasks belonging to a specific pet."""
        return [t for t in tasks if t.pet_name == pet_name]

    def detect_conflicts(self, tasks: list) -> list:
        """Detect tasks scheduled at the same time. Returns warning messages."""
        warnings = []
        for i in range(len(tasks)):
            for j in range(i + 1, len(tasks)):
                if tasks[i].time == tasks[j].time:
                    warnings.append(
                        f"⚠ Conflict: '{tasks[i].description}' ({tasks[i].pet_name}) "
                        f"and '{tasks[j].description}' ({tasks[j].pet_name}) "
                        f"are both scheduled at {tasks[i].time}"
                    )
        return warnings

    def handle_recurring(self, task: Task):
        """If a task is daily/weekly, create a new instance for the next occurrence."""
        if task.frequency == "once":
            return None

        # Build new task with same details but reset completion
        new_task = Task(
            description=task.description,
            time=task.time,
            duration_minutes=task.duration_minutes,
            priority=task.priority,
            pet_name=task.pet_name,
            frequency=task.frequency,
            is_complete=False,
        )

        # Find the right pet and attach the new task
        for pet in self.owner.pets:
            if pet.name == task.pet_name:
                pet.add_task(new_task)
                return new_task

        return None

    def mark_task_complete(self, task: Task) -> None:
        """Complete a task and handle recurrence if daily/weekly."""
        task.mark_complete()
        if task.frequency in ("daily", "weekly"):
            self.handle_recurring(task)