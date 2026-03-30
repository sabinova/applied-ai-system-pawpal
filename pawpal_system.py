"""
PawPal+ — Smart Pet Care Management System
Logic layer: all backend classes live here.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, date


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
    date: str = ""         # Format: "YYYY-MM-DD" for recurring task tracking

    def __post_init__(self):
        """Auto-set today's date if no date is provided."""
        if not self.date:
            self.date = date.today().isoformat()

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.is_complete = True

    def get_end_time(self) -> str:
        """Calculate the end time based on start time and duration."""
        start = datetime.strptime(self.time, "%H:%M")
        end = start + timedelta(minutes=self.duration_minutes)
        return end.strftime("%H:%M")


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

    # Priority weight map: higher number = higher urgency = sorted first
    PRIORITY_WEIGHT = {"high": 0, "medium": 1, "low": 2}

    def __init__(self, owner: Owner):
        """Initialize the scheduler with an owner."""
        self.owner = owner

    def get_daily_schedule(self) -> list:
        """Return today's schedule: all incomplete tasks sorted by time, then priority."""
        all_tasks = self.owner.get_all_tasks()
        pending = self.filter_by_status(all_tasks, complete=False)
        return self.sort_by_time(pending)

    def sort_by_time(self, tasks: list) -> list:
        """Sort tasks by time first, then by priority (high before low) as tiebreaker.

        Uses a tuple key with lambda: (time_string, priority_weight).
        Since 'high' maps to 0 and 'low' maps to 2, high-priority tasks
        appear first when two tasks share the same time slot.
        """
        return sorted(
            tasks,
            key=lambda t: (t.time, self.PRIORITY_WEIGHT.get(t.priority, 1))
        )

    def filter_by_status(self, tasks: list, complete: bool = False) -> list:
        """Filter tasks by completion status."""
        return [t for t in tasks if t.is_complete == complete]

    def filter_by_pet(self, tasks: list, pet_name: str) -> list:
        """Filter tasks belonging to a specific pet."""
        return [t for t in tasks if t.pet_name == pet_name]

    def detect_conflicts(self, tasks: list) -> list:
        """Detect overlapping tasks using duration-aware time window comparison.

        Instead of only flagging exact time matches, this checks whether
        one task's start time falls within another task's time window.
        A task running from 11:30 for 60 minutes (ending 12:30) conflicts
        with a task starting at 12:00.
        """
        warnings = []
        for i in range(len(tasks)):
            for j in range(i + 1, len(tasks)):
                if self._tasks_overlap(tasks[i], tasks[j]):
                    warnings.append(
                        f"⚠ Conflict: '{tasks[i].description}' ({tasks[i].pet_name}, "
                        f"{tasks[i].time}-{tasks[i].get_end_time()}) overlaps with "
                        f"'{tasks[j].description}' ({tasks[j].pet_name}, "
                        f"{tasks[j].time}-{tasks[j].get_end_time()})"
                    )
        return warnings

    def _tasks_overlap(self, task_a: Task, task_b: Task) -> bool:
        """Check if two tasks' time windows overlap.

        Two windows overlap when each one starts before the other ends.
        Using datetime objects for accurate minute-level comparison.
        """
        a_start = datetime.strptime(task_a.time, "%H:%M")
        a_end = a_start + timedelta(minutes=task_a.duration_minutes)
        b_start = datetime.strptime(task_b.time, "%H:%M")
        b_end = b_start + timedelta(minutes=task_b.duration_minutes)

        # Overlap condition: A starts before B ends AND B starts before A ends
        return a_start < b_end and b_start < a_end

    def handle_recurring(self, task: Task):
        """Create a new task for the next occurrence using timedelta.

        Daily tasks get scheduled for tomorrow (today + 1 day).
        Weekly tasks get scheduled for next week (today + 7 days).
        The new task is automatically added to the correct pet.
        """
        if task.frequency == "once":
            return None

        # Calculate the next date using timedelta
        current_date = date.fromisoformat(task.date)
        if task.frequency == "daily":
            next_date = current_date + timedelta(days=1)
        elif task.frequency == "weekly":
            next_date = current_date + timedelta(days=7)
        else:
            return None

        # Build new task with the calculated next date
        new_task = Task(
            description=task.description,
            time=task.time,
            duration_minutes=task.duration_minutes,
            priority=task.priority,
            pet_name=task.pet_name,
            frequency=task.frequency,
            is_complete=False,
            date=next_date.isoformat(),
        )

        # Find the correct pet and attach the new task
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