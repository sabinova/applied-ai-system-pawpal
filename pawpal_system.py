"""
PawPal+ — Smart Pet Care Management System
Logic layer: all backend classes live here.
"""

from dataclasses import dataclass, field


@dataclass
class Task:
    """Represents a single pet care activity."""
    description: str
    time: str  # Format: "HH:MM" (24-hour)
    duration_minutes: int
    priority: str  # "low", "medium", or "high"
    frequency: str = "once"  # "once", "daily", or "weekly"
    is_complete: bool = False

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        pass


@dataclass
class Pet:
    """Stores pet details and a list of tasks."""
    name: str
    species: str
    age: int
    tasks: list = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Add a task to this pet's task list."""
        pass

    def get_tasks(self) -> list:
        """Return all tasks for this pet."""
        pass


@dataclass
class Owner:
    """Manages multiple pets and provides access to all their tasks."""
    name: str
    pets: list = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner's pet list."""
        pass

    def get_all_tasks(self) -> list:
        """Retrieve all tasks across all pets."""
        pass


class Scheduler:
    """The 'Brain' that retrieves, organizes, and manages tasks across pets."""

    def __init__(self, owner: Owner):
        """Initialize the scheduler with an owner."""
        self.owner = owner

    def get_daily_schedule(self) -> list:
        """Return today's schedule: all tasks sorted by time."""
        pass

    def sort_by_time(self, tasks: list) -> list:
        """Sort a list of tasks by their scheduled time."""
        pass

    def filter_by_status(self, tasks: list, complete: bool = False) -> list:
        """Filter tasks by completion status."""
        pass

    def filter_by_pet(self, tasks: list, pet_name: str) -> list:
        """Filter tasks belonging to a specific pet."""
        pass

    def detect_conflicts(self, tasks: list) -> list:
        """Detect tasks scheduled at the same time. Returns warning messages."""
        pass

    def handle_recurring(self, task: Task):
        """If a task is daily/weekly, create a new instance for the next occurrence."""
        pass