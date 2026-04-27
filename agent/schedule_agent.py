"""
PawPal+ Schedule Agent

Four-step LLM agent that turns an owner's free-text description of a pet
into a balanced, conflict-free daily schedule:

    1. ANALYZE        - parse the description into a structured pet profile
                        (single LLM call, validated with pydantic).
    2. PLAN-WITH-TOOLS - draft a schedule via an agentic tool-use loop.
                        The model can call get_species_guidelines,
                        validate_schedule, and calculate_schedule_quality
                        until it returns a final JSON answer or hits
                        max_iterations.
    3. VALIDATE       - run validate_schedule directly (no LLM) on the draft.
    4. REVISE         - if conflicts remain, ask the model to fix only
                        what's necessary. The validate->revise cycle
                        runs up to 3 rounds.

Finally, calculate_schedule_quality is called one more time and recorded
on self.steps for an observable reasoning trace.

Three guardrail layers wrap this pipeline (see ``agent.validators``):

    * INPUT  - validate_user_input rejects empty / too-short / too-long
               input, descriptions with no pet vocabulary, and prompt
               injection patterns. Failure raises InvalidInputError.
    * TOOL   - the validate -> revise loop above. Conflicts found by
               validate_schedule are recorded as guardrail events.
    * OUTPUT - validate_schedule_output checks the final draft against
               the strict ScheduleOutput pydantic schema. On failure
               we run exactly one more revise round before giving up.

Public surface:

    agent = ScheduleAgent()
    result = agent.generate_schedule("Rio is my 2yo Aussie Shepherd ...")
    # result -> {
    #     "pet_profile":      {...},
    #     "tasks":            [{...}, ...],
    #     "steps":             [{"type": ..., "timestamp": ..., "details": ...}, ...],
    #     "iterations":        int,    # planner-loop iters + revise rounds
    #     "success":           bool,   # False if any guardrail blocked the run
    #     "guardrail_events":  [...],  # log of every guardrail trigger
    #     "error":             str,    # only present when success is False
    # }
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from agent.prompts import (
    ANALYZER_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    REVISER_SYSTEM_PROMPT,
    format_few_shot_messages,
)
from agent.tools import (
    TOOL_DEFINITIONS,
    TOOL_REGISTRY,
    calculate_schedule_quality,
    validate_schedule,
)
from agent.validators import (
    AgentGuardrailLog,
    validate_schedule_output,
    validate_user_input,
)


logger = logging.getLogger(__name__)


class InvalidInputError(ValueError):
    """Raised by ``ScheduleAgent.generate_schedule`` when the input
    guardrail rejects the user's pet description.

    Inherits from ``ValueError`` so callers that already catch
    ``ValueError`` for malformed input behave sensibly. The first arg
    is the user-facing rejection message produced by
    ``validate_user_input``.
    """


# ---------------------------------------------------------------------------
# Pydantic schema for the analyzer step's output
# ---------------------------------------------------------------------------

class PetProfile(BaseModel):
    """Structured pet profile produced by the analyzer step.

    Mirrors the JSON contract documented in ANALYZER_SYSTEM_PROMPT.
    `medical_needs`, `behavioral_notes`, and `special_requirements`
    default to empty lists so a minimal description still validates.
    """

    pet_name: str
    species: str
    age: int = Field(ge=0)
    energy_level: Literal["low", "medium", "high"]
    medical_needs: list[str] = Field(default_factory=list)
    behavioral_notes: list[str] = Field(default_factory=list)
    special_requirements: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Small parsing helpers
# ---------------------------------------------------------------------------

def _strip_json_fences(text: str) -> str:
    """Strip ```json fences if the model ignored the no-fences instruction."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(text: str) -> str:
    """Pull the first balanced ``{...}`` object out of a model response.

    The system prompts forbid preamble, but we still defensively trim
    fences and slice from the first ``{`` to the last ``}`` so a stray
    apology or prefix doesn't break ``json.loads``.
    """
    text = _strip_json_fences(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response")
    return text[start : end + 1]


def _response_text(response: Any) -> str:
    """Concatenate the .text fields of every text block in a Messages response."""
    return "".join(
        getattr(b, "text", "")
        for b in response.content
        if getattr(b, "type", None) == "text"
    )


def _output_tokens(response: Any) -> int:
    usage = getattr(response, "usage", None)
    return getattr(usage, "output_tokens", 0) if usage is not None else 0


def _parse_tasks_envelope(text: str) -> list:
    """Parse a ``{"tasks": [...]}`` JSON envelope, raising on bad shape.

    Used by the planner's final-answer branch and the reviser, which both
    expect the model to return a single object whose ``tasks`` field is a
    list. Any failure surfaces as ``ValueError`` / ``json.JSONDecodeError``
    so callers can trigger a retry.
    """
    json_str = _extract_json_object(text)
    parsed = json.loads(json_str)
    tasks = parsed.get("tasks") if isinstance(parsed, dict) else None
    if not isinstance(tasks, list):
        raise ValueError(f"Response missing 'tasks' list: {parsed!r}")
    return tasks


# ---------------------------------------------------------------------------
# ScheduleAgent
# ---------------------------------------------------------------------------

class ScheduleAgent:
    """Four-step pet-care schedule agent backed by Anthropic + tool use."""

    # Hard cap on validate->revise rounds in generate_schedule.
    MAX_REVISE_ROUNDS = 3

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        max_iterations: int = 8,
    ) -> None:
        load_dotenv()
        if not os.getenv("ANTHROPIC_API_KEY"):
            logger.error("ANTHROPIC_API_KEY missing from environment / .env")
        # Anthropic() reads ANTHROPIC_API_KEY from env on its own.
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_iterations = max_iterations
        self.steps: list[dict[str, Any]] = []
        # Most recent planner-loop iteration count, surfaced via generate_schedule.
        self._planner_iterations: int = 0
        # Shared sink for input / tool / output guardrail triggers; reset
        # at the top of each generate_schedule run so callers always see
        # the events from the most recent invocation.
        self.guardrail_log = AgentGuardrailLog()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate_schedule(self, user_description: str) -> dict:
        """Run the full four-step pipeline end-to-end with all three
        guardrail layers enforced.

        Layer 1 (input)  - ``validate_user_input`` runs first; on
            failure we raise ``InvalidInputError`` after logging the
            trigger. Callers must catch this if they want to keep going.
        Layer 2 (tool)   - the existing validate -> revise loop. Each
            time the validator finds conflicts we record a ``conflict``
            event on the guardrail log.
        Layer 3 (output) - ``validate_schedule_output`` runs on the
            final draft. On failure we attempt exactly one revise round
            using the validation error as a synthetic conflict; if the
            second pass still fails we return ``success=False`` with
            the error.

        Always returns a dict. Errors during a step are recorded in
        ``self.steps`` rather than raised (the only exception is
        ``InvalidInputError`` from Layer 1), so callers get a usable
        trace even on partial failure. Every result includes a
        ``guardrail_events`` list and a ``success`` boolean.
        """
        self.steps = []
        self._planner_iterations = 0
        self.guardrail_log.reset()
        total_iterations = 0
        pet_profile: dict[str, Any] = {}
        draft: list[dict[str, Any]] = []

        # ---- guardrail layer 1: input validation ----------------------------
        # Done before any LLM calls so we never burn tokens on garbage
        # or prompt-injection input.
        is_valid, message = validate_user_input(user_description)
        if not is_valid:
            self.guardrail_log.record(
                "input_invalid",
                {"reason": message, "input_length": len(user_description or "")},
            )
            self._record_step(
                "guardrail",
                {"layer": "input", "reason": message},
            )
            logger.warning("Input guardrail rejected description: %s", message)
            raise InvalidInputError(message)

        # ---- step 1: analyze --------------------------------------------------
        try:
            pet_profile = self._step_analyze(user_description)
        except Exception as exc:
            logger.exception("Analyzer step failed: %s", exc)
            self._record_step("error", {"stage": "analyze", "error": str(exc)})
            return self._build_result(
                pet_profile={},
                tasks=[],
                iterations=0,
                success=False,
                error=f"analyze step failed: {exc}",
            )

        # ---- step 2: plan with tools ----------------------------------------
        try:
            draft = self._step_plan_with_tools(pet_profile)
        except Exception as exc:
            logger.exception("Planner step failed: %s", exc)
            self._record_step("error", {"stage": "plan", "error": str(exc)})
            draft = []
        total_iterations += self._planner_iterations

        # ---- steps 3 + 4: validate -> revise loop (guardrail layer 2) -------
        # One validate runs first; on conflicts we revise then re-validate,
        # up to MAX_REVISE_ROUNDS revisions. The (rounds + 1) range gives us
        # one final validation read after the last revise.
        if draft:
            for round_idx in range(self.MAX_REVISE_ROUNDS + 1):
                check = self._step_validate(draft)
                if not check["has_conflicts"]:
                    break
                # Tool guardrail fired - log it before deciding whether
                # to revise or give up.
                self.guardrail_log.record(
                    "conflict",
                    {
                        "round": round_idx,
                        "conflicts": check["conflicts"],
                        "task_count": check["task_count"],
                    },
                )
                if round_idx >= self.MAX_REVISE_ROUNDS:
                    logger.error(
                        "Schedule still has %d conflicts after %d revise rounds",
                        len(check["conflicts"]),
                        self.MAX_REVISE_ROUNDS,
                    )
                    self._record_step(
                        "warning",
                        {
                            "stage": "revise",
                            "message": (
                                f"Schedule still has conflicts after "
                                f"{self.MAX_REVISE_ROUNDS} revise rounds."
                            ),
                            "conflicts": check["conflicts"],
                        },
                    )
                    break
                try:
                    draft = self._step_revise(draft, check["conflicts"])
                except Exception as exc:
                    logger.exception("Revise step failed: %s", exc)
                    self._record_step("error", {"stage": "revise", "error": str(exc)})
                    break
                total_iterations += 1

        # ---- final quality score --------------------------------------------
        try:
            quality = calculate_schedule_quality(draft)
            logger.info(
                "Final quality score: overall=%s breakdown=%s",
                quality.get("overall_score"),
                quality.get("breakdown"),
            )
            self._record_step("quality_score", {"quality": quality})
        except Exception as exc:
            logger.exception("calculate_schedule_quality failed: %s", exc)
            self._record_step("error", {"stage": "quality", "error": str(exc)})

        # ---- guardrail layer 3: output validation ---------------------------
        # Try once, and if pydantic rejects the schedule give the model
        # a single chance to fix it via _step_revise (using the schema
        # error as the synthetic "conflict"). If it still fails, return
        # success=False with the error rather than handing the caller a
        # malformed schedule.
        if not draft:
            return self._build_result(
                pet_profile=pet_profile,
                tasks=[],
                iterations=total_iterations,
                success=False,
                error="planner produced no tasks",
            )

        ok, validated_or_error = self._validate_output(pet_profile, draft)
        if not ok:
            error_msg = str(validated_or_error)
            self.guardrail_log.record(
                "output_invalid",
                {"error": error_msg, "task_count": len(draft)},
            )
            self._record_step(
                "guardrail",
                {"layer": "output", "attempt": 1, "error": error_msg},
            )
            logger.warning(
                "Output guardrail rejected schedule (attempt 1): %s", error_msg,
            )
            try:
                draft = self._step_revise(
                    draft,
                    [f"Output schema validation failed: {error_msg}"],
                )
                total_iterations += 1
            except Exception as exc:
                logger.exception("Output-guardrail revise retry failed: %s", exc)
                self._record_step(
                    "error",
                    {"stage": "output_revise", "error": str(exc)},
                )
                return self._build_result(
                    pet_profile=pet_profile,
                    tasks=draft,
                    iterations=total_iterations,
                    success=False,
                    error=f"output validation failed: {error_msg}",
                )

            ok, validated_or_error = self._validate_output(pet_profile, draft)
            if not ok:
                retry_error = str(validated_or_error)
                self.guardrail_log.record(
                    "output_invalid_retry",
                    {"error": retry_error, "task_count": len(draft)},
                )
                self._record_step(
                    "guardrail",
                    {"layer": "output", "attempt": 2, "error": retry_error},
                )
                logger.error(
                    "Output guardrail still failing after retry: %s", retry_error,
                )
                return self._build_result(
                    pet_profile=pet_profile,
                    tasks=draft,
                    iterations=total_iterations,
                    success=False,
                    error=f"output validation failed after retry: {retry_error}",
                )

        return self._build_result(
            pet_profile=pet_profile,
            tasks=draft,
            iterations=total_iterations,
            success=True,
        )

    # ------------------------------------------------------------------
    # Internal helpers for the output guardrail / result envelope
    # ------------------------------------------------------------------

    def _validate_output(
        self,
        pet_profile: dict[str, Any],
        draft: list[dict[str, Any]],
    ) -> tuple[bool, Any]:
        """Run ``validate_schedule_output`` against the current draft.

        Builds the ``{"pet_name", "tasks"}`` envelope the schema expects
        from the analyzer's profile and the planner's task list, then
        delegates to the validator. Returns the ``(ok, payload_or_error)``
        tuple from ``validate_schedule_output`` unchanged so the caller
        can record the error verbatim.
        """
        raw = {
            "pet_name": str(pet_profile.get("pet_name", "")),
            "tasks": draft,
        }
        return validate_schedule_output(raw)

    def _build_result(
        self,
        *,
        pet_profile: dict[str, Any],
        tasks: list[dict[str, Any]],
        iterations: int,
        success: bool,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Assemble the public result dict.

        Centralised so every return path includes ``success``,
        ``guardrail_events``, and the optional ``error`` consistently.
        """
        result: dict[str, Any] = {
            "pet_profile": pet_profile,
            "tasks": tasks,
            "steps": self.steps,
            "iterations": iterations,
            "success": success,
            "guardrail_events": self.guardrail_log.events,
        }
        if error is not None:
            result["error"] = error
        return result

    # ------------------------------------------------------------------
    # Step 1 - analyze
    # ------------------------------------------------------------------

    def _step_analyze(self, description: str) -> dict:
        """Parse the owner's free text into a validated pet profile dict."""
        messages = [{"role": "user", "content": description}]
        logger.info("Analyzer LLM call (messages=%d)", len(messages))
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            temperature=0.0,
            system=ANALYZER_SYSTEM_PROMPT,
            messages=messages,
        )
        logger.info(
            "Analyzer response: stop_reason=%s output_tokens=%s",
            response.stop_reason,
            _output_tokens(response),
        )

        text = _response_text(response)
        try:
            json_str = _extract_json_object(text)
            data = json.loads(json_str)
            profile = PetProfile.model_validate(data)
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "Analyzer JSON parse/validate failed; retrying once: %s | raw=%r",
                exc, text,
            )
            self._record_step(
                "warning",
                {"stage": "analyze_retry", "error": str(exc), "raw": text},
            )
            retry_text = self._retry_json_call(
                system=ANALYZER_SYSTEM_PROMPT,
                messages=messages,
                bad_text=text,
                max_tokens=1024,
                temperature=0.0,
            )
            try:
                json_str = _extract_json_object(retry_text)
                data = json.loads(json_str)
                profile = PetProfile.model_validate(data)
            except (ValueError, json.JSONDecodeError, ValidationError) as exc2:
                logger.error(
                    "Analyzer JSON parse/validate failed after retry: %s | raw=%r",
                    exc2, retry_text,
                )
                raise

        profile_dict = profile.model_dump()
        self._record_step(
            "analyze",
            {
                "input_description": description,
                "pet_profile": profile_dict,
            },
        )
        return profile_dict

    # ------------------------------------------------------------------
    # Step 2 - plan with tools (the agentic loop)
    # ------------------------------------------------------------------

    def _step_plan_with_tools(self, pet_profile: dict) -> list:
        """Run the agentic tool-use loop until the planner returns final JSON.

        On each iteration:
          * Call ``messages.create`` with TOOL_DEFINITIONS.
          * If ``stop_reason == 'tool_use'``, dispatch every tool_use
            block via TOOL_REGISTRY, append a tool_result message, loop.
          * If ``stop_reason == 'end_turn'``, parse the final
            ``{"tasks": [...]}`` JSON and return the list.
          * If ``max_iterations`` is exhausted, record a warning and
            return whatever final task list we last parsed (or []).
        """
        few_shot = format_few_shot_messages()
        live_user = (
            "Here is the structured pet profile. Produce the daily schedule "
            "as instructed in the system prompt. Use tools first, then "
            "return the final JSON.\n\nProfile:\n"
            + json.dumps(pet_profile, indent=2)
        )
        messages: list[dict[str, Any]] = list(few_shot) + [
            {"role": "user", "content": live_user}
        ]

        final_tasks: list[dict[str, Any]] = []
        iterations = 0

        for _ in range(self.max_iterations):
            iterations += 1
            logger.info(
                "Planner LLM call %d (messages=%d)",
                iterations,
                len(messages),
            )
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.4,
                system=PLANNER_SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )
            logger.info(
                "Planner response: stop_reason=%s output_tokens=%s",
                response.stop_reason,
                _output_tokens(response),
            )

            if response.stop_reason == "tool_use":
                # Mirror the assistant turn (text + tool_use blocks) back
                # into history so the next call has the full context.
                messages.append({"role": "assistant", "content": response.content})

                tool_results: list[dict[str, Any]] = []
                for block in response.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    tool_name = block.name
                    tool_input = dict(block.input or {})
                    logger.info("Tool call: %s input=%s", tool_name, tool_input)
                    try:
                        fn = TOOL_REGISTRY[tool_name]
                        result = fn(**tool_input)
                        is_error = False
                    except KeyError:
                        logger.error("Unknown tool requested: %s", tool_name)
                        result = {"error": f"unknown tool '{tool_name}'"}
                        is_error = True
                    except Exception as exc:
                        logger.exception("Tool %s raised: %s", tool_name, exc)
                        result = {"error": str(exc)}
                        is_error = True

                    logger.info("Tool result: %s -> %s", tool_name, result)
                    self._record_step(
                        "tool_call",
                        {
                            "iteration": iterations,
                            "tool": tool_name,
                            "input": tool_input,
                            "output": result,
                            "is_error": is_error,
                        },
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                            "is_error": is_error,
                        }
                    )

                messages.append({"role": "user", "content": tool_results})
                continue

            if response.stop_reason in ("end_turn", "stop_sequence"):
                text = _response_text(response)
                try:
                    final_tasks = _parse_tasks_envelope(text)
                except (ValueError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "Planner final-response parse failed; retrying once: %s | raw=%r",
                        exc, text,
                    )
                    self._record_step(
                        "warning",
                        {
                            "stage": "plan_parse_retry",
                            "error": str(exc),
                            "raw": text,
                        },
                    )
                    retry_text = ""
                    try:
                        retry_text = self._retry_json_call(
                            system=PLANNER_SYSTEM_PROMPT,
                            messages=messages,
                            bad_text=text,
                            max_tokens=4096,
                            temperature=0.0,
                        )
                        final_tasks = _parse_tasks_envelope(retry_text)
                    except (ValueError, json.JSONDecodeError) as exc2:
                        logger.error(
                            "Planner final-response parse failed after retry: %s | raw=%r",
                            exc2, retry_text,
                        )
                        self._record_step(
                            "error",
                            {
                                "stage": "plan_parse",
                                "error": str(exc2),
                                "raw": retry_text,
                            },
                        )
                        final_tasks = []
                    except Exception as exc2:
                        logger.exception(
                            "Planner retry call failed: %s", exc2,
                        )
                        self._record_step(
                            "error",
                            {"stage": "plan_parse", "error": str(exc2)},
                        )
                        final_tasks = []
                break

            logger.warning(
                "Planner stopped with unexpected stop_reason=%s; exiting loop",
                response.stop_reason,
            )
            break
        else:
            # for/else: only runs when the loop exhausts without `break`,
            # i.e. we hit max_iterations while still in tool_use.
            logger.error(
                "Planner exhausted max_iterations=%d without finalizing",
                self.max_iterations,
            )
            self._record_step(
                "warning",
                {
                    "stage": "plan",
                    "message": (
                        f"Planner hit max_iterations={self.max_iterations} "
                        "without returning a final schedule."
                    ),
                },
            )

        self._planner_iterations = iterations
        self._record_step(
            "plan",
            {
                "tasks": final_tasks,
                "planner_iterations": iterations,
            },
        )
        return final_tasks

    # ------------------------------------------------------------------
    # Step 3 - validate (deterministic, no LLM)
    # ------------------------------------------------------------------

    def _step_validate(self, tasks: list) -> dict:
        """Run validate_schedule directly and record the result."""
        result = validate_schedule(tasks)
        logger.info(
            "Validate: has_conflicts=%s conflicts=%d task_count=%d",
            result["has_conflicts"],
            len(result["conflicts"]),
            result["task_count"],
        )
        self._record_step("validate", {"result": result})
        return result

    # ------------------------------------------------------------------
    # Step 4 - revise (LLM call, no tools)
    # ------------------------------------------------------------------

    def _step_revise(self, tasks: list, conflicts: list) -> list:
        """Ask the model to resolve the listed conflicts in the draft."""
        user_msg = (
            "Here is the previous draft schedule and the conflicts the "
            "validator detected. Produce a revised schedule that resolves "
            "every conflict, preserving as much of the original plan as "
            "possible.\n\n"
            "DRAFT:\n"
            + json.dumps({"tasks": tasks}, indent=2)
            + "\n\nCONFLICTS:\n"
            + json.dumps(conflicts, indent=2)
        )
        revise_messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_msg}
        ]
        logger.info(
            "Reviser LLM call (tasks=%d conflicts=%d)", len(tasks), len(conflicts)
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=0.0,
            system=REVISER_SYSTEM_PROMPT,
            messages=revise_messages,
        )
        logger.info(
            "Reviser response: stop_reason=%s output_tokens=%s",
            response.stop_reason,
            _output_tokens(response),
        )

        text = _response_text(response)
        try:
            new_tasks = _parse_tasks_envelope(text)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "Reviser parse failed; retrying once: %s | raw=%r", exc, text,
            )
            self._record_step(
                "warning",
                {"stage": "revise_parse_retry", "error": str(exc), "raw": text},
            )
            retry_text = ""
            try:
                retry_text = self._retry_json_call(
                    system=REVISER_SYSTEM_PROMPT,
                    messages=revise_messages,
                    bad_text=text,
                    max_tokens=4096,
                    temperature=0.0,
                )
                new_tasks = _parse_tasks_envelope(retry_text)
            except (ValueError, json.JSONDecodeError) as exc2:
                logger.error(
                    "Reviser parse failed after retry: %s | raw=%r",
                    exc2, retry_text,
                )
                self._record_step(
                    "error",
                    {
                        "stage": "revise_parse",
                        "error": str(exc2),
                        "raw": retry_text,
                    },
                )
                # Safest fallback: keep the original draft so
                # generate_schedule can surface a warning and stop revising.
                return tasks
            except Exception as exc2:
                logger.exception("Reviser retry call failed: %s", exc2)
                self._record_step(
                    "error",
                    {"stage": "revise_parse", "error": str(exc2)},
                )
                return tasks

        self._record_step(
            "revise",
            {
                "input_conflicts": conflicts,
                "input_tasks": tasks,
                "revised_tasks": new_tasks,
            },
        )
        return new_tasks

    # ------------------------------------------------------------------
    # Retry helper - one-shot "your previous response wasn't valid JSON"
    # ------------------------------------------------------------------

    def _retry_json_call(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        bad_text: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        """Re-prompt the model after a JSON parse failure.

        Echoes the model's malformed response back as an assistant turn,
        then appends a user reminder that the reply must be a single JSON
        object with no prose or fences. Tools are deliberately omitted so
        the model is forced to emit JSON instead of calling another tool.
        Returns the concatenated text of the retry response. Any API or
        parse error in the retry itself propagates to the caller.
        """
        # Anthropic rejects empty assistant text, so guard against the
        # rare case where bad_text is whitespace-only.
        echo = bad_text if bad_text.strip() else "(no parseable response)"
        retry_messages = list(messages) + [
            {"role": "assistant", "content": echo},
            {
                "role": "user",
                "content": (
                    "Your previous response was not valid JSON. "
                    "Return ONLY a single JSON object matching the schema "
                    "in the system prompt. No prose, no code fences, "
                    "no preamble."
                ),
            },
        ]
        logger.info("Retry LLM call (messages=%d)", len(retry_messages))
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=retry_messages,
        )
        logger.info(
            "Retry response: stop_reason=%s output_tokens=%s",
            response.stop_reason,
            _output_tokens(response),
        )
        return _response_text(response)

    # ------------------------------------------------------------------
    # Observable-reasoning trace
    # ------------------------------------------------------------------

    def _record_step(self, step_type: str, details: dict) -> None:
        """Append a timestamped entry to ``self.steps``.

        Each entry is a plain dict so it round-trips through ``json.dumps``
        for UI display and test snapshots.
        """
        self.steps.append(
            {
                "type": step_type,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "details": details,
            }
        )
