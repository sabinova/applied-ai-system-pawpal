# 🐾 PawPal+ Smart Schedule Generator — Model Card

> Companion document to [`README.md`](README.md). Per the assignment rubric, this card describes the system's intended use, limitations, and an honest record of what was built, what broke, and what's still rough.

---

## 1. System Overview

**PawPal+ Smart Schedule Generator** is an agentic Python system that turns a free-text description of a pet into a balanced, conflict-free daily schedule. It exposes a Streamlit UI (`app.py`) and a CLI smoke test (`demo_agent.py`) on top of a four-step LLM pipeline (`agent/schedule_agent.py`):

1. **Analyze** — strict-JSON pet profile extraction
2. **Plan** — agentic tool-use loop with three deterministic tools
3. **Validate** — duration-aware conflict detection (delegates to the legacy `Scheduler.detect_conflicts`)
4. **Revise** — targeted repair of any detected conflicts (≤ 3 rounds)

The reasoning model is **Anthropic's `claude-sonnet-4-5`**, called via the official `anthropic` Python SDK with structured tool-use (`agent/tools.py` defines `validate_schedule`, `get_species_guidelines`, `calculate_schedule_quality`). The output is type-checked by Pydantic models in `agent/validators.py` (`TaskOutput`, `ScheduleOutput`) before it ever reaches the legacy persistence layer (`Owner`, `Pet`, `Task`, `Scheduler` in `pawpal_system.py`).

---

## 2. Intended Use

Daily-routine planning for **hobbyist pet owners** managing one healthy companion animal at home. Typical user: a dog/cat/bird owner who wants a starting-point schedule for meals, walks, play, and routine medications based on a one-paragraph description.

The system is intended as a **planning aid**, not a clinical or operational system. The output is meant to be reviewed by the owner before acting on it.

---

## 3. Out-of-Scope Uses

This system is **not** appropriate for:

- **Veterinary or medical advice.** It does not diagnose conditions, prescribe medications, or determine dosages. Medication times in the output reflect the cadence the *user* described, never anything the model invented.
- **Emergency medical decisions.** If a pet shows symptoms of distress, contact a veterinarian. The agent has no access to live vital data and cannot triage.
- **Unusual or exotic species.** `get_species_guidelines` only returns curated defaults for `dog`, `cat`, and `bird`. Anything else falls back to a generic `unknown` marker; schedules for reptiles, amphibians, fish, livestock, or wild animals should not be trusted.
- **Multi-pet households with complex interactions** (e.g., cat-dog feeding-time conflicts in shared spaces). The agent reasons about one pet at a time.
- **High-stakes professional settings** — kennels, shelters, breeders, working-dog programs. The output is a starting draft, not a regulated care plan.

---

## 4. Inputs & Outputs

**Input** — a single string (`description`) passed to `ScheduleAgent.generate_schedule()`:

| Constraint | Value |
|---|---|
| Type | `str` (UTF-8) |
| Length | 15 – 1500 characters |
| Language | English (untested on others) |
| Required content | Must contain at least one whole-word match from `SPECIES_KEYWORDS`, `BREED_KEYWORDS`, or `PET_CARE_KEYWORDS` |
| Forbidden content | Substring matches against `PROMPT_INJECTION_PATTERNS` (`"ignore previous"`, `"system prompt"`, `"you are now"`) |

**Output** — a dict with the following shape (validated by `ScheduleOutput`):

```jsonc
{
  "pet_profile": { "pet_name": str, "species": str, "age": int, "energy_level": "low|medium|high",
                   "medical_needs": [str], "behavioral_notes": [str], "special_requirements": [str] },
  "tasks": [
    { "description": str (≥1 char),
      "time": "HH:MM" (24-hour, 00:00-23:59),
      "duration_minutes": int (1–240),
      "priority": "low|medium|high",
      "frequency": "once|daily|weekly",
      "pet_name": str }
    // 1–15 items, no duplicate (time, description) pairs
  ],
  "steps": [...],            // typed reasoning trace
  "iterations": int,
  "success": bool,
  "guardrail_events": [...]
}
```

If any guardrail fails, `success` is `False`, `tasks` is `[]`, and `error` carries a human-readable message.

---

## 5. Architecture Summary

