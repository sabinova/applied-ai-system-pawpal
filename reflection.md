# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.
    - My UML design uses four classes. Task is the core data unit holding a description, scheduled time, duration, priority, frequency, and completion status. Pet stores pet info (name, species, age) and owns a list of Tasks. Owner holds the owner's name and a list of Pets, with a get_all_tasks() method that collects tasks across all pets. Scheduler is the behavioral "brain" — it takes an Owner reference and provides sorting, filtering, conflict detection, and recurring task logic. The relationships are: Owner has many Pets (one-to-many), each Pet has many Tasks (one-to-many), and the Scheduler manages one Owner (one-to-one). The Scheduler never stores its own copy of tasks — it always reaches through the Owner to get fresh data, preventing stale or out-of-sync task lists.
- What classes did you include, and what responsibilities did you assign to each?
    - The three core actions identified are:
        1. Add a pet to their profile — The owner should be able to register a pet with basic info like name, species, and age. This maps to `Owner.add_pet()`.
        2. Schedule a care task for a pet — The owner should be able to create tasks like walks, feedings, medications, or grooming appointments, each with a scheduled time, duration, and priority level. This maps to `Pet.add_task()`.
        3. View today's daily care schedule — The system should generate an organized daily plan that sorts and prioritizes all tasks across all pets, showing the owner what to do and when. This maps to `Scheduler.get_daily_schedule()`.

**b. Design changes**

- Did your design change during implementation?
    - Yes, the design changed during the skeleton review. I made two additions based on identifying potential logic bottlenecks.
- If yes, describe at least one change and why you made it.
    - First, I added a `pet_name` attribute to the Task class. The original design had no way to trace a Task back to the Pet it belonged to. This became a problem when I considered how `filter_by_pet()` would work — once the Scheduler collects all tasks into a flat list via `Owner.get_all_tasks()`, there was no field to check against a pet's name. Adding `pet_name` directly to the Task gives every task a built-in reference to its owner pet, keeping the filtering logic simple.
    - Second, I added a `mark_task_complete(task)` method to the Scheduler class. The original skeleton only had `mark_complete()` on the Task itself, which just flips a boolean. But the project requires recurring tasks to automatically generate a new instance when completed. If the user calls `task.mark_complete()` directly, the Scheduler never gets involved and recurrence is silently skipped. The new method acts as the proper entry point — it calls `task.mark_complete()` internally and then triggers `handle_recurring()` if the task is daily or weekly.
    - During Phase 4, I also added a `date` attribute and `get_end_time()` method to Task, a `_tasks_overlap()` private helper to Scheduler, and a `PRIORITY_WEIGHT` dictionary for the priority-aware sorting tiebreaker. These emerged naturally as I implemented the algorithmic layer and realized the initial skeleton needed richer data and behavior to support duration-based conflict detection and smart sorting.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
    - My scheduler considers three main constraints: scheduled time, priority level, and task duration. Time is the primary constraint because a daily care plan must follow chronological order — the owner needs to know what comes first. Priority acts as a secondary constraint, so when two tasks land at the same time slot, the high-priority task (like medication) surfaces before a low-priority one (like grooming). Duration feeds into conflict detection — the scheduler calculates each task's full time window (start time + duration) to determine if tasks physically overlap, not just if they start at the same moment.
- How did you decide which constraints mattered most?
    - I decided time mattered most because the core use case is a "what do I do next?" daily plan — chronological order is the most natural way a pet owner would think about their day. Priority mattered second because the consequences of missing tasks vary significantly: skipping a medication could affect a pet's health, while delaying a grooming session has minimal impact. Duration was essential for conflict detection because real-world tasks aren't just a point in time — a 60-minute vet appointment starting at 11:30 physically prevents you from starting a 12:00 feeding, and the scheduler needs to understand that.

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
    - My scheduler's conflict detection uses a nested loop that compares every pair of tasks (O(n²) time complexity) to find duration-based overlaps. This means if there are 10 tasks, the system makes 45 comparisons; if there are 20 tasks, it makes 190. A sorted-interval sweep algorithm would be faster at scale (O(n log n)), but the nested loop is far easier to read, debug, and maintain.
- Why is that tradeoff reasonable for this scenario?
    - This tradeoff is reasonable because a typical pet owner has 5 to 15 daily tasks, making the performance difference negligible — both algorithms complete instantly at that scale. Clarity and correctness are more valuable than speed when the dataset is small. If PawPal+ ever scaled to managing hundreds of tasks (e.g., a pet daycare facility), I would refactor to the more efficient approach, but for a single household the simplicity of the nested loop makes the code easier to understand and less prone to bugs.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
    - I used AI tools throughout all six phases of the project. During Phase 1 (System Design), I used AI to brainstorm the attributes and methods for each class and to generate the Mermaid.js UML diagram. During Phase 2 (Core Implementation), AI helped flesh out the method logic — particularly the data flow pattern where the Scheduler reaches through the Owner to access tasks across all pets. During Phase 4 (Algorithmic Layer), I used AI to implement the duration-overlap conflict detection algorithm using the interval overlap formula (`a_start < b_end and b_start < a_end`) and the `timedelta`-based recurring task logic. For Phase 5 (Testing), AI helped generate a comprehensive 19-test pytest suite covering happy paths and edge cases across all system behaviors.
