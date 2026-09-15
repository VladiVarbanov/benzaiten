from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path

import pytest

from config import (
    LOGICAL_CONTEXTS,
    NORMAL_PLANNING_CONTEXTS,
    PLAN_PROTOCOL_PATH,
    QWEN_MODEL,
)
from director import run_normal_planning
from model_client import ModelClient, ModelResponse
from planning import (
    ARCHITECTURE_ASSESSMENT_SEMANTIC_SHAPE,
    ASSESSMENT_CRITERIA,
    ASSESSMENT_SEMANTIC_SHAPE,
    CHANGE_DISPOSITION_SEMANTIC_SHAPE,
    FROZEN_ARCHITECTURE_INVARIANTS,
    NO_MANUFACTURED_DISAGREEMENT,
    OVERALL_SYNTHESIS_SEMANTIC_SHAPE,
    PLAN_STEPS_SEMANTIC_SHAPE,
    PROPOSAL_SEMANTIC_SHAPE,
    architecture_assessment_response_format,
    assemble_final_plan,
    assemble_proposal,
    change_disposition_numbers,
    change_disposition_response_format,
    combine_synthesis_semantics,
    overall_synthesis_response_format,
    parse_json_object,
    plan_steps_response_format,
    render_architecture_assessment_messages,
    render_conformance_repair_messages,
    render_proposal_messages,
    render_semantic_completion_messages,
    semantic_plan_fidelity_policy,
    validate_architecture_assessment_semantics,
    validate_assessment_semantics,
    validate_change_disposition_semantics,
    validate_final_plan,
    validate_overall_synthesis_semantics,
    validate_plan_steps_semantics,
    validate_proposal,
    validate_proposal_semantics,
)
from structures import ValidationIssue

REQUEST = (
    'Alphabetically sort ["pear", "apple", "banana"]. Return only a JSON '
    'object with exactly two keys: ordered, containing the sorted array, and '
    'count, containing 3.'
)


def proposal(assigned: dict[str, object], label: str) -> dict[str, object]:
    return {
        "id": assigned["id"],
        "iteration": assigned["iteration"],
        "author_ref": assigned["author_ref"],
        "summary": f"{label} proposes a single bounded sorting step.",
        "main_points": ["Sort ascending and return exactly ordered and count."],
        "reason": "The request is deterministic and fully specified.",
        "assumptions": ["Alphabetical means ascending lexical order."],
        "message_refs": [],
        "artifact_refs": [],
        "proposal_state": assigned["proposal_state"],
        "proposal_reason": None,
        "decided_by_ref": None,
        "decided_in_revision_ref": None,
    }


def proposal_semantics(label: str) -> dict[str, object]:
    return {
        "summary": f"{label} proposes a single bounded sorting step.",
        "main_points": ["Sort ascending and return ordered and count."],
        "assumptions": ["Alphabetical means ascending lexical order."],
        "reason": "The request is deterministic and fully specified.",
    }


def assessment_semantics(label: str) -> dict[str, object]:
    return {
        "severity": "low",
        "strengths": [f"{label} finds the approach direct and bounded."],
        "weaknesses": [],
        "uncertainty": [],
        "missing_information": [],
        "useful_questions": [],
        "complementary_ideas": ["Explicitly validate the output key set."],
        "genuine_contradictions_or_tradeoffs": [],
        "synthesis_or_improvement_opportunities": [
            "Combine the shared sort and validation approach."
        ],
        "suggested_changes": [],
    }


def overall_synthesis_semantics() -> dict[str, object]:
    return {
        "goal": "Plan the requested alphabetical sort without executing it.",
        "approach_summary": ["Use one deterministic sort-and-format step."],
        "decision_rationale": (
            "Both proposals converge and both assessments find no conflict."
        ),
        "rejected_alternatives": [],
        "change_summary": [
            "Synthesized both proposals and reciprocal assessments."
        ],
        "decision_reason": (
            "The reciprocal assessments reveal no material conflict."
        ),
        "unresolved_risks": [],
        "unresolved_questions": [],
    }


def plan_steps_semantics() -> dict[str, object]:
    return {
        "steps": [{
            "action": "Sort the supplied strings and format the result.",
            "reason": "This directly satisfies the frozen request.",
            "instructions": [
                "Sort pear, apple, and banana alphabetically.",
                "Return only ordered and count.",
            ],
            "scope_boundary": "Do not execute during planning or add prose.",
            "expected_result": (
                '{"ordered":["apple","banana","pear"],"count":3}'
            ),
            "validation": [
                "Output has exactly ordered and count.",
                "ordered is alphabetic and count equals 3.",
            ],
            "depends_on_step_numbers": [],
        }],
    }


def change_disposition_semantics(
    *dispositions: tuple[int, str],
) -> dict[str, object]:
    return {
        "dispositions": [
            {"change_number": number, "disposition": disposition}
            for number, disposition in dispositions
        ]
    }


def architecture_assessment_semantics(
    *,
    compliant: bool = True,
    violations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "compliant": compliant,
        "violations": [] if violations is None else deepcopy(violations),
    }


def architecture_violation(
    finding: str,
    affected_step_or_field: str | None,
) -> dict[str, object]:
    return {
        "finding": finding,
        "affected_step_or_field": affected_step_or_field,
    }


def boundary_correction_semantics(
    *,
    overall: dict[str, object] | None = None,
    steps: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "overall_synthesis": (
            overall_synthesis_semantics() if overall is None else overall
        ),
        "plan_steps": plan_steps_semantics() if steps is None else steps,
    }


def assessment_with_change(label: str) -> dict[str, object]:
    result = assessment_semantics(label)
    result["suggested_changes"] = [{
        "description": "Validate the output key set explicitly.",
        "reason": "The output contract requires exactly two keys.",
    }]
    return result


