# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.
    - My UML design uses four classes. Task is the core data unit holding a description, scheduled time, duration, priority, frequency, and completion status. Pet stores pet info (name, species, age) and owns a list of Tasks. Owner holds the owner's name and a list of Pets, with a get_all_tasks() method that collects tasks across all pets. Scheduler is the behavioral "brain" — it takes an Owner reference and provides sorting, filtering, conflict detection, and recurring task logic.
- What classes did you include, and what responsibilities did you assign to each?
    - The three core classes identified are: 
        1. Add a pet to their profile — The owner should be able to register a pet with basic info like name, species, and age.
        2.  Schedule a care task for a pet — The owner should be able to create tasks like walks, feedings, medications, or grooming appointments, each with a scheduled time, duration, and priority level.
        3. View today's daily care schedule — The system should generate an organized daily plan that sorts and prioritizes all tasks across all pets, showing the owner what to do and when.

**b. Design changes**

- Did your design change during implementation?
    - Yes, the design changed during the skeleton review. I made two additions based on identifying potential logic bottlenecks.
- If yes, describe at least one change and why you made it.
    - First, I added a pet_name attribute to the Task class. The original design had no way to trace a Task back to the Pet it belonged to. This became a problem when I considered how filter_by_pet() would work — once the Scheduler collects all tasks into a flat list via Owner.get_all_tasks(), there was no field to check against a pet's name. Adding pet_name directly to the Task gives every task a built-in reference to its owner pet, keeping the filtering logic simple.
    - Second, I added a mark_task_complete(task) method to the Scheduler class. The original skeleton only had mark_complete() on the Task itself, which just flips a boolean. But the project requires recurring tasks to automatically generate a new instance when completed. If the user calls task.mark_complete() directly, the Scheduler never gets involved and recurrence is silently skipped. The new method acts as the proper entry point — it calls task.mark_complete() internally and then triggers handle_recurring() if the task is daily or weekly.
---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
    - My scheduler considers three main constraints: scheduled time, priority level, and task duration. Time is the primary constraint because a daily care plan must follow chronological order — the owner needs to know what comes first. Priority acts as a secondary constraint, so when two tasks land at the same time slot, the high-priority task (like medication) surfaces before a low-priority one (like grooming). Duration feeds into conflict detection — the scheduler calculates each task's full time window (start time + duration) to determine if tasks physically overlap, not just if they start at the same moment. I decided time mattered most because the core use case is a "what do I do next?" daily plan, and priority mattered second because missing a medication is more consequential than skipping an enrichment activity.
- How did you decide which constraints mattered most?
    - My scheduler's conflict detection uses a nested loop that compares every pair of tasks (O(n²) time complexity) to find duration-based overlaps. This means if there are 10 tasks, the system makes 45 comparisons; if there are 20 tasks, it makes 190. The tradeoff is performance versus simplicity — a sorted-interval sweep algorithm would be faster at scale (O(n log n)), but the nested loop is far easier to read, debug, and maintain. This tradeoff is reasonable because a typical pet owner has 5 to 15 daily tasks, making the performance difference negligible. Clarity and correctness are more valuable than speed at this scale.

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
