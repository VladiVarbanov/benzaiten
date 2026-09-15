from __future__ import annotations

from copy import deepcopy
import json

import pytest

from director import evaluate_task_execution, run_iteration_3, run_normal_planning
from test_managed_work_iteration3 import (
    FakeCaller, accept_evaluation, certified_plan, exact_worker_result,
    executed_task, revise_evaluation, successor_plan_semantics, valid_selection,
)
from test_normal_planning import (
    REQUEST, CapturingCaller, architecture_assessment_semantics,
    assessment_semantics, assessment_with_change, change_disposition_semantics,
    overall_synthesis_semantics, plan_steps_semantics,
)


@pytest.mark.parametrize("field", ["continue_work", "decision", "reason", "evidence_numbers"])
@pytest.mark.parametrize("empty", [False, True])
def test_f1_missing_evaluation_uses_grounded_completion(field, empty):
    plan, handoff, executed = executed_task()
    complete = accept_evaluation(continue_work=True)
    incomplete = deepcopy(complete)
    if empty:
        incomplete[field] = None
    else:
        del incomplete[field]
    caller = FakeCaller([incomplete, complete])
    result = evaluate_task_execution(
        executed["task_execution"], frozen_request="ORIGINAL_DELIVERABLE_MANDATE",
        certified_plan=plan, selected_step=handoff["selected_step"],
        director_task=handoff["director_task"], model_caller=caller,
        reasoning_task_count=8,
    )
    assert result["disposition"] == "accepted_continue"
    assert result["reasoning_task_count"] == 10
    assert result["conformance_repairs"] == []
    assert len(result["semantic_completions"]) == 1
    assert caller.calls[0][0] == caller.calls[1][0]
    payload = json.loads(caller.calls[1][1][1]["content"])
    assert payload["frozen_request"] == "ORIGINAL_DELIVERABLE_MANDATE"
    context = payload["semantic_context"]
    assert context["task_execution"]["result"] == executed["task_execution"]["result"]
    assert context["selected_step"]["id"] == handoff["selected_step"]["id"]
    assert context["director_task"]["task_id"] == handoff["director_task"]["task_id"]
    assert context["numbered_evidence"]
    assert context["certified_plan"]["steps"] == plan["steps"]
    assert result["task_execution"]["plan_execution"]["outcomes"][0]["resulting_plan_ref"] is None


def test_f1_completion_cannot_change_supplied_judgment():
    plan, handoff, executed = executed_task()
    incomplete = accept_evaluation(continue_work=True)
    del incomplete["reason"]
    changed = accept_evaluation(continue_work=False)
    with pytest.raises(ValueError, match="changed an already-supplied judgment"):
        evaluate_task_execution(
            executed["task_execution"], frozen_request=REQUEST,
            certified_plan=plan, selected_step=handoff["selected_step"],
            director_task=handoff["director_task"],
            model_caller=FakeCaller([incomplete, changed]),
        )


def test_f7_conditional_nullability_is_representation_repair():
    plan, handoff, executed = executed_task()
    invalid = accept_evaluation()
    invalid["backtrack_checkpoint_number"] = 1
    result = evaluate_task_execution(
        executed["task_execution"], frozen_request=REQUEST,
        certified_plan=plan, selected_step=handoff["selected_step"],
        director_task=handoff["director_task"],
        model_caller=FakeCaller([invalid, accept_evaluation()]),
    )
    assert len(result["conformance_repairs"]) == 1
    assert result["semantic_completions"] == []
    assert result["reasoning_task_count"] == 2