class CapturingCaller:
    def __init__(
        self,
        *,
        director_outputs: list[object] | None = None,
        assessment_outputs: list[dict[str, object]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, tuple[dict[str, str], ...]]] = []
        self.response_formats: list[dict[str, object] | None] = []
        self.chat_template_kwargs: list[dict[str, object] | None] = []
        self.director_outputs = deepcopy(
            [
                overall_synthesis_semantics(),
                plan_steps_semantics(),
                architecture_assessment_semantics(),
            ]
            if director_outputs is None
            else director_outputs
        )
        self.assessment_outputs = deepcopy(
            [assessment_semantics("Qwen"), assessment_semantics("Gemma")]
            if assessment_outputs is None
            else assessment_outputs
        )

    def __call__(
        self,
        context_name: str,
        messages: tuple[dict[str, str], ...],
        *,
        response_format: dict[str, object] | None,
        chat_template_kwargs: dict[str, object] | None,
    ) -> ModelResponse:
        self.calls.append((context_name, deepcopy(messages)))
        self.response_formats.append(deepcopy(response_format))
        self.chat_template_kwargs.append(deepcopy(chat_template_kwargs))
        index = len(self.calls)
        if index == 1:
            result: object = proposal_semantics("Gemma")
        elif index == 2:
            result = proposal_semantics("Qwen")
        elif index in (3, 4):
            result = self.assessment_outputs[index - 3]
        else:
            director_index = index - 5
            if director_index >= len(self.director_outputs):
                raise AssertionError("Normal planning exceeded expected calls")
            result = self.director_outputs[director_index]
        output = result if isinstance(result, str) else json.dumps(result)
        return ModelResponse(
            request_id=f"request-{index}",
            server_request_id=f"server-{index}",
            model_name=LOGICAL_CONTEXTS[context_name].worker_ref,
            text=output,
            reasoning_text=None,
            finish_reason="stop",
            prompt_tokens=10 * index,
            completion_tokens=20 * index,
            total_tokens=30 * index,
            latency_ms=float(index),
        )


def run_fixture() -> tuple[dict[str, object], CapturingCaller]:
    caller = CapturingCaller()
    trace = run_normal_planning(
        REQUEST,
        model_caller=caller,
        plan_id="plan-test",
    )
    return dict(trace), caller


def test_proposals_share_frozen_input_without_cross_leakage() -> None:
    trace, caller = run_fixture()
    gemma_payload = json.loads(caller.calls[0][1][1]["content"])
    qwen_payload = json.loads(caller.calls[1][1][1]["content"])

    assert gemma_payload["frozen_request"] == qwen_payload["frozen_request"] == REQUEST
    assert caller.calls[0][1] == caller.calls[1][1]
    assert set(gemma_payload) == set(qwen_payload) == {
        "frozen_request", "normal_policy", "required_semantic_output", "rules"
    }
    assert set(gemma_payload["required_semantic_output"]) == set(
        PROPOSAL_SEMANTIC_SHAPE
    )
    trusted_fields = {
        "id", "author_ref", "iteration", "message_refs", "artifact_refs",
        "proposal_state", "proposal_reason", "decided_by_ref",
        "decided_in_revision_ref",
    }
    assert not trusted_fields & set(gemma_payload["required_semantic_output"])
    gemma_messages = json.dumps(caller.calls[0][1])
    qwen_messages = json.dumps(caller.calls[1][1])
    assert trace["qwen_proposal"]["summary"] not in gemma_messages
    assert trace["gemma_proposal"]["summary"] not in qwen_messages
    assert "target_proposal" not in gemma_payload
    assert "target_proposal" not in qwen_payload


def test_assessments_are_reciprocal_and_constructive() -> None:
    trace, caller = run_fixture()
    qwen_payload = json.loads(caller.calls[2][1][1]["content"])
    gemma_payload = json.loads(caller.calls[3][1][1]["content"])

    assert qwen_payload["target_proposal"] == trace["gemma_proposal"]
    assert gemma_payload["target_proposal"] == trace["qwen_proposal"]
    for payload in (qwen_payload, gemma_payload):
        assert payload["assessment_criteria"] == list(ASSESSMENT_CRITERIA)
        assert payload["assessment_rule"] == NO_MANUFACTURED_DISAGREEMENT
        assert NO_MANUFACTURED_DISAGREEMENT in caller.calls[2][1][0]["content"]


def test_director_synthesis_is_split_into_focused_semantic_units() -> None:
    trace, caller = run_fixture()

    assert [item["stage"] for item in trace["calls"][4:]] == [
        "director_overall_synthesis",
        "director_plan_steps",
        "architecture_assessment",
    ]
    overall_payload = json.loads(caller.calls[4][1][1]["content"])
    steps_payload = json.loads(caller.calls[5][1][1]["content"])
    for payload in (overall_payload, steps_payload):
        assert payload["gemma_proposal"] == trace["gemma_proposal"]
        assert payload["qwen_proposal"] == trace["qwen_proposal"]
        assert payload["qwen_assessment_of_gemma"] == trace["qwen_assessment"]
        assert payload["gemma_assessment_of_qwen"] == trace["gemma_assessment"]
    assert set(overall_payload["required_semantic_output"]) == set(
        OVERALL_SYNTHESIS_SEMANTIC_SHAPE
    )
    assert set(steps_payload["required_semantic_output"]) == set(
        PLAN_STEPS_SEMANTIC_SHAPE
    )
    assert "steps" not in overall_payload["required_semantic_output"]
    assert "goal" not in steps_payload["required_semantic_output"]
    forbidden = {
        "plan_id", "revision_ref", "participants", "integrity", "status",
        "created_at", "author_ref", "task_ref", "id",
    }
    assert not forbidden & set(overall_payload["required_semantic_output"])
    assert not forbidden & set(
        steps_payload["required_semantic_output"]["steps"][0]
    )
    requirements = json.dumps(
        overall_payload["requirements"] + steps_payload["requirements"]
    )
    assert "Director selects semantic requirements" in requirements
    assert "Task Executive and configuration" in requirements
    assert "Plan is passive structured state" in requirements
    assert "Do not introduce a Router" in requirements
    assert "frontier escalation" in requirements


def test_zero_changes_skip_disposition_call_and_use_empty_semantics() -> None:
    trace, caller = run_fixture()

    assert trace["change_dispositions"] == {"dispositions": []}
    assert all(
        item["stage"] != "director_change_disposition"
        for item in trace["calls"]
    )
    assert len(caller.calls) == 7


