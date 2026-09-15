from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
import orchestrator as orchestrator_module

from config import (
    DEFAULT_JOB_BUDGET,
    FRONTIER_GUIDANCE_PROVIDER,
    LOGICAL_CONTEXTS,
    MANAGED_OUTPUT_CONTRACTS,
    PARTICIPANT_ROLE_CONTEXTS,
    PLAN_PROTOCOL_PATH,
)
from director import (
    eligible_plan_steps,
    evaluate_task_execution,
    run_iteration_3,
    select_director_task,
    validate_director_task_for_execution,
)
from model_client import ModelClientError, ModelResponse
from orchestrator import (
    execute_managed_director_task,
    load_managed_work_state,
    managed_work_artifact_paths,
    persist_managed_work_run,
    resolve_guidance_target,
    update_managed_work_guidance_policy,
)
from planning import (
    execution_transition_budget_state,
    root_checkpoint_evidence_refs,
    validate_planning_root_checkpoint,
)
from task_execution import (
    validate_task_execution_checkpoint_context,
    validate_task_execution_mapping,
)
from structures import load_json_mapping


def certified_plan() -> dict[str, object]:
    revision_ref = "plan-iteration-3@r1"
    step_one = f"{revision_ref}:step-1"
    integrity_rules = deepcopy(
        load_json_mapping(PLAN_PROTOCOL_PATH)["integrity"]["rules"]
    )
    return {
        "protocol": {"name": "plan", "version": "v0"},
        "plan_id": "plan-iteration-3",
        "revision": 1,
        "revision_ref": revision_ref,
        "based_on_revision_ref": None,
        "parent_plan_ref": None,
        "status": "final",
        "goal": "Return a verified exact JSON result.",
        "approach_summary": ["Perform the bounded work.", "Verify the result."],
        "current_work_ref": "request:abc123",
        "participants": {
            "proposers": [],
            "supporters": [],
            "critics": [],
            "synthesizer": "gemma_director",
            "decision_maker": "gemma_director",
            "arbiter": None,
        },
        "process": {
            "mode": "synthesis",
            "iteration": {"current": 3, "maximum": 3},
            "stop_criteria": {
                "implemented": False,
                "description": "Fixed Normal V0 planning completion.",
            },
        },
        "planning_cycle": {
            "proposals": [],
            "support": [],
            "critiques": [],
            "suggested_changes": [],
            "decisions": [{
                "id": "plan-iteration-3:decision-finalize",
                "iteration": 3,
                "author_ref": "gemma_director",
                "type": "finalize",
                "target_refs": [],
                "rationale": "The bounded Plan is ready for execution.",
                "accepted_change_refs": [],
                "rejected_change_refs": [],
                "deferred_change_refs": [],
                "rejected_alternatives": [],
                "resulting_revision_ref": revision_ref,
                "message_refs": [],
                "artifact_refs": [],
            }],
            "revisions": [{
                "revision_ref": revision_ref,
                "based_on_revision_ref": None,
                "author_ref": "gemma_director",
                "source_proposal_refs": [],
                "source_support_refs": [],
                "source_critique_refs": [],
                "source_change_refs": [],
                "change_summary": ["Created the certified root Plan."],
                "created_at": "2026-09-15T08:00:00+00:00",
            }],
        },
        "final": {
            "is_final": True,
            "selected_revision_ref": revision_ref,
            "decision_maker_ref": "gemma_director",
            "decision_reason": "The Plan is ready for managed execution.",
            "unresolved_risks": [],
            "unresolved_questions": [],
            "decided_at": "2026-09-15T08:00:00+00:00",
        },
        "integrity": {
            "rules": integrity_rules,
            "validation": {
                "status": "valid",
                "validated_by_ref": "deterministic_plan_validator",
                "validated_at": "2026-09-15T08:00:00+00:00",
                "errors": [],
            },
        },
        "steps": [
            {
                "index": 1,
                "id": step_one,
                "action": "Produce and independently verify the requested JSON.",
                "reason": "The requested result is directly observable.",
                "target_ref": "request:abc123",
                "instructions": ["Return exactly the required JSON object."],
                "scope_boundary": "Do not add prose or unrelated work.",
                "expected_result": '{"ordered":["apple","banana","pear"],"count":3}',
                "validation": [
                    "Output is a JSON object with exactly ordered and count.",
                    "ordered and count have the exact requested values.",
                ],
                "depends_on": [],
                "support_refs": [],
                "critique_refs": [],
                "task_ref": None,
                "status": "proposed",
            },
            {
                "index": 2,
                "id": f"{revision_ref}:step-2",
                "action": "Use the verified result downstream.",
                "reason": "This depends on the first result.",
                "target_ref": "request:abc123",
                "instructions": ["Use only the completed first-step result."],
                "scope_boundary": "Do not run before step 1 completes.",
                "expected_result": "A downstream result.",
                "validation": ["Step 1 was completed first."],
                "depends_on": [step_one],
                "support_refs": [],
                "critique_refs": [],
                "task_ref": None,
                "status": "proposed",
            },
        ],
    }


def successor_plan(
    predecessor: dict[str, object],
    revision: int,
    *,
    based_on_revision_ref: str,
) -> dict[str, object]:
    successor = deepcopy(predecessor)
    revision_ref = f"{predecessor['plan_id']}@r{revision}"
    successor["revision"] = revision
    successor["revision_ref"] = revision_ref
    successor["based_on_revision_ref"] = based_on_revision_ref
    successor["final"]["selected_revision_ref"] = revision_ref
    return successor


def test_execution_transition_budget_is_distinct_and_lineage_derived() -> None:
    root = certified_plan()
    state = execution_transition_budget_state([root])

    assert DEFAULT_JOB_BUDGET["semantic_iterations"] == 3
    assert DEFAULT_JOB_BUDGET["execution_transitions"] == 3
    assert state == {
        "maximum": 3,
        "consumed": 0,
        "remaining": 3,
        "can_create_successor": True,
        "current_plan_ref": "plan-iteration-3@r1",
    }
    assert root["process"]["iteration"] == {
        "current": 3, "maximum": 3,
    }


def test_backtracking_revision_still_consumes_chronological_transition() -> None:
    root = certified_plan()
    revision_two = successor_plan(
        root, 2, based_on_revision_ref=root["revision_ref"],
    )
    revision_three = successor_plan(
        revision_two, 3,
        based_on_revision_ref=revision_two["revision_ref"],
    )
    revision_four = successor_plan(
        revision_three, 4, based_on_revision_ref=root["revision_ref"],
    )

    state = execution_transition_budget_state([
        root, revision_two, revision_three, revision_four,
    ])

    assert state["consumed"] == 3
    assert state["remaining"] == 0
    assert state["can_create_successor"] is False
    assert all(
        plan["process"]["iteration"] == {"current": 3, "maximum": 3}
        for plan in (root, revision_two, revision_three, revision_four)
    )


def test_transition_accounting_rejects_revision_gaps_and_overrun() -> None:
    root = certified_plan()
    revision_three = successor_plan(
        root, 3, based_on_revision_ref=root["revision_ref"],
    )
    with pytest.raises(ValueError, match="chronological revision"):
        execution_transition_budget_state([root, revision_three])

    revision_two = successor_plan(
        root, 2, based_on_revision_ref=root["revision_ref"],
    )
    with pytest.raises(RuntimeError, match="budget exceeded"):
        execution_transition_budget_state(
            [root, revision_two], maximum=0,
        )


def test_root_checkpoint_requires_planning_finalization_and_certification() -> None:
    root = certified_plan()
    assert validate_planning_root_checkpoint(root) == ()
    assert root_checkpoint_evidence_refs(root) == (
        "plan-iteration-3@r1#planning_cycle.decisions/"
        "plan-iteration-3:decision-finalize",
        "plan-iteration-3@r1#integrity.validation",
    )

    uncertified = deepcopy(root)
    uncertified["integrity"]["validation"]["status"] = "pending"
    assert any(
        issue.code == "not_certified_root"
        for issue in validate_planning_root_checkpoint(uncertified)
    )


def valid_selection() -> dict[str, object]:
    return {
        "selected_step_number": 1,
        "selected_input_numbers": [1],
        "output_contract_kind": "json_object",
        "capability": "knowledge_synthesis",
        "participant_role": "reviewer",
        "objective": "Produce and independently verify the exact JSON result.",
        "instruction": "Return only the exact JSON object required by the step.",
        "action": "synthesize",
        "anchors": [{"kind": "plan_step", "value": "step-1"}],
        "entities": [{"kind": "input_collection", "name": "three fruit names"}],
        "focus": {
            "questions": ["Does the result exactly match the Plan expectation?"],
            "angles": ["content and output-shape correctness"],
            "granularity": "fine",
        },
        "reason": "This is the first eligible step and has no dependencies.",
        "requirements": ["Use only the declared request input."],
        "acceptance": "The returned JSON passes every selected-step validation.",
    }


def response(payload: object, number: int) -> ModelResponse:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return ModelResponse(
        request_id=f"request-{number}",
        server_request_id=None,
        model_name="diffusiongemma-26b-a4b-it-nvfp4",
        text=text,
        reasoning_text=None,
        finish_reason="stop",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        latency_ms=10.0,
    )


class FakeCaller:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[str, tuple[dict[str, str], ...], object, object]] = []

    def __call__(
        self,
        context_name: str,
        messages: tuple[dict[str, str], ...],
        *,
        response_format: object,
        chat_template_kwargs: object,
    ) -> ModelResponse:
        self.calls.append((
            context_name, messages, response_format, chat_template_kwargs,
        ))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return response(output, len(self.calls))


