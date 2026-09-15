"""Deterministic projections and validation for Director-owned Normal planning."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import json
import re
from typing import Any, Mapping, Sequence

from config import (
    DEFAULT_JOB_BUDGET,
    PLAN_PROTOCOL_PATH,
    PLAN_PROTOCOL_VOCABULARY_PATH,
    PLANNING_POLICY_PATH,
)
from structures import ValidationIssue, load_json_mapping, load_yaml_mapping

ASSESSMENT_CRITERIA = (
    "strengths",
    "weaknesses",
    "uncertainty",
    "missing information",
    "useful questions",
    "complementary ideas",
    "genuine contradictions/trade-offs",
    "synthesis/improvement opportunities",
)
NO_MANUFACTURED_DISAGREEMENT = (
    "Do not manufacture disagreement. Agreement, complementarity, partial "
    "overlap, and genuine conflict are all valid findings."
)

PROPOSAL_SEMANTIC_SHAPE = {
    "summary": "<concise candidate approach>",
    "main_points": ["<main proposal point>"],
    "assumptions": ["<assumption, or an empty array>"],
    "reason": "<why this approach is proposed>",
}

ASSESSMENT_SEMANTIC_SHAPE = {
    "severity": "<blocking | high | medium | low>",
    "strengths": ["<strength, or an empty array>"],
    "weaknesses": ["<weakness, or an empty array>"],
    "uncertainty": ["<uncertainty, or an empty array>"],
    "missing_information": ["<missing item, or an empty array>"],
    "useful_questions": ["<useful question, or an empty array>"],
    "complementary_ideas": ["<complementary idea, or an empty array>"],
    "genuine_contradictions_or_tradeoffs": [
        "<genuine conflict or trade-off, or an empty array>"
    ],
    "synthesis_or_improvement_opportunities": [
        "<synthesis opportunity, or an empty array>"
    ],
    "suggested_changes": [
        {
            "description": "<concise suggested modification>",
            "reason": "<why the modification helps>",
        }
    ],
}

CHANGE_DISPOSITION_SEMANTIC_SHAPE = {
    "dispositions": [],
}

OVERALL_SYNTHESIS_SEMANTIC_SHAPE = {
    "goal": "<one-sentence objective>",
    "approach_summary": ["<key idea>"],
    "decision_rationale": "<why this synthesis is final>",
    "rejected_alternatives": [],
    "change_summary": ["<how the proposals and assessments were synthesized>"],
    "decision_reason": "<why the resulting Plan is final>",
    "unresolved_risks": ["<risk, or an empty array>"],
    "unresolved_questions": ["<question, or an empty array>"],
}

PLAN_STEPS_SEMANTIC_SHAPE = {
    "steps": [
        {
            "action": "<concise imperative action>",
            "reason": "<why the step exists>",
            "instructions": ["<bounded instruction>"],
            "scope_boundary": "<what the step must not do>",
            "expected_result": "<observable result>",
            "validation": ["<pass-or-fail criterion>"],
            "depends_on_step_numbers": [],
        }
    ],
}

ARCHITECTURE_ASSESSMENT_SEMANTIC_SHAPE = {
    "compliant": "<boolean>",
    "violations": [],
}

SEMANTIC_BOUNDARY_CORRECTION_SHAPE = {
    "overall_synthesis": OVERALL_SYNTHESIS_SEMANTIC_SHAPE,
    "plan_steps": PLAN_STEPS_SEMANTIC_SHAPE,
}

FROZEN_ARCHITECTURE_INVARIANTS = (
    "Director decides what semantic work and capabilities are required.",
    "Task Executive and configuration decide how and resolve the concrete model mechanically.",
    "Director must not directly resolve model IDs, endpoints, or hosts.",
    "Plan is passive state and has no decision authority.",
    "No third intelligent manager, coordinator, or Router is introduced.",
    "Any routing helper is deterministic machinery owned by Task Executive or configuration, not another authority.",
    "Model routing is configuration-driven and generic.",
    "Generic execution logic contains no hard-coded Gemma or Qwen branches.",
    "V0 uses static capability metadata only.",
    "V0 has no dynamic benchmarking, learned or adaptive routing, or runtime performance scoring.",
    "There is no hidden frontier or external fallback.",
    "Any local fallback is explicit deterministic configuration, not implicit semantic escalation.",
)

_JSON_FENCE = re.compile(
    r"\A\s*```json[ \t]*\r?\n(?P<body>[\s\S]*?)\r?\n```[ \t]*\s*\Z"
)
_LEADING_THINK = re.compile(
    r"\A\s*<think>[\s\S]*?</think>\s*(?P<body>[\s\S]+?)\s*\Z"
)


def _issue(field: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(field=field, code=code, message=message)


def validate_planning_root_checkpoint(
    plan: object,
) -> tuple[ValidationIssue, ...]:
    """Prove that a Plan is the distinguished planning-certified V0 root."""

    if not isinstance(plan, Mapping):
        return (_issue(
            "root_checkpoint.plan", "invalid_shape",
            "Root checkpoint Plan must be an object.",
        ),)

    issues: list[ValidationIssue] = []
    plan_id = plan.get("plan_id")
    revision_ref = plan.get("revision_ref")
    if not isinstance(plan_id, str) or not plan_id.strip():
        issues.append(_issue(
            "root_checkpoint.plan_id", "invalid_shape",
            "Root checkpoint plan_id must be a non-empty string.",
        ))
    expected_ref = (
        f"{plan_id}@r1" if isinstance(plan_id, str) and plan_id.strip()
        else None
    )
    if plan.get("revision") != 1:
        issues.append(_issue(
            "root_checkpoint.revision", "invalid_root_revision",
            "The planning-created root checkpoint must be revision 1.",
        ))
    if revision_ref != expected_ref:
        issues.append(_issue(
            "root_checkpoint.revision_ref", "invalid_root_revision",
            "The root checkpoint revision_ref must be <plan_id>@r1.",
        ))
    if plan.get("based_on_revision_ref") is not None:
        issues.append(_issue(
            "root_checkpoint.based_on_revision_ref", "invalid_root_lineage",
            "The planning-created root cannot be based on another revision.",
        ))
    if plan.get("status") != "final":
        issues.append(_issue(
            "root_checkpoint.status", "not_certified_root",
            "The root checkpoint Plan must have final status.",
        ))

    process = plan.get("process")
    iteration = process.get("iteration") if isinstance(process, Mapping) else None
    if (
        not isinstance(iteration, Mapping)
        or iteration.get("current") != DEFAULT_JOB_BUDGET["semantic_iterations"]
        or iteration.get("maximum") != DEFAULT_JOB_BUDGET["semantic_iterations"]
    ):
        issues.append(_issue(
            "root_checkpoint.process.iteration", "not_planning_complete",
            "The root checkpoint must preserve the completed planning 3/3 state.",
        ))

    final = plan.get("final")
    if (
        not isinstance(final, Mapping)
        or final.get("is_final") is not True
        or final.get("selected_revision_ref") != revision_ref
    ):
        issues.append(_issue(
            "root_checkpoint.final", "not_final",
            "The root checkpoint must be the Plan's selected final revision.",
        ))

    validation = None
    integrity = plan.get("integrity")
    if isinstance(integrity, Mapping):
        validation = integrity.get("validation")
    if (
        not isinstance(validation, Mapping)
        or validation.get("status") != "valid"
        or validation.get("validated_by_ref")
        != "deterministic_plan_validator"
        or not isinstance(validation.get("validated_at"), str)
        or not validation["validated_at"].strip()
        or validation.get("errors") != []
    ):
        issues.append(_issue(
            "root_checkpoint.integrity.validation", "not_certified_root",
            "The root checkpoint requires trusted deterministic certification.",
        ))

    cycle = plan.get("planning_cycle")
    decisions = cycle.get("decisions") if isinstance(cycle, Mapping) else None
    finalize_records = [
        item for item in decisions
        if (
            isinstance(item, Mapping)
            and item.get("type") == "finalize"
            and item.get("resulting_revision_ref") == revision_ref
            and isinstance(item.get("id"), str)
            and item["id"].strip()
            and isinstance(item.get("author_ref"), str)
            and item["author_ref"].strip()
        )
    ] if isinstance(decisions, list) else []
    if len(finalize_records) != 1:
        issues.append(_issue(
            "root_checkpoint.planning_cycle.decisions",
            "missing_finalization_evidence",
            "The root checkpoint requires exactly one trusted finalize decision.",
        ))

    revisions = cycle.get("revisions") if isinstance(cycle, Mapping) else None
    root_revisions = [
        item for item in revisions
        if (
            isinstance(item, Mapping)
            and item.get("revision_ref") == revision_ref
            and item.get("based_on_revision_ref") is None
        )
    ] if isinstance(revisions, list) else []
    if len(root_revisions) != 1:
        issues.append(_issue(
            "root_checkpoint.planning_cycle.revisions",
            "missing_root_revision_evidence",
            "The root checkpoint requires its trusted root revision record.",
        ))
    return tuple(issues)


def root_checkpoint_evidence_refs(
    plan: Mapping[str, Any],
) -> tuple[str, str]:
    """Return stable references to embedded root finalization/certification."""

    issues = validate_planning_root_checkpoint(plan)
    if issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in issues
        )
        raise ValueError(f"Invalid planning root checkpoint: {details}")
    revision_ref = plan["revision_ref"]
    decisions = plan["planning_cycle"]["decisions"]
    finalize = next(
        item for item in decisions
        if item.get("type") == "finalize"
        and item.get("resulting_revision_ref") == revision_ref
    )
    return (
        f"{revision_ref}#planning_cycle.decisions/{finalize['id']}",
        f"{revision_ref}#integrity.validation",
    )


def execution_transition_budget_state(
    plan_history: Sequence[Mapping[str, Any]],
    *,
    maximum: int | None = None,
) -> dict[str, Any]:
    """Validate V0 revision accounting and derive transition consumption."""

    limit = (
        DEFAULT_JOB_BUDGET["execution_transitions"]
        if maximum is None
        else maximum
    )
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError(
            "Execution-transition maximum must be a non-negative integer."
        )
    if (
        not isinstance(plan_history, Sequence)
        or isinstance(plan_history, (str, bytes))
        or not plan_history
    ):
        raise ValueError("Plan history must contain the certified @r1 root.")

    issues: list[ValidationIssue] = []
    root = plan_history[0]
    issues.extend(validate_planning_root_checkpoint(root))
    plan_id = root.get("plan_id") if isinstance(root, Mapping) else None
    known_refs: set[str] = set()

    for position, plan in enumerate(plan_history, start=1):
        field = f"plan_history[{position - 1}]"
        if not isinstance(plan, Mapping):
            issues.append(_issue(
                field, "invalid_shape", "Plan revision must be an object.",
            ))
            continue
        revision_ref = plan.get("revision_ref")
        expected_ref = (
            f"{plan_id}@r{position}" if isinstance(plan_id, str) else None
        )
        if plan.get("plan_id") != plan_id:
            issues.append(_issue(
                f"{field}.plan_id", "lineage_mismatch",
                "All execution revisions must retain the root plan_id.",
            ))
        if plan.get("revision") != position or revision_ref != expected_ref:
            issues.append(_issue(
                f"{field}.revision", "non_chronological_revision",
                "V0 Plan history must contain each chronological revision exactly once.",
            ))
        based_on = plan.get("based_on_revision_ref")
        if position == 1:
            if based_on is not None:
                issues.append(_issue(
                    f"{field}.based_on_revision_ref", "invalid_root_lineage",
                    "The @r1 root cannot have a lineage parent.",
                ))
        elif based_on not in known_refs:
            issues.append(_issue(
                f"{field}.based_on_revision_ref", "invalid_lineage_reference",
                "A successor must branch from an earlier revision in this history.",
            ))
        final = plan.get("final")
        if (
            not isinstance(final, Mapping)
            or final.get("is_final") is not True
            or final.get("selected_revision_ref") != revision_ref
        ):
            issues.append(_issue(
                f"{field}.final", "invalid_finality",
                "Every executable Plan node must select its current revision.",
            ))
        process = plan.get("process")
        iteration = (
            process.get("iteration") if isinstance(process, Mapping) else None
        )
        if (
            not isinstance(iteration, Mapping)
            or iteration.get("current")
            != DEFAULT_JOB_BUDGET["semantic_iterations"]
            or iteration.get("maximum")
            != DEFAULT_JOB_BUDGET["semantic_iterations"]
        ):
            issues.append(_issue(
                f"{field}.process.iteration", "planning_budget_mutated",
                "Execution revisions must preserve planning iteration 3/3.",
            ))
        if isinstance(revision_ref, str):
            known_refs.add(revision_ref)

    if issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in issues
        )
        raise ValueError(f"Invalid V0 execution Plan lineage: {details}")

    highest_revision = len(plan_history)
    consumed = highest_revision - 1
    if consumed > limit:
        raise RuntimeError(
            "Execution-transition budget exceeded by persisted Plan lineage."
        )
    return {
        "maximum": limit,
        "consumed": consumed,
        "remaining": limit - consumed,
        "can_create_successor": consumed < limit,
        "current_plan_ref": plan_history[-1]["revision_ref"],
    }


@lru_cache(maxsize=1)
def _plan_template() -> Mapping[str, Any]:
    return load_json_mapping(PLAN_PROTOCOL_PATH)


@lru_cache(maxsize=1)
def _plan_vocabulary() -> Mapping[str, Any]:
    return load_yaml_mapping(PLAN_PROTOCOL_VOCABULARY_PATH)


@lru_cache(maxsize=1)
def normal_policy_projection() -> Mapping[str, Any]:
    """Return only policy needed by the fixed Normal-planning sequence."""

    policy = load_yaml_mapping(PLANNING_POLICY_PATH)
    return {
        "planning_level": "normal",
        "planning_level_policy": policy["planning_levels"]["normal"],
        "iteration_semantics": policy["iteration_semantics"],
        "convergence_policy": policy["convergence_policy"],
        "numeric_budget": dict(DEFAULT_JOB_BUDGET),
    }


@lru_cache(maxsize=1)
def conformance_repair_policy() -> Mapping[str, Any]:
    """Return the generic planning-artifact conformance-repair policy."""

    policy = load_yaml_mapping(PLANNING_POLICY_PATH)
    repair = policy.get("conformance_repair")
    if not isinstance(repair, Mapping):
        raise RuntimeError("Planning policy lacks conformance_repair.")
    return repair


@lru_cache(maxsize=1)
def semantic_completion_policy() -> Mapping[str, Any]:
    """Return the Director semantic-completion policy."""

    policy = load_yaml_mapping(PLANNING_POLICY_PATH)
    completion = policy.get("semantic_completion")
    if not isinstance(completion, Mapping):
        raise RuntimeError("Planning policy lacks semantic_completion.")
    return completion


@lru_cache(maxsize=1)
def semantic_architecture_acceptance_policy() -> Mapping[str, Any]:
    """Return the semantic architecture acceptance policy."""

    policy = load_yaml_mapping(PLANNING_POLICY_PATH)
    acceptance = policy.get("semantic_architecture_acceptance")
    if not isinstance(acceptance, Mapping):
        raise RuntimeError(
            "Planning policy lacks semantic_architecture_acceptance."
        )
    return acceptance


@lru_cache(maxsize=1)
def semantic_boundary_correction_policy() -> Mapping[str, Any]:
    """Return the one-attempt semantic boundary correction policy."""

    policy = load_yaml_mapping(PLANNING_POLICY_PATH)
    correction = policy.get("semantic_boundary_correction")
    if not isinstance(correction, Mapping):
        raise RuntimeError(
            "Planning policy lacks semantic_boundary_correction."
        )
    return correction


def _schema_from_protocol_shape(value: Any) -> dict[str, Any]:
    """Build an exact-field JSON Schema from a protocol template value."""

    if isinstance(value, Mapping):
        return {
            "type": "object",
            "properties": {
                key: _schema_from_protocol_shape(item)
                for key, item in value.items()
            },
            "required": list(value),
            "additionalProperties": False,
        }
    if isinstance(value, list):
        item_schema = (
            _schema_from_protocol_shape(value[0])
            if value
            else {"type": "string"}
        )
        return {"type": "array", "items": item_schema}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, str):
        return {"type": "string"}
    if value is None:
        return {
            "anyOf": [
                {"type": "string"},
                {"type": "null"},
            ]
        }
    raise TypeError(f"Unsupported protocol template value: {type(value).__name__}")


def _json_schema_response_format(
    *,
    name: str,
    shape: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": _schema_from_protocol_shape(shape),
        },
    }


def proposal_response_format() -> dict[str, Any]:
    """Constrain only model-owned proposal semantics."""

    return _json_schema_response_format(
        name="normal_planning_proposal_semantics",
        shape=PROPOSAL_SEMANTIC_SHAPE,
    )


def assessment_response_format() -> dict[str, Any]:
    """Constrain only model-owned assessment semantics."""

    response_format = _json_schema_response_format(
        name="normal_planning_assessment_semantics",
        shape=ASSESSMENT_SEMANTIC_SHAPE,
    )
    schema = response_format["json_schema"]["schema"]
    schema["properties"]["severity"] = {
        "type": "string",
        "enum": list(_plan_vocabulary()["severity"]),
    }
    return response_format


def change_disposition_response_format() -> dict[str, Any]:
    """Constrain suggested-change disposition semantics."""

    response_format = _json_schema_response_format(
        name="normal_planning_change_dispositions",
        shape=CHANGE_DISPOSITION_SEMANTIC_SHAPE,
    )
    response_format["json_schema"]["schema"]["properties"][
        "dispositions"
    ] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "change_number": {"type": "integer"},
                "disposition": {
                    "type": "string",
                    "enum": ["accepted", "rejected", "deferred"],
                },
            },
            "required": ["change_number", "disposition"],
            "additionalProperties": False,
        },
    }
    return response_format


def overall_synthesis_response_format() -> dict[str, Any]:
    """Constrain overall Director synthesis semantics."""

    response_format = _json_schema_response_format(
        name="normal_planning_overall_synthesis",
        shape=OVERALL_SYNTHESIS_SEMANTIC_SHAPE,
    )
    response_format["json_schema"]["schema"]["properties"][
        "rejected_alternatives"
    ] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "proposal_number": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["proposal_number", "reason"],
            "additionalProperties": False,
        },
    }
    return response_format


def plan_steps_response_format() -> dict[str, Any]:
    """Constrain semantic Plan steps without protocol bookkeeping."""

    response_format = _json_schema_response_format(
        name="normal_planning_plan_steps",
        shape=PLAN_STEPS_SEMANTIC_SHAPE,
    )
    response_format["json_schema"]["schema"]["properties"]["steps"][
        "items"
    ]["properties"]["depends_on_step_numbers"] = {
        "type": "array",
        "items": {"type": "integer"},
    }
    return response_format


def architecture_assessment_response_format() -> dict[str, Any]:
    """Constrain the advisory semantic architecture assessment."""

    response_format = _json_schema_response_format(
        name="normal_planning_architecture_assessment",
        shape=ARCHITECTURE_ASSESSMENT_SEMANTIC_SHAPE,
    )
    properties = response_format["json_schema"]["schema"]["properties"]
    properties["compliant"] = {"type": "boolean"}
    properties["violations"] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "finding": {"type": "string"},
                "affected_step_or_field": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "null"},
                    ]
                },
            },
            "required": ["finding", "affected_step_or_field"],
            "additionalProperties": False,
        },
    }
    return response_format


def semantic_boundary_correction_response_format() -> dict[str, Any]:
    """Constrain corrected synthesis semantics without Plan bookkeeping."""

    response_format = _json_schema_response_format(
        name="normal_planning_semantic_boundary_correction",
        shape=SEMANTIC_BOUNDARY_CORRECTION_SHAPE,
    )
    properties = response_format["json_schema"]["schema"]["properties"]
    properties["overall_synthesis"] = deepcopy(
        overall_synthesis_response_format()["json_schema"]["schema"]
    )
    properties["plan_steps"] = deepcopy(
        plan_steps_response_format()["json_schema"]["schema"]
    )
    return response_format


def successor_plan_response_format() -> dict[str, Any]:
    """Constrain one execution-driven successor Plan semantic node."""

    response_format = _json_schema_response_format(
        name="managed_work_successor_plan_semantics",
        shape={
            "overall_synthesis": OVERALL_SYNTHESIS_SEMANTIC_SHAPE,
            "plan_steps": PLAN_STEPS_SEMANTIC_SHAPE,
        },
    )
    properties = response_format["json_schema"]["schema"]["properties"]
    properties["overall_synthesis"] = deepcopy(
        overall_synthesis_response_format()["json_schema"]["schema"]
    )
    properties["plan_steps"] = deepcopy(
        plan_steps_response_format()["json_schema"]["schema"]
    )
    return response_format


def render_proposal_messages(
    frozen_request: str,
) -> tuple[dict[str, str], ...]:
    """Render an identical semantic-only projection for either proposer."""

    content = {
        "frozen_request": frozen_request,
        "normal_policy": normal_policy_projection(),
        "required_semantic_output": PROPOSAL_SEMANTIC_SHAPE,
        "rules": [
            "This call authors proposal semantics, not the requested final result.",
            "Return exactly summary, main_points, assumptions, and reason.",
            "Do not return IDs, authorship, iteration, references, state, or disposition metadata.",
            "Do not include fields from the user-requested final output.",
        ],
    }
    return (
        {
            "role": "system",
            "content": (
                "Produce one independent Normal-planning semantic contribution. "
                "Python will construct the canonical proposal protocol record. "
                "Return exactly the four requested semantic fields as plain JSON "
                "without Markdown fences. Do not infer or discuss another branch."
            ),
        },
        {"role": "user", "content": json.dumps(content, sort_keys=True)},
    )


def render_assessment_messages(
    frozen_request: str,
    *,
    target_proposal: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    """Render one selected proposal for semantic-only constructive assessment."""

    content = {
        "frozen_request": frozen_request,
        "target_proposal": target_proposal,
        "assessment_criteria": list(ASSESSMENT_CRITERIA),
        "assessment_rule": NO_MANUFACTURED_DISAGREEMENT,
        "required_semantic_output": ASSESSMENT_SEMANTIC_SHAPE,
        "rules": [
            "Return semantic judgment only.",
            "Each assessment category is a JSON array of zero or more non-empty string findings; use [] when none is identified.",
            "Consider every category, but do not fabricate a finding merely to make an array non-empty.",
            "Do not return critique IDs, author IDs, target references, message or artifact references, proposal state, or decision metadata.",
            "suggested_changes may be empty when no change is warranted.",
        ],
    }
    return (
        {
            "role": "system",
            "content": (
                "Assess the selected proposal constructively. "
                + NO_MANUFACTURED_DISAGREEMENT
                + " Python will construct the canonical critique and suggested-change records. "
                "Return only the requested semantic fields as plain JSON without "
                "Markdown fences."
            ),
        },
        {"role": "user", "content": json.dumps(content, sort_keys=True)},
    )


DIRECTOR_AUTHORITY_REQUIREMENTS = (
    "The Director selects semantic requirements and decisions, but never concrete model IDs.",
    "The Plan is passive structured state and contains no routing or execution behavior.",
    "The Task Executive and configuration later resolve the concrete model mechanically.",
    "Do not introduce a Router, third manager, or hidden frontier escalation.",
    "Any local fallback must be explicit configuration.",
    "Use static capability metadata only; dynamic benchmarking, learned reliability, and adaptive routing are out of scope.",
)


def _synthesis_sources(
    *,
    gemma_proposal: Mapping[str, Any],
    qwen_proposal: Mapping[str, Any],
    qwen_assessment: Mapping[str, Any],
    gemma_assessment: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "gemma_proposal": deepcopy(dict(gemma_proposal)),
        "qwen_proposal": deepcopy(dict(qwen_proposal)),
        "qwen_assessment_of_gemma": deepcopy(dict(qwen_assessment)),
        "gemma_assessment_of_qwen": deepcopy(dict(gemma_assessment)),
    }


def _numbered_suggested_changes(
    qwen_assessment: Mapping[str, Any],
    gemma_assessment: Mapping[str, Any],
) -> list[dict[str, Any]]:
    changes = [
        change
        for assessment in (qwen_assessment, gemma_assessment)
        for change in assessment["suggested_changes"]
    ]
    return [
        {
            "number": number,
            "id": change["id"],
            "description": change["description"],
            "reason": change["reason"],
        }
        for number, change in enumerate(changes, start=1)
    ]


def render_change_disposition_messages(
    frozen_request: str,
    *,
    gemma_proposal: Mapping[str, Any],
    qwen_proposal: Mapping[str, Any],
    qwen_assessment: Mapping[str, Any],
    gemma_assessment: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    """Ask the Director only for suggested-change judgments."""

    content = {
        "frozen_request": frozen_request,
        **_synthesis_sources(
            gemma_proposal=gemma_proposal,
            qwen_proposal=qwen_proposal,
            qwen_assessment=qwen_assessment,
            gemma_assessment=gemma_assessment,
        ),
        "supplied_suggested_changes": _numbered_suggested_changes(
            qwen_assessment,
            gemma_assessment,
        ),
        "required_semantic_output": CHANGE_DISPOSITION_SEMANTIC_SHAPE,
        "requirements": [
            "Return one disposition per supplied suggested change.",
            "Each entry contains only change_number and disposition.",
            "Disposition must be accepted, rejected, or deferred.",
            "Reference only numbers in supplied_suggested_changes.",
            "Every supplied number must appear exactly once; do not omit or duplicate one.",
            "Do not author change IDs or canonical references; Python maps the judgments to trusted references.",
        ],
    }
    return (
        {
            "role": "system",
            "content": (
                "You are the configured Director. Classify every supplied "
                "suggested change semantically. Python owns canonical references "
                "and protocol structure. Return only the requested semantic JSON "
                "without Markdown fences."
            ),
        },
        {"role": "user", "content": json.dumps(content, sort_keys=True)},
    )


def render_overall_synthesis_messages(
    frozen_request: str,
    *,
    gemma_proposal: Mapping[str, Any],
    qwen_proposal: Mapping[str, Any],
    qwen_assessment: Mapping[str, Any],
    gemma_assessment: Mapping[str, Any],
    change_dispositions: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    """Ask the Director for overall synthesis judgments, not steps."""

    content = {
        "frozen_request": frozen_request,
        **_synthesis_sources(
            gemma_proposal=gemma_proposal,
            qwen_proposal=qwen_proposal,
            qwen_assessment=qwen_assessment,
            gemma_assessment=gemma_assessment,
        ),
        "validated_change_dispositions": deepcopy(dict(change_dispositions)),
        "normal_policy": normal_policy_projection(),
        "required_semantic_output": OVERALL_SYNTHESIS_SEMANTIC_SHAPE,
        "requirements": [
            "Resolve the overall goal, approach, rationale, alternatives, change summary, final decision reason, risks, and questions.",
            "Use proposal numbers 1 and 2 only when identifying rejected alternatives; Python maps them to canonical references.",
            *DIRECTOR_AUTHORITY_REQUIREMENTS,
            "Do not return steps or any Plan IDs, revisions, participants, references, statuses, timestamps, integrity fields, or other bookkeeping.",
            "Do not execute the Plan.",
        ],
    }
    return (
        {
            "role": "system",
            "content": (
                "You are the configured Director and semantic authority. Produce "
                "only the overall synthesis decisions. Python owns protocol "
                "structure and deterministic certification. Return plain JSON "
                "without Markdown fences."
            ),
        },
        {"role": "user", "content": json.dumps(content, sort_keys=True)},
    )


def render_plan_steps_messages(
    frozen_request: str,
    *,
    gemma_proposal: Mapping[str, Any],
    qwen_proposal: Mapping[str, Any],
    qwen_assessment: Mapping[str, Any],
    gemma_assessment: Mapping[str, Any],
    change_dispositions: Mapping[str, Any],
    overall_synthesis: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    """Ask the Director only for semantic Plan steps."""

    content = {
        "frozen_request": frozen_request,
        **_synthesis_sources(
            gemma_proposal=gemma_proposal,
            qwen_proposal=qwen_proposal,
            qwen_assessment=qwen_assessment,
            gemma_assessment=gemma_assessment,
        ),
        "validated_change_dispositions": deepcopy(dict(change_dispositions)),
        "validated_overall_synthesis": deepcopy(dict(overall_synthesis)),
        "required_semantic_output": PLAN_STEPS_SEMANTIC_SHAPE,
        "requirements": [
            "Author at least one semantic step with an observable expected result and pass/fail validation criteria.",
            "Each step contains only action, reason, instructions, scope_boundary, expected_result, validation, and depends_on_step_numbers.",
            "Use one-based earlier step numbers only for semantic dependencies; Python assigns trusted step IDs and references.",
            *DIRECTOR_AUTHORITY_REQUIREMENTS,
            "Do not return step IDs, target refs, critique refs, task refs, status, or other protocol bookkeeping.",
            "Do not execute the Plan.",
        ],
    }
    return (
        {
            "role": "system",
            "content": (
                "You are the configured Director and semantic authority. Produce "
                "only semantic Plan steps consistent with the validated synthesis. "
                "Python owns step IDs, references, and protocol structure. Return "
                "plain JSON without Markdown fences."
            ),
        },
        {"role": "user", "content": json.dumps(content, sort_keys=True)},
    )


def render_architecture_assessment_messages(
    *,
    candidate_plan: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    """Ask a configured assessor for violations without granting authority."""

    content = {
        "candidate_plan": deepcopy(dict(candidate_plan)),
        "frozen_architecture_invariants": list(
            FROZEN_ARCHITECTURE_INVARIANTS
        ),
        "authoritative_semantic_scope": [
            "goal",
            "approach_summary",
            "planning_cycle.decisions",
            "planning_cycle.revisions",
            "steps",
            "final",
        ],
        "required_semantic_output": ARCHITECTURE_ASSESSMENT_SEMANTIC_SHAPE,
        "rules": [
            "Assess whether the authoritative synthesized Plan meaning respects every frozen invariant.",
            "Treat proposals, critiques, and suggested changes as historical inputs, not accepted Plan meaning unless the synthesis copied them.",
            "Report only actual violations; do not invent disagreement or recommend unrelated improvements.",
            "Set compliant true only when violations is empty; otherwise set it false.",
            "Identify the affected step or field when possible, otherwise use null.",
            "You report findings only and gain no decision, correction, certification, routing, or execution authority.",
        ],
    }
    return (
        {
            "role": "system",
            "content": (
                "Assess the structurally certified candidate Plan against the "
                "frozen Benzaiten architecture invariants. You are an advisory "
                "assessor only. Return exactly compliant and violations as plain "
                "JSON without Markdown fences."
            ),
        },
        {"role": "user", "content": json.dumps(content, sort_keys=True)},
    )


def render_semantic_boundary_correction_messages(
    *,
    candidate_plan: Mapping[str, Any],
    architecture_violations: Sequence[Mapping[str, Any]],
    overall_synthesis: Mapping[str, Any],
    plan_steps: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    """Ask the Director to correct only identified architecture violations."""

    if not architecture_violations:
        raise ValueError(
            "Semantic boundary correction requires architecture violations."
        )
    content = {
        "candidate_plan": deepcopy(dict(candidate_plan)),
        "exact_architecture_violations": deepcopy(
            list(architecture_violations)
        ),
        "frozen_architecture_invariants": list(
            FROZEN_ARCHITECTURE_INVARIANTS
        ),
        "current_overall_synthesis": deepcopy(dict(overall_synthesis)),
        "current_plan_steps": deepcopy(dict(plan_steps)),
        "required_semantic_output": SEMANTIC_BOUNDARY_CORRECTION_SHAPE,
        "rules": [
            "Correct only the identified architecture violations and preserve all unaffected semantic intent.",
            "The Director specifies required semantic work and capabilities but must not resolve or return any model ID, endpoint, or host.",
            "Assign deterministic model resolution and any configured local fallback to Task Executive and configuration machinery.",
            "Do not introduce a Router, coordinator, manager, semantic escalation, dynamic scoring, adaptive routing, or frontier fallback.",
            "Return corrected overall_synthesis and plan_steps semantics only; Python rebuilds every canonical Plan field.",
            "Do not execute the Plan.",
        ],
    }
    return (
        {
            "role": "system",
            "content": (
                "You are the configured Director. Correct the candidate Plan's "
                "meaning only where the advisory assessment identified frozen "
                "architecture violations. Preserve unaffected intent. Python "
                "owns canonical reconstruction and both acceptance gates. Return "
                "plain JSON without Markdown fences."
            ),
        },
        {"role": "user", "content": json.dumps(content, sort_keys=True)},
    )


_CONFORMANCE_ISSUE_CATEGORIES = {
    "duplicate_id": "structural_conformance",
    "duplicate_value": "structural_conformance",
    "invalid_shape": "structural_conformance",
    "invalid_vocabulary": "structural_conformance",
    "required": "structural_conformance",
    "unknown_field": "structural_conformance",
    "invalid_reference": "invalid_reference",
    "reference_mismatch": "invalid_reference",
    "authority_mismatch": "protocol_integrity",
    "content_mismatch": "protocol_integrity",
    "integrity_mismatch": "protocol_integrity",
    "invalid_certification": "protocol_integrity",
    "invalid_budget": "protocol_integrity",
    "invalid_finality": "protocol_integrity",
    "invalid_index": "protocol_integrity",
    "invalid_iteration": "protocol_integrity",
    "invalid_partition": "protocol_integrity",
    "premature_execution": "protocol_integrity",
    "self_reference": "protocol_integrity",
    "value_mismatch": "protocol_integrity",
}


def render_conformance_repair_messages(
    *,
    artifact_kind: str,
    invalid_output: str,
    validation_issues: Sequence[ValidationIssue],
    valid_references: Mapping[str, Any],
    required_output: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    """Render a policy-limited repair request for any planning artifact."""

    if not validation_issues:
        raise ValueError("Conformance repair requires validation issues.")
    categories = {
        _CONFORMANCE_ISSUE_CATEGORIES.get(issue.code)
        for issue in validation_issues
    }
    if None in categories:
        raise ValueError("Validation issues include a non-conformance problem.")
    policy = conformance_repair_policy()
    allowed = set(policy.get("allowed_for", ()))
    if not categories <= allowed:
        raise ValueError("Planning policy does not allow this conformance repair.")
    content = {
        "artifact_kind": artifact_kind,
        "invalid_output": invalid_output,
        "validation_issues": [
            {
                "field": issue.field,
                "code": issue.code,
                "message": issue.message,
            }
            for issue in validation_issues
        ],
        "valid_references": deepcopy(dict(valid_references)),
        "required_output": deepcopy(dict(required_output)),
        "conformance_repair_policy": deepcopy(dict(policy)),
        "rules": [
            "Preserve the semantic intent of the invalid output.",
            "Repair only the listed conformance problems.",
            "Do not add, remove, or reinterpret semantic decisions.",
            "Use only the supplied valid IDs and references.",
        ],
    }
    return (
        {
            "role": "system",
            "content": (
                "Repair conformance of the artifact you produced. Preserve its "
                "semantic intent exactly and make no semantic change. Return "
                "only the repaired artifact as plain JSON without Markdown fences."
            ),
        },
        {"role": "user", "content": json.dumps(content, sort_keys=True)},
    )


def render_semantic_completion_messages(
    *,
    artifact_kind: str,
    incomplete_output: str,
    missing_decisions: Sequence[ValidationIssue],
    valid_references: Mapping[str, Any],
    required_output: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    """Ask the same Director to supply only omitted semantic decisions."""

    if not missing_decisions or any(
        issue.code != "missing_semantic_decision"
        for issue in missing_decisions
    ):
        raise ValueError(
            "Semantic completion requires only missing semantic decisions."
        )
    policy = semantic_completion_policy()
    content = {
        "artifact_kind": artifact_kind,
        "incomplete_output": incomplete_output,
        "missing_semantic_decisions": [
            {
                "field": issue.field,
                "code": issue.code,
                "message": issue.message,
            }
            for issue in missing_decisions
        ],
        "valid_references": deepcopy(dict(valid_references)),
        "required_output": deepcopy(dict(required_output)),
        "semantic_completion_policy": deepcopy(dict(policy)),
        "rules": [
            "Supply each listed missing semantic decision.",
            "Preserve every existing semantic decision exactly.",
            "Do not revise, reinterpret, or remove existing semantic content.",
            "Return the complete semantic artifact, including the newly supplied decisions.",
            "Use only the supplied valid IDs and references.",
        ],
    }
    return (
        {
            "role": "system",
            "content": (
                "Complete only the missing semantic decisions in the artifact "
                "you produced. Preserve all existing intent. Return the complete "
                "semantic artifact as plain JSON without Markdown fences."
            ),
        },
        {"role": "user", "content": json.dumps(content, sort_keys=True)},
    )


def parse_json_object(text: str, *, stage: str) -> dict[str, Any]:
    """Normalize one allowed response envelope, then parse one JSON object."""

    if not isinstance(text, str):
        raise ValueError(f"{stage} response must be text.")

    candidate = text
    fence_match = _JSON_FENCE.fullmatch(text)
    think_match = _LEADING_THINK.fullmatch(text)
    if fence_match is not None:
        candidate = fence_match.group("body")
    elif think_match is not None:
        candidate = think_match.group("body")

    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{stage} did not return valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{stage} must return one JSON object.")
    return value


def _exact_fields(
    data: object,
    *,
    field: str,
    expected: set[str],
) -> list[ValidationIssue]:
    if not isinstance(data, Mapping):
        return [_issue(field, "invalid_shape", f"{field} must be an object.")]
    issues: list[ValidationIssue] = []
    for name in sorted(set(data) - expected):
        issues.append(_issue(
            f"{field}.{name}", "unknown_field", f"Unknown field: {name}",
        ))
    for name in sorted(expected - set(data)):
        issues.append(_issue(
            f"{field}.{name}", "required", f"Missing required field: {name}",
        ))
    return issues


def _string(value: object, field: str) -> list[ValidationIssue]:
    if not isinstance(value, str) or not value.strip():
        return [_issue(field, "invalid_shape", f"{field} must be a non-empty string.")]
    return []


def _string_list(
    value: object,
    field: str,
    *,
    nonempty: bool = False,
) -> list[ValidationIssue]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        return [_issue(field, "invalid_shape", f"{field} must be a string array.")]
    if nonempty and not value:
        return [_issue(field, "required", f"{field} cannot be empty.")]
    return []


def validate_proposal_semantics(
    semantics: object,
) -> tuple[ValidationIssue, ...]:
    """Validate model-owned proposal content before canonical assembly."""

    issues = _exact_fields(
        semantics,
        field="proposal_semantics",
        expected=set(PROPOSAL_SEMANTIC_SHAPE),
    )
    if not isinstance(semantics, Mapping):
        return tuple(issues)
    for name in ("summary", "reason"):
        issues.extend(_string(
            semantics.get(name),
            f"proposal_semantics.{name}",
        ))
    issues.extend(_string_list(
        semantics.get("main_points"),
        "proposal_semantics.main_points",
        nonempty=True,
    ))
    issues.extend(_string_list(
        semantics.get("assumptions"),
        "proposal_semantics.assumptions",
    ))
    return tuple(issues)


def assemble_proposal(
    semantics: Mapping[str, Any],
    *,
    proposal_id: str,
    author_ref: str,
) -> dict[str, Any]:
    """Combine validated semantics with trusted initial-proposal metadata."""

    return {
        "id": proposal_id,
        "iteration": 1,
        "author_ref": author_ref,
        "summary": semantics["summary"],
        "main_points": deepcopy(semantics["main_points"]),
        "reason": semantics["reason"],
        "assumptions": deepcopy(semantics["assumptions"]),
        "message_refs": [],
        "artifact_refs": [],
        "proposal_state": "candidate",
        "proposal_reason": None,
        "decided_by_ref": None,
        "decided_in_revision_ref": None,
    }


_ASSESSMENT_SUMMARY_FIELDS = (
    ("strengths", "strengths"),
    ("weaknesses", "weaknesses"),
    ("uncertainty", "uncertainty"),
    ("missing information", "missing_information"),
    ("useful questions", "useful_questions"),
    ("complementary ideas", "complementary_ideas"),
    (
        "genuine contradictions/trade-offs",
        "genuine_contradictions_or_tradeoffs",
    ),
    (
        "synthesis/improvement opportunities",
        "synthesis_or_improvement_opportunities",
    ),
)


def validate_assessment_semantics(
    semantics: object,
) -> tuple[ValidationIssue, ...]:
    """Validate model-owned constructive-assessment content."""

    issues = _exact_fields(
        semantics,
        field="assessment_semantics",
        expected=set(ASSESSMENT_SEMANTIC_SHAPE),
    )
    if not isinstance(semantics, Mapping):
        return tuple(issues)
    if semantics.get("severity") not in _plan_vocabulary()["severity"]:
        issues.append(_issue(
            "assessment_semantics.severity",
            "invalid_vocabulary",
            "Invalid assessment severity.",
        ))
    for _, field_name in _ASSESSMENT_SUMMARY_FIELDS:
        issues.extend(_string_list(
            semantics.get(field_name),
            f"assessment_semantics.{field_name}",
        ))
    changes = semantics.get("suggested_changes")
    if not isinstance(changes, list):
        issues.append(_issue(
            "assessment_semantics.suggested_changes",
            "invalid_shape",
            "suggested_changes must be an array.",
        ))
        return tuple(issues)
    expected_change_fields = {"description", "reason"}
    for index, change in enumerate(changes):
        field = f"assessment_semantics.suggested_changes[{index}]"
        issues.extend(_exact_fields(
            change,
            field=field,
            expected=expected_change_fields,
        ))
        if not isinstance(change, Mapping):
            continue
        for name in expected_change_fields:
            issues.extend(_string(change.get(name), f"{field}.{name}"))
    substantive_findings = any(
        isinstance(semantics.get(field_name), list)
        and bool(semantics[field_name])
        for _, field_name in _ASSESSMENT_SUMMARY_FIELDS
    )
    if not substantive_findings and not changes:
        issues.append(_issue(
            "assessment_semantics",
            "insufficient_content",
            "Assessment must contain at least one finding or suggested change.",
        ))
    return tuple(issues)


def assemble_assessment(
    semantics: Mapping[str, Any],
    *,
    critique_id: str,
    author_ref: str,
    target_proposal_id: str,
) -> dict[str, Any]:
    """Build canonical critique/change records from validated semantics."""

    changes = []
    for index, change in enumerate(semantics["suggested_changes"], start=1):
        changes.append({
            "id": f"{critique_id}-change-{index}",
            "author_ref": author_ref,
            "target_kind": "proposal",
            "target_ref": target_proposal_id,
            "description": change["description"],
            "reason": change["reason"],
            "proposal_state": "candidate",
            "proposal_reason": None,
            "decided_by_ref": None,
            "resolved_in_revision_ref": None,
            "message_refs": [],
            "artifact_refs": [],
        })
    summary = "; ".join(
        f"{label}: " + (
            " | ".join(semantics[field_name])
            if semantics[field_name]
            else "[]"
        )
        for label, field_name in _ASSESSMENT_SUMMARY_FIELDS
    )
    return {
        "critique": {
            "id": critique_id,
            "iteration": 2,
            "author_ref": author_ref,
            "target_kind": "proposal",
            "target_ref": target_proposal_id,
            "severity": semantics["severity"],
            "summary": summary,
            "suggested_change_refs": [item["id"] for item in changes],
            "message_refs": [],
            "artifact_refs": [],
        },
        "suggested_changes": changes,
    }


def _integer_list(
    value: object,
    field: str,
) -> list[ValidationIssue]:
    if not isinstance(value, list) or any(
        not isinstance(item, int) or isinstance(item, bool)
        for item in value
    ):
        return [_issue(
            field,
            "invalid_shape",
            f"{field} must be an integer array.",
        )]
    if len(value) != len(set(value)):
        return [_issue(
            field,
            "duplicate_value",
            f"{field} cannot contain duplicate values.",
        )]
    return []


def _missing_semantic_issue(field: str, message: str) -> ValidationIssue:
    return _issue(field, "missing_semantic_decision", message)


def validate_change_disposition_semantics(
    semantics: object,
    *,
    suggested_change_count: int,
) -> tuple[ValidationIssue, ...]:
    """Validate exact-once Director dispositions without inventing omissions."""

    field = "change_disposition_semantics"
    if not isinstance(semantics, Mapping):
        return tuple(_exact_fields(
            semantics,
            field=field,
            expected=set(CHANGE_DISPOSITION_SEMANTIC_SHAPE),
        ))
    issues = [
        issue
        for issue in _exact_fields(
            semantics,
            field=field,
            expected=set(CHANGE_DISPOSITION_SEMANTIC_SHAPE),
        )
        if issue.code != "required"
    ]
    valid_numbers = set(range(1, suggested_change_count + 1))
    if "dispositions" not in semantics:
        if valid_numbers:
            issues.extend(
                _missing_semantic_issue(
                    f"{field}.dispositions[change_number={number}]",
                    f"Suggested change {number} has no semantic disposition.",
                )
                for number in sorted(valid_numbers)
            )
        else:
            issues.append(_issue(
                f"{field}.dispositions",
                "required",
                "Missing required field: dispositions",
            ))
        return tuple(issues)

    dispositions = semantics.get("dispositions")
    if not isinstance(dispositions, list):
        issues.append(_issue(
            f"{field}.dispositions",
            "invalid_shape",
            "dispositions must be an array.",
        ))
        return tuple(issues)

    covered: set[int] = set()
    seen: set[int] = set()
    for index, item in enumerate(dispositions):
        item_field = f"{field}.dispositions[{index}]"
        item_issues = _exact_fields(
            item,
            field=item_field,
            expected={"change_number", "disposition"},
        )
        if isinstance(item, Mapping) and "disposition" not in item:
            item_issues = [
                issue
                for issue in item_issues
                if issue.field != f"{item_field}.disposition"
            ]
        issues.extend(item_issues)
        if not isinstance(item, Mapping):
            continue
        number = item.get("change_number")
        if not isinstance(number, int) or isinstance(number, bool):
            issues.append(_issue(
                f"{item_field}.change_number",
                "invalid_shape",
                "change_number must be an integer.",
            ))
            continue
        if number not in valid_numbers:
            issues.append(_issue(
                f"{item_field}.change_number",
                "invalid_reference",
                "change_number must identify a supplied suggested change.",
            ))
            continue
        if number in seen:
            issues.append(_issue(
                f"{item_field}.change_number",
                "duplicate_value",
                "Each supplied suggested change may appear only once.",
            ))
        seen.add(number)
        disposition = item.get("disposition")
        if disposition is None:
            continue
        if disposition not in {"accepted", "rejected", "deferred"}:
            issues.append(_issue(
                f"{item_field}.disposition",
                "invalid_vocabulary",
                "disposition must be accepted, rejected, or deferred.",
            ))
            continue
        covered.add(number)

    issues.extend(
        _missing_semantic_issue(
            f"{field}.dispositions[change_number={number}]",
            f"Suggested change {number} has no semantic disposition.",
        )
        for number in sorted(valid_numbers - covered)
    )
    return tuple(issues)


def change_disposition_numbers(
    semantics: Mapping[str, Any],
    *,
    suggested_change_count: int,
) -> dict[str, list[int]]:
    """Group complete semantic dispositions for canonical reference mapping."""

    issues = validate_change_disposition_semantics(
        semantics,
        suggested_change_count=suggested_change_count,
    )
    if issues:
        raise ValueError("Cannot map incomplete or invalid change dispositions.")
    grouped = {
        "accepted_change_numbers": [],
        "rejected_change_numbers": [],
        "deferred_change_numbers": [],
    }
    for item in semantics["dispositions"]:
        grouped[f"{item['disposition']}_change_numbers"].append(
            item["change_number"]
        )
    return grouped


def validate_overall_synthesis_semantics(
    semantics: object,
) -> tuple[ValidationIssue, ...]:
    """Validate the Director's overall synthesis semantic unit."""

    field = "overall_synthesis_semantics"
    if not isinstance(semantics, Mapping):
        return tuple(_exact_fields(
            semantics,
            field=field,
            expected=set(OVERALL_SYNTHESIS_SEMANTIC_SHAPE),
        ))
    issues = [
        issue
        for issue in _exact_fields(
            semantics,
            field=field,
            expected=set(OVERALL_SYNTHESIS_SEMANTIC_SHAPE),
        )
        if issue.code != "required"
    ]
    for name in sorted(set(OVERALL_SYNTHESIS_SEMANTIC_SHAPE) - set(semantics)):
        issues.append(_missing_semantic_issue(
            f"{field}.{name}",
            f"Overall synthesis omitted the required semantic decision: {name}.",
        ))
    for name in ("goal", "decision_rationale", "decision_reason"):
        if name in semantics:
            issues.extend(_string(semantics[name], f"{field}.{name}"))
    for name, nonempty in (
        ("approach_summary", True),
        ("change_summary", True),
        ("unresolved_risks", False),
        ("unresolved_questions", False),
    ):
        if name in semantics:
            issues.extend(_string_list(
                semantics[name],
                f"{field}.{name}",
                nonempty=nonempty,
            ))

    if "rejected_alternatives" not in semantics:
        return tuple(issues)
    alternatives = semantics["rejected_alternatives"]
    if not isinstance(alternatives, list):
        issues.append(_issue(
            f"{field}.rejected_alternatives",
            "invalid_shape",
            "rejected_alternatives must be an array.",
        ))
        return tuple(issues)
    for index, alternative in enumerate(alternatives):
        alternative_field = f"{field}.rejected_alternatives[{index}]"
        issues.extend(_exact_fields(
            alternative,
            field=alternative_field,
            expected={"proposal_number", "reason"},
        ))
        if not isinstance(alternative, Mapping):
            continue
        if alternative.get("proposal_number") not in {1, 2}:
            issues.append(_issue(
                f"{alternative_field}.proposal_number",
                "invalid_reference",
                "proposal_number must be 1 or 2.",
            ))
        issues.extend(_string(
            alternative.get("reason"),
            f"{alternative_field}.reason",
        ))
    return tuple(issues)