def test_generic_conformance_repair_accepts_policy_issue_categories() -> None:
    issues = (
        ValidationIssue("artifact.field", "invalid_shape", "Wrong structure."),
        ValidationIssue("artifact.ref", "invalid_reference", "Unknown ID."),
        ValidationIssue(
            "artifact.integrity",
            "invalid_partition",
            "Incomplete classification.",
        ),
    )

    messages = render_conformance_repair_messages(
        artifact_kind="test_artifact",
        invalid_output='{"field": "invalid"}',
        validation_issues=issues,
        valid_references={"ids": ["valid-id"]},
        required_output={"field": "<value>"},
    )
    payload = json.loads(messages[1]["content"])

    assert payload["invalid_output"] == '{"field": "invalid"}'
    assert payload["valid_references"] == {"ids": ["valid-id"]}
    assert [item["code"] for item in payload["validation_issues"]] == [
        "invalid_shape",
        "invalid_reference",
        "invalid_partition",
    ]


def test_conformance_repair_rejects_missing_semantic_decisions() -> None:
    issue = ValidationIssue(
        "artifact.decision",
        "missing_semantic_decision",
        "A semantic judgment is absent.",
    )

    with pytest.raises(ValueError, match="non-conformance"):
        render_conformance_repair_messages(
            artifact_kind="test_artifact",
            invalid_output="{}",
            validation_issues=(issue,),
            valid_references={},
            required_output={"decision": "<value>"},
        )


def test_semantic_completion_accepts_only_missing_decisions() -> None:
    missing = ValidationIssue(
        "artifact.decision",
        "missing_semantic_decision",
        "A semantic judgment is absent.",
    )
    messages = render_semantic_completion_messages(
        artifact_kind="test_artifact",
        incomplete_output="{}",
        missing_decisions=(missing,),
        valid_references={"ids": ["valid-id"]},
        required_output={"decision": "<value>"},
    )
    payload = json.loads(messages[1]["content"])

    assert payload["incomplete_output"] == "{}"
    assert payload["missing_semantic_decisions"][0]["code"] == (
        "missing_semantic_decision"
    )
    with pytest.raises(ValueError, match="missing semantic decisions"):
        render_semantic_completion_messages(
            artifact_kind="test_artifact",
            incomplete_output="{}",
            missing_decisions=(
                ValidationIssue("artifact", "invalid_shape", "Malformed."),
            ),
            valid_references={},
            required_output={},
        )


def test_focused_synthesis_schemas_contain_only_semantic_fields() -> None:
    disposition_schema = change_disposition_response_format()[
        "json_schema"
    ]["schema"]
    item_schema = disposition_schema["properties"]["dispositions"]["items"]
    assert set(item_schema["properties"]) == {
        "change_number", "disposition",
    }
    assert item_schema["properties"]["disposition"]["enum"] == [
        "accepted", "rejected", "deferred",
    ]
    assert "[1]" not in json.dumps(CHANGE_DISPOSITION_SEMANTIC_SHAPE)
    assert set(
        overall_synthesis_response_format()["json_schema"]["schema"][
            "properties"
        ]
    ) == set(OVERALL_SYNTHESIS_SEMANTIC_SHAPE)
    dependency_schema = plan_steps_response_format()["json_schema"][
        "schema"
    ]["properties"]["steps"]["items"]["properties"][
        "depends_on_step_numbers"
    ]
    assert dependency_schema == {
        "type": "array",
        "items": {"type": "integer"},
    }


def test_every_supplied_change_receives_exactly_one_disposition() -> None:
    duplicate = change_disposition_semantics(
        (1, "accepted"),
        (1, "rejected"),
    )
    issues = validate_change_disposition_semantics(
        duplicate,
        suggested_change_count=2,
    )
    assert any(issue.code == "duplicate_value" for issue in issues)
    assert any(
        issue.code == "missing_semantic_decision"
        and "change_number=2" in issue.field
        for issue in issues
    )

    complete = change_disposition_semantics(
        (1, "accepted"),
        (2, "deferred"),
        (3, "rejected"),
    )
    assert validate_change_disposition_semantics(
        complete,
        suggested_change_count=3,
    ) == ()
    assert change_disposition_numbers(
        complete,
        suggested_change_count=3,
    ) == {
        "accepted_change_numbers": [1],
        "rejected_change_numbers": [3],
        "deferred_change_numbers": [2],
    }


def test_zero_and_nonexistent_change_references_remain_strict() -> None:
    assert validate_change_disposition_semantics(
        {"dispositions": []},
        suggested_change_count=0,
    ) == ()
    issues = validate_change_disposition_semantics(
        change_disposition_semantics((1, "accepted")),
        suggested_change_count=0,
    )
    assert any(issue.code == "invalid_reference" for issue in issues)

    issues = validate_change_disposition_semantics(
        change_disposition_semantics((2, "accepted")),
        suggested_change_count=1,
    )
    assert any(issue.code == "invalid_reference" for issue in issues)
    assert any(issue.code == "missing_semantic_decision" for issue in issues)


def test_python_combines_semantics_without_inventing_content() -> None:
    dispositions = change_disposition_semantics((1, "accepted"))
    overall = overall_synthesis_semantics()
    steps = plan_steps_semantics()
    combined = combine_synthesis_semantics(
        dispositions,
        overall,
        steps,
        suggested_change_count=1,
    )

    assert combined == {
        **overall,
        "accepted_change_numbers": [1],
        "rejected_change_numbers": [],
        "deferred_change_numbers": [],
        **steps,
    }
    with pytest.raises(ValueError, match="Cannot map incomplete"):
        combine_synthesis_semantics(
            {"dispositions": []},
            overall,
            steps,
            suggested_change_count=1,
        )


def test_python_creates_trusted_plan_bookkeeping() -> None:
    trace, _ = run_fixture()
    plan = trace["final_plan"]

    assert plan["plan_id"] == "plan-test"
    assert plan["revision_ref"] == "plan-test@r1"
    assert plan["status"] == "final"
    assert plan["planning_cycle"]["decisions"][0]["id"] == (
        "plan-test:decision-finalize"
    )
    assert plan["steps"][0]["id"] == "plan-test@r1:step-1"
    assert plan["steps"][0]["target_ref"] == plan["current_work_ref"]
    assert plan["steps"][0]["status"] == "proposed"
    assert plan["integrity"]["validation"]["status"] == "valid"
    assert set(plan) == set(json.loads(PLAN_PROTOCOL_PATH.read_text()))