def test_director_selects_only_a_mechanically_eligible_step() -> None:
    plan = certified_plan()

    assert [step["index"] for step in eligible_plan_steps(plan)] == [1]
    assert [
        step["index"]
        for step in eligible_plan_steps(
            plan,
            completed_step_refs=(plan["steps"][0]["id"],),
        )
    ] == [1, 2]


def test_valid_selection_builds_trusted_director_task() -> None:
    caller = FakeCaller([valid_selection()])

    result = select_director_task(
        certified_plan(),
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        task_id="task-iteration-3-1",
        model_caller=caller,
        reasoning_task_count=9,
    )

    task = result["director_task"]
    step = result["selected_step"]
    assert task["task_id"] == "task-iteration-3-1"
    assert task["job_ref"] == "job-iteration-3"
    assert task["work_kind"] == "execution"
    assert task["plan_ref"] == "plan-iteration-3@r1"
    assert task["target"] == {"kind": "plan_step", "locator": step["id"]}
    assert task["input_refs"] == [step["target_ref"]]
    assert task["output_contract_ref"] == (
        MANAGED_OUTPUT_CONTRACTS["json_object"]["ref"]
    )
    assert task["external_authority_ref"] is None
    assert result["reasoning_task_count"] == 10
    assert result["conformance_repairs"] == []
    assert caller.calls[0][0] == "gemma_director"

    projected = json.loads(caller.calls[0][1][1]["content"])
    plan_projection = projected["certified_plan_projection"]
    assert "planning_cycle" not in plan_projection
    assert [item["number"] for item in plan_projection["eligible_steps"]] == [1]
    assert "task_id" not in projected["required_output"]
    assert "job_ref" not in projected["required_output"]
    required = projected["required_output"]
    assert "knowledge_synthesis" in required["capability"]
    assert "synthesize" in required["action"]
    assert "fine" in required["focus"]["granularity"]
    assert "json_object" in required["output_contract_kind"]
    assert "reviewer" in required["participant_role"]
    assert "[1]" in required["selected_input_numbers"][0]
    assert "[1]" in required["selected_step_number"]
    assert "endpoint" not in json.dumps(required)


def test_unknown_trusted_field_receives_one_same_director_repair() -> None:
    invalid = {**valid_selection(), "job_ref": "model-authored-job"}
    caller = FakeCaller([invalid, valid_selection()])

    result = select_director_task(
        certified_plan(),
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        task_id="task-iteration-3-1",
        model_caller=caller,
        reasoning_task_count=4,
    )

    assert [call[0] for call in caller.calls] == [
        "gemma_director", "gemma_director",
    ]
    assert result["reasoning_task_count"] == 6
    assert len(result["conformance_repairs"]) == 1
    repair = result["conformance_repairs"][0]
    assert repair["producer_context"] == "gemma_director"
    assert repair["validation_issues"][0]["code"] == "unknown_field"


def test_unconfigured_role_and_malformed_input_receive_one_repair() -> None:
    invalid = {
        **valid_selection(),
        "participant_role": "Director",
        "selected_input_numbers": ["1"],
    }
    caller = FakeCaller([invalid, valid_selection()])

    result = select_director_task(
        certified_plan(),
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        task_id="task-iteration-3-1",
        model_caller=caller,
    )

    assert result["director_task"]["participant_role"] == "reviewer"
    assert len(result["conformance_repairs"]) == 1
    codes = {
        issue["code"]
        for issue in result["conformance_repairs"][0]["validation_issues"]
    }
    assert codes >= {"invalid_shape", "invalid_vocabulary", "unconfigured_role"}


def test_second_invalid_task_selection_terminates_without_task() -> None:
    invalid = {**valid_selection(), "selected_step_number": 99}
    caller = FakeCaller([invalid, invalid])

    with pytest.raises(ValueError, match="after one conformance repair"):
        select_director_task(
            certified_plan(),
            frozen_request="sort these values",
            job_ref="job-iteration-3",
            model_caller=caller,
        )

    assert len(caller.calls) == 2


def test_uncertified_plan_is_rejected_before_director_call() -> None:
    plan = certified_plan()
    plan["integrity"]["validation"]["status"] = "pending"
    caller = FakeCaller([valid_selection()])

    with pytest.raises(ValueError, match="not_certified|certification"):
        select_director_task(
            plan,
            frozen_request="sort these values",
            job_ref="job-iteration-3",
            model_caller=caller,
        )

    assert caller.calls == []


def test_execution_handoff_rejects_mismatched_trusted_references() -> None:
    caller = FakeCaller([valid_selection()])
    result = select_director_task(
        certified_plan(),
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        task_id="task-iteration-3-1",
        model_caller=caller,
    )
    task = deepcopy(result["director_task"])
    task["plan_ref"] = "another-plan@r1"
    task["external_authority_ref"] = "authority:not-supported"

    issues = validate_director_task_for_execution(
        task,
        certified_plan=certified_plan(),
        selected_step=result["selected_step"],
        job_ref="job-iteration-3",
    )

    assert {issue.field for issue in issues} >= {
        "plan_ref", "external_authority_ref",
    }


def test_exhausted_reasoning_budget_prevents_director_call() -> None:
    caller = FakeCaller([valid_selection()])

    with pytest.raises(RuntimeError, match="budget exhausted"):
        select_director_task(
            certified_plan(),
            frozen_request="sort these values",
            job_ref="job-iteration-3",
            model_caller=caller,
            reasoning_task_count=20,
            reasoning_task_limit=20,
        )

    assert caller.calls == []
def task_handoff() -> tuple[dict[str, object], dict[str, object]]:
    plan = certified_plan()
    result = select_director_task(
        plan,
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        task_id="task-iteration-3-1",
        model_caller=FakeCaller([valid_selection()]),
    )
    return plan, result


def exact_worker_result() -> dict[str, object]:
    return {"ordered": ["apple", "banana", "pear"], "count": 3}


def test_task_executive_routes_and_builds_successful_execution() -> None:
    plan, handoff = task_handoff()
    caller = FakeCaller([exact_worker_result()])

    result = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={
            "request:abc123": (
                'Alphabetically sort ["pear", "apple", "banana"].'
            ),
            "request:unrelated": "must not enter the prompt",
        },
        model_caller=caller,
        execution_id="execution-1",
        timestamp="2026-09-15T09:00:00+00:00",
        reasoning_task_count=handoff["reasoning_task_count"],
    )

    execution = result["task_execution"]
    assert result["reasoning_task_count"] == 2
    assert caller.calls[0][0] == "qwen_worker"
    assert caller.calls[0][2] == {"type": "json_object"}
    prompt = json.loads(caller.calls[0][1][1]["content"])
    assert [item["ref"] for item in prompt["resolved_inputs"]] == [
        "request:abc123"
    ]
    assert "request:unrelated" not in caller.calls[0][1][1]["content"]

    assert execution["control"]["status"] == "completed"
    assert execution["resolved"] == {
        "participant_role": "reviewer",
        "logical_context": "qwen_worker",
        "worker_kind": "model",
        "worker_ref": "qwen",
        "requirements": ["Use only the declared request input."],
    }
    assert execution["result"]["content"] == exact_worker_result()
    assert not isinstance(execution["result"]["content"], str)
    assert execution["error"] is None
    assert execution["trace"]["deployment"]["compute_node"] == "pc2.gpu0"
    assert execution["trace"]["deployment"]["host"] == "pc2"
    assert execution["plan_execution"]["current_step_ref"] == (
        handoff["selected_step"]["id"]
    )
    assert execution["plan_execution"]["validation_outcome"] == "passed"
    assert execution["plan_execution"]["outcomes"] == []
    assert validate_task_execution_mapping(execution) == ()


def test_semantically_nonmatching_json_is_left_for_director_judgment() -> None:
    plan, handoff = task_handoff()
    caller = FakeCaller([
        {"ordered": ["pear", "apple", "banana"], "count": 3},
    ])

    execution = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        execution_id="execution-mismatch",
        timestamp="2026-09-15T09:00:00+00:00",
    )["task_execution"]

    assert execution["control"]["status"] == "completed"
    assert execution["result"]["status"] == "complete"
    assert execution["error"] is None
    assert execution["plan_execution"]["validation_outcome"] == "passed"
    assert execution["plan_execution"]["deviation"] is None
    assert len(caller.calls) == 1


def test_malformed_worker_result_receives_one_same_worker_repair() -> None:
    plan, handoff = task_handoff()
    caller = FakeCaller(["not JSON", exact_worker_result()])

    result = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        execution_id="execution-worker-repair",
        timestamp="2026-09-15T09:00:00+00:00",
        reasoning_task_count=handoff["reasoning_task_count"],
    )

    assert len(caller.calls) == 2
    assert [call["stage"] for call in result["calls"]] == [
        "configured_worker_execution",
        "configured_worker_conformance_repair",
    ]
    assert result["reasoning_task_count"] == (
        handoff["reasoning_task_count"] + 2
    )
    assert len(result["conformance_repairs"]) == 1
    assert result["conformance_repairs"][0]["producer_context"] == (
        "qwen_worker"
    )
    assert result["task_execution"]["result"]["content"] == (
        exact_worker_result()
    )