def validate_plan_steps_semantics(
    semantics: object,
) -> tuple[ValidationIssue, ...]:
    """Validate Director-authored semantic steps before Plan assembly."""

    field = "plan_steps_semantics"
    if not isinstance(semantics, Mapping):
        return tuple(_exact_fields(
            semantics,
            field=field,
            expected=set(PLAN_STEPS_SEMANTIC_SHAPE),
        ))
    issues = [
        issue
        for issue in _exact_fields(
            semantics,
            field=field,
            expected=set(PLAN_STEPS_SEMANTIC_SHAPE),
        )
        if issue.code != "required"
    ]
    if "steps" not in semantics:
        issues.append(_missing_semantic_issue(
            f"{field}.steps",
            "Plan synthesis omitted all required semantic steps.",
        ))
        return tuple(issues)
    steps = semantics["steps"]
    if not isinstance(steps, list):
        issues.append(_issue(
            f"{field}.steps",
            "invalid_shape",
            "steps must be an array.",
        ))
        return tuple(issues)
    if not steps:
        issues.append(_missing_semantic_issue(
            f"{field}.steps",
            "Plan synthesis requires at least one semantic step.",
        ))
        return tuple(issues)

    expected_fields = set(PLAN_STEPS_SEMANTIC_SHAPE["steps"][0])
    for index, step in enumerate(steps, start=1):
        step_field = f"{field}.steps[{index - 1}]"
        step_issues = _exact_fields(
            step,
            field=step_field,
            expected=expected_fields,
        )
        issues.extend(
            issue for issue in step_issues if issue.code != "required"
        )
        if not isinstance(step, Mapping):
            continue
        for name in sorted(expected_fields - set(step)):
            issues.append(_missing_semantic_issue(
                f"{step_field}.{name}",
                f"Step {index} omitted required semantic content: {name}.",
            ))
        for name in (
            "action", "reason", "scope_boundary", "expected_result"
        ):
            if name in step:
                issues.extend(_string(step[name], f"{step_field}.{name}"))
        for name in ("instructions", "validation"):
            if name in step:
                issues.extend(_string_list(
                    step[name],
                    f"{step_field}.{name}",
                    nonempty=True,
                ))
        if "depends_on_step_numbers" not in step:
            continue
        dependencies = step["depends_on_step_numbers"]
        issues.extend(_integer_list(
            dependencies,
            f"{step_field}.depends_on_step_numbers",
        ))
        if isinstance(dependencies, list) and any(
            not isinstance(item, int)
            or isinstance(item, bool)
            or item < 1
            or item >= index
            for item in dependencies
        ):
            issues.append(_issue(
                f"{step_field}.depends_on_step_numbers",
                "invalid_reference",
                "Dependencies must use one-based numbers of earlier steps.",
            ))
    return tuple(issues)


