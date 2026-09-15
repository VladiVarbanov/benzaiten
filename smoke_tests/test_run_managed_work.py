from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import director
from run_managed_work import (
    _proof_projection,
    load_available_resources,
    load_certified_plan,
    load_resolved_inputs,
    run_managed_work,
)
from test_managed_work_iteration3 import certified_plan


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_loaders_require_certified_root_and_expected_json_shapes(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "plan.json"
    inputs_path = tmp_path / "inputs.json"
    resources_path = tmp_path / "resources.json"
    write_json(plan_path, certified_plan())
    write_json(inputs_path, {"request:abc123": "sort these values"})
    write_json(resources_path, [{
        "ref": "source:brief.txt",
        "kind": "source",
        "name": "Brief",
        "description": "A supplied local brief.",
    }])

    assert load_certified_plan(plan_path)["revision_ref"].endswith("@r1")
    assert load_resolved_inputs(inputs_path) == {
        "request:abc123": "sort these values"
    }
    assert load_available_resources(resources_path)[0]["kind"] == "source"

    invalid = certified_plan()
    invalid["integrity"]["validation"]["status"] = "pending"
    write_json(plan_path, invalid)
    with pytest.raises(ValueError, match="certified @r1"):
        load_certified_plan(plan_path)

    write_json(inputs_path, [])
    with pytest.raises(ValueError, match="JSON object"):
        load_resolved_inputs(inputs_path)


def test_launcher_loads_plan_and_delegates_without_semantic_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = tmp_path / "plan.json"
    write_json(plan_path, certified_plan())
    captured: dict[str, object] = {}

    def fake_run(plan: object, **kwargs: object) -> dict[str, object]:
        captured["plan"] = deepcopy(plan)
        captured.update(kwargs)
        return {
            "status": "accepted",
            "plan_history": [deepcopy(plan)],
            "director_selections": [],
            "director_tasks": [],
            "calls": [],
            "task_executions": [],
            "evaluations": [],
            "conformance_repairs": [],
            "accepted_checkpoints": [],
            "execution_transition_state": {},
            "resume_state": {},
            "artifact_root": str(tmp_path / "artifacts" / "job-proof"),
        }

    monkeypatch.setattr(director, "run_iteration_3", fake_run)
    result = run_managed_work(
        plan_path,
        job_ref="job-proof",
        resolved_inputs={"request:abc123": "sort these values"},
        artifact_root=tmp_path / "artifacts",
        reasoning_task_count=10,
    )

    assert captured["plan"]["revision_ref"] == "plan-iteration-3@r1"
    assert captured["job_ref"] == "job-proof"
    assert captured["resolved_inputs"] == {
        "request:abc123": "sort these values"
    }
    assert captured["artifact_root"] == tmp_path / "artifacts"
    assert captured["guidance_policy"] == "USER_ONLY"
    assert captured["frontier_authorized"] is False
    assert captured["reasoning_task_count"] == 10
    assert result["status"] == "accepted"


def test_launcher_refuses_implicit_replay_of_valid_persisted_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = tmp_path / "plan.json"
    write_json(plan_path, certified_plan())
    resume_path = tmp_path / "artifacts" / "job-proof" / "resume.json"
    resume_path.parent.mkdir(parents=True)
    write_json(resume_path, {})
    loaded = {
        "resume_state": {
            "status": "completed",
            "current_plan_ref": "plan-iteration-3@r1",
        }
    }
    monkeypatch.setattr(
        "orchestrator.load_managed_work_state",
        lambda *args, **kwargs: loaded,
    )

    with pytest.raises(RuntimeError, match="implicit replay is forbidden"):
        run_managed_work(
            plan_path,
            job_ref="job-proof",
            resolved_inputs={"request:abc123": "sort these values"},
            artifact_root=tmp_path / "artifacts",
        )


def test_proof_projection_exposes_existing_boundary_evidence() -> None:
    result = {
        "status": "accepted",
        "plan_history": [{"revision_ref": "plan-live@r1"}],
        "director_selections": [{"semantics": {"decision": "work"}}],
        "director_tasks": [{"task_id": "task-live"}],
        "calls": [{"stage": "director_task_selection"}],
        "task_executions": [{"execution_id": "execution-live"}],
        "evaluations": [{"semantics": {"decision": "ACCEPT"}}],
        "conformance_repairs": [],
        "accepted_checkpoints": [{"kind": "execution"}],
        "execution_transition_state": {"consumed": 0},
        "resume_state": {"status": "completed"},
        "artifact_root": "/tmp/live",
    }

    proof = _proof_projection(result)

    assert proof["selected_certified_plan_ref"] == "plan-live@r1"
    assert proof["director_selections"] == result["director_selections"]
    assert proof["task_executions"] == result["task_executions"]
    assert proof["resume_state"] == {"status": "completed"}

    result.update(
        status="semantic_plan_unresolved",
        semantic_plan_error="Corrected Plan still weakens the original success criterion.",
        semantic_plan_assessments=[{"compliant": False}],
        semantic_boundary_corrections=[{"attempt": 1}],
    )
    unresolved = _proof_projection(result)
    for key in ("semantic_plan_error", "semantic_plan_assessments", "semantic_boundary_corrections"):
        assert unresolved[key] == result[key]