def test_second_malformed_worker_result_stops_after_one_repair() -> None:
    plan, handoff = task_handoff()
    caller = FakeCaller(["not JSON", "still not JSON"])

    result = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        execution_id="execution-worker-invalid-twice",
        timestamp="2026-09-15T09:00:00+00:00",
    )

    assert len(caller.calls) == 2
    assert len(result["conformance_repairs"]) == 1
    execution = result["task_execution"]
    assert execution["control"]["status"] == "failed"
    assert execution["result"] is None
    assert execution["error"]["category"] == "validation"
    assert execution["plan_execution"]["validation_outcome"] == "failed"


def test_text_output_contract_gates_representation_only() -> None:
    selection = valid_selection()
    selection["output_contract_kind"] = "text"
    plan = certified_plan()
    handoff = select_director_task(
        plan,
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        model_caller=FakeCaller([selection]),
    )
    caller = FakeCaller(["A semantically debatable but well-formed answer."])

    execution = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "sort these values"},
        trusted_input_refs=handoff["trusted_input_refs"],
        trusted_output_contract_ref=handoff[
            "trusted_output_contract_ref"
        ],
        model_caller=caller,
        execution_id="execution-text-contract",
        timestamp="2026-09-15T09:00:00+00:00",
    )["task_execution"]

    assert caller.calls[0][2] is None
    assert execution["result"]["status"] == "complete"
    assert execution["plan_execution"]["validation_outcome"] == "passed"


def test_transport_error_becomes_failed_task_execution() -> None:
    plan, handoff = task_handoff()
    failure = ModelClientError(
        request_id="transport-request-1",
        kind="timeout",
        message="Qwen timed out",
        retryable=True,
    )
    caller = FakeCaller([failure])

    execution = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        execution_id="execution-timeout",
        timestamp="2026-09-15T09:00:00+00:00",
    )["task_execution"]

    assert execution["control"]["status"] == "failed"
    assert execution["result"] is None
    assert execution["error"] == {
        "code": "model_timeout",
        "category": "timeout",
        "detail": "Qwen timed out",
        "retryable": True,
        "source": "model",
    }
    assert execution["trace"]["deployment"]["session"] == (
        "transport-request-1"
    )
    assert execution["plan_execution"]["validation_outcome"] == "inconclusive"
    assert validate_task_execution_mapping(execution) == ()


def test_task_executive_rejects_bad_handoff_before_worker_call() -> None:
    plan, handoff = task_handoff()
    task = deepcopy(handoff["director_task"])
    task["plan_ref"] = "untrusted-plan@r9"
    caller = FakeCaller([exact_worker_result()])

    with pytest.raises(ValueError, match="before resolution"):
        execute_managed_director_task(
            task,
            job_ref="job-iteration-3",
            certified_plan=plan,
            selected_step=handoff["selected_step"],
            resolved_inputs={"request:abc123": "sort these values"},
            model_caller=caller,
        )

    assert caller.calls == []


def test_missing_declared_input_prevents_worker_call() -> None:
    plan, handoff = task_handoff()
    caller = FakeCaller([exact_worker_result()])

    with pytest.raises(ValueError, match="inputs are unavailable"):
        execute_managed_director_task(
            handoff["director_task"],
            job_ref="job-iteration-3",
            certified_plan=plan,
            selected_step=handoff["selected_step"],
            resolved_inputs={},
            model_caller=caller,
        )

    assert caller.calls == []


def test_role_reassignment_changes_execution_without_code_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, handoff = task_handoff()
    monkeypatch.setitem(
        PARTICIPANT_ROLE_CONTEXTS, "reviewer", "gemma_worker",
    )
    caller = FakeCaller([exact_worker_result()])

    execution = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        execution_id="execution-rerouted",
        timestamp="2026-09-15T09:00:00+00:00",
    )["task_execution"]

    assert LOGICAL_CONTEXTS["gemma_worker"].worker_ref == "diffusion_gemma"
    assert caller.calls[0][0] == "gemma_worker"
    assert caller.calls[0][2] is None
    assert execution["resolved"]["logical_context"] == "gemma_worker"
    assert execution["trace"]["deployment"]["host"] == "pc1"


def test_execution_budget_is_checked_before_worker_call() -> None:
    plan, handoff = task_handoff()
    caller = FakeCaller([exact_worker_result()])

    with pytest.raises(RuntimeError, match="budget exhausted"):
        execute_managed_director_task(
            handoff["director_task"],
            job_ref="job-iteration-3",
            certified_plan=plan,
            selected_step=handoff["selected_step"],
            resolved_inputs={"request:abc123": "sort these values"},
            model_caller=caller,
            reasoning_task_count=20,
            reasoning_task_limit=20,
        )

    assert caller.calls == []


def test_full_task_execution_validator_rejects_unknown_fields() -> None:
    plan, handoff = task_handoff()
    execution = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=FakeCaller([exact_worker_result()]),
        execution_id="execution-unknown-field",
        timestamp="2026-09-15T09:00:00+00:00",
    )["task_execution"]
    execution["semantic_decision"] = "ACCEPT"

    issues = validate_task_execution_mapping(execution)

    assert any(
        issue.field == "execution.semantic_decision"
        and issue.code == "unknown_field"
        for issue in issues
    )


def resource_descriptor(kind: str) -> dict[str, str]:
    return {
        "ref": f"{kind}:evidence.txt",
        "kind": kind,
        "name": f"{kind} evidence",
        "description": "Relevant evidence available to managed work.",
    }


def resource_selection(
    *, participant_role: str = "tool",
) -> dict[str, object]:
    selected = valid_selection()
    selected.update({
        "selected_input_numbers": [1, 2],
        "participant_role": participant_role,
        "action": "verify_support",
        "objective": "Retrieve the selected evidence for evaluation.",
        "instruction": "Return the declared evidence without selecting sources.",
        "requirements": ["Use only the numbered evidence selected here."],
        "acceptance": "The declared evidence is returned with its trusted ref.",
    })
    return selected


def test_director_selects_semantic_resource_number_not_mechanics() -> None:
    resource = resource_descriptor("vault")
    caller = FakeCaller([resource_selection(participant_role="reviewer")])

    result = select_director_task(
        certified_plan(),
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        available_resources=[resource],
        model_caller=caller,
    )

    assert result["director_task"]["input_refs"] == [
        "request:abc123", "vault:evidence.txt",
    ]
    projection = json.loads(caller.calls[0][1][1]["content"])
    assert projection["available_inputs"][1] == {
        "number": 2,
        "kind": "vault",
        "name": "vault evidence",
        "description": "Relevant evidence available to managed work.",
    }
    rendered = caller.calls[0][1][1]["content"]
    assert str(orchestrator_module.VAULT_DIR) not in rendered
    assert "endpoint_url" not in rendered
    assert "model_name" not in rendered


@pytest.mark.parametrize("kind", ["vault", "source"])
def test_configured_local_resource_tool_builds_task_execution(
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_root = tmp_path / kind
    resource_root.mkdir()
    (resource_root / "evidence.txt").write_text(
        f"trusted {kind} evidence", encoding="utf-8",
    )
    monkeypatch.setitem(
        orchestrator_module.MANAGED_RESOURCE_ROOTS, kind, resource_root,
    )
    resource = resource_descriptor(kind)
    plan = certified_plan()
    handoff = select_director_task(
        plan,
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        available_resources=[resource],
        model_caller=FakeCaller([resource_selection()]),
    )
    fallback = FakeCaller([exact_worker_result()])

    result = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "original request"},
        resource_catalog=[resource],
        trusted_input_refs=handoff["trusted_input_refs"],
        model_caller=fallback,
        execution_id=f"execution-{kind}",
        timestamp="2026-09-15T09:00:00+00:00",
        reasoning_task_count=handoff["reasoning_task_count"],
    )

    execution = result["task_execution"]
    assert fallback.calls == []
    assert result["reasoning_task_count"] == handoff["reasoning_task_count"]
    assert execution["control"]["status"] == "completed"
    assert execution["resolved"]["worker_kind"] == "tool"
    assert execution["trace"]["deployment"]["model"] is None
    assert execution["trace"]["deployment"]["agent"] == (
        "benzaiten_orchestrator"
    )
    returned = execution["result"]["content"]["resources"]
    assert returned[1] == {
        "ref": f"{kind}:evidence.txt",
        "content": f"trusted {kind} evidence",
    }
    assert validate_task_execution_mapping(execution) == ()


def test_unconfigured_web_resource_fails_explicitly_without_fallback() -> None:
    resource = resource_descriptor("web")
    plan = certified_plan()
    handoff = select_director_task(
        plan,
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        available_resources=[resource],
        model_caller=FakeCaller([resource_selection()]),
    )
    model_fallback = FakeCaller([exact_worker_result()])
    web_calls: list[object] = []

    execution = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "original request"},
        resource_catalog=[resource],
        trusted_input_refs=handoff["trusted_input_refs"],
        model_caller=model_fallback,
        web_caller=lambda *args: web_calls.append(args),
        execution_id="execution-web-unavailable",
        timestamp="2026-09-15T09:00:00+00:00",
    )["task_execution"]

    assert model_fallback.calls == []
    assert web_calls == []
    assert execution["control"]["status"] == "failed"
    assert execution["error"]["code"] == "web_provider_unavailable"
    assert execution["error"]["source"] == "tool"


