from __future__ import annotations

from copy import deepcopy
import json

import pytest

from planning import (
    assemble_final_plan,
    assemble_successor_plan,
    certify_final_plan,
    execution_transition_budget_state,
    validate_successor_plan,
)


def proposal_record(proposal_id: str, author_ref: str) -> dict[str, object]:
    return {
        "id": proposal_id,
        "iteration": 1,
        "author_ref": author_ref,
        "summary": "Use one bounded execution step.",
        "main_points": ["Produce and validate the requested result."],
        "reason": "The requested result is directly observable.",
        "assumptions": [],
        "message_refs": [],
        "artifact_refs": [],
        "proposal_state": "candidate",
        "proposal_reason": None,
        "decided_by_ref": None,
        "decided_in_revision_ref": None,
    }


def assessment_record(
    critique_id: str,
    *,
    author_ref: str,
    target_ref: str,
) -> dict[str, object]:
    return {
        "critique": {
            "id": critique_id,
            "iteration": 2,
            "author_ref": author_ref,
            "target_kind": "proposal",
            "target_ref": target_ref,
            "severity": "low",
            "summary": "The bounded approach is adequate.",
            "suggested_change_refs": [],
            "message_refs": [],
            "artifact_refs": [],
        },
        "suggested_changes": [],
    }


def certified_root() -> dict[str, object]:
    proposals = [
        proposal_record("proposal-gemma", "gemma_worker"),
        proposal_record("proposal-qwen", "qwen_worker"),
    ]
    assessments = [
        assessment_record(
            "critique-qwen", author_ref="qwen_worker",
            target_ref="proposal-gemma",
        ),
        assessment_record(
            "critique-gemma", author_ref="gemma_worker",
            target_ref="proposal-qwen",
        ),
    ]
    semantics = {
        "goal": "Produce a verified managed-work result.",
        "approach_summary": ["Execute one bounded semantic step."],
        "decision_rationale": "Both proposals support the bounded step.",
        "rejected_alternatives": [],
        "change_summary": ["Created the planning-certified root."],
        "decision_reason": "The Plan is ready for managed execution.",
        "unresolved_risks": [],
        "unresolved_questions": [],
        "accepted_change_numbers": [],
        "rejected_change_numbers": [],
        "deferred_change_numbers": [],
        "steps": [{
            "action": "Produce the requested result.",
            "reason": "This directly advances the managed mandate.",
            "instructions": ["Return only the requested result."],
            "scope_boundary": "Do not add unrelated work.",
            "expected_result": "A verified result.",
            "validation": ["The result satisfies the request."],
            "depends_on_step_numbers": [],
        }],
    }
    return certify_final_plan(assemble_final_plan(
        semantics,
        plan_id="plan-lineage",
        current_work_ref="request:lineage",
        director_ref="gemma_director",
        proposals=proposals,
        assessments=assessments,
    ))


def successor_semantics(label: str) -> dict[str, object]:
    return {
        "overall_synthesis": {
            "goal": f"Produce the verified result using {label}.",
            "approach_summary": [f"Use {label} for the next bounded step."],
            "decision_rationale": (
                f"Execution evidence requires the {label} successor."
            ),
            "rejected_alternatives": [],
            "change_summary": [f"Revised execution semantics to {label}."],
            "decision_reason": f"The {label} state is ready for execution.",
            "unresolved_risks": [],
            "unresolved_questions": [],
        },
        "plan_steps": {
            "steps": [{
                "action": f"Produce the result using {label}.",
                "reason": "The prior execution evidence requires revision.",
                "instructions": [f"Apply {label} and return the result."],
                "scope_boundary": "Do not mutate prior Plan artifacts.",
                "expected_result": f"A verified {label} result.",
                "validation": [f"The result demonstrates {label}."],
                "depends_on_step_numbers": [],
            }],
        },
    }


def accept_outcome(
    outcome_id: str,
    revision_ref: str,
) -> dict[str, object]:
    return {
        "id": outcome_id,
        "decision": "ACCEPT",
        "checkpoint_revision_ref": revision_ref,
        "checkpoint_outcome_ref": outcome_id,
        "execution_ref": f"{outcome_id}:execution",
    }


def assemble_and_certify(
    history: list[dict[str, object]],
    *,
    checkpoint_revision_ref: str,
    checkpoint_outcome_ref: str | None,
    accepted_outcomes: dict[str, dict[str, object]],
    label: str,
    execution_ref: str,
    outcome_ref: str,
) -> dict[str, object]:
    candidate = assemble_successor_plan(
        history,
        checkpoint_revision_ref=checkpoint_revision_ref,
        checkpoint_outcome_ref=checkpoint_outcome_ref,
        accepted_outcomes_by_ref=accepted_outcomes,
        successor_semantics=successor_semantics(label),
        triggering_execution_ref=execution_ref,
        triggering_outcome_ref=outcome_ref,
        director_ref="gemma_director",
        timestamp="2026-09-15T12:00:00+00:00",
    )
    certified = certify_final_plan(candidate)
    assert validate_successor_plan(
        certified,
        prior_plan_history=history,
        checkpoint_revision_ref=checkpoint_revision_ref,
        checkpoint_outcome_ref=checkpoint_outcome_ref,
        accepted_outcomes_by_ref=accepted_outcomes,
        triggering_execution_ref=execution_ref,
        triggering_outcome_ref=outcome_ref,
        director_ref="gemma_director",
    ) == ()
    return certified