@pytest.mark.parametrize("recovered", [True, False])
def test_f7_successor_missing_goal_uses_bounded_grounded_completion(recovered):
    good = successor_plan_semantics()
    missing = deepcopy(good)
    del missing["overall_synthesis"]["goal"]
    outputs = [
        valid_selection(), exact_worker_result(), revise_evaluation(),
        missing, good if recovered else missing,
    ]
    if recovered:
        outputs.extend([
            architecture_assessment_semantics(), valid_selection(),
            exact_worker_result(), accept_evaluation(),
        ])
    caller = FakeCaller(outputs)
    kwargs = dict(
        reasoning_task_count=0,
        job_ref="successor-completion", resolved_inputs={"request:abc123": REQUEST},
        model_caller=caller,
    )
    if recovered:
        result = run_iteration_3(certified_plan(), **kwargs)
        assert result["execution_transition_state"]["consumed"] == 1
        assert result["reasoning_task_count"] == 9
        assert len(result["semantic_completions"]) == 1
        assert result["conformance_repairs"] == []
    else:
        with pytest.raises(ValueError, match="after one semantic completion"):
            run_iteration_3(certified_plan(), **kwargs)
        assert len(caller.calls) == 5
    payload = json.loads(caller.calls[4][1][1]["content"])
    assert payload["frozen_request"] == REQUEST
    assert payload["semantic_context"]["triggering_execution"]["result"]["content"] == exact_worker_result()
    assert payload["semantic_context"]["selected_checkpoint"]["revision_ref"].endswith("@r1")


@pytest.mark.parametrize("stage", ["disposition", "overall", "steps"])
def test_root_completion_retains_its_full_synthesis_context(stage):
    overall = overall_synthesis_semantics()
    steps = plan_steps_semantics()
    if stage == "disposition":
        outputs = [
            change_disposition_semantics(), change_disposition_semantics((1, "accepted")),
            overall, steps, architecture_assessment_semantics(),
        ]
        assessments = [assessment_with_change("Qwen"), assessment_semantics("Gemma")]
        recovery_index = 5
    elif stage == "overall":
        incomplete = deepcopy(overall)
        del incomplete["decision_rationale"]
        outputs = [incomplete, overall, steps, architecture_assessment_semantics()]
        assessments = None
        recovery_index = 5
    else:
        incomplete = deepcopy(steps)
        del incomplete["steps"][0]["expected_result"]
        outputs = [overall, incomplete, steps, architecture_assessment_semantics()]
        assessments = None
        recovery_index = 6
    caller = CapturingCaller(director_outputs=outputs, assessment_outputs=assessments)
    result = run_normal_planning(REQUEST, model_caller=caller)
    assert len(result["semantic_completions"]) == 1
    payload = json.loads(caller.calls[recovery_index][1][1]["content"])
    assert payload["frozen_request"] == REQUEST
    context = payload["semantic_context"]
    assert context["gemma_proposal"]["main_points"]
    assert context["qwen_proposal"]["main_points"]
    assert context["qwen_assessment_of_gemma"]["critique"]
    assert context["gemma_assessment_of_qwen"]["critique"]
    if stage == "steps":
        assert context["validated_overall_synthesis"] == overall


@pytest.mark.parametrize("select_history", [False, True])
def test_f2_continuation_exposes_history_but_worker_receives_only_selected_inputs(select_history):
    first_result = {"value": "DISTINCTIVE_ACCEPTED_RESULT_71294"}
    second_selection = valid_selection()
    if select_history:
        second_selection["selected_input_numbers"] = [1, 2]
    caller = FakeCaller([
        valid_selection(), first_result, accept_evaluation(continue_work=True),
        successor_plan_semantics(), architecture_assessment_semantics(),
        second_selection, exact_worker_result(), accept_evaluation(),
    ])
    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0, job_ref="history-input", resolved_inputs={"request:abc123": REQUEST},
        model_caller=caller,
    )
    selection_payload = json.loads(caller.calls[5][1][1]["content"])
    history = selection_payload["available_inputs"][1]
    assert history["kind"] == "execution"
    assert history["content"]["result"]["content"] == first_result
    worker_payload = json.loads(caller.calls[6][1][1]["content"])
    assert ("DISTINCTIVE_ACCEPTED_RESULT_71294" in json.dumps(worker_payload)) is select_history
    if select_history:
        selected = worker_payload["resolved_inputs"][1]
        assert selected["ref"] == "execution:" + result["task_executions"][0]["execution_id"]
        assert selected["content"]["result"]["content"] == first_result
    assert result["execution_transition_state"]["consumed"] == 1