def test_configured_web_resource_uses_only_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = resource_descriptor("web")
    monkeypatch.setattr(
        orchestrator_module, "WEB_RESEARCH_PROVIDER", "test-web-provider",
    )
    plan = certified_plan()
    handoff = select_director_task(
        plan,
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        available_resources=[resource],
        model_caller=FakeCaller([resource_selection()]),
    )
    calls: list[tuple[object, object]] = []

    def web_caller(provider: object, request: object) -> object:
        calls.append((provider, request))
        return {"facts": ["configured evidence"]}

    execution = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "original request"},
        resource_catalog=[resource],
        trusted_input_refs=handoff["trusted_input_refs"],
        web_caller=web_caller,
        execution_id="execution-web-configured",
        timestamp="2026-09-15T09:00:00+00:00",
    )["task_execution"]

    assert calls[0][0] == "test-web-provider"
    assert execution["control"]["status"] == "completed"
    assert execution["result"]["content"]["resources"][1]["content"] == {
        "facts": ["configured evidence"],
    }


def test_configured_local_model_worker_receives_selected_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "evidence.txt").write_text(
        "source material", encoding="utf-8",
    )
    monkeypatch.setitem(
        orchestrator_module.MANAGED_RESOURCE_ROOTS, "source", source_root,
    )
    resource = resource_descriptor("source")
    plan = certified_plan()
    handoff = select_director_task(
        plan,
        frozen_request="sort these values",
        job_ref="job-iteration-3",
        available_resources=[resource],
        model_caller=FakeCaller([
            resource_selection(participant_role="reviewer"),
        ]),
    )
    worker = FakeCaller([exact_worker_result()])

    execution = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "original request"},
        resource_catalog=[resource],
        trusted_input_refs=handoff["trusted_input_refs"],
        model_caller=worker,
        execution_id="execution-model-with-source",
        timestamp="2026-09-15T09:00:00+00:00",
        reasoning_task_count=handoff["reasoning_task_count"],
    )["task_execution"]

    prompt = json.loads(worker.calls[0][1][1]["content"])
    assert prompt["resolved_inputs"][1] == {
        "ref": "source:evidence.txt", "content": "source material",
    }
    assert execution["resolved"]["worker_kind"] == "model"
    assert execution["trace"]["deployment"]["model"] == (
        "qwen3-30b-a3b-nvfp4"
    )


def test_resource_execution_persists_and_resumes_without_reasoning_charge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "evidence.txt").write_text(
        "persisted source material", encoding="utf-8",
    )
    monkeypatch.setitem(
        orchestrator_module.MANAGED_RESOURCE_ROOTS, "source", source_root,
    )
    resource = resource_descriptor("source")
    artifact_root = tmp_path / "managed-work"

    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0,
        job_ref="job-resource-resume",
        resolved_inputs={"request:abc123": "original request"},
        available_resources=[resource],
        model_caller=FakeCaller([
            resource_selection(),
            accept_evaluation(),
        ]),
        artifact_root=artifact_root,
        task_ids=("task-resource",),
        execution_ids=("execution-resource",),
        outcome_ids=("outcome-resource",),
        timestamp="2026-09-15T09:00:00+00:00",
    )

    assert result["status"] == "accepted"
    assert result["reasoning_task_count"] == 2
    assert any(call["reasoning_task"] is None for call in result["calls"])
    restored = load_managed_work_state(
        "job-resource-resume", artifact_root=artifact_root,
    )
    assert restored["reasoning_task_count"] == 2
    assert restored["available_resources"] == [resource]
    assert restored["resume_state"]["status"] == "completed"