def test_supported_planning_calls_constrain_semantics_only() -> None:
    trace, caller = run_fixture()

    assert len(caller.response_formats) == 7
    assert caller.response_formats[0] is None
    assert caller.response_formats[3:] == [None, None, None, None]
    for index in (1, 2):
        response_format = caller.response_formats[index]
        assert response_format is not None
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True
        assert response_format["json_schema"]["schema"][
            "additionalProperties"
        ] is False
    qwen_schema = caller.response_formats[1]["json_schema"]["schema"]
    assert set(qwen_schema["required"]) == set(PROPOSAL_SEMANTIC_SHAPE)
    assert set(qwen_schema["properties"]) == set(PROPOSAL_SEMANTIC_SHAPE)
    assert "id" not in qwen_schema["properties"]
    assert "proposal_reason" not in qwen_schema["properties"]
    assert caller.chat_template_kwargs == [
        None,
        {"enable_thinking": False},
        {"enable_thinking": False},
        None,
        None,
        None,
        None,
    ]
    assert [item["response_format"] for item in trace["calls"]] == [
        None,
        "json_schema",
        "json_schema",
        None,
        None,
        None,
        None,
    ]


def test_budget_and_semantic_advancement_match_normal_policy() -> None:
    trace, caller = run_fixture()

    assert len(caller.calls) == trace["reasoning_task_count"] == 7
    assert trace["semantic_iteration_count"] == 3
    assert [item["event"] for item in trace["semantic_advancements"]] == [
        "validated_candidate_set",
        "validated_deliberation_resolution",
        "validated_final_plan",
    ]
    assert [item["semantic_iteration"] for item in trace["calls"]] == [
        0, 0, 1, 1, 2, 2, 2,
    ]
    assert [item["reasoning_task"] for item in trace["calls"]] == list(
        range(1, 8)
    )
    assert trace["plan_validation"] == {"valid": True, "issues": []}
    assert trace["final_plan"]["integrity"]["validation"]["status"] == (
        "valid"
    )


def test_missing_disposition_uses_same_director_semantic_completion() -> None:
    incomplete = change_disposition_semantics()
    completed = change_disposition_semantics((1, "accepted"))
    caller = CapturingCaller(
        assessment_outputs=[
            assessment_with_change("Qwen"),
            assessment_semantics("Gemma"),
        ],
        director_outputs=[
            incomplete,
            completed,
            overall_synthesis_semantics(),
            plan_steps_semantics(),
            architecture_assessment_semantics(),
        ],
    )

    trace = run_normal_planning(
        REQUEST,
        model_caller=caller,
        plan_id="plan-completed",
    )

    assert [item["stage"] for item in trace["calls"][4:6]] == [
        "director_change_disposition",
        "director_change_disposition_semantic_completion",
    ]
    assert caller.calls[4][0] == caller.calls[5][0] == (
        NORMAL_PLANNING_CONTEXTS["director_synthesis"]
    )
    assert trace["reasoning_task_count"] == 9
    assert trace["calls"][5]["semantic_iteration"] == 2
    assert trace["conformance_repairs"] == []
    assert len(trace["semantic_completions"]) == 1
    completion = trace["semantic_completions"][0]
    assert completion["producer_context"] == caller.calls[4][0]
    completion_payload = json.loads(caller.calls[5][1][1]["content"])
    assert completion_payload["incomplete_output"] == json.dumps(incomplete)
    assert completion_payload["missing_semantic_decisions"] == completion[
        "missing_semantic_decisions"
    ]
    assert all(
        item["code"] == "missing_semantic_decision"
        for item in completion_payload["missing_semantic_decisions"]
    )
    assert trace["final_plan"]["planning_cycle"]["decisions"][0][
        "accepted_change_refs"
    ] == ["assessment-qwen-of-gemma-change-1"]


def test_malformed_known_intent_uses_same_director_conformance_repair() -> None:
    malformed = (
        '{"dispositions":[{"change_number":1,'
        '"disposition":"accepted"}]'
    )
    repaired = change_disposition_semantics((1, "accepted"))
    caller = CapturingCaller(
        assessment_outputs=[
            assessment_with_change("Qwen"),
            assessment_semantics("Gemma"),
        ],
        director_outputs=[
            malformed,
            repaired,
            overall_synthesis_semantics(),
            plan_steps_semantics(),
            architecture_assessment_semantics(),
        ],
    )

    trace = run_normal_planning(
        REQUEST,
        model_caller=caller,
        plan_id="plan-repaired",
    )

    assert [item["stage"] for item in trace["calls"][4:6]] == [
        "director_change_disposition",
        "director_change_disposition_conformance_repair",
    ]
    assert caller.calls[4][0] == caller.calls[5][0] == (
        NORMAL_PLANNING_CONTEXTS["director_synthesis"]
    )
    assert trace["reasoning_task_count"] == 9
    assert trace["calls"][5]["semantic_iteration"] == 2
    assert trace["semantic_completions"] == []
    assert len(trace["conformance_repairs"]) == 1
    repair = trace["conformance_repairs"][0]
    repair_payload = json.loads(caller.calls[5][1][1]["content"])
    assert repair_payload["invalid_output"] == malformed
    assert repair_payload["validation_issues"] == repair[
        "validation_issues"
    ]
    assert {item["code"] for item in repair_payload["validation_issues"]} == {
        "invalid_shape"
    }
    assert trace["final_plan"]["integrity"]["validation"]["status"] == (
        "valid"
    )


def test_invalid_second_semantic_completion_stops_honestly() -> None:
    incomplete = change_disposition_semantics()
    caller = CapturingCaller(
        assessment_outputs=[
            assessment_with_change("Qwen"),
            assessment_semantics("Gemma"),
        ],
        director_outputs=[incomplete, incomplete],
    )

    with pytest.raises(
        ValueError,
        match="remains incomplete after one semantic completion",
    ):
        run_normal_planning(
            REQUEST,
            model_caller=caller,
            plan_id="plan-incomplete",
        )

    assert len(caller.calls) == 6
    assert caller.calls[4][0] == caller.calls[5][0]


def test_invalid_second_conformance_repair_stops_honestly() -> None:
    malformed = (
        '{"dispositions":[{"change_number":1,'
        '"disposition":"accepted"}]'
    )
    caller = CapturingCaller(
        assessment_outputs=[
            assessment_with_change("Qwen"),
            assessment_semantics("Gemma"),
        ],
        director_outputs=[malformed, malformed],
    )

    with pytest.raises(
        ValueError,
        match="remains invalid after one conformance repair",
    ):
        run_normal_planning(
            REQUEST,
            model_caller=caller,
            plan_id="plan-invalid-repair",
        )

    assert len(caller.calls) == 6
    assert caller.calls[4][0] == caller.calls[5][0]


