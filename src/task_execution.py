"""Deterministic validation for the existing TaskExecution contract."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

from config import (
    TASK_EXECUTION_PROTOCOL_PATH,
    TASK_EXECUTION_VOCABULARY_PATH,
)
from structures import (
    ValidationIssue,
    load_json_mapping,
    load_yaml_mapping,
)


def _issue(field: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(field=field, code=code, message=message)


@lru_cache(maxsize=1)
def _template() -> Mapping[str, Any]:
    return load_json_mapping(TASK_EXECUTION_PROTOCOL_PATH)["execution"]


@lru_cache(maxsize=1)
def _vocabulary() -> Mapping[str, Any]:
    return load_yaml_mapping(TASK_EXECUTION_VOCABULARY_PATH)


def _allowed(name: str) -> frozenset[str]:
    values = _vocabulary().get(name)
    if not isinstance(values, list) or not all(
        isinstance(item, str) for item in values
    ):
        raise RuntimeError(f"Invalid TaskExecution vocabulary: {name}")
    return frozenset(values)


def _exact_fields(
    value: object,
    *,
    field: str,
    expected: set[str],
) -> list[ValidationIssue]:
    if not isinstance(value, Mapping):
        return [_issue(
            field, "invalid_shape", f"{field} must be an object.",
        )]
    issues: list[ValidationIssue] = []
    for name in sorted(set(value) - expected):
        issues.append(_issue(
            f"{field}.{name}", "unknown_field",
            f"Unknown {field} field: {name}",
        ))
    for name in sorted(expected - set(value)):
        issues.append(_issue(
            f"{field}.{name}", "required",
            f"Missing required {field} field: {name}",
        ))
    return issues


def _string(
    value: object,
    field: str,
    *,
    nullable: bool = False,
) -> list[ValidationIssue]:
    if nullable and value is None:
        return []
    if not isinstance(value, str) or not value.strip():
        return [_issue(
            field, "invalid_shape", f"{field} must be a non-empty string.",
        )]
    return []


def _string_list(value: object, field: str) -> list[ValidationIssue]:
    if not isinstance(value, list):
        return [_issue(
            field, "invalid_shape", f"{field} must be an array.",
        )]
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return [_issue(
            field, "invalid_shape",
            f"{field} must contain only non-empty strings.",
        )]
    return []


def _plan_ref_identity(value: object) -> tuple[str, int] | None:
    if not isinstance(value, str) or "@r" not in value:
        return None
    plan_id, revision_text = value.rsplit("@r", 1)
    if not plan_id or not revision_text.isdigit():
        return None
    revision = int(revision_text)
    if revision < 1:
        return None
    return plan_id, revision


def _validate_guidance(
    guidance: object,
    *,
    field: str,
) -> list[ValidationIssue]:
    template = _template()["plan_execution"]["outcomes"][0]["guidance"]
    issues = _exact_fields(
        guidance, field=field, expected=set(template),
    )
    if not isinstance(guidance, Mapping):
        return issues
    for name in (
        "hurdle", "materiality", "remaining_unresolved",
        "recommendation", "question",
    ):
        issues.extend(_string(guidance.get(name), f"{field}.{name}"))
    issues.extend(_string_list(
        guidance.get("evidence_refs"), f"{field}.evidence_refs",
    ))
    issues.extend(_string_list(
        guidance.get("options"), f"{field}.options",
    ))

    attempts = guidance.get("attempts")
    if not isinstance(attempts, list):
        issues.append(_issue(
            f"{field}.attempts", "invalid_shape",
            "Guidance attempts must be an array.",
        ))
    else:
        attempt_fields = set(template["attempts"][0])
        for index, attempt in enumerate(attempts):
            attempt_field = f"{field}.attempts[{index}]"
            issues.extend(_exact_fields(
                attempt, field=attempt_field, expected=attempt_fields,
            ))
            if not isinstance(attempt, Mapping):
                continue
            for name in ("description", "established"):
                issues.extend(_string(
                    attempt.get(name), f"{attempt_field}.{name}",
                ))
            issues.extend(_string_list(
                attempt.get("evidence_refs"),
                f"{attempt_field}.evidence_refs",
            ))

    target = guidance.get("target")
    policy = guidance.get("policy")
    authorized = guidance.get("frontier_authorized")
    if target not in _allowed("guidance_target"):
        issues.append(_issue(
            f"{field}.target", "invalid_vocabulary",
            "Guidance target must be user or frontier.",
        ))
    if policy not in _allowed("guidance_policy"):
        issues.append(_issue(
            f"{field}.policy", "invalid_vocabulary",
            "Invalid user-controlled guidance policy.",
        ))
    if not isinstance(authorized, bool):
        issues.append(_issue(
            f"{field}.frontier_authorized", "invalid_shape",
            "frontier_authorized must be boolean.",
        ))
    if target == "frontier" and authorized is not True:
        issues.append(_issue(
            f"{field}.target", "frontier_not_authorized",
            "A frontier target requires explicit user authorization.",
        ))
    if policy == "USER_ONLY" and (
        target != "user" or authorized is not False
    ):
        issues.append(_issue(
            f"{field}.policy", "policy_mismatch",
            "USER_ONLY requires a user target and no frontier authorization.",
        ))
    return issues


def validate_task_execution_terminal_profile(
    execution: object,
) -> tuple[ValidationIssue, ...]:
    """Validate terminal result/error exclusivity and artifact-record shape."""

    if not isinstance(execution, Mapping):
        return (_issue(
            "execution", "invalid_shape", "TaskExecution must be an object.",
        ),)

    control = execution.get("control")
    if not isinstance(control, Mapping):
        return (_issue(
            "control", "invalid_shape", "control must be an object.",
        ),)

    status = control.get("status")
    result = execution.get("result")
    error = execution.get("error")
    issues: list[ValidationIssue] = []

    if status == "completed":
        if not isinstance(result, Mapping):
            issues.append(_issue(
                "result", "required_for_success",
                "Completed execution must contain a result object.",
            ))
        if error is not None:
            issues.append(_issue(
                "error", "forbidden_for_success",
                "Completed execution must clear error.",
            ))
    elif status == "failed":
        if not isinstance(error, Mapping):
            issues.append(_issue(
                "error", "required_for_failure",
                "Failed execution must contain an error object.",
            ))
        if result is not None:
            issues.append(_issue(
                "result", "forbidden_for_failure",
                "Failed execution must clear result.",
            ))

    artifact_record = execution.get("artifact_record")
    if artifact_record is not None and not isinstance(artifact_record, Mapping):
        issues.append(_issue(
            "artifact_record", "invalid_shape",
            "artifact_record must be null/absent or an object.",
        ))
    return tuple(issues)


def validate_task_execution_mapping(
    execution: object,
) -> tuple[ValidationIssue, ...]:
    """Validate the full protocol-shaped TaskExecution mapping."""

    issues = list(_exact_fields(
        execution,
        field="execution",
        expected=set(_template()),
    ))
    if not isinstance(execution, Mapping):
        return tuple(issues)

    for name in ("execution_id", "task_ref", "job_ref", "output_contract_ref"):
        issues.extend(_string(execution.get(name), name))

    control = execution.get("control")
    issues.extend(_exact_fields(
        control, field="control", expected=set(_template()["control"]),
    ))
    if isinstance(control, Mapping):
        if control.get("status") not in _allowed("execution_status"):
            issues.append(_issue(
                "control.status", "invalid_vocabulary",
                "Invalid execution status.",
            ))
        if control.get("priority") not in _allowed("priority"):
            issues.append(_issue(
                "control.priority", "invalid_vocabulary",
                "Invalid execution priority.",
            ))
        attempt = control.get("attempt")
        issues.extend(_exact_fields(
            attempt,
            field="control.attempt",
            expected=set(_template()["control"]["attempt"]),
        ))
        if isinstance(attempt, Mapping):
            current = attempt.get("current")
            maximum = attempt.get("maximum")
            if (
                isinstance(current, bool)
                or not isinstance(current, int)
                or isinstance(maximum, bool)
                or not isinstance(maximum, int)
                or current < 1
                or maximum < current
            ):
                issues.append(_issue(
                    "control.attempt", "invalid_attempt",
                    "Attempt must use positive current <= maximum.",
                ))

    resolved = execution.get("resolved")
    issues.extend(_exact_fields(
        resolved, field="resolved", expected=set(_template()["resolved"]),
    ))
    if isinstance(resolved, Mapping):
        for name in ("participant_role", "logical_context", "worker_ref"):
            issues.extend(_string(
                resolved.get(name), f"resolved.{name}",
            ))
        if resolved.get("worker_kind") not in _allowed("worker_kind"):
            issues.append(_issue(
                "resolved.worker_kind", "invalid_vocabulary",
                "Invalid resolved worker kind.",
            ))
        issues.extend(_string_list(
            resolved.get("requirements"), "resolved.requirements",
        ))

    result = execution.get("result")
    if isinstance(result, Mapping):
        issues.extend(_exact_fields(
            result, field="result", expected=set(_template()["result"]),
        ))
        if result.get("status") not in _allowed("result_status"):
            issues.append(_issue(
                "result.status", "invalid_vocabulary",
                "Invalid result status.",
            ))
        if result.get("content") is None:
            issues.append(_issue(
                "result.content", "required",
                "Execution result content cannot be null.",
            ))
        issues.extend(_string_list(
            result.get("artifact_refs"), "result.artifact_refs",
        ))
        issues.extend(_string(
            result.get("notes"), "result.notes", nullable=True,
        ))

    error = execution.get("error")
    if isinstance(error, Mapping):
        issues.extend(_exact_fields(
            error, field="error", expected=set(_template()["error"]),
        ))
        issues.extend(_string(error.get("code"), "error.code"))
        if error.get("category") not in _allowed("error_category"):
            issues.append(_issue(
                "error.category", "invalid_vocabulary",
                "Invalid error category.",
            ))
        issues.extend(_string(error.get("detail"), "error.detail"))
        if not isinstance(error.get("retryable"), bool):
            issues.append(_issue(
                "error.retryable", "invalid_shape",
                "error.retryable must be boolean.",
            ))
        if error.get("source") not in _allowed("error_source"):
            issues.append(_issue(
                "error.source", "invalid_vocabulary",
                "Invalid error source.",
            ))

    for section_name in ("provenance", "persistence"):
        issues.extend(_exact_fields(
            execution.get(section_name),
            field=section_name,
            expected=set(_template()[section_name]),
        ))
    provenance = execution.get("provenance")
    if isinstance(provenance, Mapping):
        issues.extend(_string(
            provenance.get("prompt_artifact_ref"),
            "provenance.prompt_artifact_ref",
            nullable=True,
        ))
        for name in ("created_at", "updated_at"):
            issues.extend(_string(
                provenance.get(name), f"provenance.{name}",
            ))
    persistence = execution.get("persistence")
    if isinstance(persistence, Mapping):
        if not isinstance(persistence.get("save"), bool):
            issues.append(_issue(
                "persistence.save", "invalid_shape",
                "persistence.save must be boolean.",
            ))
        issues.extend(_string(
            persistence.get("location"),
            "persistence.location",
            nullable=not persistence.get("save", False),
        ))

    trace = execution.get("trace")
    issues.extend(_exact_fields(
        trace, field="trace", expected=set(_template()["trace"]),
    ))
    if isinstance(trace, Mapping):
        if trace.get("resolved_by") != "task_executive":
            issues.append(_issue(
                "trace.resolved_by", "authority_mismatch",
                "Only Task Executive may record deterministic resolution.",
            ))
        issues.extend(_string(trace.get("resolved_at"), "trace.resolved_at"))
        deployment = trace.get("deployment")
        issues.extend(_exact_fields(
            deployment,
            field="trace.deployment",
            expected=set(_template()["trace"]["deployment"]),
        ))
        if isinstance(deployment, Mapping):
            for name in ("session", "compute_node", "host"):
                issues.extend(_string(
                    deployment.get(name), f"trace.deployment.{name}",
                ))
            resolved_kind = (
                resolved.get("worker_kind")
                if isinstance(resolved, Mapping)
                else None
            )
            issues.extend(_string(
                deployment.get("model"),
                "trace.deployment.model",
                nullable=resolved_kind == "tool",
            ))
            if resolved_kind == "model" and deployment.get("model") is None:
                issues.append(_issue(
                    "trace.deployment.model", "required_for_model",
                    "Model-backed execution requires model deployment identity.",
                ))
            issues.extend(_string(
                deployment.get("agent"),
                "trace.deployment.agent",
                nullable=True,
            ))
        if not isinstance(trace.get("events"), list):
            issues.append(_issue(
                "trace.events", "invalid_shape",
                "trace.events must be an array.",
            ))

    plan_execution = execution.get("plan_execution")
    issues.extend(_exact_fields(
        plan_execution,
        field="plan_execution",
        expected=set(_template()["plan_execution"]),
    ))
    if isinstance(plan_execution, Mapping):
        for name in (
            "plan_ref", "execution_authorizer", "current_step_ref",
            "expected_result_ref",
        ):
            issues.extend(_string(
                plan_execution.get(name), f"plan_execution.{name}",
            ))
        issues.extend(_string(
            plan_execution.get("next_step_ref"),
            "plan_execution.next_step_ref",
            nullable=True,
        ))
        steps = plan_execution.get("steps")
        if not isinstance(steps, list) or len(steps) != 1:
            issues.append(_issue(
                "plan_execution.steps", "invalid_shape",
                "V0 TaskExecution must record exactly one selected step.",
            ))
        else:
            step = steps[0]
            issues.extend(_exact_fields(
                step,
                field="plan_execution.steps[0]",
                expected=set(_template()["plan_execution"]["steps"][0]),
            ))
            if isinstance(step, Mapping):
                issues.extend(_string(
                    step.get("step_ref"), "plan_execution.steps[0].step_ref",
                ))
                on_failure = step.get("on_failure")
                issues.extend(_exact_fields(
                    on_failure,
                    field="plan_execution.steps[0].on_failure",
                    expected=set(
                        _template()["plan_execution"]["steps"][0]["on_failure"]
                    ),
                ))
                if isinstance(on_failure, Mapping):
                    if on_failure.get("policy") not in _allowed("failure_policy"):
                        issues.append(_issue(
                            "plan_execution.steps[0].on_failure.policy",
                            "invalid_vocabulary",
                            "Invalid failure policy.",
                        ))
                    retries = on_failure.get("max_retries")
                    if (
                        isinstance(retries, bool)
                        or not isinstance(retries, int)
                        or retries < 0
                    ):
                        issues.append(_issue(
                            "plan_execution.steps[0].on_failure.max_retries",
                            "invalid_shape",
                            "max_retries must be a non-negative integer.",
                        ))
        authorization = plan_execution.get("authorization")
        issues.extend(_exact_fields(
            authorization,
            field="plan_execution.authorization",
            expected=set(_template()["plan_execution"]["authorization"]),
        ))
        if isinstance(authorization, Mapping):
            if authorization.get("authorized") is not True:
                issues.append(_issue(
                    "plan_execution.authorization.authorized",
                    "not_authorized",
                    "Execution record requires prior authorization.",
                ))
            for name in (
                "authorizer_ref", "authorization_record_ref", "authorized_at",
            ):
                issues.extend(_string(
                    authorization.get(name),
                    f"plan_execution.authorization.{name}",
                ))
        if plan_execution.get("validation_outcome") not in _allowed(
            "validation_outcome"
        ):
            issues.append(_issue(
                "plan_execution.validation_outcome", "invalid_vocabulary",
                "Invalid validation outcome.",
            ))
        issues.extend(_string_list(
            plan_execution.get("validation_evidence_refs"),
            "plan_execution.validation_evidence_refs",
        ))
        if not isinstance(plan_execution.get("replan_requested"), bool):
            issues.append(_issue(
                "plan_execution.replan_requested", "invalid_shape",
                "replan_requested must be boolean.",
            ))
        issues.extend(_string(
            plan_execution.get("replan_reason"),
            "plan_execution.replan_reason",
            nullable=not plan_execution.get("replan_requested", False),
        ))
        outcomes = plan_execution.get("outcomes")
        if not isinstance(outcomes, list):
            issues.append(_issue(
                "plan_execution.outcomes", "invalid_shape",
                "outcomes must be an array.",
            ))
        else:
            outcome_fields = set(
                _template()["plan_execution"]["outcomes"][0]
            )
            for index, outcome in enumerate(outcomes):
                field = f"plan_execution.outcomes[{index}]"
                issues.extend(_exact_fields(
                    outcome, field=field, expected=outcome_fields,
                ))
                if not isinstance(outcome, Mapping):
                    continue
                if outcome.get("decision") not in _allowed(
                    "director_outcome"
                ):
                    issues.append(_issue(
                        f"{field}.decision", "invalid_vocabulary",
                        "Director outcome must be ACCEPT, REVISE, or ASK_GUIDANCE.",
                    ))
                for name in (
                    "id", "reason", "decided_by_ref", "created_at",
                    "task_ref", "execution_ref",
                ):
                    issues.extend(_string(
                        outcome.get(name), f"{field}.{name}",
                    ))
                issues.extend(_string_list(
                    outcome.get("evidence_refs"), f"{field}.evidence_refs",
                ))
                checkpoint_revision_ref = outcome.get(
                    "checkpoint_revision_ref"
                )
                checkpoint_identity = _plan_ref_identity(
                    checkpoint_revision_ref
                )
                if checkpoint_identity is None:
                    issues.append(_issue(
                        f"{field}.checkpoint_revision_ref",
                        "invalid_plan_reference",
                        "Checkpoint revision must be a qualified Plan revision reference.",
                    ))
                current_identity = _plan_ref_identity(
                    plan_execution.get("plan_ref")
                )
                if (
                    checkpoint_identity is not None
                    and current_identity is not None
                    and checkpoint_identity[0] != current_identity[0]
                ):
                    issues.append(_issue(
                        f"{field}.checkpoint_revision_ref",
                        "lineage_mismatch",
                        "Checkpoint and execution must belong to the same plan_id.",
                    ))
                checkpoint_outcome_ref = outcome.get(
                    "checkpoint_outcome_ref"
                )
                issues.extend(_string(
                    checkpoint_outcome_ref,
                    f"{field}.checkpoint_outcome_ref",
                    nullable=True,
                ))
                issues.extend(_string(
                    outcome.get("resulting_plan_ref"),
                    f"{field}.resulting_plan_ref",
                    nullable=True,
                ))
                if (
                    checkpoint_outcome_ref is None
                    and checkpoint_identity is not None
                    and checkpoint_identity[1] != 1
                ):
                    issues.append(_issue(
                        f"{field}.checkpoint_outcome_ref",
                        "missing_execution_checkpoint",
                        "Only the distinguished @r1 root may omit an ACCEPT outcome reference.",
                    ))

                decision = outcome.get("decision")
                guidance = outcome.get("guidance")
                if decision == "ASK_GUIDANCE":
                    issues.extend(_validate_guidance(
                        guidance, field=f"{field}.guidance",
                    ))
                    if outcome.get("resulting_plan_ref") is not None:
                        issues.append(_issue(
                            f"{field}.resulting_plan_ref",
                            "premature_successor",
                            "ASK_GUIDANCE cannot identify a successor before guidance returns.",
                        ))
                elif guidance is not None:
                    issues.append(_issue(
                        f"{field}.guidance", "invalid_semantics",
                        "Only ASK_GUIDANCE may contain guidance details.",
                    ))
                if decision == "ACCEPT":
                    if checkpoint_revision_ref != plan_execution.get(
                        "plan_ref"
                    ):
                        issues.append(_issue(
                            f"{field}.checkpoint_revision_ref",
                            "reference_mismatch",
                            "ACCEPT checkpoints the evaluated Plan revision.",
                        ))
                    if checkpoint_outcome_ref != outcome.get("id"):
                        issues.append(_issue(
                            f"{field}.checkpoint_outcome_ref",
                            "reference_mismatch",
                            "An ACCEPT execution checkpoint must reference its real outcome.",
                        ))
                if outcome.get("task_ref") != execution.get("task_ref"):
                    issues.append(_issue(
                        f"{field}.task_ref", "reference_mismatch",
                        "Outcome task_ref must identify this execution task.",
                    ))
                if outcome.get("execution_ref") != execution.get(
                    "execution_id"
                ):
                    issues.append(_issue(
                        f"{field}.execution_ref", "reference_mismatch",
                        "Outcome must identify this TaskExecution.",
                    ))
        plan_persistence = plan_execution.get("persistence")
        issues.extend(_exact_fields(
            plan_persistence,
            field="plan_execution.persistence",
            expected=set(_template()["plan_execution"]["persistence"]),
        ))
        if isinstance(plan_persistence, Mapping):
            if not isinstance(plan_persistence.get("save"), bool):
                issues.append(_issue(
                    "plan_execution.persistence.save", "invalid_shape",
                    "plan-execution save must be boolean.",
                ))
            issues.extend(_string(
                plan_persistence.get("location"),
                "plan_execution.persistence.location",
                nullable=not plan_persistence.get("save", False),
            ))
            for name in ("created_at", "updated_at"):
                issues.extend(_string(
                    plan_persistence.get(name),
                    f"plan_execution.persistence.{name}",
                ))

    issues.extend(validate_task_execution_terminal_profile(execution))
    return tuple(issues)


def validate_task_execution_checkpoint_context(
    execution: object,
    *,
    plans_by_ref: Mapping[str, Mapping[str, Any]],
    accepted_outcomes_by_ref: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[ValidationIssue, ...]:
    """Resolve root/execution checkpoint identity against trusted history."""

    if not isinstance(execution, Mapping):
        return (_issue(
            "execution", "invalid_shape", "TaskExecution must be an object.",
        ),)
    plan_execution = execution.get("plan_execution")
    if not isinstance(plan_execution, Mapping):
        return (_issue(
            "plan_execution", "invalid_shape",
            "TaskExecution plan_execution must be an object.",
        ),)
    outcomes = plan_execution.get("outcomes")
    if not isinstance(outcomes, list):
        return (_issue(
            "plan_execution.outcomes", "invalid_shape",
            "TaskExecution outcomes must be an array.",
        ),)

    catalog = dict(accepted_outcomes_by_ref or {})
    for outcome in outcomes:
        if isinstance(outcome, Mapping) and isinstance(outcome.get("id"), str):
            catalog[outcome["id"]] = outcome

    issues: list[ValidationIssue] = []
    for index, outcome in enumerate(outcomes):
        if not isinstance(outcome, Mapping):
            continue
        field = f"plan_execution.outcomes[{index}]"
        revision_ref = outcome.get("checkpoint_revision_ref")
        checkpoint_plan = plans_by_ref.get(revision_ref)
        if checkpoint_plan is None:
            issues.append(_issue(
                f"{field}.checkpoint_revision_ref", "unknown_checkpoint",
                "Checkpoint Plan revision is not present in trusted history.",
            ))
            continue

        checkpoint_outcome_ref = outcome.get("checkpoint_outcome_ref")
        if checkpoint_outcome_ref is None:
            from planning import (
                root_checkpoint_evidence_refs,
                validate_planning_root_checkpoint,
            )

            root_issues = validate_planning_root_checkpoint(checkpoint_plan)
            if root_issues:
                issues.append(_issue(
                    f"{field}.checkpoint_outcome_ref",
                    "invalid_root_checkpoint",
                    "A null outcome reference requires the planning-certified @r1 root.",
                ))
                issues.extend(root_issues)
                continue
            required_evidence = set(
                root_checkpoint_evidence_refs(checkpoint_plan)
            )
            evidence_refs = outcome.get("evidence_refs")
            if (
                not isinstance(evidence_refs, list)
                or not required_evidence.issubset(evidence_refs)
            ):
                issues.append(_issue(
                    f"{field}.evidence_refs",
                    "missing_root_certification_evidence",
                    "Root checkpoints must reference trusted planning finalization and certification evidence.",
                ))
            continue

        accepted = catalog.get(checkpoint_outcome_ref)
        if not isinstance(accepted, Mapping):
            issues.append(_issue(
                f"{field}.checkpoint_outcome_ref", "unknown_checkpoint",
                "Execution checkpoint must resolve to a real ACCEPT outcome.",
            ))
            continue
        if accepted.get("decision") != "ACCEPT":
            issues.append(_issue(
                f"{field}.checkpoint_outcome_ref", "not_accepted",
                "Execution checkpoint must reference an ACCEPT outcome.",
            ))
        if accepted.get("checkpoint_revision_ref") != revision_ref:
            issues.append(_issue(
                f"{field}.checkpoint_outcome_ref", "reference_mismatch",
                "Execution checkpoint outcome must accept the referenced Plan revision.",
            ))
    return tuple(issues)