The agent sits between a Streamlit input form and the legacy `pawpal_system.py` persistence classes. A user description is gated by `validate_user_input`, expanded into a typed pet profile by the analyzer, drafted into 5–10 tasks by an Anthropic tool-use loop, hardened by a deterministic conflict re-check with up to three revise rounds, and finally type-checked by a Pydantic schema before reaching the legacy `Owner / Pet / Task / Scheduler` graph. See [`assets/system_architecture.png`](assets/system_architecture.png) for the full flow and [`README.md`](README.md#-system-architecture) for the prose walkthrough.

---

## 6. Limitations & Biases

1. **Few-shot examples bias the planner toward dog-first thinking.** `agent/prompts.py`'s few-shot set leans on canine scenarios (high-energy young dogs, multi-need rescues). Cat and bird drafts may inherit dog-shaped pacing (e.g., over-emphasis on "walks" framing) even though species guidelines correct for it.
2. **English-only.** The input regex, the prompt-injection list, and the system prompts all assume English. Non-English descriptions are likely to fail the keyword guardrail or produce English-language tasks regardless.
3. **Assumes a single, standard 24-hour day.** Tasks are bucketed inside a roughly 06:00–22:00 waking window. The agent does not model night-shift owners, polyphasic schedules, daylight-saving transitions, or owners in different time zones from their pet sitter.
4. **The LLM may hallucinate species-specific facts despite tool guidance.** `get_species_guidelines` only covers `dog`, `cat`, `bird`. For anything else the planner has only its training-data prior, which is not vetted. Even for supported species, the model can occasionally invent breed-specific quirks the user never described.
5. **Quality scoring is heuristic, not validated.** `calculate_schedule_quality` rewards activity spacing, priority balance, and density on hand-picked thresholds (4-hour spread, 12-task ceiling, etc.). It has *not* been validated against expert veterinary or behavioral opinion — a schedule scoring 100 is internally consistent, not professionally endorsed.
6. **Input guardrail is permissive by design.** Pet vocabulary (`leash`, `walks`, `vet`) accepts any English description that *sounds* pet-related; it does not verify the described animal is actually present, healthy, or owned by the user.
7. **No memory across sessions.** Every run is independent. Re-submitting yesterday's description does not yield yesterday's schedule; the agent does not learn the owner's preferences over time.

---

## 7. Potential Misuse

| Misuse | Risk |
|---|---|
| Substituting agent output for a veterinary consultation | Could delay treatment of real medical conditions; the model has no diagnostic ability. |
| Asking the agent to schedule activity for a sick or post-operative pet | The system has no awareness of recovery contraindications and may suggest exertion levels that are unsafe. |
| Generating schedules for animals outside the supported species set (livestock, reptiles, fish, wildlife) | Falls back to the model's untested prior; outputs should not be trusted. |
| Using the schedule to enforce strict feeding/medication timing for animals where flexibility matters (e.g., diabetic pets needing precise dosing tied to glucose) | The agent does not model glycemic curves or any other physiological feedback loop. |
| Bypassing guardrails through clever phrasing to elicit non-pet content | Mitigated but not eliminated — see Safeguards below. |

---

## 8. Safeguards

Three independent guardrail layers, all logged to `AgentGuardrailLog` and surfaced on `result["guardrail_events"]`:

| # | Layer | Code path | Catches |
|---|---|---|---|
| 1 | **Input** | `validators.validate_user_input` | Empty / `< 15` / `> 1500` chars; descriptions with no whole-word match against `SPECIES_KEYWORDS ∪ BREED_KEYWORDS ∪ PET_CARE_KEYWORDS`; substring hits on `PROMPT_INJECTION_PATTERNS` |
| 2 | **Tool** | `tools.validate_schedule` + `ScheduleAgent`'s revise loop (≤ 3 rounds) | Duration-aware time-window overlaps; the conflict list is fed verbatim into the reviser as a structured fix-it prompt |
| 3 | **Output** | `validators.ScheduleOutput` (Pydantic) + `validate_schedule_output` | Bad `HH:MM`, `duration_minutes` outside 1–240, priority/frequency outside the literal sets, blank descriptions, duplicate `(time, description)` pairs, `< 1` or `> 15` tasks. On failure: **one** revise retry, then fail closed. |

Layer 1 runs *before* the first LLM call (cost: 0 tokens). Layer 3 runs *after* the planner finishes and is the last gate before anything reaches the legacy `Pet.tasks` list.

---

## 9. AI Collaboration During Development

I built this on top of my Module 2 PawPal+ codebase with extensive use of Cursor's AI agent (Claude). A few moments are worth recording honestly:

### One helpful AI suggestion I accepted

The Streamlit app's *own* recommended example — "Rio is my 2-year-old Australian Shepherd…" — was being rejected by the input guardrail. I expected an API-key issue; the AI instead traced the rejection to `agent/validators.py`, where the original `PET_KEYWORDS` was a 10-word list (`pet, dog, cat, bird, fish, rabbit, hamster, animal, puppy, kitten`) and "Australian Shepherd" matched none of them as whole words. The proposed fix split the list into three labeled buckets — `SPECIES_KEYWORDS`, `BREED_KEYWORDS`, `PET_CARE_KEYWORDS` — and merged them back into `PET_KEYWORDS` for backwards compatibility, while keeping the `\b…\b` whole-word matcher and the `PROMPT_INJECTION_PATTERNS` list untouched. I accepted this because it (a) actually fixed a demo-blocking bug, (b) made the keyword categorization visible in the code instead of hiding it as a magic blob, and (c) didn't loosen the security check. The regression is now pinned by `tests/test_agent.py::test_validate_user_input_*`.

### One flawed AI suggestion I rejected

While reviewing the agent loop, the AI also suggested adding a `PetTask`-style Pydantic model **inside** `_step_plan_with_tools` so the planner could schema-validate tasks the moment the LLM returned them — and trigger the JSON retry-once helper from there. I didn't apply it. Coupling schema validation into the planner would have meant the same retry helper was now responsible for two unrelated failure modes (malformed JSON *and* schema mismatch), and the planner step would have become a confusing mix of tool-use orchestration and schema repair. Instead, when I later built the validators (`agent/validators.py`), I pushed schema validation out to a **separate third guardrail layer** (`ScheduleOutput` + `validate_schedule_output`) that runs *after* the planner finishes, with its own one-revise-retry and a fail-closed terminal. The result is cleaner separation of concerns, a single observable place where output-shape problems show up (`guardrail_events[type="output_invalid"]`), and a planner step that stays focused on tool-use orchestration.

### How I used AI for prompts / debugging / design

- **Prompt drafting:** Iterated `ANALYZER_SYSTEM_PROMPT`, `PLANNER_SYSTEM_PROMPT`, and `REVISER_SYSTEM_PROMPT` with the AI as a sounding board — landing on the firm "MUST / NEVER" register, the explicit "first character `{`, last character `}`" contract for the analyzer, and the medication-anchoring rule in the reviser.
- **Code review of AI-generated code:** Used the AI to audit my own agent loop against three classic failure modes (does it actually loop until `stop_reason != "tool_use"`? do `tool_result` blocks echo back the right `tool_use_id`? does JSON parsing have a retry path?). The third check surfaced a real gap and produced the `_retry_json_call` helper that's now used by the analyzer, planner, and reviser.
- **Debugging:** When the validator false-rejected its own demo input, I pasted the failing description back into Cursor and asked it to trace exactly which branch fired before any LLM call — much faster than I would have done by inserting prints.
- **Heuristic design:** Brainstormed the three quality dimensions (`activity_spacing`, `priority_balance`, `realistic_density`) and stress-tested the thresholds (4-hour spread, 12-task ceiling) against hand-built edge cases before committing them.
- **Documentation:** Generated the Mermaid sources for `assets/system_architecture.png` and `assets/uml_class_diagram.png`, plus drafts of the README and this model card.

---

## 10. Testing Summary

### Unit tests — `pytest tests/ -v`

**39 tests pass in 0.21 s.** Split:

| File | Count | Focus |
|---|---|---|
| `tests/test_pawpal.py` | 19 | Legacy logic — `Task`, `Pet`, `Owner`, `Scheduler.sort_by_time`, `detect_conflicts`, `handle_recurring`, recurrence date math |
| `tests/test_agent.py` | 20 | `validate_user_input` (6 paths), `validate_schedule_output` (4 paths), each tool's contract (3 + 4 + 3 paths). All LLM calls are mocked via `unittest.mock.patch`. |

### Integration evaluation — `python -m evaluation.run_evaluation`

Latest run on `claude-sonnet-4-5` with `max_iterations=8`:

| Result | Value |
|---|---|
| **Cases passed** | **8 / 8** |
| Average quality score (6 non-adversarial) | **100.0** |
| Adversarial cases blocked at the input guardrail | 2 / 2 (0 tokens spent) |
| Slowest case | `case_05_budgie_social` — 6 planner iterations, self-revised 89 → 100 on quality feedback |

**What passed:** every realistic-pet case produced 5–10 tasks, no time conflicts, the right medication cadence (1× / 2× daily), and all required keyword categories. Both adversarial cases (too-short input, prompt-injection attempt) were rejected by Layer 1 before any LLM call.

**What I learned:**
- Giving the model a small deterministic feedback signal (`calculate_schedule_quality` returns numeric scores *and* a free-text feedback list) caused the planner to self-improve mid-run on `case_05` — a much stronger result than longer system prompts alone produced.
- The original 10-word `PET_KEYWORDS` list false-rejected the app's own "Australian Shepherd" example. The fix (split into species / breed / pet-care buckets while keeping whole-word matching) is now covered by `tests/test_agent.py` so it can't regress silently.
- The `validate_schedule` tool's reuse of `Scheduler.detect_conflicts` paid off: I never had to debug "why does the agent think this conflicts but the UI doesn't?" — both call the same code.

---

## 11. What Surprised Me

- **A 3-line feedback list moved the model more than a 60-line prompt.** On `case_05_budgie_social`, the planner first emitted a draft that scored 89 — passable, but `calculate_schedule_quality` returned `feedback: ["missing priority tier: low"]`. With no extra prompting, on the next iteration the model re-balanced priorities and pushed the score to 100. A tiny deterministic signal applied at the right moment did more than several rounds of system-prompt tightening had.
- **Most of the work was *not* the LLM call.** Roughly 80% of the code I wrote — input validation, Pydantic schemas, the conflict tool, the quality tool, the guardrail event log, the reasoning-trace plumbing in `app.py`, the eval harness, the JSON-retry helper — sits *around* the three actual `messages.create` calls. The model is a small, well-bounded component in a much bigger reliability surface. That ratio was not what I expected going in.
- **The guardrail rejected its own demo example.** Watching the app reject the very description it was suggesting to the user was humbling — guardrails aren't only there to stop bad input, they can themselves *be* a bug. After that, I started treating guardrail failures the same way I'd treat a 500: log them, regression-test them, and make the failing input a fixture (`test_validate_user_input_*`).
- **Schema validation on the way out caught more real issues than the conflict detector did.** I'd assumed time-overlap would be the dominant failure mode. In practice, the `ScheduleOutput` layer caught more — non-`HH:MM` time strings (e.g. `"7:30am"`), missing `pet_name`, and very occasionally a duplicate task — than `validate_schedule` ever flagged on a real run.

---

## 12. Future Improvements

1. **Cross-session memory.** Persist `pet_profile` and the last accepted schedule per pet so re-runs build on prior context instead of starting cold. A small SQLite store keyed on `pet_name` would be enough; the agent would pre-load it as an extra system message.
2. **RAG over a vetted veterinary corpus.** Replace the hand-coded `get_species_guidelines` defaults with retrieval over a curated set of vet-authored care guides (AAHA, ASPCA, breed clubs), with citations surfaced in the UI so users can verify a claim's source.
3. **Calendar integration.** Export the final schedule as ICS / Google Calendar events with reminders, so the agent's output becomes actionable instead of a static table. Round-tripping completion status back into `Task.is_complete` would close the loop with the legacy `Scheduler`.
4. **Human-rated model evals.** The current eval harness uses keyword matches and conflict counts. A more honest signal would be a 50-case set rated by 2–3 pet-care professionals on a 1–5 Likert scale for safety and realism, then used to compare prompt and model variants.
5. **Distill into a smaller, cheaper model.** Once the eval set is human-rated, fine-tune a small open model (e.g., Llama-3 8B) on `(description, accepted_schedule)` pairs from `evaluation/results_*.json`. Goal: serve the 80% common path without an API call, falling back to Claude only for edge cases.

---

_See [`README.md`](README.md) for setup, run instructions, sample interactions, and the system architecture diagram._