def test_routing_is_configuration_driven_and_qwen_is_remote() -> None:
    trace, caller = run_fixture()

    assert [context for context, _ in caller.calls] == [
        NORMAL_PLANNING_CONTEXTS["gemma_proposal"],
        NORMAL_PLANNING_CONTEXTS["qwen_proposal"],
        NORMAL_PLANNING_CONTEXTS["qwen_assessment"],
        NORMAL_PLANNING_CONTEXTS["gemma_assessment"],
        NORMAL_PLANNING_CONTEXTS["director_synthesis"],
        NORMAL_PLANNING_CONTEXTS["director_synthesis"],
        NORMAL_PLANNING_CONTEXTS["architecture_assessment"],
    ]
    qwen_calls = [
        item
        for item in trace["calls"]
        if item["logical_context"] == "qwen_worker"
    ]
    assert len(qwen_calls) == 2
    assert all(
        item["endpoint_url"] == QWEN_MODEL.endpoint_url
        for item in qwen_calls
    )
    assert QWEN_MODEL.node == "pc2.gpu0"
    assert QWEN_MODEL.endpoint_url == "http://192.168.50.2:8001/v1"


def routing_steps_semantics(action: str) -> dict[str, object]:
    semantics = plan_steps_semantics()
    semantics["steps"][0]["action"] = action
    semantics["steps"][0]["instructions"] = [
        action,
        "Use static capability metadata only.",
    ]
    semantics["steps"][0]["expected_result"] = (
        "A deterministic, configuration-driven V0 routing strategy."
    )
    return semantics


def test_compliant_plan_passes_semantic_architecture_gate() -> None:
    trace, caller = run_fixture()

    assert trace["architecture_acceptance"] == {
        "compliant": True,
        "assessment_count": 1,
        "violations": [],
    }
    assert trace["architecture_assessments"] == [{
        "id": "plan-test:architecture-assessment-1",
        "iteration": 2,
        "assessor_ref": NORMAL_PLANNING_CONTEXTS[
            "architecture_assessment"
        ],
        "candidate_revision_ref": "plan-test@r1",
        "compliant": True,
        "violations": [],
    }]
    assert trace["semantic_boundary_corrections"] == []
    assert trace["semantic_iteration_count"] == 3
    assessment_payload = json.loads(caller.calls[6][1][1]["content"])
    assert assessment_payload["candidate_plan"] == trace["initial_candidate_plan"]
    assert assessment_payload["frozen_architecture_invariants"] == list(
        FROZEN_ARCHITECTURE_INVARIANTS
    )


def test_architecture_assessment_semantics_require_consistent_judgment() -> None:
    violation = architecture_violation(
        "Director resolves a concrete model.",
        "steps[0].action",
    )

    assert validate_architecture_assessment_semantics(
        architecture_assessment_semantics()
    ) == ()
    assert validate_architecture_assessment_semantics(
        architecture_assessment_semantics(
            compliant=False,
            violations=[violation],
        )
    ) == ()
    contradictory = validate_architecture_assessment_semantics(
        architecture_assessment_semantics(violations=[violation])
    )
    empty_noncompliant = validate_architecture_assessment_semantics(
        architecture_assessment_semantics(compliant=False)
    )
    assert any(issue.code == "invalid_partition" for issue in contradictory)
    assert any(
        issue.code == "missing_semantic_decision"
        for issue in empty_noncompliant
    )


@pytest.mark.parametrize(
    ("bad_action", "finding"),
    [
        (
            "The Director resolves and returns the concrete model ID.",
            "Director directly resolves a concrete model ID.",
        ),
        (
            "Create an intelligent Router manager to choose the worker.",
            "A third intelligent Router authority is introduced.",
        ),
        (
            "If local selection fails, silently escalate to a fallback model.",
            "Fallback is implicit and unconstrained by local configuration.",
        ),
    ],
)
def test_architecture_violations_trigger_scoped_director_correction(
    bad_action: str,
    finding: str,
) -> None:
    violation = architecture_violation(finding, "steps[0].action")
    compliant_steps = routing_steps_semantics(
        "Task Executive mechanically resolves the concrete model from explicit "
        "configuration and static capability requirements selected by the "
        "Director."
    )
    caller = CapturingCaller(director_outputs=[
        overall_synthesis_semantics(),
        routing_steps_semantics(bad_action),
        architecture_assessment_semantics(
            compliant=False,
            violations=[violation],
        ),
        boundary_correction_semantics(steps=compliant_steps),
        architecture_assessment_semantics(),
    ])

    trace = run_normal_planning(
        REQUEST,
        model_caller=caller,
        plan_id="plan-boundary-corrected",
    )

    assert bad_action in json.dumps(trace["initial_candidate_plan"])
    assert bad_action not in json.dumps(trace["final_plan"])
    assert trace["architecture_assessments"][0]["violations"] == [violation]
    assert trace["architecture_assessments"][1]["compliant"] is True
    assert len(trace["semantic_boundary_corrections"]) == 1
    correction = trace["semantic_boundary_corrections"][0]
    assert correction["producer_context"] == NORMAL_PLANNING_CONTEXTS[
        "director_synthesis"
    ]
    assert correction["violations"] == [violation]
    assert correction["corrected_semantics"]["plan_steps"] == compliant_steps
    correction_payload = json.loads(caller.calls[7][1][1]["content"])
    assert correction_payload["exact_architecture_violations"] == [violation]
    assert correction_payload["candidate_plan"] == trace["initial_candidate_plan"]
    assert trace["reasoning_task_count"] == 9
    assert [item["reasoning_task"] for item in trace["calls"][6:]] == [
        7, 8, 9,
    ]
    assert [item["semantic_iteration"] for item in trace["calls"][6:]] == [
        2, 2, 2,
    ]
    assert trace["semantic_iteration_count"] == 3
    assert [item["attempt"] for item in trace["structural_certifications"]] == [
        1, 2,
    ]


