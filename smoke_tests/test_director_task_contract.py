from __future__ import annotations

import inspect
import json
from dataclasses import fields

import pytest

from config import DIRECTOR_TASK_PROTOCOL_PATH
from director import DirectorTask, parse_director_task
from orchestrator import prepare_managed_director_task


def fully_populated_task_mapping() -> dict[str, object]:
    return {
        "task_id": "task-1",
        "job_ref": "job-1",
        "capability": "knowledge_synthesis",
        "participant_role": "reviewer",
        "objective": "Assess the selected plan step",
        "input_refs": ["artifact:proposal-1"],
        "instruction": "Identify material defects only.",
        "work_kind": "execution",
        "plan_ref": "plan-1/rev-1",
        "action": "critique",
        "target": {"kind": "step", "locator": "plan-1/rev-1/step-1"},
        "anchors": [{"kind": "artifact", "value": "proposal-1"}],
        "entities": [{"kind": "concept", "name": "semantic authority"}],
        "focus": {
            "questions": ["Does the step preserve the control seam?"],
            "angles": ["authority"],
            "granularity": "fine",
        },
        "reason": "Independent assessment is required.",
        "requirements": ["Use only referenced evidence."],
        "acceptance": "All material issues are explicitly identified.",
        "output_contract_ref": "contract:critique-v0",
        "external_authority_ref": "authority:future-review-board",
    }


def test_python_fields_match_authoritative_protocol() -> None:
    protocol = json.loads(DIRECTOR_TASK_PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert {field.name for field in fields(DirectorTask)} == set(protocol["task"])


def test_all_protocol_fields_round_trip_through_semantic_payload() -> None:
    source = fully_populated_task_mapping()
    task = parse_director_task(source)

    assert task.semantic_payload() == source
    assert task.work_kind == "execution"
    assert task.plan_ref == "plan-1/rev-1"
    assert task.action == "critique"
    assert task.target == source["target"]
    assert [dict(item) for item in task.anchors] == source["anchors"]
    assert [dict(item) for item in task.entities] == source["entities"]
    assert task.reason == source["reason"]
    assert task.external_authority_ref == "authority:future-review-board"


def test_unknown_semantic_field_is_rejected() -> None:
    mapping = fully_populated_task_mapping()
    mapping["semantic_guess"] = "must-not-disappear"

    with pytest.raises(ValueError, match="Unknown DirectorTask field"):
        parse_director_task(mapping)


@pytest.mark.parametrize(
    ("field", "malformed"),
    [
        ("target", {"kind": "step"}),
        ("anchors", [{"kind": "artifact", "unexpected": "x"}]),
        ("entities", [{"kind": "concept", "name": 42}]),
        ("focus", {"questions": "not-an-array", "angles": []}),
    ],
)
def test_malformed_nested_structures_are_rejected(
    field: str,
    malformed: object,
) -> None:
    mapping = fully_populated_task_mapping()
    mapping[field] = malformed

    with pytest.raises(ValueError):
        parse_director_task(mapping)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("capability", "general_intelligence"),
        ("participant_role", "qwen"),
        ("work_kind", "coordination"),
        ("action", "invent_operation"),
        ("focus", {"questions": [], "angles": [], "granularity": "atomic"}),
    ],
)
def test_invalid_vocabulary_values_are_rejected(
    field: str,
    value: object,
) -> None:
    mapping = fully_populated_task_mapping()
    mapping[field] = value

    with pytest.raises(ValueError, match="must be one of"):
        parse_director_task(mapping)


def test_executable_managed_work_requires_plan_ref() -> None:
    mapping = fully_populated_task_mapping()
    mapping["plan_ref"] = None

    with pytest.raises(ValueError, match="plan_ref is required"):
        parse_director_task(mapping)


def test_managed_preparation_uses_director_task_action_only() -> None:
    task = parse_director_task(fully_populated_task_mapping())

    prepared = prepare_managed_director_task(task)

    assert prepared["action"] == task.action == "critique"
    assert "action" not in inspect.signature(prepare_managed_director_task).parameters
    with pytest.raises(TypeError):
        prepare_managed_director_task(task, action="revise")