def executed_task(
    worker_output: object | None = None,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    plan, handoff = task_handoff()
    execution = execute_managed_director_task(
        handoff["director_task"],
        job_ref="job-iteration-3",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=FakeCaller([
            exact_worker_result()
            if worker_output is None
            else worker_output
        ]),
        execution_id="execution-for-evaluation",
        timestamp="2026-09-15T09:00:00+00:00",
        reasoning_task_count=handoff["reasoning_task_count"],
    )
    return plan, handoff, execution


def accept_evaluation(
    *,
    continue_work: bool = False,
) -> dict[str, object]:
    return {
        "decision": "ACCEPT",
        "reason": "The exact JSON result matches every Plan criterion.",
        "evidence_numbers": [1],
        "continue_work": continue_work,
        "backtrack_checkpoint_number": None,
        "guidance": None,
    }


def revise_evaluation(
    *,
    checkpoint_number: int = 1,
) -> dict[str, object]:
    return {
        "decision": "REVISE",
        "reason": "Execution evidence requires a successor Plan revision.",
        "evidence_numbers": [1],
        "continue_work": True,
        "backtrack_checkpoint_number": checkpoint_number,
        "guidance": None,
    }


def ask_guidance_evaluation(
    *,
    target: str = "user",
) -> dict[str, object]:
    return {
        "decision": "ASK_GUIDANCE",
        "reason": "A material ambiguity remains after local evidence review.",
        "evidence_numbers": [1],
        "continue_work": False,
        "backtrack_checkpoint_number": None,
        "guidance": {
            "hurdle": "Two interpretations remain viable.",
            "materiality": "They produce incompatible execution results.",
            "attempts": [{
                "description": "Reviewed the completed TaskExecution.",
                "established": "Execution evidence does not select a meaning.",
                "evidence_numbers": [1],
            }],
            "remaining_unresolved": "Which interpretation is authoritative?",
            "evidence_numbers": [1],
            "options": ["Use interpretation A", "Use interpretation B"],
            "recommendation": "Use interpretation A.",
            "question": "Should execution use interpretation A?",
            "target": target,
        },
    }


def test_director_accept_is_recorded_in_existing_task_execution_fields() -> None:
    plan, handoff, execution_result = executed_task()
    caller = FakeCaller([accept_evaluation()])

    result = evaluate_task_execution(
        execution_result["task_execution"],
        frozen_request="sort these values",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        director_task=handoff["director_task"],
        model_caller=caller,
        outcome_id="outcome-accept-1",
        timestamp="2026-09-15T09:01:00+00:00",
        reasoning_task_count=execution_result["reasoning_task_count"],
    )

    evaluated = result["task_execution"]
    assert result["disposition"] == "accepted"
    assert result["semantic_iteration_advanced"] is False
    assert result["reasoning_task_count"] == 3
    assert caller.calls[0][0] == "gemma_director"
    assert evaluated["plan_execution"]["outcomes"] == [{
        "id": "outcome-accept-1",
        "decision": "ACCEPT",
        "reason": "The exact JSON result matches every Plan criterion.",
        "evidence_refs": ["execution-for-evaluation"],
        "checkpoint_revision_ref": "plan-iteration-3@r1",
        "checkpoint_outcome_ref": "outcome-accept-1",
        "resulting_plan_ref": None,
        "guidance": None,
        "decided_by_ref": "gemma_director",
        "created_at": "2026-09-15T09:01:00+00:00",
        "task_ref": "task-iteration-3-1",
        "execution_ref": "execution-for-evaluation",
    }]
    assert evaluated["plan_execution"]["replan_requested"] is False
    assert evaluated["plan_execution"]["replan_reason"] is None
    assert validate_task_execution_mapping(evaluated) == ()

    projected = json.loads(caller.calls[0][1][1]["content"])
    assert set(projected) == {
        "frozen_request", "semantic_plan_fidelity", "prior_execution_evidence",
        "certified_plan",
        "selected_step",
        "director_task",
        "task_execution",
            "numbered_evidence",
            "numbered_accepted_checkpoints",
            "required_output",
            "conditional_field_rules",
        }
    assert "trace" not in projected["task_execution"]
    assert "provenance" not in projected["task_execution"]
    assert "planning_cycle" not in projected["certified_plan"]


def test_director_revise_selects_the_certified_root_checkpoint() -> None:
    plan, handoff, execution_result = executed_task({
        "ordered": ["pear", "apple", "banana"],
        "count": 3,
    })

    result = evaluate_task_execution(
        execution_result["task_execution"],
        frozen_request="sort these values",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        director_task=handoff["director_task"],
        model_caller=FakeCaller([revise_evaluation()]),
        timestamp="2026-09-15T09:01:00+00:00",
    )

    evaluated = result["task_execution"]
    assert result["disposition"] == "revise"
    assert evaluated["plan_execution"]["plan_ref"] == plan["revision_ref"]
    assert evaluated["plan_execution"]["current_step_ref"] == (
        handoff["selected_step"]["id"]
    )
    assert evaluated["plan_execution"]["replan_requested"] is True
    assert evaluated["plan_execution"]["replan_reason"] == (
        "Execution evidence requires a successor Plan revision."
    )
    outcome = evaluated["plan_execution"]["outcomes"][0]
    assert outcome["checkpoint_revision_ref"] == "plan-iteration-3@r1"
    assert outcome["checkpoint_outcome_ref"] is None
    assert set(outcome["evidence_refs"]) == {
        execution_result["task_execution"]["execution_id"],
        *root_checkpoint_evidence_refs(plan),
    }
    assert validate_task_execution_checkpoint_context(
        evaluated, plans_by_ref={plan["revision_ref"]: plan},
    ) == ()


def test_null_checkpoint_outcome_is_valid_only_for_certified_root() -> None:
    plan, handoff, execution_result = executed_task()
    evaluated = evaluate_task_execution(
        execution_result["task_execution"],
        frozen_request="sort these values",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        director_task=handoff["director_task"],
        model_caller=FakeCaller([revise_evaluation()]),
    )["task_execution"]

    non_root = deepcopy(evaluated)
    non_root["plan_execution"]["outcomes"][0][
        "checkpoint_revision_ref"
    ] = "plan-iteration-3@r2"
    assert any(
        issue.code == "missing_execution_checkpoint"
        for issue in validate_task_execution_mapping(non_root)
    )

    uncertified = deepcopy(plan)
    uncertified["integrity"]["validation"]["status"] = "pending"
    assert any(
        issue.code == "invalid_root_checkpoint"
        for issue in validate_task_execution_checkpoint_context(
            evaluated,
            plans_by_ref={plan["revision_ref"]: uncertified},
        )
    )


def test_ask_guidance_outcome_contract_is_structurally_representable() -> None:
    plan, _, execution_result = executed_task()
    execution = deepcopy(execution_result["task_execution"])
    execution["plan_execution"]["outcomes"].append({
        "id": "outcome-guidance-1",
        "decision": "ASK_GUIDANCE",
        "reason": "A material ambiguity remains after local evidence review.",
        "evidence_refs": list(root_checkpoint_evidence_refs(plan)),
        "checkpoint_revision_ref": plan["revision_ref"],
        "checkpoint_outcome_ref": None,
        "resulting_plan_ref": None,
        "guidance": {
            "hurdle": "Two interpretations remain viable.",
            "materiality": "They produce incompatible execution results.",
            "attempts": [{
                "description": "Reviewed the supplied source.",
                "established": "The source does not select either meaning.",
                "evidence_refs": ["request:abc123"],
            }],
            "remaining_unresolved": "Which interpretation is authoritative?",
            "evidence_refs": ["request:abc123"],
            "options": ["Use interpretation A", "Use interpretation B"],
            "recommendation": "Use interpretation A.",
            "question": "Should execution use interpretation A?",
            "target": "user",
            "policy": "USER_ONLY",
            "frontier_authorized": False,
        },
        "decided_by_ref": "gemma_director",
        "created_at": "2026-09-15T09:01:00+00:00",
        "task_ref": execution["task_ref"],
        "execution_ref": execution["execution_id"],
    })

    assert validate_task_execution_mapping(execution) == ()
    assert validate_task_execution_checkpoint_context(
        execution, plans_by_ref={plan["revision_ref"]: plan},
    ) == ()


def test_revise_always_requests_successor_plan_semantics() -> None:
    plan, handoff, execution_result = executed_task()

    result = evaluate_task_execution(
        execution_result["task_execution"],
        frozen_request="sort these values",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        director_task=handoff["director_task"],
        model_caller=FakeCaller([revise_evaluation()]),
        timestamp="2026-09-15T09:01:00+00:00",
    )

    assert result["disposition"] == "revise"
    assert result["task_execution"]["plan_execution"][
        "replan_requested"
    ] is True
    assert result["task_execution"]["plan_execution"]["replan_reason"] == (
        "Execution evidence requires a successor Plan revision."
    )


def test_invalid_evaluation_receives_one_same_director_repair() -> None:
    plan, handoff, execution_result = executed_task()
    invalid = {**accept_evaluation(), "decision": "APPROVE"}
    caller = FakeCaller([invalid, accept_evaluation()])

    result = evaluate_task_execution(
        execution_result["task_execution"],
        frozen_request="sort these values",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        director_task=handoff["director_task"],
        model_caller=caller,
        reasoning_task_count=8,
    )

    assert [call[0] for call in caller.calls] == [
        "gemma_director", "gemma_director",
    ]
    assert result["reasoning_task_count"] == 10
    assert len(result["conformance_repairs"]) == 1
    assert result["conformance_repairs"][0]["producer_context"] == (
        "gemma_director"
    )

    initial_projection = json.loads(caller.calls[0][1][1]["content"])
    assert initial_projection["conditional_field_rules"]["ACCEPT"] == {
        "backtrack_checkpoint_number": None,
        "continue_work": "boolean",
        "guidance": None,
    }
    repair_projection = json.loads(caller.calls[1][1][1]["content"])
    assert repair_projection["valid_references"][
        "conditional_field_rules"
    ]["REVISE"]["guidance"] is None


def test_second_invalid_evaluation_terminates() -> None:
    plan, handoff, execution_result = executed_task()
    invalid = {**accept_evaluation(), "decision": "APPROVE"}
    caller = FakeCaller([invalid, invalid])

    with pytest.raises(ValueError, match="after one conformance repair"):
        evaluate_task_execution(
            execution_result["task_execution"],
            frozen_request="sort these values",
            certified_plan=plan,
            selected_step=handoff["selected_step"],
            director_task=handoff["director_task"],
            model_caller=caller,
        )

    assert len(caller.calls) == 2


def test_mismatched_execution_evidence_is_rejected_before_evaluation() -> None:
    plan, handoff, execution_result = executed_task()
    execution = deepcopy(execution_result["task_execution"])
    execution["plan_execution"]["current_step_ref"] = (
        "plan-iteration-3@r1:step-99"
    )
    caller = FakeCaller([accept_evaluation()])

    with pytest.raises(ValueError, match="rejected TaskExecution evidence"):
        evaluate_task_execution(
            execution,
            frozen_request="sort these values",
            certified_plan=plan,
            selected_step=handoff["selected_step"],
            director_task=handoff["director_task"],
            model_caller=caller,
        )

    assert caller.calls == []


def test_outcome_record_rejects_unknown_semantic_fields() -> None:
    plan, handoff, execution_result = executed_task()
    evaluated = evaluate_task_execution(
        execution_result["task_execution"],
        frozen_request="sort these values",
        certified_plan=plan,
        selected_step=handoff["selected_step"],
        director_task=handoff["director_task"],
        model_caller=FakeCaller([accept_evaluation()]),
    )["task_execution"]
    evaluated["plan_execution"]["outcomes"][0]["selected_model"] = "qwen"

    issues = validate_task_execution_mapping(evaluated)

    assert any(
        issue.field.endswith(".selected_model")
        and issue.code == "unknown_field"
        for issue in issues
    )
def successor_plan_semantics(label: str = "corrected approach") -> dict[str, object]:
    return {
        "overall_synthesis": {
            "goal": f"Produce the exact JSON using the {label}.",
            "approach_summary": [f"Apply the {label} and validate it."],
            "decision_rationale": (
                "The TaskExecution evidence requires revised Plan semantics."
            ),
            "rejected_alternatives": [],
            "change_summary": [f"Replaced the failed branch with {label}."],
            "decision_reason": "The successor is ready for execution.",
            "unresolved_risks": [],
            "unresolved_questions": [],
        },
        "plan_steps": {
            "steps": [{
                "action": "Produce and verify the corrected JSON.",
                "reason": "The prior execution did not satisfy the result.",
                "instructions": ["Return only the exact JSON object."],
                "scope_boundary": "Do not mutate prior Plan revisions.",
                "expected_result": (
                    '{"ordered":["apple","banana","pear"],"count":3}'
                ),
                "validation": [
                    "The object contains the exact ordered values and count."
                ],
                "depends_on_step_numbers": [],
            }],
        },
    }


def test_iteration_3_accept_stops_without_another_model_call() -> None:
    caller = FakeCaller([
        valid_selection(),
        exact_worker_result(),
        accept_evaluation(),
    ])

    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0,
        job_ref="job-iteration-3",
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        task_ids=("task-1",),
        execution_ids=("execution-1",),
        outcome_ids=("outcome-1",),
        timestamp="2026-09-15T10:00:00+00:00",
    )

    assert result["status"] == "accepted"
    assert len(caller.calls) == 3
    assert [call[0] for call in caller.calls] == [
        "gemma_director", "qwen_worker", "gemma_director",
    ]
    assert len(result["director_tasks"]) == 1
    assert len(result["task_executions"]) == 1
    assert result["task_executions"][0]["plan_execution"][
        "outcomes"
    ][0]["decision"] == "ACCEPT"
    assert result["semantic_iteration_count"] == 3
    assert result["semantic_iteration_advanced"] is False
    assert len(result["plan_history"]) == 1
    assert result["execution_transition_state"]["consumed"] == 0


def test_revise_creates_successor_plan_before_next_task() -> None:
    wrong = {"ordered": ["pear", "apple", "banana"], "count": 3}
    original = certified_plan()
    frozen_original = json.dumps(original, sort_keys=True)
    caller = FakeCaller([
        valid_selection(),
        wrong,
        revise_evaluation(),
        successor_plan_semantics(),
        {"compliant": True, "violations": []},
        valid_selection(),
        exact_worker_result(),
        accept_evaluation(),
    ])

    result = run_iteration_3(
        original, reasoning_task_count=0,
        job_ref="job-iteration-3",
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        task_ids=("task-1", "task-2"),
        execution_ids=("execution-1", "execution-2"),
        outcome_ids=("outcome-revise-1", "outcome-accept-2"),
        timestamp="2026-09-15T10:00:00+00:00",
    )

    assert result["status"] == "accepted"
    assert len(caller.calls) == 8
    assert [call[0] for call in caller.calls] == [
        "gemma_director",
        "qwen_worker",
        "gemma_director",
        "gemma_director",
        "gemma_worker",
        "gemma_director",
        "qwen_worker",
        "gemma_director",
    ]
    assert [task["task_id"] for task in result["director_tasks"]] == [
        "task-1", "task-2",
    ]
    assert [task["plan_ref"] for task in result["director_tasks"]] == [
        "plan-iteration-3@r1", "plan-iteration-3@r2",
    ]
    assert len({
        task["target"]["locator"] for task in result["director_tasks"]
    }) == 2
    assert [
        item["semantics"]["decision"] for item in result["evaluations"]
    ] == ["REVISE", "ACCEPT"]
    assert result["reasoning_task_count"] == 8
    assert json.dumps(original, sort_keys=True) == frozen_original
    assert [plan["revision_ref"] for plan in result["plan_history"]] == [
        "plan-iteration-3@r1", "plan-iteration-3@r2",
    ]
    assert result["plan_history"][1]["based_on_revision_ref"] == (
        "plan-iteration-3@r1"
    )
    assert result["execution_transition_state"]["consumed"] == 1
    assert result["task_executions"][0]["plan_execution"]["outcomes"][0][
        "resulting_plan_ref"
    ] == "plan-iteration-3@r2"

    successor_prompt = json.loads(caller.calls[3][1][1]["content"])
    assert successor_prompt["current_plan"]["revision_ref"] == (
        "plan-iteration-3@r1"
    )
    assert successor_prompt["selected_checkpoint"]["revision_ref"] == (
        "plan-iteration-3@r1"
    )
    assert successor_prompt["triggering_outcome"]["decision"] == "REVISE"
    assert "trace" not in successor_prompt["triggering_execution"]