def test_deterministic_task_executive_configuration_routing_language_passes() -> None:
    compliant_action = (
        "Task Executive mechanically resolves a concrete local model from "
        "explicit configuration using the Director's static capability "
        "requirements; configured fallback is deterministic and local."
    )
    caller = CapturingCaller(director_outputs=[
        overall_synthesis_semantics(),
        routing_steps_semantics(compliant_action),
        architecture_assessment_semantics(),
    ])

    trace = run_normal_planning(
        REQUEST,
        model_caller=caller,
        plan_id="plan-config-routing",
    )

    assert compliant_action in json.dumps(trace["final_plan"])
    assert trace["architecture_acceptance"]["compliant"] is True
    assert trace["semantic_boundary_corrections"] == []


def test_architecture_assessment_routing_is_configuration_driven(
    monkeypatch,
) -> None:
    from structures import LogicalContextStruct

    alternate = LogicalContextStruct(
        name="alternate_architecture_assessor",
        participant_role="primary_worker",
        worker_kind="model",
        worker_ref="qwen",
    )
    monkeypatch.setitem(LOGICAL_CONTEXTS, alternate.name, alternate)
    monkeypatch.setitem(
        NORMAL_PLANNING_CONTEXTS,
        "architecture_assessment",
        alternate.name,
    )
    caller = CapturingCaller()

    trace = run_normal_planning(
        REQUEST,
        model_caller=caller,
        plan_id="plan-rerouted-assessment",
    )

    assert caller.calls[6][0] == alternate.name
    assert trace["calls"][6]["logical_context"] == alternate.name
    assert trace["calls"][6]["model_name"] == QWEN_MODEL.model_name
    assert trace["architecture_assessments"][0]["assessor_ref"] == (
        alternate.name
    )


def test_structural_certification_precedes_each_architecture_assessment(
    monkeypatch,
) -> None:
    import planning

    bad_action = "The Director returns the selected concrete model."
    violation = architecture_violation(
        "Director directly resolves a concrete model.",
        "steps[0].action",
    )
    caller = CapturingCaller(director_outputs=[
        overall_synthesis_semantics(),
        routing_steps_semantics(bad_action),
        architecture_assessment_semantics(
            compliant=False,
            violations=[violation],
        ),
        boundary_correction_semantics(),
        architecture_assessment_semantics(),
    ])
    original_validate = planning.validate_final_plan
    call_counts_at_structural_validation: list[int] = []

    def record_validation(*args, **kwargs):
        call_counts_at_structural_validation.append(len(caller.calls))
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(planning, "validate_final_plan", record_validation)

    trace = run_normal_planning(
        REQUEST,
        model_caller=caller,
        plan_id="plan-validation-order",
    )

    assert call_counts_at_structural_validation == [6, 8]
    assert [item["stage"] for item in trace["calls"][6:]] == [
        "architecture_assessment",
        "director_semantic_boundary_correction",
        "architecture_reassessment",
    ]


def test_second_semantic_boundary_failure_stops_after_one_correction() -> None:
    violation = architecture_violation(
        "Director directly resolves a concrete model.",
        "steps[0].action",
    )
    noncompliant = architecture_assessment_semantics(
        compliant=False,
        violations=[violation],
    )
    caller = CapturingCaller(director_outputs=[
        overall_synthesis_semantics(),
        routing_steps_semantics(
            "The Director returns the selected concrete model."
        ),
        noncompliant,
        boundary_correction_semantics(),
        noncompliant,
    ])

    with pytest.raises(
        ValueError,
        match=(
            "remains semantically noncompliant after one boundary correction"
        ),
    ):
        run_normal_planning(
            REQUEST,
            model_caller=caller,
            plan_id="plan-boundary-failure",
        )

    assert len(caller.calls) == 9
    systems = [messages[0]["content"] for _, messages in caller.calls]
    assert sum("advisory assessor only" in item for item in systems) == 2
    assert sum(
        "Correct the candidate Plan's meaning" in item
        for item in systems
    ) == 1
    assert caller.calls[6][0] == caller.calls[8][0] == (
        NORMAL_PLANNING_CONTEXTS["architecture_assessment"]
    )
    assert caller.calls[7][0] == NORMAL_PLANNING_CONTEXTS[
        "director_synthesis"
    ]


@pytest.mark.parametrize("diagnostic", [False, True])
def test_mandate_policy_reaches_all_planning_calls(diagnostic: bool) -> None:
    request = (
        "Determine whether the execution-time constraints are feasible."
        if diagnostic else
        "Produce a feasible configuration. Report impossibility truthfully, "
        "but an impossibility report is not alternative fulfillment. "
        "Detailed authoritative constraints are deferred until execution."
    )
    steps = plan_steps_semantics()
    steps["steps"][0]["instructions"] = ["Read the execution-time evidence."]
    steps["steps"][0]["expected_result"] = (
        "A sound feasibility finding, including a proof of impossibility."
        if diagnostic else "A feasible configuration with validation."
    )
    steps["steps"][0]["validation"] = ["Meet the original request."]
    overall = overall_synthesis_semantics()
    overall["unresolved_risks"] = ["Constraints are supplied at execution."]
    caller = CapturingCaller(
        assessment_outputs=[assessment_with_change("Qwen"), assessment_semantics("Gemma")],
        director_outputs=[
            change_disposition_semantics((1, "accepted")), overall, steps,
            architecture_assessment_semantics(),
        ],
    )
    trace = run_normal_planning(request, model_caller=caller)
    for _, messages in caller.calls:
        payload = json.loads(messages[1]["content"])
        assert payload["frozen_request"] == request
        policy = payload.get("semantic_plan_fidelity")
        if policy is None:
            policy = payload["normal_policy"]["semantic_plan_fidelity"]
        assert policy == semantic_plan_fidelity_policy()
    assert trace["final_plan"]["steps"][0]["expected_result"] == steps["steps"][0]["expected_result"]
    assert trace["final_plan"]["final"]["unresolved_risks"] == overall["unresolved_risks"]