def test_f2_backtracking_resolves_earlier_accepting_execution():
    first_result = {"checkpoint_value": "EARLIER_ACCEPTED_EVIDENCE"}
    backtrack = revise_evaluation()
    backtrack["backtrack_checkpoint_number"] = 2  # Real ACCEPT at r1, not the root exception.
    caller = FakeCaller([
        valid_selection(), first_result, accept_evaluation(continue_work=True),
        successor_plan_semantics(), architecture_assessment_semantics(),
        valid_selection(), {"newer_value": "SECOND_BRANCH"}, accept_evaluation(continue_work=True),
        successor_plan_semantics(), architecture_assessment_semantics(),
        valid_selection(), {"contradiction": "THIRD_BRANCH"}, backtrack,
        successor_plan_semantics(), architecture_assessment_semantics(),
        valid_selection(), exact_worker_result(), accept_evaluation(),
    ])
    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0, job_ref="evidence-backtracking",
        resolved_inputs={"request:abc123": REQUEST}, model_caller=caller,
    )
    synthesis = json.loads(caller.calls[13][1][1]["content"])
    checkpoint = synthesis["checkpoint_execution_evidence"]
    assert checkpoint["result"]["content"] == first_result
    assert checkpoint["outcomes"][0]["decision"] == "ACCEPT"
    assert synthesis["triggering_execution"]["result"]["content"] == {"contradiction": "THIRD_BRANCH"}
    gate = json.loads(caller.calls[14][1][1]["content"])
    assert gate["execution_context"]["checkpoint_execution_evidence"] == checkpoint
    assert result["plan_history"][-1]["revision"] == 4
    assert result["plan_history"][-1]["based_on_revision_ref"].endswith("@r1")
    assert result["execution_transition_state"]["consumed"] == 3


def test_f6_normal_independent_steps_share_one_trusted_request_input():
    from director import select_director_task

    steps = plan_steps_semantics()
    steps["steps"].append(deepcopy(steps["steps"][0]))
    trace = run_normal_planning(
        REQUEST,
        model_caller=CapturingCaller(director_outputs=[
            overall_synthesis_semantics(), steps, architecture_assessment_semantics(),
        ]),
    )
    plan = trace["final_plan"]
    selection = valid_selection()
    selection["selected_step_number"] = 2
    caller = FakeCaller([selection])
    handoff = select_director_task(
        plan, frozen_request=REQUEST, job_ref="shared-request", model_caller=caller,
    )
    assert len(caller.calls) == 1
    payload = json.loads(caller.calls[0][1][1]["content"])
    assert len(payload["available_inputs"]) == 1
    assert len(payload["certified_plan_projection"]["eligible_steps"]) == 2
    assert handoff["director_task"]["input_refs"] == [plan["current_work_ref"]]
    assert handoff["director_task"]["target"]["locator"] == plan["steps"][1]["id"]


def test_f3_exhausted_worker_shape_repair_is_failed_evidence_not_success():
    from orchestrator import execute_managed_director_task
    from test_managed_work_iteration3 import task_handoff

    plan, handoff = task_handoff()
    result = execute_managed_director_task(
        handoff["director_task"], job_ref="job-iteration-3",
        certified_plan=plan, selected_step=handoff["selected_step"],
        resolved_inputs={"request:abc123": REQUEST},
        model_caller=FakeCaller(["first malformed response", "second malformed response"]),
    )
    execution = result["task_execution"]
    assert execution["control"]["status"] == "failed"
    assert execution["result"] is None
    assert execution["error"]["code"] == "output_contract_violation"
    assert "first malformed response" in json.dumps(execution["trace"]["events"])
    assert "second malformed response" in json.dumps(execution["trace"]["events"])
    kwargs = dict(
        frozen_request=REQUEST, certified_plan=plan,
        selected_step=handoff["selected_step"], director_task=handoff["director_task"],
    )
    with pytest.raises(ValueError, match="ACCEPT requires"):
        evaluate_task_execution(execution, model_caller=FakeCaller([accept_evaluation()]), **kwargs)
    evaluated = evaluate_task_execution(
        execution, model_caller=FakeCaller([revise_evaluation()]), **kwargs,
    )
    assert evaluated["disposition"] == "revise"
    assert evaluated["task_execution"]["control"]["status"] == "failed"
    assert evaluated["task_execution"]["plan_execution"]["outcomes"][0]["checkpoint_outcome_ref"] is None