def validate_architecture_assessment_semantics(
    semantics: object,
) -> tuple[ValidationIssue, ...]:
    """Validate an advisory assessment without interpreting Plan meaning."""

    field = "architecture_assessment_semantics"
    expected = set(ARCHITECTURE_ASSESSMENT_SEMANTIC_SHAPE)
    if not isinstance(semantics, Mapping):
        return tuple(_exact_fields(semantics, field=field, expected=expected))
    issues = [
        issue
        for issue in _exact_fields(semantics, field=field, expected=expected)
        if issue.code != "required"
    ]
    for name in sorted(expected - set(semantics)):
        issues.append(_missing_semantic_issue(
            f"{field}.{name}",
            f"Architecture assessment omitted required judgment: {name}.",
        ))
    if "compliant" in semantics and not isinstance(
        semantics["compliant"], bool
    ):
        issues.append(_issue(
            f"{field}.compliant",
            "invalid_shape",
            "compliant must be a boolean.",
        ))
    if "violations" not in semantics:
        return tuple(issues)
    violations = semantics["violations"]
    if not isinstance(violations, list):
        issues.append(_issue(
            f"{field}.violations",
            "invalid_shape",
            "violations must be an array.",
        ))
        return tuple(issues)
    for index, violation in enumerate(violations):
        violation_field = f"{field}.violations[{index}]"
        issues.extend(_exact_fields(
            violation,
            field=violation_field,
            expected={"finding", "affected_step_or_field"},
        ))
        if not isinstance(violation, Mapping):
            continue
        issues.extend(_string(
            violation.get("finding"),
            f"{violation_field}.finding",
        ))
        affected = violation.get("affected_step_or_field")
        if affected is not None:
            issues.extend(_string(
                affected,
                f"{violation_field}.affected_step_or_field",
            ))
    compliant = semantics.get("compliant")
    if compliant is True and violations:
        issues.append(_issue(
            field,
            "invalid_partition",
            "A compliant assessment cannot contain violations.",
        ))
    if compliant is False and not violations:
        issues.append(_missing_semantic_issue(
            f"{field}.violations",
            "A noncompliant assessment must identify at least one violation.",
        ))
    return tuple(issues)


