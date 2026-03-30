"""
PawPal+ — CLI Demo Script (Phase 4: Algorithmic Layer)
Demonstrates sorting, filtering, conflict detection, and recurring tasks.
Run with: python main.py
"""

from pawpal_system import Task, Pet, Owner, Scheduler


def main():
    # --- Setup: Create Owner and Pets ---
    owner = Owner(name="SabinaR")

    mochi = Pet(name="Mochi", species="dog", age=3)
    luna = Pet(name="Luna", species="cat", age=5)

    owner.add_pet(mochi)
    owner.add_pet(luna)

    # --- Add Tasks (intentionally out of order to test sorting) ---
    # Tasks added in scrambled time order to prove sorting works
    mochi.add_task(Task(
        description="Evening walk",
        time="18:00",
        duration_minutes=30,
        priority="medium",
        frequency="daily",
    ))
    mochi.add_task(Task(
        description="Morning walk",
        time="07:00",
        duration_minutes=30,
        priority="high",
        frequency="daily",
    ))
    # This task starts at 11:30 and runs 60 minutes (ends at 12:30)
    # It should overlap with Luna's vet appointment at 12:00
    mochi.add_task(Task(
        description="Medication + feeding",
        time="11:30",
        duration_minutes=60,
        priority="high",
        frequency="daily",
    ))

    luna.add_task(Task(
        description="Breakfast feeding",
        time="08:00",
        duration_minutes=10,
        priority="high",
        frequency="daily",
    ))
    luna.add_task(Task(
        description="Grooming",
        time="14:00",
        duration_minutes=20,
        priority="low",
        frequency="weekly",
    ))
    # This task at 12:00 overlaps with Mochi's 11:30-12:30 medication window
    luna.add_task(Task(
        description="Vet appointment",
        time="12:00",
        duration_minutes=60,
        priority="high",
        frequency="once",
    ))
    # Same time as grooming (14:00) but different priority — tests priority sorting
    luna.add_task(Task(
        description="Enrichment play",
        time="14:00",
        duration_minutes=15,
        priority="high",
        frequency="daily",
    ))

    # --- Initialize Scheduler ---
    scheduler = Scheduler(owner=owner)

    # ============================
    # TEST 1: Smart Sorting
    # ============================
    print(f"\n{'='*55}")
    print(f"  🐾 PawPal+ Daily Schedule for {owner.name}")
    print(f"{'='*55}\n")

    schedule = scheduler.get_daily_schedule()
    for task in schedule:
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.priority, "⚪")
        end = task.get_end_time()
        print(f"  {task.time}-{end}  {icon} [{task.pet_name}] {task.description} ({task.duration_minutes} min)")

    # Notice at 14:00: Enrichment play (high) appears BEFORE Grooming (low)
    # This proves priority-based secondary sorting works

    # ============================
    # TEST 2: Filtering by Pet
    # ============================
    print(f"\n{'─'*55}")
    print(f"  🔍 Filtered: Only Mochi's tasks")
    print(f"{'─'*55}\n")

    all_tasks = owner.get_all_tasks()
    mochi_tasks = scheduler.filter_by_pet(all_tasks, "Mochi")
    for task in scheduler.sort_by_time(mochi_tasks):
        print(f"  {task.time}  [{task.pet_name}] {task.description}")

    # ============================
    # TEST 3: Duration-Overlap Conflict Detection
    # ============================
    print(f"\n{'─'*55}")
    print(f"  ⚠ Conflict Detection (Duration-Aware)")
    print(f"{'─'*55}\n")

    conflicts = scheduler.detect_conflicts(all_tasks)
    if conflicts:
        for warning in conflicts:
            print(f"    {warning}")
    else:
        print("    No conflicts detected.")

    # Key test: Mochi's 11:30-12:30 medication should overlap with
    # Luna's 12:00-13:00 vet appointment, even though they don't
    # share the exact same start time. Old logic would miss this!

    # ============================
    # TEST 4: Recurring Tasks with timedelta
    # ============================
    print(f"\n{'─'*55}")
    print(f"  🔄 Recurring Task Test (timedelta)")
    print(f"{'─'*55}\n")

    morning_walk = mochi.get_tasks()[1]  # Morning walk (daily)
    print(f"    Before: Morning walk date = {morning_walk.date}")
    print(f"    Before: Mochi's task count = {len(mochi.get_tasks())}")

    scheduler.mark_task_complete(morning_walk)

    # The new recurring task should have tomorrow's date
    new_task = mochi.get_tasks()[-1]  # Last task = the newly created one
    print(f"\n    After completing daily task:")
    print(f"    Original completed: {morning_walk.is_complete}")
    print(f"    New task date: {new_task.date} (tomorrow)")
    print(f"    New task completed: {new_task.is_complete}")
    print(f"    Mochi's task count = {len(mochi.get_tasks())}")

    # ============================
    # TEST 5: Filtering by Status
    # ============================
    print(f"\n{'─'*55}")
    print(f"  ✅ Filtering: Completed vs Pending tasks")
    print(f"{'─'*55}\n")

    all_tasks = owner.get_all_tasks()
    completed = scheduler.filter_by_status(all_tasks, complete=True)
    pending = scheduler.filter_by_status(all_tasks, complete=False)
    print(f"    Completed tasks: {len(completed)}")
    print(f"    Pending tasks:   {len(pending)}")

    print()


if __name__ == "__main__":
    main()