# Controller-plus-persistence adversarial regressions; no endpoint calls.
from pathlib import Path

from orchestrator import (
    load_managed_work_state, managed_work_artifact_paths, persist_managed_work_run,
)
from test_managed_work_iteration3 import ask_guidance_evaluation


def persisted_run(tmp_path, outputs, **kwargs):
    kwargs.setdefault("reasoning_task_count", 0)
    return run_iteration_3(
        certified_plan(), job_ref="repair-proof",
        resolved_inputs={"request:abc123": "ORIGINAL_DELIVERABLE_MANDATE"},
        model_caller=FakeCaller(outputs), artifact_root=tmp_path, **kwargs,
    )


def reload_run(tmp_path):
    return load_managed_work_state("repair-proof", artifact_root=tmp_path)


def artifact_paths(tmp_path):
    return managed_work_artifact_paths("repair-proof", artifact_root=tmp_path)


def test_f9_repeated_persistence_changes_only_resume_timestamp(tmp_path):
    result = persisted_run(tmp_path, [valid_selection(), exact_worker_result(), accept_evaluation()])
    paths = artifact_paths(tmp_path)
    before = {p: p.read_bytes() for p in paths["root"].rglob("*.json") if p != paths["resume"]}
    again = persist_managed_work_run(
        result, job_ref="repair-proof",
        resolved_inputs={"request:abc123": "ORIGINAL_DELIVERABLE_MANDATE"},
        artifact_root=tmp_path, timestamp="2030-01-01T00:00:00+00:00",
    )
    assert before == {p: p.read_bytes() for p in before}
    assert again["resume_state"]["updated_at"] == "2030-01-01T00:00:00+00:00"
    assert reload_run(tmp_path)["task_executions"] == again["task_executions"]
    conflict = deepcopy(again)
    conflict["task_executions"][0]["result"]["content"]["count"] = 99
    with pytest.raises(FileExistsError, match="already differs"):
        persist_managed_work_run(
            conflict, job_ref="repair-proof",
            resolved_inputs={"request:abc123": "ORIGINAL_DELIVERABLE_MANDATE"},
            artifact_root=tmp_path,
        )


@pytest.mark.parametrize("mode", ["budget", "endpoint", "structural_accept_conflict"])
def test_f4_worker_evidence_survives_evaluation_interruption(tmp_path, mode):
    outputs = [valid_selection(), exact_worker_result()]
    if mode == "endpoint":
        outputs.append(RuntimeError("evaluation endpoint unavailable"))
    if mode == "structural_accept_conflict":
        outputs = [valid_selection(), "not json", "still not json", accept_evaluation()]
    result = persisted_run(tmp_path, outputs, reasoning_task_limit=2 if mode == "budget" else 20)
    assert result["status"] == "interrupted"
    assert len(result["task_executions"]) == 1
    worker = result["task_executions"][0]
    assert worker["plan_execution"]["outcomes"] == []
    assert worker["control"]["status"] == ("failed" if mode == "structural_accept_conflict" else "completed")
    restored = reload_run(tmp_path)
    assert restored["task_executions"] == result["task_executions"]
    assert restored["evaluations"] == []
    assert restored["resume_state"]["status"] == "unresolved"
    assert restored["resume_state"]["accepted_checkpoint_ref"].endswith("@r1")
    assert restored["execution_transition_state"]["consumed"] == 0
    assert list(artifact_paths(tmp_path)["executions"].glob("*.json")) == []
    assert restored["reasoning_task_count"] == len(outputs)
    if mode == "endpoint":
        failed = [c for c in restored["calls"] if "call_error" in c]
        assert len(failed) == 1 and "response_text" not in failed[0]