def validate_semantic_boundary_correction_semantics(
    semantics: object,
) -> tuple[ValidationIssue, ...]:
    """Validate corrected Director semantics before canonical reassembly."""

    field = "semantic_boundary_correction"
    expected = set(SEMANTIC_BOUNDARY_CORRECTION_SHAPE)
    if not isinstance(semantics, Mapping):
        return tuple(_exact_fields(semantics, field=field, expected=expected))
    issues = [
        issue
        for issue in _exact_fields(semantics, field=field, expected=expected)
        if issue.code != "required"
    ]
    for name in sorted(expected - set(semantics)):
        issues.append(_missing_semantic_issue(
            f"{field}.{name}",
            f"Boundary correction omitted required semantics: {name}.",
        ))
    if "overall_synthesis" in semantics:
        issues.extend(validate_overall_synthesis_semantics(
            semantics["overall_synthesis"]
        ))
    if "plan_steps" in semantics:
        issues.extend(validate_plan_steps_semantics(semantics["plan_steps"]))
    return tuple(issues)


def combine_synthesis_semantics(
    change_dispositions: Mapping[str, Any],
    overall_synthesis: Mapping[str, Any],
    plan_steps: Mapping[str, Any],
    *,
    suggested_change_count: int,
) -> dict[str, Any]:
    """Combine validated semantic units without adding semantic content."""

    grouped = change_disposition_numbers(
        change_dispositions,
        suggested_change_count=suggested_change_count,
    )
    return {
        **deepcopy(dict(overall_synthesis)),
        **grouped,
        **deepcopy(dict(plan_steps)),
    }