@pytest.mark.parametrize("corrected", [True, False])
def test_request_fidelity_uses_bounded_semantic_correction(corrected: bool) -> None:
    request = (
        "Produce a feasible configuration and validation. An incompatibility "
        "report is useful evidence, not alternative fulfillment."
    )
    bad = plan_steps_semantics()
    bad["steps"][0].update(
        instructions=["Report incompatibility truthfully; never fabricate a solution."],
        expected_result="A configuration OR an incompatibility report.",
        validation=["Either output is success."],
    )
    good = deepcopy(bad)
    good["steps"][0].update(
        expected_result="A feasible configuration plus a validation record.",
        validation=["Configuration satisfies every requirement."],
    )
    violation = architecture_violation(
        "The request excludes an incompatibility report as fulfillment; "
        "steps[0].expected_result and validation allow that alternative.",
        "steps[0].expected_result",
    )
    negative = architecture_assessment_semantics(compliant=False, violations=[violation])
    caller = CapturingCaller(director_outputs=[
        overall_synthesis_semantics(), bad, negative,
        boundary_correction_semantics(steps=good),
        architecture_assessment_semantics() if corrected else negative,
    ])
    if corrected:
        trace = run_normal_planning(request, model_caller=caller)
        assert trace["final_plan"]["steps"][0]["expected_result"] == good["steps"][0]["expected_result"]
        assert trace["final_plan"]["steps"][0]["instructions"] == bad["steps"][0]["instructions"]
        assert trace["initial_candidate_plan"]["steps"][0]["expected_result"] == bad["steps"][0]["expected_result"]
        assert len(trace["semantic_boundary_corrections"]) == 1
        assert trace["conformance_repairs"] == []
        assert trace["semantic_iteration_count"] == 3
    else:
        with pytest.raises(ValueError, match="request excludes an incompatibility"):
            run_normal_planning(request, model_caller=caller)
    for index in (6, 7, 8):
        payload = json.loads(caller.calls[index][1][1]["content"])
        assert payload["frozen_request"] == request
        assert payload["semantic_plan_fidelity"] == semantic_plan_fidelity_policy()
    assert len(caller.calls) == 9


def test_final_plan_rejects_invalid_dependency() -> None:
    trace, _ = run_fixture()
    plan = deepcopy(trace["final_plan"])
    plan["integrity"]["validation"] = {
        "status": "pending",
        "validated_by_ref": None,
        "validated_at": None,
        "errors": [],
    }
    plan["steps"][0]["depends_on"] = ["missing-step"]
    issues = validate_final_plan(
        plan,
        plan_id="plan-test",
        current_work_ref=plan["current_work_ref"],
        director_ref=NORMAL_PLANNING_CONTEXTS["director_synthesis"],
        proposals=plan["planning_cycle"]["proposals"],
        assessments=(trace["qwen_assessment"], trace["gemma_assessment"]),
    )
    assert any(issue.field.endswith("depends_on") for issue in issues)


def test_planning_adds_no_execution_router_or_third_manager() -> None:
    trace, _ = run_fixture()
    director_source = Path("src/director.py").read_text(encoding="utf-8")
    planning_source = Path("src/planning.py").read_text(encoding="utf-8")

    assert "task_execution" not in trace
    assert "director_task" not in trace
    assert "JobContext" not in director_source
    assert "JobContext" not in planning_source
    assert "class Plan" not in planning_source
    assert "class Router" not in director_source
    assert "class Router" not in planning_source
    assert "RepairManager" not in director_source
    assert "CompletionManager" not in director_source
    assert "qwen" not in inspect.getsource(ModelClient).lower()
    assert "gemma" not in inspect.getsource(ModelClient).lower()


def test_insufficient_budget_prevents_any_call() -> None:
    caller = CapturingCaller()
    with pytest.raises(ValueError, match="at least seven calls"):
        run_normal_planning(
            REQUEST,
            model_caller=caller,
            budget={"reasoning_tasks": 5, "semantic_iterations": 3},
        )
    assert caller.calls == []


def test_stage_routing_changes_through_configuration(monkeypatch) -> None:
    from structures import LogicalContextStruct

    alternate = LogicalContextStruct(
        name="alternate_planner",
        participant_role="primary_worker",
        worker_kind="model",
        worker_ref="qwen",
    )
    monkeypatch.setitem(LOGICAL_CONTEXTS, alternate.name, alternate)
    monkeypatch.setitem(
        NORMAL_PLANNING_CONTEXTS,
        "gemma_proposal",
        alternate.name,
    )
    caller = CapturingCaller()

    trace = run_normal_planning(
        REQUEST,
        model_caller=caller,
        plan_id="plan-rerouted",
    )

    assert caller.calls[0][0] == "alternate_planner"
    assert trace["calls"][0]["model_name"] == QWEN_MODEL.model_name
    assert trace["calls"][0]["endpoint_url"] == QWEN_MODEL.endpoint_url


@pytest.mark.parametrize(
    "text",
    [
        '{"value": 1}',
        '  {"value": 1}\n',
        '```json\n{"value": 1}\n```',
        ' \n```json\n{"value": 1}\n```\n ',
        '<think>internal reasoning</think>\n{"value": 1}',
        ' \n<think>\ninternal reasoning\n</think>\n {"value": 1}\n',
    ],
)
def test_json_output_envelopes_accept_only_the_three_supported_forms(
    text: str,
) -> None:
    assert parse_json_object(text, stage="test") == {"value": 1}


@pytest.mark.parametrize(
    "text",
    [
        'Result: {"value": 1}',
        '{"value": 1} done',
        '```\n{"value": 1}\n```',
        '```JSON\n{"value": 1}\n```',
        '```json\n{"value": 1}\n``` trailing',
        '```json\n{"value": 1}\n```\n```json\n{"value": 2}\n```',
        '<think>one</think><think>two</think>{"value": 1}',
        '<think>reason</think> prose {"value": 1}',
        '<think>reason</think>\n```json\n{"value": 1}\n```',
        '<think>unterminated\n{"value": 1}',
        '{"value": }',
        '{"value": 1}{"value": 2}',
    ],
)
def test_json_output_envelopes_reject_other_wrapping_and_malformed_json(
    text: str,
) -> None:
    with pytest.raises(ValueError, match="did not return valid JSON"):
        parse_json_object(text, stage="test")


def test_json_output_envelope_still_requires_an_object() -> None:
    with pytest.raises(ValueError, match="must return one JSON object"):
        parse_json_object("```json\n[]\n```", stage="test")