def test_multiple_revises_create_chronological_plan_nodes() -> None:
    wrong = {"ordered": ["pear", "apple", "banana"], "count": 3}
    caller = FakeCaller([
        valid_selection(),
        wrong,
        revise_evaluation(),
        successor_plan_semantics("revision two"),
        {"compliant": True, "violations": []},
        valid_selection(),
        wrong,
        revise_evaluation(),
        successor_plan_semantics("revision three"),
        {"compliant": True, "violations": []},
        valid_selection(),
        exact_worker_result(),
        accept_evaluation(),
    ])

    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0,
        job_ref="job-iteration-3",
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        task_ids=("task-1", "task-2", "task-3"),
        execution_ids=("execution-1", "execution-2", "execution-3"),
        outcome_ids=("outcome-1", "outcome-2", "outcome-3"),
    )

    assert result["status"] == "accepted"
    assert len(result["director_tasks"]) == 3
    assert len(result["task_executions"]) == 3
    assert [
        item["semantics"]["decision"] for item in result["evaluations"]
    ] == ["REVISE", "REVISE", "ACCEPT"]
    assert [
        plan["revision_ref"] for plan in result["plan_history"]
    ] == [
        "plan-iteration-3@r1",
        "plan-iteration-3@r2",
        "plan-iteration-3@r3",
    ]
    assert result["execution_transition_state"]["consumed"] == 2


def test_revise_can_backtrack_to_a_real_execution_accept_checkpoint() -> None:
    wrong = {"ordered": ["pear", "apple", "banana"], "count": 3}
    caller = FakeCaller([
        valid_selection(),
        exact_worker_result(),
        accept_evaluation(continue_work=True),
        successor_plan_semantics("continued work"),
        {"compliant": True, "violations": []},
        valid_selection(),
        wrong,
        revise_evaluation(checkpoint_number=2),
        successor_plan_semantics("execution-checkpoint backtrack"),
        {"compliant": True, "violations": []},
        valid_selection(),
        exact_worker_result(),
        accept_evaluation(),
    ])

    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0,
        job_ref="job-iteration-3",
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        task_ids=("task-r1", "task-r2", "task-r3"),
        execution_ids=("execution-r1", "execution-r2", "execution-r3"),
        outcome_ids=(
            "outcome-accept-r1", "outcome-revise-r2",
            "outcome-accept-r3",
        ),
    )

    assert result["status"] == "accepted"
    assert [
        plan["based_on_revision_ref"] for plan in result["plan_history"]
    ] == [None, "plan-iteration-3@r1", "plan-iteration-3@r1"]
    revise_outcome = result["task_executions"][1]["plan_execution"][
        "outcomes"
    ][0]
    assert revise_outcome["checkpoint_revision_ref"] == (
        "plan-iteration-3@r1"
    )
    assert revise_outcome["checkpoint_outcome_ref"] == "outcome-accept-r1"
    latest_decision = result["plan_history"][2]["planning_cycle"][
        "decisions"
    ][-1]
    assert "outcome-accept-r1" in latest_decision["artifact_refs"]
    assert result["execution_transition_state"]["consumed"] == 2


def test_ask_guidance_persists_a_non_terminal_resumable_seam(
    tmp_path: object,
) -> None:
    wrong = {"ordered": ["pear", "apple", "banana"], "count": 3}
    caller = FakeCaller([
        valid_selection(),
        wrong,
        ask_guidance_evaluation(target="frontier"),
    ])

    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0,
        job_ref="job-guidance",
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        task_ids=("task-guidance",),
        execution_ids=("execution-guidance",),
        outcome_ids=("outcome-guidance",),
        timestamp="2026-09-15T13:00:00+00:00",
        artifact_root=tmp_path,
    )

    assert result["status"] == "awaiting_guidance"
    assert len(result["plan_history"]) == 1
    assert result["execution_transition_state"]["consumed"] == 0
    outcome = result["task_executions"][0]["plan_execution"]["outcomes"][0]
    assert outcome["decision"] == "ASK_GUIDANCE"
    assert outcome["checkpoint_revision_ref"] == "plan-iteration-3@r1"
    assert outcome["checkpoint_outcome_ref"] is None
    assert outcome["resulting_plan_ref"] is None
    assert outcome["guidance"]["target"] == "user"
    assert outcome["guidance"]["policy"] == "USER_ONLY"
    assert outcome["guidance"]["frontier_authorized"] is False
    assert result["resume_state"] == {
        "job_ref": "job-guidance",
        "current_plan_ref": "plan-iteration-3@r1",
        "accepted_checkpoint_ref": "plan-iteration-3@r1",
        "pending_guidance_outcome_ref": "outcome-guidance",
        "status": "awaiting_guidance",
        "guidance_policy": "USER_ONLY",
        "frontier_authorized": False,
        "updated_at": "2026-09-15T13:00:00+00:00",
    }

    restored = load_managed_work_state(
        "job-guidance", artifact_root=tmp_path,
    )
    assert restored["resume_state"] == result["resume_state"]
    assert restored["reasoning_task_count"] == 3
    assert restored["execution_transition_state"]["consumed"] == 0
    restored_outcome = restored["task_executions"][0][
        "plan_execution"
    ]["outcomes"][0]
    assert restored_outcome["id"] == "outcome-guidance"
    assert restored_outcome["guidance"]["question"] == (
        "Should execution use interpretation A?"
    )


def test_user_frontier_policy_persists_and_requires_provider(
    tmp_path: object,
) -> None:
    wrong = {"ordered": ["pear", "apple", "banana"], "count": 3}
    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0,
        job_ref="job-frontier-policy",
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=FakeCaller([
            valid_selection(),
            wrong,
            ask_guidance_evaluation(target="frontier"),
        ]),
        task_ids=("task-frontier",),
        execution_ids=("execution-frontier",),
        outcome_ids=("outcome-frontier",),
        timestamp="2026-09-15T13:30:00+00:00",
        artifact_root=tmp_path,
        guidance_policy="ASK_BEFORE_FRONTIER",
        frontier_authorized=False,
    )

    guidance = result["task_executions"][0]["plan_execution"]["outcomes"][0][
        "guidance"
    ]
    assert FRONTIER_GUIDANCE_PROVIDER is None
    assert guidance["target"] == "user"
    assert guidance["policy"] == "ASK_BEFORE_FRONTIER"
    assert guidance["frontier_authorized"] is False
    assert result["resume_state"]["guidance_policy"] == (
        "ASK_BEFORE_FRONTIER"
    )
    assert result["resume_state"]["frontier_authorized"] is False

    updated = update_managed_work_guidance_policy(
        "job-frontier-policy",
        guidance_policy="FRONTIER_ALLOWED",
        frontier_authorized=True,
        artifact_root=tmp_path,
        timestamp="2026-09-15T13:31:00+00:00",
    )
    assert updated["guidance_policy"] == "FRONTIER_ALLOWED"
    assert updated["frontier_authorized"] is True
    restored = load_managed_work_state(
        "job-frontier-policy", artifact_root=tmp_path,
    )
    assert restored["resume_state"] == updated

    assert resolve_guidance_target(
        "frontier",
        guidance_policy="FRONTIER_ALLOWED",
        frontier_authorized=True,
        frontier_provider_ref=None,
    ) == "user"
    assert resolve_guidance_target(
        "frontier",
        guidance_policy="FRONTIER_ALLOWED",
        frontier_authorized=True,
        frontier_provider_ref="configured-frontier-adviser",
    ) == "frontier"


def test_frontier_allowed_requires_explicit_persisted_authorization(
    tmp_path: object,
) -> None:
    caller = FakeCaller([])
    with pytest.raises(ValueError, match="explicit persisted authorization"):
        run_iteration_3(
            certified_plan(), reasoning_task_count=0,
            job_ref="job-invalid-frontier-policy",
            resolved_inputs={"request:abc123": "sort these values"},
            model_caller=caller,
            artifact_root=tmp_path,
            guidance_policy="FRONTIER_ALLOWED",
            frontier_authorized=False,
        )
    assert caller.calls == []


def test_ask_guidance_is_not_enabled_without_persistence() -> None:
    wrong = {"ordered": ["pear", "apple", "banana"], "count": 3}
    ask = ask_guidance_evaluation()
    caller = FakeCaller([
        valid_selection(), wrong, ask, ask,
    ])

    with pytest.raises(ValueError, match="after one conformance repair"):
        run_iteration_3(
            certified_plan(), reasoning_task_count=0,
            job_ref="job-no-guidance-persistence",
            resolved_inputs={"request:abc123": "sort these values"},
            model_caller=caller,
        )

    assert len(caller.calls) == 4