def test_f4_accepted_successor_is_durable_before_next_selection(tmp_path):
    result = persisted_run(tmp_path, [
        valid_selection(), exact_worker_result(), revise_evaluation(),
        successor_plan_semantics(), {"compliant": True, "violations": []},
    ], reasoning_task_limit=5)
    assert result["status"] == "interrupted"
    restored = reload_run(tmp_path)
    assert restored["resume_state"]["current_plan_ref"].endswith("@r2")
    assert restored["execution_transition_state"]["consumed"] == 1
    assert restored["reasoning_task_count"] == 5
    assert len(restored["task_executions"]) == 1
    outcome = restored["task_executions"][0]["plan_execution"]["outcomes"][0]
    assert outcome["decision"] == "REVISE"
    assert outcome["checkpoint_outcome_ref"] is None
    assert outcome["resulting_plan_ref"].endswith("@r2")
    assert (artifact_paths(tmp_path)["plans"] / "rev-0002.json").exists()
    assert len(list(artifact_paths(tmp_path)["executions"].glob("*.json"))) == 1


def test_f9_continuation_keeps_already_persisted_history_bytes(tmp_path):
    caller = FakeCaller([
        valid_selection(), exact_worker_result(), accept_evaluation(continue_work=True),
        successor_plan_semantics(), {"compliant": True, "violations": []},
        valid_selection(), exact_worker_result(), accept_evaluation(),
    ])
    saved = {}

    def observed_caller(*args, **kwargs):
        if len(caller.calls) == 5:
            paths = artifact_paths(tmp_path)
            for path in [paths["plans"] / "rev-0001.json", *paths["executions"].glob("*.json")]:
                saved[path] = path.read_bytes()
            assert len(saved) == 2
            intermediate = reload_run(tmp_path)
            assert intermediate["resume_state"]["status"] == "active"
            assert intermediate["evaluations"][0]["semantics"]["continue_work"] is True
        return caller(*args, **kwargs)

    result = run_iteration_3(
        certified_plan(), reasoning_task_count=0, job_ref="repair-proof",
        resolved_inputs={"request:abc123": "ORIGINAL_DELIVERABLE_MANDATE"},
        model_caller=observed_caller, artifact_root=tmp_path,
    )
    assert result["status"] == "accepted"
    assert saved and all(path.read_bytes() == content for path, content in saved.items())
    assert reload_run(tmp_path)["resume_state"]["status"] == "completed"


def test_f8_planning_seven_call_handoff_is_not_reset(tmp_path, monkeypatch):
    from run_managed_work import run_managed_work
    plan_path = tmp_path / "certified.json"
    plan_path.write_text(json.dumps(certified_plan()), encoding="utf-8")
    caller = FakeCaller([valid_selection(), exact_worker_result(), accept_evaluation()])
    monkeypatch.setattr("orchestrator.invoke_model_context", caller)
    result = run_managed_work(
        plan_path, job_ref="repair-proof", artifact_root=tmp_path,
        resolved_inputs={"request:abc123": "ORIGINAL_DELIVERABLE_MANDATE"},
        reasoning_task_count=7,
    )
    assert result["reasoning_task_count"] == 10
    restored = reload_run(tmp_path)
    assert restored["reasoning_task_count"] == 10
    assert [c["reasoning_task"] for c in restored["calls"] if c["reasoning_task"] is not None] == [8, 9, 10]


def test_f8_launcher_requires_prior_count_before_dispatch(tmp_path):
    from run_managed_work import run_managed_work
    with pytest.raises(ValueError, match="Prior planning reasoning-call consumption is required"):
        run_managed_work(
            tmp_path / "not-read.json", job_ref="repair-proof",
            resolved_inputs={}, artifact_root=tmp_path,
        )
    assert not artifact_paths(tmp_path)["root"].exists()


def test_f8_failed_successor_assessment_remains_charged_after_reload(tmp_path):
    result = persisted_run(tmp_path, [
        valid_selection(), exact_worker_result(), revise_evaluation(),
        successor_plan_semantics(), RuntimeError("assessor endpoint unavailable"),
    ], reasoning_task_count=7)
    assert result["status"] == "semantic_plan_unresolved"
    restored = reload_run(tmp_path)
    assert result["reasoning_task_count"] == restored["reasoning_task_count"] == 12
    assert restored["execution_transition_state"]["consumed"] == 0
    failed = [c for c in restored["calls"] if c.get("call_error")]
    assert len(failed) == 1 and failed[0]["reasoning_task"] == 12
    assert failed[0]["stage"] == "architecture_assessment"
    assert "response_text" not in failed[0]
    outcome = restored["task_executions"][0]["plan_execution"]["outcomes"][0]
    assert outcome["resulting_plan_ref"] is None