def assemble_final_plan(
    semantics: Mapping[str, Any],
    *,
    plan_id: str,
    current_work_ref: str,
    director_ref: str,
    proposals: Sequence[Mapping[str, Any]],
    assessments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the canonical Plan while preserving model semantic choices."""

    plan = deepcopy(dict(_plan_template()))
    revision_ref = f"{plan_id}@r1"
    decided_at = datetime.now(timezone.utc).isoformat()
    critiques = [item["critique"] for item in assessments]
    changes = [
        change
        for item in assessments
        for change in item["suggested_changes"]
    ]

    def change_refs(field: str) -> list[str]:
        return [
            changes[number - 1]["id"]
            for number in semantics[field]
        ]

    plan.update({
        "plan_id": plan_id,
        "revision": 1,
        "revision_ref": revision_ref,
        "based_on_revision_ref": None,
        "parent_plan_ref": None,
        "status": "final",
        "goal": semantics["goal"],
        "approach_summary": deepcopy(semantics["approach_summary"]),
        "current_work_ref": current_work_ref,
        "participants": {
            "proposers": [item["author_ref"] for item in proposals],
            "supporters": [],
            "critics": [item["author_ref"] for item in critiques],
            "synthesizer": director_ref,
            "decision_maker": director_ref,
            "arbiter": None,
        },
        "process": {
            "mode": "synthesis",
            "iteration": {"current": 3, "maximum": 3},
            "stop_criteria": {
                "implemented": False,
                "description": (
                    "Fixed Normal V0 convergence after validated synthesis."
                ),
            },
        },
    })
    plan["planning_cycle"] = {
        "proposals": deepcopy(list(proposals)),
        "support": [],
        "critiques": deepcopy(critiques),
        "suggested_changes": deepcopy(changes),
        "decisions": [{
            "id": f"{plan_id}:decision-finalize",
            "iteration": 3,
            "author_ref": director_ref,
            "type": "finalize",
            "target_refs": [item["id"] for item in proposals],
            "rationale": semantics["decision_rationale"],
            "accepted_change_refs": change_refs("accepted_change_numbers"),
            "rejected_change_refs": change_refs("rejected_change_numbers"),
            "deferred_change_refs": change_refs("deferred_change_numbers"),
            "rejected_alternatives": [
                {
                    "target_ref": proposals[item["proposal_number"] - 1]["id"],
                    "reason": item["reason"],
                }
                for item in semantics["rejected_alternatives"]
            ],
            "resulting_revision_ref": revision_ref,
            "message_refs": [],
            "artifact_refs": [],
        }],
        "revisions": [{
            "revision_ref": revision_ref,
            "based_on_revision_ref": None,
            "author_ref": director_ref,
            "source_proposal_refs": [item["id"] for item in proposals],
            "source_support_refs": [],
            "source_critique_refs": [item["id"] for item in critiques],
            "source_change_refs": [item["id"] for item in changes],
            "change_summary": deepcopy(semantics["change_summary"]),
            "created_at": decided_at,
        }],
    }
    step_ids = [
        f"{revision_ref}:step-{index}"
        for index in range(1, len(semantics["steps"]) + 1)
    ]
    plan["steps"] = [
        {
            "index": index,
            "id": step_ids[index - 1],
            "action": step["action"],
            "reason": step["reason"],
            "target_ref": current_work_ref,
            "instructions": deepcopy(step["instructions"]),
            "scope_boundary": step["scope_boundary"],
            "expected_result": step["expected_result"],
            "validation": deepcopy(step["validation"]),
            "depends_on": [
                step_ids[number - 1]
                for number in step["depends_on_step_numbers"]
            ],
            "support_refs": [],
            "critique_refs": [item["id"] for item in critiques],
            "task_ref": None,
            "status": "proposed",
        }
        for index, step in enumerate(semantics["steps"], start=1)
    ]
    plan["final"] = {
        "is_final": True,
        "selected_revision_ref": revision_ref,
        "decision_maker_ref": director_ref,
        "decision_reason": semantics["decision_reason"],
        "unresolved_risks": deepcopy(semantics["unresolved_risks"]),
        "unresolved_questions": deepcopy(semantics["unresolved_questions"]),
        "decided_at": decided_at,
    }
    plan["integrity"]["validation"] = {
        "status": "pending",
        "validated_by_ref": None,
        "validated_at": None,
        "errors": [],
    }
    return plan


def validate_proposal(
    proposal: object,
    *,
    expected_author: str,
    expected_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate one Plan-protocol proposal contribution."""

    expected = set(_plan_template()["planning_cycle"]["proposals"][0])
    issues = _exact_fields(proposal, field="proposal", expected=expected)
    if not isinstance(proposal, Mapping):
        return tuple(issues)
    for name in ("id", "author_ref", "summary", "reason"):
        issues.extend(_string(proposal.get(name), f"proposal.{name}"))
    for name in ("main_points", "assumptions", "message_refs", "artifact_refs"):
        issues.extend(_string_list(
            proposal.get(name), f"proposal.{name}", nonempty=name == "main_points",
        ))
    if proposal.get("id") != expected_id:
        issues.append(_issue("proposal.id", "reference_mismatch", "Unexpected proposal ID."))
    if proposal.get("author_ref") != expected_author:
        issues.append(_issue("proposal.author_ref", "reference_mismatch", "Unexpected proposal author."))
    if proposal.get("iteration") != 1:
        issues.append(_issue("proposal.iteration", "invalid_iteration", "Initial proposal iteration must be 1."))
    if proposal.get("proposal_state") not in _plan_vocabulary()["proposal_state"]:
        issues.append(_issue("proposal.proposal_state", "invalid_vocabulary", "Invalid proposal state."))
    for name in ("proposal_reason", "decided_by_ref", "decided_in_revision_ref"):
        if proposal.get(name) is not None:
            issues.extend(_string(proposal.get(name), f"proposal.{name}"))
    return tuple(issues)


def validate_assessment(
    assessment: object,
    *,
    expected_author: str,
    expected_target: str,
    expected_id: str,
) -> tuple[ValidationIssue, ...]:
    """Validate one constructive assessment in existing critique fields."""

    issues = _exact_fields(
        assessment,
        field="assessment",
        expected={"critique", "suggested_changes"},
    )
    if not isinstance(assessment, Mapping):
        return tuple(issues)
    critique = assessment.get("critique")
    critique_fields = set(_plan_template()["planning_cycle"]["critiques"][0])
    issues.extend(_exact_fields(
        critique, field="assessment.critique", expected=critique_fields,
    ))
    if isinstance(critique, Mapping):
        for name in ("id", "author_ref", "target_kind", "target_ref", "severity", "summary"):
            issues.extend(_string(critique.get(name), f"assessment.critique.{name}"))
        for name in ("suggested_change_refs", "message_refs", "artifact_refs"):
            issues.extend(_string_list(
                critique.get(name), f"assessment.critique.{name}",
            ))
        expected_values = {
            "id": expected_id,
            "iteration": 2,
            "author_ref": expected_author,
            "target_kind": "proposal",
            "target_ref": expected_target,
        }
        for name, expected_value in expected_values.items():
            if critique.get(name) != expected_value:
                issues.append(_issue(
                    f"assessment.critique.{name}", "reference_mismatch",
                    f"Expected {expected_value!r}.",
                ))
        if critique.get("severity") not in _plan_vocabulary()["severity"]:
            issues.append(_issue(
                "assessment.critique.severity", "invalid_vocabulary",
                "Invalid critique severity.",
            ))
        summary = critique.get("summary")
        if isinstance(summary, str):
            lowered = summary.lower()
            for criterion in ASSESSMENT_CRITERIA:
                if criterion not in lowered:
                    issues.append(_issue(
                        "assessment.critique.summary", "missing_section",
                        f"Missing constructive assessment section: {criterion}",
                    ))

    changes = assessment.get("suggested_changes")
    if not isinstance(changes, list):
        issues.append(_issue(
            "assessment.suggested_changes", "invalid_shape",
            "suggested_changes must be an array.",
        ))
        return tuple(issues)
    change_fields = set(_plan_template()["planning_cycle"]["suggested_changes"][0])
    change_ids: set[str] = set()
    for index, change in enumerate(changes):
        field = f"assessment.suggested_changes[{index}]"
        issues.extend(_exact_fields(change, field=field, expected=change_fields))
        if not isinstance(change, Mapping):
            continue
        for name in ("id", "author_ref", "target_kind", "target_ref", "description", "reason", "proposal_state"):
            issues.extend(_string(change.get(name), f"{field}.{name}"))
        for name in ("message_refs", "artifact_refs"):
            issues.extend(_string_list(change.get(name), f"{field}.{name}"))
        if change.get("author_ref") != expected_author or change.get("target_ref") != expected_target or change.get("target_kind") != "proposal":
            issues.append(_issue(field, "reference_mismatch", "Suggested change must target the assessed proposal and author."))
        if change.get("proposal_state") not in _plan_vocabulary()["proposal_state"]:
            issues.append(_issue(f"{field}.proposal_state", "invalid_vocabulary", "Invalid proposal state."))
        change_id = change.get("id")
        if isinstance(change_id, str):
            if change_id in change_ids:
                issues.append(_issue(f"{field}.id", "duplicate_id", "Duplicate suggested-change ID."))
            change_ids.add(change_id)
        for name in ("proposal_reason", "decided_by_ref", "resolved_in_revision_ref"):
            if change.get(name) is not None:
                issues.extend(_string(change.get(name), f"{field}.{name}"))
    if isinstance(critique, Mapping):
        refs = critique.get("suggested_change_refs")
        if isinstance(refs, list) and set(refs) != change_ids:
            issues.append(_issue(
                "assessment.critique.suggested_change_refs", "reference_mismatch",
                "Critique suggested_change_refs must exactly reference its changes.",
            ))
    return tuple(issues)


def _validate_cycle_records(
    plan: Mapping[str, Any],
    *,
    director_ref: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    cycle = plan.get("planning_cycle")
    if not isinstance(cycle, Mapping):
        return issues
    collections = (
        "proposals", "support", "critiques", "suggested_changes", "decisions"
    )
    seen_ids: set[str] = set()
    for collection in collections:
        records = cycle.get(collection)
        if not isinstance(records, list):
            continue
        for index, record in enumerate(records):
            field = f"plan.planning_cycle.{collection}[{index}]"
            if not isinstance(record, Mapping):
                issues.append(_issue(
                    field, "invalid_shape", f"{field} must be an object."
                ))
                continue
            record_id = record.get("id")
            issues.extend(_string(record_id, f"{field}.id"))
            if isinstance(record_id, str):
                if record_id in seen_ids:
                    issues.append(_issue(
                        f"{field}.id", "duplicate_id",
                        "Planning-cycle IDs must be globally unique.",
                    ))
                seen_ids.add(record_id)

    known_proposals = {
        item.get("id") for item in cycle.get("proposals", [])
        if isinstance(item, Mapping)
    }
    known_critiques = {
        item.get("id") for item in cycle.get("critiques", [])
        if isinstance(item, Mapping)
    }
    known_changes = {
        item.get("id") for item in cycle.get("suggested_changes", [])
        if isinstance(item, Mapping)
    }
    known_support = {
        item.get("id") for item in cycle.get("support", [])
        if isinstance(item, Mapping)
    }
    known_steps = {
        item.get("id") for item in plan.get("steps", [])
        if isinstance(item, Mapping)
    }
    revision_ref = plan.get("revision_ref")
    known_revisions = {
        item.get("revision_ref") for item in cycle.get("revisions", [])
        if isinstance(item, Mapping)
    }
    known_targets = known_proposals | known_steps | known_revisions | {
        revision_ref
    }

    decision_fields = set(
        _plan_template()["planning_cycle"]["decisions"][0]
    )
    decision_types = {
        "select_proposal", "request_revision", "finalize", "defer", "abort"
    }
    for index, decision in enumerate(cycle.get("decisions", [])):
        field = f"plan.planning_cycle.decisions[{index}]"
        issues.extend(_exact_fields(
            decision, field=field, expected=decision_fields
        ))
        if not isinstance(decision, Mapping):
            continue
        if decision.get("author_ref") != director_ref:
            issues.append(_issue(
                f"{field}.author_ref", "authority_mismatch",
                "Only the configured Director may author synthesis decisions.",
            ))
        if decision.get("type") not in decision_types:
            issues.append(_issue(
                f"{field}.type", "invalid_vocabulary",
                "Invalid decision type.",
            ))
        issues.extend(_string(decision.get("rationale"), f"{field}.rationale"))
        for name, known in (
            ("target_refs", known_targets),
            ("accepted_change_refs", known_changes),
            ("rejected_change_refs", known_changes),
            ("deferred_change_refs", known_changes),
        ):
            value = decision.get(name)
            issues.extend(_string_list(value, f"{field}.{name}"))
            if isinstance(value, list) and any(ref not in known for ref in value):
                issues.append(_issue(
                    f"{field}.{name}", "invalid_reference",
                    f"{name} contains an unknown reference.",
                ))
        for name in ("message_refs", "artifact_refs"):
            issues.extend(_string_list(decision.get(name), f"{field}.{name}"))

    revision_fields = set(
        _plan_template()["planning_cycle"]["revisions"][0]
    )
    for index, revision in enumerate(cycle.get("revisions", [])):
        field = f"plan.planning_cycle.revisions[{index}]"
        issues.extend(_exact_fields(
            revision, field=field, expected=revision_fields
        ))
        if not isinstance(revision, Mapping):
            continue
        for name, known in (
            ("source_proposal_refs", known_proposals),
            ("source_support_refs", known_support),
            ("source_critique_refs", known_critiques),
            ("source_change_refs", known_changes),
        ):
            value = revision.get(name)
            issues.extend(_string_list(value, f"{field}.{name}"))
            if isinstance(value, list) and any(ref not in known for ref in value):
                issues.append(_issue(
                    f"{field}.{name}", "invalid_reference",
                    f"{name} contains an unknown reference.",
                ))
        issues.extend(_string_list(
            revision.get("change_summary"),
            f"{field}.change_summary",
            nonempty=True,
        ))
        issues.extend(_string(revision.get("created_at"), f"{field}.created_at"))
    return issues


def _validate_plan_steps(plan: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        return [_issue("steps", "required", "Final Plan requires at least one step.")]
    expected_fields = set(_plan_template()["steps"][0])
    ids: list[str] = []
    critique_ids = {
        item.get("id") for item in plan.get("planning_cycle", {}).get("critiques", [])
        if isinstance(item, Mapping)
    }
    support_ids = {
        item.get("id") for item in plan.get("planning_cycle", {}).get("support", [])
        if isinstance(item, Mapping)
    }
    for index, step in enumerate(steps, start=1):
        field = f"steps[{index - 1}]"
        issues.extend(_exact_fields(step, field=field, expected=expected_fields))
        if not isinstance(step, Mapping):
            continue
        if step.get("index") != index:
            issues.append(_issue(f"{field}.index", "invalid_index", "Step indexes must be contiguous from 1."))
        for name in ("id", "action", "reason", "target_ref", "scope_boundary", "expected_result"):
            issues.extend(_string(step.get(name), f"{field}.{name}"))
        for name in ("instructions", "validation"):
            issues.extend(_string_list(step.get(name), f"{field}.{name}", nonempty=True))
        for name in ("depends_on", "support_refs", "critique_refs"):
            issues.extend(_string_list(step.get(name), f"{field}.{name}"))
        step_id = step.get("id")
        if isinstance(step_id, str):
            if step_id in ids:
                issues.append(_issue(f"{field}.id", "duplicate_id", "Step IDs must be unique."))
            ids.append(step_id)
        dependencies = step.get("depends_on")
        if isinstance(dependencies, list) and any(ref not in ids[:-1] for ref in dependencies):
            issues.append(_issue(f"{field}.depends_on", "invalid_reference", "Dependencies must reference earlier steps."))
        if isinstance(step.get("critique_refs"), list) and any(ref not in critique_ids for ref in step["critique_refs"]):
            issues.append(_issue(f"{field}.critique_refs", "invalid_reference", "Unknown critique reference."))
        if isinstance(step.get("support_refs"), list) and any(ref not in support_ids for ref in step["support_refs"]):
            issues.append(_issue(f"{field}.support_refs", "invalid_reference", "Unknown support reference."))
        if step.get("task_ref") is not None:
            issues.append(_issue(f"{field}.task_ref", "premature_execution", "Iteration 2 Plan must not contain DirectorTask references."))
        if step.get("status") not in _plan_vocabulary()["step_status"]:
            issues.append(_issue(f"{field}.status", "invalid_vocabulary", "Invalid step status."))
    return issues


def validate_final_plan(
    plan: object,
    *,
    plan_id: str,
    current_work_ref: str,
    director_ref: str,
    proposals: Sequence[Mapping[str, Any]],
    assessments: Sequence[Mapping[str, Any]],
    require_pending_validation: bool = False,
) -> tuple[ValidationIssue, ...]:
    """Validate final Plan structure, vocabulary, IDs, references, and integrity."""

    expected_top = set(_plan_template())
    issues = _exact_fields(plan, field="plan", expected=expected_top)
    if not isinstance(plan, Mapping):
        return tuple(issues)
    revision_ref = f"{plan_id}@r1"
    expected_scalars = {
        "plan_id": plan_id,
        "revision": 1,
        "revision_ref": revision_ref,
        "based_on_revision_ref": None,
        "status": "final",
        "current_work_ref": current_work_ref,
    }
    for name, expected_value in expected_scalars.items():
        if plan.get(name) != expected_value:
            issues.append(_issue(f"plan.{name}", "value_mismatch", f"Expected {expected_value!r}."))
    if plan.get("parent_plan_ref") == plan_id:
        issues.append(_issue("plan.parent_plan_ref", "self_reference", "Plan cannot parent itself."))
    issues.extend(_string(plan.get("goal"), "plan.goal"))
    issues.extend(_string_list(plan.get("approach_summary"), "plan.approach_summary", nonempty=True))
    if plan.get("status") not in _plan_vocabulary()["plan_status"]:
        issues.append(_issue("plan.status", "invalid_vocabulary", "Invalid Plan status."))

    participants = plan.get("participants")
    participant_fields = set(_plan_template()["participants"])
    issues.extend(_exact_fields(participants, field="plan.participants", expected=participant_fields))
    if isinstance(participants, Mapping):
        for name in ("proposers", "supporters", "critics"):
            issues.extend(_string_list(participants.get(name), f"plan.participants.{name}"))
        if set(participants.get("proposers", [])) != {item["author_ref"] for item in proposals}:
            issues.append(_issue("plan.participants.proposers", "reference_mismatch", "Both proposal authors must be listed."))
        if set(participants.get("critics", [])) != {item["critique"]["author_ref"] for item in assessments}:
            issues.append(_issue("plan.participants.critics", "reference_mismatch", "Both assessment authors must be listed."))
        if participants.get("synthesizer") != director_ref or participants.get("decision_maker") != director_ref:
            issues.append(_issue("plan.participants", "authority_mismatch", "Configured Director must synthesize and decide."))

    process = plan.get("process")
    issues.extend(_exact_fields(process, field="plan.process", expected=set(_plan_template()["process"])))
    if isinstance(process, Mapping):
        if process.get("mode") != "synthesis" or process.get("mode") not in _plan_vocabulary()["planning_mode"]:
            issues.append(_issue("plan.process.mode", "invalid_vocabulary", "Final Normal Plan mode must be synthesis."))
        iteration = process.get("iteration")
        if not isinstance(iteration, Mapping) or iteration.get("current") != 3 or iteration.get("maximum") != 3:
            issues.append(_issue("plan.process.iteration", "invalid_budget", "Final Normal Plan iteration must be 3 of 3."))

    cycle = plan.get("planning_cycle")
    cycle_fields = set(_plan_template()["planning_cycle"])
    issues.extend(_exact_fields(cycle, field="plan.planning_cycle", expected=cycle_fields))
    if isinstance(cycle, Mapping):
        if cycle.get("proposals") != list(proposals):
            issues.append(_issue("plan.planning_cycle.proposals", "content_mismatch", "Synthesis must preserve both validated proposals."))
        expected_critiques = [item["critique"] for item in assessments]
        expected_changes = [change for item in assessments for change in item["suggested_changes"]]
        if cycle.get("critiques") != expected_critiques:
            issues.append(_issue("plan.planning_cycle.critiques", "content_mismatch", "Synthesis must preserve both validated assessments."))
        if cycle.get("suggested_changes") != expected_changes:
            issues.append(_issue("plan.planning_cycle.suggested_changes", "content_mismatch", "Synthesis must preserve assessment changes."))
        for name in ("support", "decisions", "revisions"):
            if not isinstance(cycle.get(name), list):
                issues.append(_issue(f"plan.planning_cycle.{name}", "invalid_shape", f"{name} must be an array."))
        decisions = cycle.get("decisions")
        if not isinstance(decisions, list) or not decisions:
            issues.append(_issue("plan.planning_cycle.decisions", "required", "Director synthesis requires a decision record."))
        elif not any(
            isinstance(item, Mapping)
            and item.get("author_ref") == director_ref
            and item.get("type") == "finalize"
            and item.get("resulting_revision_ref") == revision_ref
            for item in decisions
        ):
            issues.append(_issue("plan.planning_cycle.decisions", "authority_mismatch", "Director finalize decision is required."))
        revisions = cycle.get("revisions")
        if not isinstance(revisions, list) or not any(
            isinstance(item, Mapping)
            and item.get("revision_ref") == revision_ref
            and item.get("author_ref") == director_ref
            for item in revisions
        ):
            issues.append(_issue("plan.planning_cycle.revisions", "reference_mismatch", "Current Director-authored revision is required."))

    issues.extend(_validate_cycle_records(plan, director_ref=director_ref))
    issues.extend(_validate_plan_steps(plan))
    final = plan.get("final")
    issues.extend(_exact_fields(final, field="plan.final", expected=set(_plan_template()["final"])))
    if isinstance(final, Mapping):
        if final.get("is_final") is not True or final.get("selected_revision_ref") != revision_ref:
            issues.append(_issue("plan.final", "invalid_finality", "Final Plan must select its current revision."))
        if final.get("decision_maker_ref") != director_ref:
            issues.append(_issue("plan.final.decision_maker_ref", "authority_mismatch", "Configured Director must be decision maker."))
        issues.extend(_string(final.get("decision_reason"), "plan.final.decision_reason"))
        for name in ("unresolved_risks", "unresolved_questions"):
            issues.extend(_string_list(final.get(name), f"plan.final.{name}"))
        issues.extend(_string(final.get("decided_at"), "plan.final.decided_at"))

    integrity = plan.get("integrity")
    issues.extend(_exact_fields(integrity, field="plan.integrity", expected=set(_plan_template()["integrity"])))
    if isinstance(integrity, Mapping):
        rules = integrity.get("rules")
        expected_rules = _plan_template()["integrity"]["rules"]
        if rules != expected_rules:
            issues.append(_issue("plan.integrity.rules", "integrity_mismatch", "All authoritative integrity rules must be preserved."))
        validation = integrity.get("validation")
        expected_validation_fields = set(_plan_template()["integrity"]["validation"])
        issues.extend(_exact_fields(validation, field="plan.integrity.validation", expected=expected_validation_fields))
        if isinstance(validation, Mapping):
            status = validation.get("status")
            if require_pending_validation:
                if status != "pending":
                    issues.append(_issue(
                        "plan.integrity.validation.status", "authority_mismatch",
                        "Model must leave structural validation pending.",
                    ))
                if (
                    validation.get("validated_by_ref") is not None
                    or validation.get("validated_at") is not None
                    or validation.get("errors") != []
                ):
                    issues.append(_issue(
                        "plan.integrity.validation", "authority_mismatch",
                        "Model cannot certify structural validity.",
                    ))
            elif status == "valid":
                if (
                    validation.get("validated_by_ref")
                    != "deterministic_plan_validator"
                    or not isinstance(validation.get("validated_at"), str)
                    or validation.get("errors") != []
                ):
                    issues.append(_issue(
                        "plan.integrity.validation", "invalid_certification",
                        "Valid Plan must carry deterministic certification.",
                    ))
            elif status != "pending":
                issues.append(_issue(
                    "plan.integrity.validation.status", "invalid_vocabulary",
                    "Plan validation status must be pending or valid.",
                ))
    return tuple(issues)


def certify_final_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Mark a structurally valid Plan using deterministic validator authority."""

    certified = deepcopy(dict(plan))
    certified["integrity"]["validation"] = {
        "status": "valid",
        "validated_by_ref": "deterministic_plan_validator",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "errors": [],
    }
    return certified


def validate_successor_plan_semantics(
    semantics: object,
) -> tuple[ValidationIssue, ...]:
    """Validate focused Director semantics for one successor Plan node."""

    expected = {"overall_synthesis", "plan_steps"}
    issues = _exact_fields(
        semantics, field="successor_plan_semantics", expected=expected,
    )
    if not isinstance(semantics, Mapping):
        return tuple(issues)
    issues.extend(validate_overall_synthesis_semantics(
        semantics.get("overall_synthesis")
    ))
    issues.extend(validate_plan_steps_semantics(semantics.get("plan_steps")))
    return tuple(issues)


def _accepted_checkpoint_issues(
    plan_history: Sequence[Mapping[str, Any]],
    *,
    checkpoint_revision_ref: str,
    checkpoint_outcome_ref: str | None,
    accepted_outcomes_by_ref: Mapping[str, Mapping[str, Any]],
) -> list[ValidationIssue]:
    plans_by_ref = {
        plan.get("revision_ref"): plan
        for plan in plan_history
        if isinstance(plan.get("revision_ref"), str)
    }
    checkpoint_plan = plans_by_ref.get(checkpoint_revision_ref)
    if checkpoint_plan is None:
        return [_issue(
            "checkpoint_revision_ref", "unknown_checkpoint",
            "Selected checkpoint Plan is not present in immutable history.",
        )]
    if checkpoint_outcome_ref is None:
        root_issues = validate_planning_root_checkpoint(checkpoint_plan)
        if root_issues:
            return [
                _issue(
                    "checkpoint_outcome_ref", "invalid_root_checkpoint",
                    "Only the planning-certified @r1 root may omit an ACCEPT outcome.",
                ),
                *root_issues,
            ]
        return []

    outcome = accepted_outcomes_by_ref.get(checkpoint_outcome_ref)
    if not isinstance(outcome, Mapping):
        return [_issue(
            "checkpoint_outcome_ref", "unknown_checkpoint",
            "Execution checkpoint must resolve to a real ACCEPT outcome.",
        )]
    issues: list[ValidationIssue] = []
    if outcome.get("id") != checkpoint_outcome_ref:
        issues.append(_issue(
            "checkpoint_outcome_ref", "reference_mismatch",
            "Accepted outcome identity does not match its trusted catalog key.",
        ))
    if outcome.get("decision") != "ACCEPT":
        issues.append(_issue(
            "checkpoint_outcome_ref", "not_accepted",
            "Execution checkpoint must reference an ACCEPT outcome.",
        ))
    if outcome.get("checkpoint_revision_ref") != checkpoint_revision_ref:
        issues.append(_issue(
            "checkpoint_outcome_ref", "reference_mismatch",
            "Accepted outcome does not identify the selected Plan revision.",
        ))
    return issues


def validate_successor_plan(
    plan: object,
    *,
    prior_plan_history: Sequence[Mapping[str, Any]],
    checkpoint_revision_ref: str,
    checkpoint_outcome_ref: str | None,
    accepted_outcomes_by_ref: Mapping[str, Mapping[str, Any]],
    triggering_execution_ref: str,
    triggering_outcome_ref: str,
    director_ref: str,
    require_pending_validation: bool = False,
) -> tuple[ValidationIssue, ...]:
    """Validate one immutable chronological successor against prior history."""

    issues = list(_exact_fields(
        plan, field="plan", expected=set(_plan_template()),
    ))
    if not isinstance(plan, Mapping):
        return tuple(issues)
    if not prior_plan_history:
        issues.append(_issue(
            "prior_plan_history", "required",
            "Successor validation requires immutable prior Plan history.",
        ))
        return tuple(issues)

    issues.extend(_accepted_checkpoint_issues(
        prior_plan_history,
        checkpoint_revision_ref=checkpoint_revision_ref,
        checkpoint_outcome_ref=checkpoint_outcome_ref,
        accepted_outcomes_by_ref=accepted_outcomes_by_ref,
    ))
    current = prior_plan_history[-1]
    expected_revision = len(prior_plan_history) + 1
    plan_id = prior_plan_history[0].get("plan_id")
    revision_ref = f"{plan_id}@r{expected_revision}"
    expected_scalars = {
        "plan_id": plan_id,
        "revision": expected_revision,
        "revision_ref": revision_ref,
        "based_on_revision_ref": checkpoint_revision_ref,
        "parent_plan_ref": current.get("parent_plan_ref"),
        "status": "final",
        "current_work_ref": current.get("current_work_ref"),
    }
    for name, expected_value in expected_scalars.items():
        if plan.get(name) != expected_value:
            issues.append(_issue(
                f"plan.{name}", "value_mismatch",
                f"Expected {expected_value!r}.",
            ))

    try:
        execution_transition_budget_state([
            *prior_plan_history, plan,
        ])
    except (ValueError, RuntimeError) as exc:
        issues.append(_issue(
            "plan.revision", "invalid_execution_transition", str(exc),
        ))

    if plan.get("participants") != current.get("participants"):
        issues.append(_issue(
            "plan.participants", "history_mutation",
            "Successor must preserve configured planning participants.",
        ))
    if plan.get("process") != current.get("process"):
        issues.append(_issue(
            "plan.process", "planning_state_mutation",
            "Successor must preserve the completed planning 3/3 process.",
        ))
    issues.extend(_string(plan.get("goal"), "plan.goal"))
    issues.extend(_string_list(
        plan.get("approach_summary"), "plan.approach_summary", nonempty=True,
    ))

    cycle = plan.get("planning_cycle")
    current_cycle = current.get("planning_cycle")
    if not isinstance(cycle, Mapping) or not isinstance(current_cycle, Mapping):
        issues.append(_issue(
            "plan.planning_cycle", "invalid_shape",
            "Successor and current Plan require planning_cycle objects.",
        ))
    else:
        for name in (
            "proposals", "support", "critiques", "suggested_changes",
        ):
            if cycle.get(name) != current_cycle.get(name):
                issues.append(_issue(
                    f"plan.planning_cycle.{name}", "history_mutation",
                    f"Successor must preserve prior {name} records.",
                ))
        decisions = cycle.get("decisions")
        prior_decisions = current_cycle.get("decisions")
        revisions = cycle.get("revisions")
        prior_revisions = current_cycle.get("revisions")
        if (
            not isinstance(decisions, list)
            or not isinstance(prior_decisions, list)
            or decisions[:-1] != prior_decisions
        ):
            issues.append(_issue(
                "plan.planning_cycle.decisions", "history_mutation",
                "Successor must append exactly one decision to prior history.",
            ))
        elif not decisions:
            issues.append(_issue(
                "plan.planning_cycle.decisions", "required",
                "Successor requires a Director revision decision.",
            ))
        else:
            decision = decisions[-1]
            if (
                not isinstance(decision, Mapping)
                or decision.get("author_ref") != director_ref
                or decision.get("type") != "request_revision"
                or decision.get("target_refs") != [
                    checkpoint_revision_ref
                ]
                or decision.get("resulting_revision_ref") != revision_ref
                or triggering_execution_ref
                not in decision.get("artifact_refs", [])
                or triggering_outcome_ref
                not in decision.get("artifact_refs", [])
            ):
                issues.append(_issue(
                    "plan.planning_cycle.decisions[-1]",
                    "invalid_revision_decision",
                    "Successor requires one trusted Director revision decision with triggering evidence.",
                ))
        if (
            not isinstance(revisions, list)
            or not isinstance(prior_revisions, list)
            or revisions[:-1] != prior_revisions
        ):
            issues.append(_issue(
                "plan.planning_cycle.revisions", "history_mutation",
                "Successor must append exactly one revision to prior history.",
            ))
        elif not revisions:
            issues.append(_issue(
                "plan.planning_cycle.revisions", "required",
                "Successor requires one revision record.",
            ))
        else:
            revision = revisions[-1]
            if (
                not isinstance(revision, Mapping)
                or revision.get("revision_ref") != revision_ref
                or revision.get("based_on_revision_ref")
                != checkpoint_revision_ref
                or revision.get("author_ref") != director_ref
            ):
                issues.append(_issue(
                    "plan.planning_cycle.revisions[-1]",
                    "invalid_revision_record",
                    "Successor revision record must identify its chronological node and branch parent.",
                ))
        issues.extend(_validate_cycle_records(plan, director_ref=director_ref))

    issues.extend(_validate_plan_steps(plan))
    prior_step_ids = {
        step.get("id")
        for prior in prior_plan_history
        for step in prior.get("steps", [])
        if isinstance(step, Mapping)
    }
    steps = plan.get("steps")
    if isinstance(steps, list):
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, Mapping):
                continue
            expected_step_id = f"{revision_ref}:step-{index}"
            if step.get("id") != expected_step_id:
                issues.append(_issue(
                    f"plan.steps[{index - 1}].id", "invalid_revision_step_id",
                    "Successor step ID must be qualified by the new revision.",
                ))
            if step.get("id") in prior_step_ids:
                issues.append(_issue(
                    f"plan.steps[{index - 1}].id", "reused_step_id",
                    "Successor step IDs must never reuse historical IDs.",
                ))

    final = plan.get("final")
    if (
        not isinstance(final, Mapping)
        or final.get("is_final") is not True
        or final.get("selected_revision_ref") != revision_ref
        or final.get("decision_maker_ref") != director_ref
    ):
        issues.append(_issue(
            "plan.final", "invalid_finality",
            "Successor must be a Director-decided final current revision.",
        ))

    integrity = plan.get("integrity")
    if not isinstance(integrity, Mapping):
        issues.append(_issue(
            "plan.integrity", "invalid_shape",
            "Successor must preserve Plan integrity metadata.",
        ))
    else:
        if integrity.get("rules") != _plan_template()["integrity"]["rules"]:
            issues.append(_issue(
                "plan.integrity.rules", "integrity_mismatch",
                "Successor must preserve all authoritative integrity rules.",
            ))
        validation = integrity.get("validation")
        if not isinstance(validation, Mapping):
            issues.append(_issue(
                "plan.integrity.validation", "invalid_shape",
                "Successor validation state must be an object.",
            ))
        elif require_pending_validation:
            if validation != {
                "status": "pending",
                "validated_by_ref": None,
                "validated_at": None,
                "errors": [],
            }:
                issues.append(_issue(
                    "plan.integrity.validation", "authority_mismatch",
                    "Uncertified successor must leave deterministic validation pending.",
                ))
        elif (
            validation.get("status") != "valid"
            or validation.get("validated_by_ref")
            != "deterministic_plan_validator"
            or not isinstance(validation.get("validated_at"), str)
            or not validation["validated_at"].strip()
            or validation.get("errors") != []
        ):
            issues.append(_issue(
                "plan.integrity.validation", "invalid_certification",
                "Certified successor requires trusted deterministic validation.",
            ))
    return tuple(issues)


def assemble_successor_plan(
    plan_history: Sequence[Mapping[str, Any]],
    *,
    checkpoint_revision_ref: str,
    checkpoint_outcome_ref: str | None,
    accepted_outcomes_by_ref: Mapping[str, Mapping[str, Any]],
    successor_semantics: Mapping[str, Any],
    triggering_execution_ref: str,
    triggering_outcome_ref: str,
    director_ref: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Assemble one immutable successor without mutating prior Plan nodes."""

    transition_state = execution_transition_budget_state(plan_history)
    if not transition_state["can_create_successor"]:
        raise RuntimeError("Execution-transition budget exhausted.")
    checkpoint_issues = _accepted_checkpoint_issues(
        plan_history,
        checkpoint_revision_ref=checkpoint_revision_ref,
        checkpoint_outcome_ref=checkpoint_outcome_ref,
        accepted_outcomes_by_ref=accepted_outcomes_by_ref,
    )
    semantic_issues = validate_successor_plan_semantics(successor_semantics)
    issues = [*checkpoint_issues, *semantic_issues]
    if issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in issues
        )
        raise ValueError(f"Cannot assemble successor Plan: {details}")
    for name, value in (
        ("triggering_execution_ref", triggering_execution_ref),
        ("triggering_outcome_ref", triggering_outcome_ref),
        ("director_ref", director_ref),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string.")

    current = plan_history[-1]
    plan = deepcopy(dict(current))
    overall = successor_semantics["overall_synthesis"]
    step_semantics = successor_semantics["plan_steps"]["steps"]
    revision = len(plan_history) + 1
    revision_ref = f"{plan['plan_id']}@r{revision}"
    created_at = timestamp or datetime.now(timezone.utc).isoformat()
    plan.update({
        "revision": revision,
        "revision_ref": revision_ref,
        "based_on_revision_ref": checkpoint_revision_ref,
        "status": "final",
        "goal": overall["goal"],
        "approach_summary": deepcopy(overall["approach_summary"]),
    })

    cycle = plan["planning_cycle"]
    proposals = cycle["proposals"]
    artifact_refs = [triggering_execution_ref, triggering_outcome_ref]
    if (
        checkpoint_outcome_ref is not None
        and checkpoint_outcome_ref not in artifact_refs
    ):
        artifact_refs.append(checkpoint_outcome_ref)
    cycle["decisions"].append({
        "id": f"{plan['plan_id']}:decision-revision-{revision}",
        "iteration": DEFAULT_JOB_BUDGET["semantic_iterations"],
        "author_ref": director_ref,
        "type": "request_revision",
        "target_refs": [checkpoint_revision_ref],
        "rationale": overall["decision_rationale"],
        "accepted_change_refs": [],
        "rejected_change_refs": [],
        "deferred_change_refs": [],
        "rejected_alternatives": [
            {
                "target_ref": proposals[item["proposal_number"] - 1]["id"],
                "reason": item["reason"],
            }
            for item in overall["rejected_alternatives"]
        ],
        "resulting_revision_ref": revision_ref,
        "message_refs": [],
        "artifact_refs": artifact_refs,
    })
    cycle["revisions"].append({
        "revision_ref": revision_ref,
        "based_on_revision_ref": checkpoint_revision_ref,
        "author_ref": director_ref,
        "source_proposal_refs": [],
        "source_support_refs": [],
        "source_critique_refs": [],
        "source_change_refs": [],
        "change_summary": deepcopy(overall["change_summary"]),
        "created_at": created_at,
    })

    step_ids = [
        f"{revision_ref}:step-{index}"
        for index in range(1, len(step_semantics) + 1)
    ]
    plan["steps"] = [
        {
            "index": index,
            "id": step_ids[index - 1],
            "action": step["action"],
            "reason": step["reason"],
            "target_ref": plan["current_work_ref"],
            "instructions": deepcopy(step["instructions"]),
            "scope_boundary": step["scope_boundary"],
            "expected_result": step["expected_result"],
            "validation": deepcopy(step["validation"]),
            "depends_on": [
                step_ids[number - 1]
                for number in step["depends_on_step_numbers"]
            ],
            "support_refs": [],
            "critique_refs": [],
            "task_ref": None,
            "status": "proposed",
        }
        for index, step in enumerate(step_semantics, start=1)
    ]
    plan["final"] = {
        "is_final": True,
        "selected_revision_ref": revision_ref,
        "decision_maker_ref": director_ref,
        "decision_reason": overall["decision_reason"],
        "unresolved_risks": deepcopy(overall["unresolved_risks"]),
        "unresolved_questions": deepcopy(overall["unresolved_questions"]),
        "decided_at": created_at,
    }
    plan["integrity"]["validation"] = {
        "status": "pending",
        "validated_by_ref": None,
        "validated_at": None,
        "errors": [],
    }

    validation_issues = validate_successor_plan(
        plan,
        prior_plan_history=plan_history,
        checkpoint_revision_ref=checkpoint_revision_ref,
        checkpoint_outcome_ref=checkpoint_outcome_ref,
        accepted_outcomes_by_ref=accepted_outcomes_by_ref,
        triggering_execution_ref=triggering_execution_ref,
        triggering_outcome_ref=triggering_outcome_ref,
        director_ref=director_ref,
        require_pending_validation=True,
    )
    if validation_issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in validation_issues
        )
        raise ValueError(f"Invalid assembled successor Plan: {details}")
    return plan
