import streamlit as st
from pawpal_system import Task, Pet, Owner, Scheduler

# --- Page Configuration ---
st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")
st.caption("A smart pet care management system that helps you stay on top of your pet's daily routine.")

# --- Session State: Persistent "Memory" ---
# This block only runs once on the first page load.
# On every subsequent rerun (button click, form submit, etc.),
# Streamlit finds these keys already in session_state and skips creation.
if "owner" not in st.session_state:
    st.session_state.owner = Owner(name="")
    st.session_state.scheduler = Scheduler(owner=st.session_state.owner)

# Shortcuts for cleaner code below
owner = st.session_state.owner
scheduler = st.session_state.scheduler

# --- Section 1: Owner Setup ---
st.subheader("👤 Owner Info")
owner_name = st.text_input("Your name", value=owner.name)
# Update the owner's name whenever the text input changes
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
        # Create a Pet object and attach it to the Owner
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
        # Let the user pick which pet this task is for
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
            # Convert the time_input object to "HH:MM" string format
            time_str = task_time.strftime("%H:%M")

            # Create the Task object
            new_task = Task(
                description=task_desc,
                time=time_str,
                duration_minutes=int(duration),
                priority=priority,
                frequency=frequency,
            )

            # Find the selected pet and add the task to it
            for pet in owner.pets:
                if pet.name == selected_pet_name:
                    pet.add_task(new_task)
                    st.success(f"Added '{task_desc}' for {selected_pet_name} at {time_str}!")
                    break
else:
    st.info("Add a pet first before scheduling tasks.")

st.divider()

# --- Section 4: Daily Schedule ---
st.subheader("📅 Today's Schedule")

if st.button("Generate Schedule"):
    schedule = scheduler.get_daily_schedule()

    if schedule:
        # Display the sorted schedule as a formatted table
        schedule_data = []
        for task in schedule:
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.priority, "⚪")
            schedule_data.append({
                "Time": task.time,
                "Priority": priority_icon,
                "Pet": task.pet_name,
                "Task": task.description,
                "Duration": f"{task.duration_minutes} min",
                "Frequency": task.frequency,
            })
        st.table(schedule_data)

        # Check for conflicts and show warnings
        all_tasks = owner.get_all_tasks()
        conflicts = scheduler.detect_conflicts(all_tasks)
        if conflicts:
            for warning in conflicts:
                st.warning(warning)
        else:
            st.success("No scheduling conflicts detected!")
    else:
        st.info("No tasks scheduled yet. Add some tasks above!")