def test_f8_dispatched_incomplete_call_is_charged_without_invented_response(tmp_path):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt("process interrupted after attempt was recorded")

    with pytest.raises(KeyboardInterrupt):
        run_iteration_3(
            certified_plan(), job_ref="repair-proof",
            resolved_inputs={"request:abc123": "ORIGINAL_DELIVERABLE_MANDATE"},
            model_caller=interrupted, artifact_root=tmp_path, reasoning_task_count=7,
        )
    restored = reload_run(tmp_path)
    assert restored["reasoning_task_count"] == 8
    assert restored["task_executions"] == []
    assert restored["resume_state"]["status"] == "active"
    last = restored["calls"][-1]
    assert "response_text" not in last and "call_error" not in last
    assert last["reasoning_task"] == 8


def test_f5_completed_pointer_without_execution_cannot_create_acceptance(tmp_path):
    result = persisted_run(tmp_path, [], reasoning_task_count=7, reasoning_task_limit=7)
    assert result["status"] == "interrupted"
    assert reload_run(tmp_path)["task_executions"] == []
    path = artifact_paths(tmp_path)["resume"]
    resume = json.loads(path.read_text())
    resume["status"] = "completed"
    path.write_text(json.dumps(resume), encoding="utf-8")
    with pytest.raises(ValueError, match="completed requires"):
        reload_run(tmp_path)


@pytest.mark.parametrize("field", ["empty_steps", "pending_certification", "false_trigger", "false_parent", "false_assessment"])
def test_f5_reload_rejects_invalid_successor_or_publication(tmp_path, field):
    persisted_run(tmp_path, [
        valid_selection(), exact_worker_result(), revise_evaluation(), successor_plan_semantics(),
        {"compliant": True, "violations": []}, valid_selection(), exact_worker_result(), accept_evaluation(),
    ])
    paths = artifact_paths(tmp_path)
    path = paths["plans"] / "rev-0002.json"
    plan = json.loads(path.read_text())
    if field == "empty_steps":
        plan["steps"] = []
    elif field == "pending_certification":
        plan["integrity"]["validation"]["status"] = "pending"
    elif field == "false_trigger":
        plan["planning_cycle"]["decisions"][-1]["artifact_refs"] = ["invented-trigger"]
    elif field == "false_parent":
        plan["based_on_revision_ref"] = plan["revision_ref"]
    else:
        record = next(c for c in reload_run(tmp_path)["calls"] if c["stage"] == "successor_publication")
        from orchestrator import _managed_artifact_component
        path = paths["calls"] / (_managed_artifact_component(record["call_id"]) + ".response.json")
        plan = json.loads(path.read_text())
        plan["payload"]["semantic_plan_assessments"][-1]["compliant"] = False
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        reload_run(tmp_path)


@pytest.mark.parametrize("field", ["job", "task", "step", "expected_result", "deployment", "continue_work"])
def test_f5_reload_rejects_false_execution_or_completion_links(tmp_path, field):
    result = persisted_run(tmp_path, [valid_selection(), exact_worker_result(), accept_evaluation()])
    paths = artifact_paths(tmp_path)
    path = next(paths["executions"].glob("*.json"))
    value = json.loads(path.read_text())
    if field == "job":
        value["job_ref"] = "unrelated-job"
    elif field == "task":
        value["task_ref"] = "unrelated-task"
    elif field == "step":
        value["plan_execution"]["current_step_ref"] = "unrelated-step"
    elif field == "expected_result":
        value["plan_execution"]["expected_result_snapshot"] = "different expectation"
    elif field == "deployment":
        value["trace"]["deployment"]["model"] = "invented-model"
    else:
        record = next(c for c in result["calls"] if c["stage"] == "director_evaluation")
        from orchestrator import _managed_artifact_component
        path = paths["calls"] / (_managed_artifact_component(record["call_id"]) + ".response.json")
        value = json.loads(path.read_text())
        value["payload"]["semantics"]["continue_work"] = True
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        reload_run(tmp_path)


