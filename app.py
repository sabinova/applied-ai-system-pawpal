import streamlit as st
from pawpal_system import Task, Pet, Owner, Scheduler

# --- Page Configuration ---
st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")
st.caption("A smart pet care management system that helps you stay on top of your pet's daily routine.")

# --- Session State: Persistent "Memory" ---
if "owner" not in st.session_state:
    st.session_state.owner = Owner(name="")
    st.session_state.scheduler = Scheduler(owner=st.session_state.owner)

owner = st.session_state.owner
scheduler = st.session_state.scheduler

# --- Section 1: Owner Setup ---
st.subheader("👤 Owner Info")
owner_name = st.text_input("Your name", value=owner.name)
owner.name = owner_name

st.divider()

# --- Section 2: Add a Pet ---
st.subheader("🐶 Add a Pet")
with st.form("add_pet_form", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        pet_name = st.text_input("Pet name")
    with col2:
        species = st.selectbox("Species", ["dog", "cat", "bird", "fish", "other"])
    with col3:
        age = st.number_input("Age", min_value=0, max_value=30, value=1)

    add_pet = st.form_submit_button("Add Pet")

    if add_pet and pet_name:
        new_pet = Pet(name=pet_name, species=species, age=age)
        owner.add_pet(new_pet)
        st.success(f"Added {pet_name} the {species}!")

# Display current pets
if owner.pets:
    st.markdown("**Your pets:**")
    pet_display = []
    for pet in owner.pets:
        pet_display.append({
            "Name": pet.name,
            "Species": pet.species,
            "Age": pet.age,
            "Tasks": len(pet.get_tasks()),
        })
    st.table(pet_display)
else:
    st.info("No pets yet. Add one above!")

st.divider()

# --- Section 3: Add a Task ---
st.subheader("📋 Add a Task")

if owner.pets:
    with st.form("add_task_form", clear_on_submit=True):
        pet_names = [pet.name for pet in owner.pets]
        selected_pet_name = st.selectbox("Assign to pet", pet_names)

        col1, col2 = st.columns(2)
        with col1:
            task_desc = st.text_input("Task description", value="Morning walk")
            task_time = st.time_input("Scheduled time")
        with col2:
            duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
            priority = st.selectbox("Priority", ["high", "medium", "low"])

        frequency = st.selectbox("Frequency", ["once", "daily", "weekly"])

        add_task = st.form_submit_button("Add Task")

        if add_task and task_desc:
            time_str = task_time.strftime("%H:%M")
            new_task = Task(
                description=task_desc,
                time=time_str,
                duration_minutes=int(duration),
                priority=priority,
                frequency=frequency,
            )
            for pet in owner.pets:
                if pet.name == selected_pet_name:
                    pet.add_task(new_task)
                    st.success(f"Added '{task_desc}' for {selected_pet_name} at {time_str}!")
                    break
else:
    st.info("Add a pet first before scheduling tasks.")

st.divider()

# --- Section 4: Daily Schedule with Smart Features ---
st.subheader("📅 Today's Schedule")

# Filter controls — let the user narrow the view by pet
if owner.pets:
    filter_options = ["All Pets"] + [pet.name for pet in owner.pets]
    selected_filter = st.selectbox("Filter by pet", filter_options)

if st.button("Generate Schedule"):
    all_tasks = owner.get_all_tasks()

    # Apply pet filter if the user selected a specific pet
    if owner.pets and selected_filter != "All Pets":
        all_tasks = scheduler.filter_by_pet(all_tasks, selected_filter)

    # Get the sorted schedule (incomplete tasks only, sorted by time then priority)
    schedule = scheduler.sort_by_time(
        scheduler.filter_by_status(all_tasks, complete=False)
    )

    if schedule:
        # Build the schedule table with time windows and priority icons
        schedule_data = []
        for task in schedule:
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.priority, "⚪")
            schedule_data.append({
                "Time": f"{task.time} - {task.get_end_time()}",
                "Priority": priority_icon,
                "Pet": task.pet_name,
                "Task": task.description,
                "Duration": f"{task.duration_minutes} min",
                "Frequency": task.frequency,
            })
        st.table(schedule_data)

        # Run conflict detection on ALL incomplete tasks (not just filtered)
        pending_all = scheduler.filter_by_status(owner.get_all_tasks(), complete=False)
        conflicts = scheduler.detect_conflicts(pending_all)
        if conflicts:
            for warning in conflicts:
                st.warning(warning)
        else:
            st.success("No scheduling conflicts detected!")
    else:
        st.info("No pending tasks to display. Add some tasks above!")

st.divider()

# --- Section 5: Mark Tasks Complete ---
st.subheader("✅ Complete a Task")

if owner.pets:
    # Build a list of all incomplete tasks the user can mark as done
    incomplete_tasks = scheduler.filter_by_status(owner.get_all_tasks(), complete=False)

    if incomplete_tasks:
        # Create readable labels for the dropdown
        task_labels = [
            f"[{t.pet_name}] {t.time} — {t.description} ({t.frequency})"
            for t in incomplete_tasks
        ]
        selected_label = st.selectbox("Select a task to complete", task_labels)

        if st.button("Mark Complete"):
            # Find the matching task by its label index
            task_index = task_labels.index(selected_label)
            task_to_complete = incomplete_tasks[task_index]

            # Use the scheduler's smart completion (handles recurrence)
            scheduler.mark_task_complete(task_to_complete)

            # Show different messages based on whether recurrence was triggered
            if task_to_complete.frequency in ("daily", "weekly"):
                st.success(
                    f"Completed '{task_to_complete.description}'! "
                    f"A new {task_to_complete.frequency} task has been auto-scheduled."
                )
            else:
                st.success(f"Completed '{task_to_complete.description}'!")

            st.rerun()
    else:
        st.info("All tasks are complete! Great job! 🎉")

st.divider()

# --- Section 6: Completed Tasks Log ---
st.subheader("📜 Completed Tasks")
completed = scheduler.filter_by_status(owner.get_all_tasks(), complete=True)
if completed:
    completed_data = []
    for task in completed:
        completed_data.append({
            "Pet": task.pet_name,
            "Task": task.description,
            "Was scheduled": task.time,
            "Date": task.date,
        })
    st.table(completed_data)
else:
    st.caption("No completed tasks yet.")