@pytest.mark.parametrize(
    "envelope",
    [
        "```json\n{}\n```",
        "<think>internal reasoning</think>\n{}",
    ],
)
def test_supported_envelopes_preserve_a_valid_proposal(
    envelope: str,
) -> None:
    raw = proposal(
        {
            "id": "proposal-gemma",
            "iteration": 1,
            "author_ref": "gemma_worker",
            "proposal_state": "candidate",
        },
        "Gemma",
    )
    parsed = parse_json_object(
        envelope.format(json.dumps(raw)),
        stage="Gemma proposal",
    )

    assert validate_proposal(
        parsed,
        expected_author="gemma_worker",
        expected_id="proposal-gemma",
    ) == ()


def test_normalization_preserves_unknown_semantic_fields_for_validation() -> None:
    raw = proposal(
        {
            "id": "proposal-qwen",
            "iteration": 1,
            "author_ref": "qwen_worker",
            "proposal_state": "candidate",
        },
        "Qwen",
    )
    raw.update({"ordered": ["apple", "banana", "pear"], "count": 3})
    parsed = parse_json_object(
        "<think>planning</think>\n" + json.dumps(raw),
        stage="Qwen proposal",
    )

    assert parsed["ordered"] == ["apple", "banana", "pear"]
    assert parsed["count"] == 3
    issues = validate_proposal(
        parsed,
        expected_author="qwen_worker",
        expected_id="proposal-qwen",
    )
    unknown_fields = {
        issue.field
        for issue in issues
        if issue.code == "unknown_field"
    }
    assert unknown_fields == {
        "proposal.count",
        "proposal.ordered",
    }


def test_proposal_prompt_requests_only_semantic_content() -> None:
    messages = render_proposal_messages(REQUEST)
    system_prompt = messages[0]["content"]
    payload = json.loads(messages[1]["content"])

    assert "semantic contribution" in system_prompt
    assert "four requested semantic fields" in system_prompt
    assert "Python will construct the canonical proposal" in system_prompt
    assert set(payload["required_semantic_output"]) == {
        "summary", "main_points", "assumptions", "reason",
    }
    assert any(
        "not the requested final result" in rule
        for rule in payload["rules"]
    )
    assert any(
        "Do not return IDs" in rule
        for rule in payload["rules"]
    )


def test_both_models_assemble_to_the_same_canonical_proposal_shape() -> None:
    gemma = assemble_proposal(
        proposal_semantics("Gemma"),
        proposal_id="proposal-gemma",
        author_ref="gemma_worker",
    )
    qwen = assemble_proposal(
        proposal_semantics("Qwen"),
        proposal_id="proposal-qwen",
        author_ref="qwen_worker",
    )
    protocol_fields = set(
        json.loads(PLAN_PROTOCOL_PATH.read_text())
        ["planning_cycle"]["proposals"][0]
    )

    assert set(gemma) == set(qwen) == protocol_fields
    assert gemma["id"] == "proposal-gemma"
    assert gemma["author_ref"] == "gemma_worker"
    assert qwen["id"] == "proposal-qwen"
    assert qwen["author_ref"] == "qwen_worker"
    for item in (gemma, qwen):
        assert item["iteration"] == 1
        assert item["message_refs"] == []
        assert item["artifact_refs"] == []
        assert item["proposal_state"] == "candidate"
        assert item["proposal_reason"] is None
        assert item["decided_by_ref"] is None
        assert item["decided_in_revision_ref"] is None


def test_missing_proposal_semantics_fail_before_assembly() -> None:
    semantics = proposal_semantics("Gemma")
    del semantics["reason"]
    issues = validate_proposal_semantics(semantics)

    assert any(
        issue.field == "proposal_semantics.reason"
        and issue.code == "required"
        for issue in issues
    )


def test_unknown_proposal_semantics_remain_invalid() -> None:
    semantics = proposal_semantics("Qwen")
    semantics["ordered"] = ["apple", "banana", "pear"]
    issues = validate_proposal_semantics(semantics)

    assert any(
        issue.field == "proposal_semantics.ordered"
        and issue.code == "unknown_field"
        for issue in issues
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "weaknesses",
        "useful_questions",
        "genuine_contradictions_or_tradeoffs",
        "missing_information",
    ],
)
def test_assessment_category_may_have_no_findings(field_name: str) -> None:
    semantics = assessment_semantics("Qwen")
    semantics[field_name] = []

    assert validate_assessment_semantics(semantics) == ()


def test_assessment_cannot_be_entirely_semantically_empty() -> None:
    semantics = assessment_semantics("Gemma")
    for field_name in set(ASSESSMENT_SEMANTIC_SHAPE) - {
        "severity", "suggested_changes",
    }:
        semantics[field_name] = []
    semantics["suggested_changes"] = []

    issues = validate_assessment_semantics(semantics)

    assert any(
        issue.field == "assessment_semantics"
        and issue.code == "insufficient_content"
        for issue in issues
    )


@pytest.mark.parametrize(
    ("field_name", "malformed"),
    [
        ("weaknesses", "none identified"),
        ("useful_questions", [1]),
        ("missing_information", None),
    ],
)
def test_assessment_finding_types_remain_strict(
    field_name: str,
    malformed: object,
) -> None:
    semantics = assessment_semantics("Qwen")
    semantics[field_name] = malformed

    issues = validate_assessment_semantics(semantics)

    assert any(
        issue.field == f"assessment_semantics.{field_name}"
        and issue.code == "invalid_shape"
        for issue in issues
    )


def test_unknown_assessment_semantics_remain_invalid() -> None:
    semantics = assessment_semantics("Gemma")
    semantics["manufactured_disagreement"] = []

    issues = validate_assessment_semantics(semantics)

    assert any(
        issue.field == "assessment_semantics.manufactured_disagreement"
        and issue.code == "unknown_field"
        for issue in issues
    )


def test_full_proposal_protocol_validation_runs_after_assembly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import planning

    original = planning.assemble_proposal

    def assemble_with_protocol_drift(*args, **kwargs):
        assembled = original(*args, **kwargs)
        assembled["unexpected_runtime_field"] = True
        return assembled

    monkeypatch.setattr(planning, "assemble_proposal", assemble_with_protocol_drift)
    caller = CapturingCaller()

    with pytest.raises(ValueError, match="Invalid canonical proposals"):
        run_normal_planning(
            REQUEST,
            model_caller=caller,
            plan_id="plan-invalid-assembly",
        )
    assert len(caller.calls) == 2