def test_f5_backtracking_retains_real_r1_execution_checkpoint(tmp_path):
    outputs = []
    for index in range(3):
        decision = accept_evaluation(continue_work=True) if index < 2 else revise_evaluation()
        if index == 2:
            decision["backtrack_checkpoint_number"] = 2  # ACCEPT on r1, not the root exception
        outputs.extend([valid_selection(), {"distinct": index}, decision, successor_plan_semantics(),
                        {"compliant": True, "violations": []}])
    outputs.extend([valid_selection(), exact_worker_result(), accept_evaluation()])
    result = persisted_run(tmp_path, outputs)
    assert result["status"] == "accepted"
    restored = reload_run(tmp_path)
    assert restored["execution_transition_state"]["consumed"] == 3
    assert restored["plan_history"][-1]["based_on_revision_ref"].endswith("@r1")
    third = restored["task_executions"][2]["plan_execution"]["outcomes"][0]
    first = restored["task_executions"][0]["plan_execution"]["outcomes"][0]
    assert third["checkpoint_outcome_ref"] == first["id"]
    assert len(restored["task_executions"]) == 4


def test_f5_awaiting_guidance_retains_nonterminal_judgment_and_root(tmp_path):
    result = persisted_run(tmp_path, [
        valid_selection(), {"impossible": "constraints conflict"}, ask_guidance_evaluation(),
    ])
    restored = reload_run(tmp_path)
    assert restored["resume_state"] == result["resume_state"]
    assert restored["resume_state"]["status"] == "awaiting_guidance"
    assert restored["execution_transition_state"]["consumed"] == 0
    assert restored["evaluations"][0]["semantics"]["decision"] == "ASK_GUIDANCE"
    assert restored["task_executions"][0]["plan_execution"]["outcomes"][0]["checkpoint_outcome_ref"] is None


def test_f1_controller_missing_completion_intent_stays_grounded_and_nonterminal(tmp_path):
    incomplete = accept_evaluation(continue_work=True)
    del incomplete["continue_work"]
    result = persisted_run(tmp_path, [
        valid_selection(), exact_worker_result(), incomplete,
        accept_evaluation(continue_work=True),
    ], reasoning_task_limit=4)
    assert result["status"] == "interrupted"  # no budget to synthesize a successor
    assert result["conformance_repairs"] == []
    assert len(result["semantic_completions"]) == 1
    restored = reload_run(tmp_path)
    assert restored["reasoning_task_count"] == 4
    assert restored["execution_transition_state"]["consumed"] == 0
    assert restored["resume_state"]["status"] == "unresolved"
    assert restored["evaluations"][0]["semantics"]["continue_work"] is True
    recovery = next(c for c in restored["calls"] if c["stage"].endswith("_semantic_completion"))
    payload = json.loads(recovery["messages"][1]["content"])
    assert payload["frozen_request"] == "ORIGINAL_DELIVERABLE_MANDATE"
    assert payload["semantic_context"]["task_execution"]["result"]["content"] == exact_worker_result()


def test_f7_recovery_paths_cannot_reset_each_others_limits(tmp_path):
    wrong_null = accept_evaluation()
    wrong_null["backtrack_checkpoint_number"] = 1
    missing_reason = accept_evaluation()
    del missing_reason["reason"]
    result = persisted_run(tmp_path, [
        valid_selection(), exact_worker_result(), wrong_null, missing_reason, wrong_null,
    ])
    # One representation repair and one grounded completion have run. The
    # still-invalid conditional field cannot open another repair attempt.
    assert result["status"] == "interrupted"
    assert result["reasoning_task_count"] == 5
    restored = reload_run(tmp_path)
    assert restored["execution_transition_state"]["consumed"] == 0
    assert restored["evaluations"] == []
    assert restored["task_executions"][0]["plan_execution"]["outcomes"] == []
    stages = [c["stage"] for c in restored["calls"]]
    assert stages.count("director_execution_evaluation_conformance_repair") == 1
    assert stages.count("director_execution_evaluation_semantic_completion") == 1