- What kinds of prompts or questions were most helpful?
    - The most helpful prompts were specific and contextual — grounded in the actual code rather than abstract. For example, asking "Based on my skeletons in `pawpal_system.py`, how should the Scheduler retrieve all tasks from the Owner's pets?" produced a clear, actionable data flow design. Asking for a "lightweight conflict detection strategy that returns a warning message rather than crashing the program" steered the implementation toward user-friendly warning strings instead of exceptions. Prompts that asked AI to review existing code for bottlenecks (like the skeleton review in Phase 1) were especially valuable because they helped me catch structural gaps before they became implementation bugs.

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
    - During the skeleton review in Phase 1, the initial AI-generated design had no `pet_name` field on the Task class and no `mark_task_complete()` method on the Scheduler. While the skeleton looked correct in isolation, I identified these gaps by mentally tracing the data flow end-to-end — asking myself "how would `filter_by_pet()` actually work if a Task doesn't know which Pet it belongs to?" and "what triggers recurrence if the user calls `task.mark_complete()` directly instead of going through the Scheduler?" These were structural bottlenecks that only became visible when I considered how the classes would interact at runtime, not by reading any single class on its own.
- How did you evaluate or verify what the AI suggested?
    - I evaluated the AI's suggestions by testing them against the project requirements. The README states that the app should let users filter tasks by pet and handle recurring tasks automatically — both of those features would silently fail without the `pet_name` field and the `mark_task_complete()` orchestrator. I verified the fixes by running the CLI demo script (`main.py`) in the terminal and confirming that filtering returned correct results and that completing a daily task actually generated a new instance with tomorrow's date. The CLI-first workflow was essential here because it let me validate backend logic independently before connecting it to the Streamlit UI.

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
    - The automated test suite covers 19 tests across six groups: task basics (completion status flipping, default date auto-assignment via `__post_init__`, and end-time calculation both within and crossing hour boundaries), pet-task linking (task count increases on addition, `pet_name` auto-stamping when a task is added to a pet, and cross-pet aggregation via `Owner.get_all_tasks()`), sorting correctness (chronological ordering regardless of insert order, and priority-based tiebreaking where high-priority tasks appear before low-priority ones at the same time), recurrence logic (daily tasks create a new instance dated tomorrow, weekly tasks add 7 days, and one-time tasks produce no recurrence), conflict detection (exact start-time matches flagged, duration-based overlaps detected even when start times differ, and no false positives for non-overlapping tasks), and edge cases (empty schedule returns an empty list, filtering by a non-existent pet name returns empty, and completed tasks are excluded from the daily schedule).
- Why were these tests important?
    - These tests were important because they verify every layer of the system independently, from basic data operations up through algorithmic intelligence. The sorting and conflict tests are especially critical because they validate the core scheduling logic that the entire user experience depends on — if sorting breaks, the owner sees a scrambled plan, and if conflict detection misses an overlap, the owner might double-book their time. The edge case tests protect against silent failures that could confuse users even if the core algorithms work perfectly.

**b. Confidence**

- How confident are you that your scheduler works correctly?
    - I'm fairly confident — I'd rate it 4 out of 5 stars. The 19 tests cover all happy paths and the most important edge cases, and every test passes consistently. The CLI demo script also serves as an integration test that exercises the full data flow from object creation through scheduling output.
- What edge cases would you test next if you had more time?
    - If I had more time, I would test tasks that span midnight (e.g., a task starting at 23:30 with a 60-minute duration — does `get_end_time()` handle the day rollover correctly?), multi-day scheduling where tasks from different dates need to be filtered or separated, duplicate task handling (adding the same task description to the same pet twice at the same time), and stress testing the conflict detection with a large number of overlapping tasks to verify it remains accurate.

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?
    - I'm most satisfied with the CLI-first workflow and the clean separation between backend logic and UI. Building and verifying all the scheduling logic in `main.py` before touching Streamlit meant that when I connected the UI in Phase 3, everything worked immediately — there was no debugging of "is the bug in my logic or in my UI code?" because the logic was already proven correct in the terminal. The modular architecture (with `pawpal_system.py` as the logic layer and `app.py` as the presentation layer) made each phase feel incremental rather than overwhelming.

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?
    - If I had another iteration, I would add data persistence using JSON so that pets and tasks survive between app restarts — currently, closing the Streamlit server loses all data because everything lives in `st.session_state` (in-memory only). I would also add the ability to edit or delete tasks after they've been created, since right now you can only add and complete them. Finally, I would improve the conflict detection to suggest resolution options — instead of just warning "these tasks overlap," the scheduler could recommend moving one task to the next available time slot, making it a true scheduling assistant.

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
    - The most important thing I learned is that being the "lead architect" when collaborating with AI means you are responsible for the system design decisions, not the AI. AI is excellent at generating code that implements a given design, but it doesn't automatically catch structural gaps like missing data relationships or broken data flow paths. The skeleton review in Phase 1 — where I identified the missing `pet_name` field and `mark_task_complete()` method — was driven by my own mental trace of how the classes would interact at runtime. AI provided the building blocks, but I had to verify that they fit together correctly. The lesson is: always trace the data flow end-to-end before trusting that generated code will work as a system, because individual pieces can look correct in isolation while hiding integration problems.