def test_completed_run_persists_immutable_artifacts_and_resume(
    tmp_path: object,
) -> None:
    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0,
        job_ref="job-persisted-accept",
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=FakeCaller([
            valid_selection(), exact_worker_result(), accept_evaluation(),
        ]),
        task_ids=("task-persisted",),
        execution_ids=("execution-persisted",),
        outcome_ids=("outcome-persisted",),
        timestamp="2026-09-15T14:00:00+00:00",
        artifact_root=tmp_path,
    )
    paths = managed_work_artifact_paths(
        "job-persisted-accept", artifact_root=tmp_path,
    )

    assert paths["request"].is_file()
    assert (paths["plans"] / "rev-0001.json").is_file()
    assert len(list(paths["tasks"].glob("*.json"))) == 1
    assert len(list(paths["executions"].glob("*.json"))) == 1
    assert len(list(paths["calls"].glob("*.request.json"))) == 6
    assert len(list(paths["calls"].glob("*.response.json"))) == 6
    assert len([call for call in result["calls"] if call["reasoning_task"] is not None]) == 3
    assert result["resume_state"]["status"] == "completed"
    assert result["resume_state"]["accepted_checkpoint_ref"] == (
        "outcome-persisted"
    )
    assert result["task_executions"][0]["persistence"]["save"] is True

    restored = load_managed_work_state(
        "job-persisted-accept", artifact_root=tmp_path,
    )
    assert restored["resume_state"] == result["resume_state"]
    assert restored["reasoning_task_count"] == 3

    altered = deepcopy(result)
    altered["plan_history"][0]["goal"] = "Mutated history is forbidden."
    with pytest.raises(FileExistsError, match="already differs"):
        persist_managed_work_run(
            altered,
            job_ref="job-persisted-accept",
            resolved_inputs={"request:abc123": "sort these values"},
            artifact_root=tmp_path,
            timestamp="2026-09-15T14:00:00+00:00",
        )


def test_execution_transition_budget_stops_before_unconfigured_r5() -> None:
    wrong = {"ordered": ["pear", "apple", "banana"], "count": 3}
    outputs: list[object] = []
    for revision in range(1, 5):
        outputs.extend([
            valid_selection(),
            wrong,
            revise_evaluation(),
        ])
        if revision < 4:
            outputs.append(successor_plan_semantics(f"revision {revision + 1}"))
            outputs.append({"compliant": True, "violations": []})
    caller = FakeCaller(outputs)

    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0,
        job_ref="job-iteration-3",
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller,
        task_ids=tuple(f"task-{number}" for number in range(1, 5)),
        execution_ids=tuple(
            f"execution-{number}" for number in range(1, 5)
        ),
        outcome_ids=tuple(f"outcome-{number}" for number in range(1, 5)),
    )

    assert result["status"] == "execution_transition_budget_exhausted"
    assert len(result["plan_history"]) == 4
    assert len(result["director_tasks"]) == 4
    assert result["execution_transition_state"] == {
        "maximum": 3,
        "consumed": 3,
        "remaining": 0,
        "can_create_successor": False,
        "current_plan_ref": "plan-iteration-3@r4",
    }


# These fixtures supply model judgments. They validate wiring, not live reasoning.
FEASIBLE_MANDATE = (
    "Produce a feasible configuration and a validation record. "
    "An incompatibility report is useful evidence, not alternative fulfillment. "
    "Do not relax mandatory constraints without user authority. "
    "Detailed constraints arrive during execution."
)
IMPOSSIBILITY_EVIDENCE = {
    "configuration": None,
    "constraints": [{"id": "minimum", "x_min": 10}, {"id": "maximum", "x_max": 5}],
    "proof": "Every feasible X would require 10 <= X <= 5; the intersection is empty.",
}


def mandate_root(request: str) -> dict[str, object]:
    from hashlib import sha256

    plan = certified_plan()
    reference = "request:" + sha256(request.encode("utf-8")).hexdigest()
    plan["current_work_ref"] = reference
    for step in plan["steps"]:
        step["target_ref"] = reference
    plan["goal"] = "Produce a feasible configuration."
    plan["steps"] = plan["steps"][:1]
    plan["steps"][0].update(
        action="Determine and validate a feasible configuration.",
        instructions=["Use execution-time constraints; report impossibility truthfully."],
        expected_result="A feasible configuration with constraint-by-constraint validation.",
        validation=["Every mandatory constraint is satisfied."],
    )
    return plan


@pytest.mark.parametrize("inputs", [{}, {"wrong": "contents"}, "not a mapping"])
def test_missing_original_mandate_stops_before_reasoning(inputs: object) -> None:
    from orchestrator import resolve_original_request

    plan = mandate_root(FEASIBLE_MANDATE)
    with pytest.raises(ValueError, match="Original request"):
        resolve_original_request(plan, inputs)


def test_original_mandate_digest_checked_before_run_and_after_reload(tmp_path: Path) -> None:
    request = "Determine whether the authoritative requirements are feasible."
    plan = mandate_root(request)
    plan["goal"] = request
    plan["steps"][0].update(
        action="Assess joint feasibility of the requirements.",
        expected_result="A supported feasibility determination, including an infeasibility proof when applicable.",
        validation=["The evidence supports the feasibility determination."],
    )
    inputs = {plan["current_work_ref"]: request}
    caller = FakeCaller([])
    with pytest.raises(ValueError, match="digest"):
        run_iteration_3(
            plan, reasoning_task_count=0, job_ref="tampered", resolved_inputs={plan["current_work_ref"]: "Weakened mandate"},
            model_caller=caller, artifact_root=tmp_path,
        )
    assert caller.calls == []
    with pytest.raises(ValueError, match="digest"):
        persist_managed_work_run(
            {"plan_history": [plan]}, job_ref="tampered-persist",
            resolved_inputs={plan["current_work_ref"]: "Weakened mandate"},
            artifact_root=tmp_path,
        )
    assert not managed_work_artifact_paths("tampered-persist", artifact_root=tmp_path)["request"].exists()

    caller = FakeCaller([valid_selection(), IMPOSSIBILITY_EVIDENCE, accept_evaluation()])
    result = run_iteration_3(
        plan, reasoning_task_count=0, job_ref="diagnostic", resolved_inputs=inputs,
        model_caller=caller, artifact_root=tmp_path,
    )
    assert result["status"] == "accepted"  # Supplied semantic judgment is authoritative.
    paths = managed_work_artifact_paths("diagnostic", artifact_root=tmp_path)
    snapshot = json.loads(paths["request"].read_text())
    snapshot["resolved_inputs"][plan["current_work_ref"]] = "Weakened mandate"
    paths["request"].write_text(json.dumps(snapshot))
    with pytest.raises(ValueError, match="digest"):
        load_managed_work_state("diagnostic", artifact_root=tmp_path)


def test_impossibility_guidance_keeps_completed_execution_and_original_mandate(tmp_path: Path) -> None:
    plan = mandate_root(FEASIBLE_MANDATE)
    guidance = ask_guidance_evaluation(target="frontier")
    guidance["reason"] = "The requested configuration cannot exist without changing a mandatory requirement."
    guidance["guidance"].update(
        hurdle="Mandatory minimum 10 exceeds maximum 5.",
        materiality="No requested feasible configuration exists.",
        attempts=[{
            "description": "Intersected all mandatory bounds.",
            "established": "The intersection is empty.",
            "evidence_numbers": [1],
        }],
        remaining_unresolved="Which constraint, if any, may be changed?",
        options=["Authorize lowering the minimum.", "Authorize raising the maximum.", "Keep requirements and pause."],
        recommendation="Ask the requirement owner which bound may change.",
        question="May either mandatory bound be relaxed, and which one?",
    )
    caller = FakeCaller([valid_selection(), IMPOSSIBILITY_EVIDENCE, guidance])
    result = run_iteration_3(
        plan, reasoning_task_count=0, job_ref="impossible", resolved_inputs={plan["current_work_ref"]: FEASIBLE_MANDATE},
        model_caller=caller, artifact_root=tmp_path,
    )
    execution = result["task_executions"][0]
    assert execution["control"]["status"] == "completed"
    assert execution["plan_execution"]["validation_outcome"] == "passed"
    assert execution["result"]["content"] == IMPOSSIBILITY_EVIDENCE
    assert result["resume_state"]["status"] == "awaiting_guidance"
    assert result["execution_transition_state"]["consumed"] == 0
    assert result["task_executions"][0]["plan_execution"]["outcomes"][0]["guidance"]["target"] == "user"
    for index in (0, 2):
        payload = json.loads(caller.calls[index][1][1]["content"])
        assert payload["frozen_request"] == FEASIBLE_MANDATE
        assert "semantic_plan_fidelity" in payload
    restored = load_managed_work_state("impossible", artifact_root=tmp_path)
    assert restored["resume_state"] == result["resume_state"]
    assert restored["resolved_inputs"][plan["current_work_ref"]] == FEASIBLE_MANDATE