def test_f8_direct_controller_also_requires_explicit_handoff(tmp_path):
    caller = FakeCaller([])
    with pytest.raises(ValueError, match="Prior planning reasoning-call consumption"):
        run_iteration_3(
            certified_plan(), job_ref="repair-proof",
            resolved_inputs={"request:abc123": "mandate"}, model_caller=caller,
            artifact_root=tmp_path,
        )
    assert caller.calls == []
    assert not artifact_paths(tmp_path)["root"].exists()


def test_f5_orphan_uncertified_r2_cannot_become_current_state(tmp_path):
    persisted_run(tmp_path, [], reasoning_task_count=7, reasoning_task_limit=7)
    paths = artifact_paths(tmp_path)
    plan = certified_plan()
    plan.update(revision=2, revision_ref="plan-iteration-3@r2", based_on_revision_ref="plan-iteration-3@r1")
    plan["steps"] = []
    plan["final"]["selected_revision_ref"] = plan["revision_ref"]
    plan["integrity"]["validation"]["status"] = "pending"
    (paths["plans"] / "rev-0002.json").write_text(json.dumps(plan), encoding="utf-8")
    resume = json.loads(paths["resume"].read_text())
    resume["current_plan_ref"] = plan["revision_ref"]
    paths["resume"].write_text(json.dumps(resume), encoding="utf-8")
    with pytest.raises(ValueError, match="published successor lacks"):
        reload_run(tmp_path)


def test_f5_reload_requires_original_worker_and_attempt_evidence(tmp_path):
    result = persisted_run(tmp_path, [valid_selection(), exact_worker_result(), accept_evaluation()])
    paths = artifact_paths(tmp_path)
    from orchestrator import _managed_artifact_component
    handoff = next(c for c in result["calls"] if c["stage"] == "planning_handoff")
    path = paths["calls"] / (_managed_artifact_component(handoff["call_id"]) + ".response.json")
    state = json.loads(path.read_text())
    del state["payload"]["prior_reasoning_task_count"]
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ValueError, match="planning handoff"):
        reload_run(tmp_path)


def test_f9_immutable_write_rejects_symlink_redirection(tmp_path):
    from orchestrator import _write_json_once
    destination = tmp_path / "outside"
    destination.mkdir()
    link = tmp_path / "redirect"
    link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        _write_json_once(link / "artifact.json", {"value": "must not escape"})
    assert not (destination / "artifact.json").exists()


def test_f4_interrupted_worker_is_not_implicitly_replayed(tmp_path):
    result = persisted_run(tmp_path, [valid_selection(), exact_worker_result()], reasoning_task_limit=2)
    assert result["status"] == "interrupted"
    caller = FakeCaller([])
    with pytest.raises(RuntimeError, match="implicit replay is forbidden"):
        run_iteration_3(
            certified_plan(), reasoning_task_count=2, job_ref="repair-proof",
            resolved_inputs={"request:abc123": "ORIGINAL_DELIVERABLE_MANDATE"},
            model_caller=caller, artifact_root=tmp_path,
        )
    assert caller.calls == []
    assert reload_run(tmp_path)["task_executions"][0]["result"]["content"] == exact_worker_result()


def test_f5_f8_normal_certification_handoff_execution_and_reload(tmp_path):
    planning = run_normal_planning(
        REQUEST,
        model_caller=CapturingCaller(director_outputs=[
            overall_synthesis_semantics(), plan_steps_semantics(), architecture_assessment_semantics(),
        ]),
    )
    assert planning["reasoning_task_count"] == 7
    plan = planning["final_plan"]
    result = run_iteration_3(
        plan, job_ref="repair-proof", resolved_inputs={plan["current_work_ref"]: REQUEST},
        reasoning_task_count=planning["reasoning_task_count"], artifact_root=tmp_path,
        model_caller=FakeCaller([valid_selection(), exact_worker_result(), accept_evaluation()]),
    )
    assert result["status"] == "accepted"
    restored = reload_run(tmp_path)
    assert restored["plan_history"][0] == plan
    assert len(restored["plan_history"][0]["planning_cycle"]["proposals"]) == 2
    assert restored["reasoning_task_count"] == 10
    assert restored["resume_state"]["status"] == "completed"
    assert restored["evaluations"][0]["context"]["frozen_request"] == REQUEST
