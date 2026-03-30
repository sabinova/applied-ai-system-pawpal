"""
PawPal+ — CLI Demo Script
Temporary testing ground to verify backend logic in the terminal.
Run with: python main.py
"""

from pawpal_system import Task, Pet, Owner, Scheduler


def main():
    # --- Setup: Create Owner and Pets ---
    owner = Owner(name="Jordan")

    mochi = Pet(name="Mochi", species="dog", age=3)
    luna = Pet(name="Luna", species="cat", age=5)

    owner.add_pet(mochi)
    owner.add_pet(luna)

    # --- Add Tasks (intentionally out of order to test sorting) ---
    mochi.add_task(Task(
        description="Morning walk",
        time="07:00",
        duration_minutes=30,
        priority="high",
        frequency="daily",
    ))
    mochi.add_task(Task(
        description="Medication",
        time="12:00",
        duration_minutes=5,
        priority="high",
        frequency="daily",
    ))
    mochi.add_task(Task(
        description="Evening walk",
        time="18:00",
        duration_minutes=30,
        priority="medium",
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
    # This task intentionally conflicts with Mochi's medication at 12:00
    luna.add_task(Task(
        description="Vet appointment",
        time="12:00",
        duration_minutes=60,
        priority="high",
        frequency="once",
    ))

    # --- Initialize Scheduler ---
    scheduler = Scheduler(owner=owner)

    # --- Print Today's Schedule ---
    print(f"\n{'='*50}")
    print(f"  🐾 PawPal+ Daily Schedule for {owner.name}")
    print(f"{'='*50}\n")

    schedule = scheduler.get_daily_schedule()
    for task in schedule:
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.priority, "⚪")
        print(f"  {task.time}  {priority_icon} [{task.pet_name}] {task.description} ({task.duration_minutes} min)")

    # --- Detect Conflicts ---
    all_tasks = owner.get_all_tasks()
    conflicts = scheduler.detect_conflicts(all_tasks)
    if conflicts:
        print(f"\n{'─'*50}")
        print("  ⚠ Schedule Conflicts Detected:")
        for warning in conflicts:
            print(f"    {warning}")

    # --- Test Completing a Recurring Task ---
    print(f"\n{'─'*50}")
    print("  ✅ Completing Mochi's morning walk...\n")
    morning_walk = mochi.get_tasks()[0]
    scheduler.mark_task_complete(morning_walk)
    print(f"    Original task completed: {morning_walk.is_complete}")
    print(f"    Mochi's task count is now: {len(mochi.get_tasks())}")
    print(f"    (New recurring task was auto-created)\n")

    # --- Print Updated Schedule ---
    print(f"{'='*50}")
    print(f"  📋 Updated Schedule (after completing morning walk)")
    print(f"{'='*50}\n")

    updated_schedule = scheduler.get_daily_schedule()
    for task in updated_schedule:
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.priority, "⚪")
        print(f"  {task.time}  {priority_icon} [{task.pet_name}] {task.description} ({task.duration_minutes} min)")

    print()


if __name__ == "__main__":
    main()