@pytest.mark.parametrize("corrected", [True, False])
def test_successor_fidelity_gate_precedes_publication(corrected: bool, tmp_path: Path) -> None:
    request = FEASIBLE_MANDATE + " Either approved method A or B may be used."
    plan = mandate_root(request)
    before = json.dumps(plan, sort_keys=True)
    evidence = {"method_A": "unavailable", "method_B": "authorized and available"}
    bad = successor_plan_semantics("unauthorized relaxation")
    bad["plan_steps"]["steps"][0]["expected_result"] = "A configuration OR an incompatibility report."
    good = successor_plan_semantics("authorized method B")
    good["overall_synthesis"]["goal"] = plan["goal"]
    good["plan_steps"]["steps"][0].update(
        action="Determine and validate a feasible configuration using method B.",
        instructions=["Apply authorized method B without relaxing mandatory constraints."],
        expected_result=plan["steps"][0]["expected_result"],
        validation=plan["steps"][0]["validation"],
    )
    violation = {
        "compliant": False,
        "violations": [{
            "finding": "The original request excludes a report as fulfillment; candidate expected_result accepts it.",
            "affected_step_or_field": "steps[0].expected_result",
        }],
    }
    outputs = [
        valid_selection(), evidence, revise_evaluation(), bad,
        violation, good,
        {"compliant": True, "violations": []} if corrected else violation,
    ]
    if corrected:
        outputs.extend([valid_selection(), {"configuration": {"x": 12}}, accept_evaluation()])
    caller = FakeCaller(outputs)
    result = run_iteration_3(
        plan, reasoning_task_count=0, job_ref="successor-fidelity", resolved_inputs={plan["current_work_ref"]: request},
        model_caller=caller, artifact_root=tmp_path,
    )
    assert json.dumps(plan, sort_keys=True) == before
    assert len(result["semantic_boundary_corrections"]) == 1
    assert result["conformance_repairs"] == []
    paths = managed_work_artifact_paths("successor-fidelity", artifact_root=tmp_path)
    assert json.loads((paths["plans"] / "rev-0001.json").read_text()) == plan
    for index in (0, 2, 3, 4, 5, 6):
        payload = json.loads(caller.calls[index][1][1]["content"])
        assert payload["frozen_request"] == request
        assert "semantic_plan_fidelity" in payload
    assert caller.calls[4][0] == caller.calls[6][0] == "gemma_worker"
    assert caller.calls[5][0] == "gemma_director"
    outcome = result["task_executions"][0]["plan_execution"]["outcomes"][0]
    assert outcome["decision"] == "REVISE"
    assert outcome["checkpoint_revision_ref"] == plan["revision_ref"]
    assert outcome["checkpoint_outcome_ref"] is None
    assert result["task_executions"][0]["result"]["content"] == evidence
    if corrected:
        assert result["status"] == "accepted"
        assert result["execution_transition_state"]["consumed"] == 1
        successor = result["plan_history"][1]
        assert successor["revision"] == 2
        assert successor["based_on_revision_ref"] == plan["revision_ref"]
        assert successor["steps"][0]["expected_result"] == good["plan_steps"]["steps"][0]["expected_result"]
        assert outcome["resulting_plan_ref"] == successor["revision_ref"]
        gate_calls = json.loads(caller.calls[4][1][1]["content"])
        assert gate_calls["execution_context"]["triggering_execution"]["result"]["content"] == evidence
    else:
        assert result["status"] == "semantic_plan_unresolved"
        assert "excludes a report" in result["semantic_plan_error"]
        assert result["resume_state"]["status"] == "unresolved"
        assert result["resume_state"]["current_plan_ref"] == plan["revision_ref"]
        assert result["execution_transition_state"]["consumed"] == 0
        assert outcome["resulting_plan_ref"] is None
        assert not (paths["plans"] / "rev-0002.json").exists()
    assert load_managed_work_state("successor-fidelity", artifact_root=tmp_path)["resume_state"] == result["resume_state"]


def test_intermediate_accept_preserves_overall_mandate_until_completion(tmp_path: Path) -> None:
    request = FEASIBLE_MANDATE + " Either approved method A or B may be used."
    plan = mandate_root(request)
    successor = successor_plan_semantics("method B")
    successor["overall_synthesis"]["goal"] = plan["goal"]
    successor["plan_steps"]["steps"][0].update(
        action=plan["steps"][0]["action"],
        instructions=["Apply approved method B and validate every mandatory constraint."],
        expected_result=plan["steps"][0]["expected_result"],
        validation=plan["steps"][0]["validation"],
    )
    plan["steps"][0].update(
        action="Determine which approved methods are available.",
        instructions=["Inspect availability evidence for both approved methods."],
        expected_result="An evidence-backed assessment of approved method availability.",
        validation=["Both approved methods have an evidence-backed availability status."],
    )
    inputs = {plan["current_work_ref"]: request}
    outputs = [
        valid_selection(), {"diagnosis": "Method A is unavailable; B remains authorized."},
        accept_evaluation(continue_work=True), successor,
        {"compliant": True, "violations": []},
        valid_selection(), {"configuration": {"x": 12}}, accept_evaluation(),
    ]
    caller = FakeCaller(outputs)
    result = run_iteration_3(
        plan, reasoning_task_count=0, job_ref="intermediate", resolved_inputs=inputs,
        model_caller=caller, artifact_root=tmp_path,
    )
    assert len(result["task_executions"]) == 2
    assert result["resume_state"]["status"] == "completed"
    first = result["task_executions"][0]["plan_execution"]["outcomes"][0]
    assert first["decision"] == "ACCEPT"
    assert first["resulting_plan_ref"].endswith("@r2")
    for index in (2, 7):
        system = caller.calls[index][1][0]["content"]
        assert "intermediate step success alone is insufficient" in system
        payload = json.loads(caller.calls[index][1][1]["content"])
        assert payload["frozen_request"] == request
        assert "steps" in payload["certified_plan"]
    final_payload = json.loads(caller.calls[7][1][1]["content"])
    assert final_payload["prior_execution_evidence"][0]["outcomes"][0]["id"] == first["id"]


@pytest.mark.parametrize("recovered", [True, False])
@pytest.mark.parametrize("mode", ["conformance", "semantic_completion"])
def test_successor_gate_recovery_is_bounded_and_grounded(
    mode: str, recovered: bool, tmp_path: Path,
) -> None:
    malformed = {"compliant": "true", "violations": []}
    incomplete = {}
    initial = malformed if mode == "conformance" else incomplete
    outputs = [
        valid_selection(), {"ordered": ["pear", "apple", "banana"], "count": 3},
        revise_evaluation(), successor_plan_semantics(), initial,
        {"compliant": True, "violations": []} if recovered else initial,
    ]
    if recovered:
        outputs.extend([valid_selection(), exact_worker_result(), accept_evaluation()])
    caller = FakeCaller(outputs)
    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0, job_ref="gate-recovery",
        resolved_inputs={"request:abc123": "sort these values"},
        model_caller=caller, artifact_root=tmp_path,
    )
    assert caller.calls[4][0] == caller.calls[5][0] == "gemma_worker"
    assert len(result["conformance_repairs"]) == (1 if mode == "conformance" else 0)
    assert len(result["semantic_completions"]) == (1 if mode == "semantic_completion" else 0)
    assert result["semantic_boundary_corrections"] == []
    assert result["semantic_iteration_count"] == 3
    assert result["execution_transition_state"]["consumed"] == (1 if recovered else 0)
    assert result["status"] == ("accepted" if recovered else "semantic_plan_unresolved")
    assert len(caller.calls) == (9 if recovered else 6)
    if mode == "semantic_completion":
        payload = json.loads(caller.calls[5][1][1]["content"])
        assert payload["frozen_request"] == "sort these values"
        context = payload["semantic_context"]
        assert context["frozen_architecture_invariants"]
        assert context["candidate_plan"]["revision_ref"].endswith("@r2")
        assert context["execution_context"]["triggering_execution"]["result"]["content"] == outputs[1]
    assert load_managed_work_state("gate-recovery", artifact_root=tmp_path)["resume_state"] == result["resume_state"]


def test_successor_gate_budget_exhaustion_preserves_evidence_without_transition(tmp_path: Path) -> None:
    caller = FakeCaller([
        valid_selection(), IMPOSSIBILITY_EVIDENCE, revise_evaluation(),
        successor_plan_semantics(),
    ])
    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0, job_ref="gate-budget",
        resolved_inputs={"request:abc123": FEASIBLE_MANDATE},
        model_caller=caller, artifact_root=tmp_path, reasoning_task_limit=4,
    )
    assert result["status"] == "semantic_plan_unresolved"
    assert "budget exhausted" in result["semantic_plan_error"]
    assert result["reasoning_task_count"] == 4
    assert result["execution_transition_state"]["consumed"] == 0
    assert result["resume_state"]["status"] == "unresolved"
    assert result["task_executions"][0]["control"]["status"] == "completed"


def test_iteration_3_requires_certified_plan_semantic_iteration() -> None:
    caller = FakeCaller([
        valid_selection(),
        exact_worker_result(),
        accept_evaluation(),
    ])

    with pytest.raises(ValueError, match="semantic iteration 3"):
        run_iteration_3(
            certified_plan(), reasoning_task_count=0,
            job_ref="job-iteration-3",
            resolved_inputs={"request:abc123": "sort these values"},
            model_caller=caller,
            semantic_iteration_count=2,
        )

    assert caller.calls == []
def test_task_executive_rejects_active_job_mismatch_before_resolution() -> None:
    plan, handoff = task_handoff()
    caller = FakeCaller([exact_worker_result()])

    with pytest.raises(ValueError, match="before resolution"):
        execute_managed_director_task(
            handoff["director_task"],
            job_ref="different-active-job",
            certified_plan=plan,
            selected_step=handoff["selected_step"],
            resolved_inputs={"request:abc123": "sort these values"},
            model_caller=caller,
        )

    assert caller.calls == []