def test_root_backed_successor_is_immutable_and_consumes_one_transition() -> None:
    root = certified_root()
    frozen_root = json.dumps(root, sort_keys=True)

    revision_two = assemble_and_certify(
        [root],
        checkpoint_revision_ref="plan-lineage@r1",
        checkpoint_outcome_ref=None,
        accepted_outcomes={},
        label="revision two",
        execution_ref="execution-r1-revise",
        outcome_ref="outcome-r1-revise",
    )

    assert json.dumps(root, sort_keys=True) == frozen_root
    assert revision_two["plan_id"] == root["plan_id"]
    assert revision_two["revision"] == 2
    assert revision_two["revision_ref"] == "plan-lineage@r2"
    assert revision_two["based_on_revision_ref"] == "plan-lineage@r1"
    assert revision_two["parent_plan_ref"] == root["parent_plan_ref"]
    assert revision_two["process"] == root["process"]
    assert revision_two["steps"][0]["id"] == (
        "plan-lineage@r2:step-1"
    )
    assert revision_two["planning_cycle"]["decisions"][:-1] == (
        root["planning_cycle"]["decisions"]
    )
    assert revision_two["planning_cycle"]["revisions"][:-1] == (
        root["planning_cycle"]["revisions"]
    )
    assert execution_transition_budget_state(
        [root, revision_two]
    )["consumed"] == 1


def test_later_revision_can_backtrack_to_root_without_losing_branch() -> None:
    root = certified_root()
    revision_two = assemble_and_certify(
        [root],
        checkpoint_revision_ref=root["revision_ref"],
        checkpoint_outcome_ref=None,
        accepted_outcomes={},
        label="revision two",
        execution_ref="execution-1",
        outcome_ref="outcome-revise-1",
    )
    accepted_two = accept_outcome(
        "outcome-accept-r2", revision_two["revision_ref"],
    )
    accepted = {accepted_two["id"]: accepted_two}
    revision_three = assemble_and_certify(
        [root, revision_two],
        checkpoint_revision_ref=revision_two["revision_ref"],
        checkpoint_outcome_ref=accepted_two["id"],
        accepted_outcomes=accepted,
        label="revision three",
        execution_ref="execution-2",
        outcome_ref="outcome-revise-2",
    )
    frozen_branch = json.dumps(
        [root, revision_two, revision_three], sort_keys=True,
    )

    revision_four = assemble_and_certify(
        [root, revision_two, revision_three],
        checkpoint_revision_ref=root["revision_ref"],
        checkpoint_outcome_ref=None,
        accepted_outcomes=accepted,
        label="root backtrack",
        execution_ref="execution-3",
        outcome_ref="outcome-revise-3",
    )

    assert json.dumps(
        [root, revision_two, revision_three], sort_keys=True,
    ) == frozen_branch
    assert revision_four["revision_ref"] == "plan-lineage@r4"
    assert revision_four["based_on_revision_ref"] == "plan-lineage@r1"
    assert [
        item["revision_ref"]
        for item in revision_four["planning_cycle"]["revisions"]
    ] == [
        "plan-lineage@r1",
        "plan-lineage@r2",
        "plan-lineage@r3",
        "plan-lineage@r4",
    ]
    assert execution_transition_budget_state([
        root, revision_two, revision_three, revision_four,
    ])["consumed"] == 3


def test_non_root_checkpoint_requires_real_accept_outcome() -> None:
    root = certified_root()
    revision_two = assemble_and_certify(
        [root],
        checkpoint_revision_ref=root["revision_ref"],
        checkpoint_outcome_ref=None,
        accepted_outcomes={},
        label="revision two",
        execution_ref="execution-1",
        outcome_ref="outcome-revise-1",
    )

    with pytest.raises(ValueError, match="ACCEPT outcome"):
        assemble_successor_plan(
            [root, revision_two],
            checkpoint_revision_ref=revision_two["revision_ref"],
            checkpoint_outcome_ref="outcome-not-accepted",
            accepted_outcomes_by_ref={
                "outcome-not-accepted": {
                    "id": "outcome-not-accepted",
                    "decision": "REVISE",
                    "checkpoint_revision_ref": revision_two["revision_ref"],
                },
            },
            successor_semantics=successor_semantics("invalid checkpoint"),
            triggering_execution_ref="execution-2",
            triggering_outcome_ref="outcome-revise-2",
            director_ref="gemma_director",
        )


def test_transition_budget_blocks_a_fourth_successor() -> None:
    root = certified_root()
    history = [root]
    for revision in range(2, 5):
        history.append(assemble_and_certify(
            history,
            checkpoint_revision_ref=root["revision_ref"],
            checkpoint_outcome_ref=None,
            accepted_outcomes={},
            label=f"revision {revision}",
            execution_ref=f"execution-{revision}",
            outcome_ref=f"outcome-revise-{revision}",
        ))

    with pytest.raises(RuntimeError, match="budget exhausted"):
        assemble_successor_plan(
            history,
            checkpoint_revision_ref=root["revision_ref"],
            checkpoint_outcome_ref=None,
            accepted_outcomes_by_ref={},
            successor_semantics=successor_semantics("revision five"),
            triggering_execution_ref="execution-5",
            triggering_outcome_ref="outcome-revise-5",
            director_ref="gemma_director",
        )
