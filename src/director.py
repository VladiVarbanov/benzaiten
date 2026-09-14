"""Validated Python adapter for the authoritative DirectorTask protocol."""

from __future__ import annotations

from dataclasses import dataclass, fields
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Mapping, Optional

from config import DIRECTOR_TASK_VOCABULARY_PATH
from structures import ValidationIssue, load_yaml_mapping

DIRECTOR_TASK_FIELD_NAMES = frozenset({
    "task_id", "job_ref", "capability", "participant_role", "objective",
    "input_refs", "instruction", "work_kind", "plan_ref", "action",
    "target", "anchors", "entities", "focus", "reason", "requirements",
    "acceptance", "output_contract_ref", "external_authority_ref",
})
_REQUIRED_FIELDS = (
    "task_id", "job_ref", "capability", "participant_role", "objective",
)
_OPTIONAL_STRINGS = (
    "instruction", "work_kind", "plan_ref", "action", "reason", "acceptance",
    "output_contract_ref", "external_authority_ref",
)


def _issue(field: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(field=field, code=code, message=message)


@lru_cache(maxsize=1)
def _vocabulary() -> Mapping[str, Any]:
    return load_yaml_mapping(DIRECTOR_TASK_VOCABULARY_PATH)


def _allowed(section: str) -> frozenset[str]:
    value = _vocabulary().get(section)
    if isinstance(value, Mapping):
        return frozenset(value)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return frozenset(value)
    raise RuntimeError(f"Invalid DirectorTask vocabulary section: {section}")


def _validate_string_array(value: object, field: str) -> list[ValidationIssue]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        return [_issue(field, "invalid_shape", f"{field} must be an array.")]
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return [_issue(
            field, "invalid_shape",
            f"{field} must contain only non-empty strings.",
        )]
    return []


def _validate_record(
    value: object,
    field: str,
    expected: frozenset[str],
) -> list[ValidationIssue]:
    if not isinstance(value, Mapping):
        return [_issue(field, "invalid_shape", f"{field} must be an object.")]
    issues: list[ValidationIssue] = []
    keys = set(value)
    for name in sorted(keys - expected):
        issues.append(_issue(
            f"{field}.{name}", "unknown_field",
            f"Unknown {field} field: {name}",
        ))
    for name in sorted(expected - keys):
        issues.append(_issue(
            f"{field}.{name}", "required",
            f"Missing required {field} field: {name}",
        ))
    for name in sorted(keys & expected):
        item = value[name]
        if not isinstance(item, str) or not item.strip():
            issues.append(_issue(
                f"{field}.{name}", "invalid_shape",
                f"{field}.{name} must be a non-empty string.",
            ))
    return issues


def validate_director_task_mapping(data: object) -> tuple[ValidationIssue, ...]:
    """Validate a model-produced task without dropping unknown semantics."""

    if not isinstance(data, Mapping):
        return (_issue("task", "invalid_shape", "DirectorTask must be an object."),)

    issues: list[ValidationIssue] = []
    for name in sorted(set(data) - DIRECTOR_TASK_FIELD_NAMES):
        issues.append(_issue(
            name, "unknown_field", f"Unknown DirectorTask field: {name}",
        ))

    for name in _REQUIRED_FIELDS:
        value = data.get(name)
        if not isinstance(value, str) or not value.strip():
            issues.append(_issue(
                name, "required", f"{name} must be a non-empty string.",
            ))
    for name in _OPTIONAL_STRINGS:
        value = data.get(name)
        if value is not None and (
            not isinstance(value, str) or not value.strip()
        ):
            issues.append(_issue(
                name, "invalid_shape",
                f"{name} must be null or a non-empty string.",
            ))
    for name in ("input_refs", "requirements"):
        issues.extend(_validate_string_array(data.get(name, ()), name))

    vocabulary_fields = {
        "capability": "capability",
        "participant_role": "participant_role",
        "work_kind": "work_kind",
        "action": "semantic_operation",
    }
    for field_name, vocabulary_name in vocabulary_fields.items():
        value = data.get(field_name)
        if isinstance(value, str) and value.strip() and value not in _allowed(vocabulary_name):
            issues.append(_issue(
                field_name, "invalid_vocabulary",
                f"{field_name} must be one of {sorted(_allowed(vocabulary_name))}.",
            ))

    target = data.get("target")
    if target is not None:
        issues.extend(_validate_record(
            target, "target", frozenset({"kind", "locator"}),
        ))
    for field_name, expected in (
        ("anchors", frozenset({"kind", "value"})),
        ("entities", frozenset({"kind", "name"})),
    ):
        value = data.get(field_name, ())
        if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
            issues.append(_issue(
                field_name, "invalid_shape", f"{field_name} must be an array.",
            ))
        else:
            for index, item in enumerate(value):
                issues.extend(_validate_record(item, f"{field_name}[{index}]", expected))

    focus = data.get("focus")
    if focus is not None:
        if not isinstance(focus, Mapping):
            issues.append(_issue("focus", "invalid_shape", "focus must be an object."))
        else:
            expected = frozenset({"questions", "angles", "granularity"})
            for name in sorted(set(focus) - expected):
                issues.append(_issue(
                    f"focus.{name}", "unknown_field", f"Unknown focus field: {name}",
                ))
            for name in ("questions", "angles"):
                issues.extend(_validate_string_array(
                    focus.get(name, ()), f"focus.{name}",
                ))
            granularity = focus.get("granularity")
            if granularity is not None:
                if not isinstance(granularity, str) or not granularity.strip():
                    issues.append(_issue(
                        "focus.granularity", "invalid_shape",
                        "focus.granularity must be null or a non-empty string.",
                    ))
                elif granularity not in _allowed("granularity"):
                    issues.append(_issue(
                        "focus.granularity", "invalid_vocabulary",
                        f"focus.granularity must be one of {sorted(_allowed('granularity'))}.",
                    ))

    if data.get("work_kind") == "execution":
        for name in ("plan_ref", "action"):
            value = data.get(name)
            if not isinstance(value, str) or not value.strip():
                issues.append(_issue(
                    name, "required_for_execution",
                    f"{name} is required for executable managed work.",
                ))
    return tuple(issues)


def _immutable_record(value: Mapping[str, object]) -> Mapping[str, str]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class TaskFocus:
    questions: tuple[str, ...] = ()
    angles: tuple[str, ...] = ()
    granularity: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "questions", tuple(self.questions))
        object.__setattr__(self, "angles", tuple(self.angles))
        issues = [
            *_validate_string_array(self.questions, "focus.questions"),
            *_validate_string_array(self.angles, "focus.angles"),
        ]
        if self.granularity is not None:
            if (
                not isinstance(self.granularity, str)
                or not self.granularity.strip()
                or self.granularity not in _allowed("granularity")
            ):
                issues.append(_issue(
                    "focus.granularity", "invalid_vocabulary",
                    f"focus.granularity must be one of {sorted(_allowed('granularity'))}.",
                ))
        if issues:
            details = "; ".join(
                f"{issue.field}: {issue.message}" for issue in issues
            )
            raise ValueError(f"Invalid TaskFocus: {details}")


@dataclass(frozen=True)
class DirectorTask:
    """Semantic intent created by the Director and certified deterministically."""

    task_id: str
    job_ref: str
    capability: str
    participant_role: str
    objective: str
    input_refs: tuple[str, ...] = ()
    instruction: Optional[str] = None
    work_kind: Optional[str] = None
    plan_ref: Optional[str] = None
    action: Optional[str] = None
    target: Optional[Mapping[str, str]] = None
    anchors: tuple[Mapping[str, str], ...] = ()
    entities: tuple[Mapping[str, str], ...] = ()
    focus: Optional[TaskFocus] = None
    reason: Optional[str] = None
    requirements: tuple[str, ...] = ()
    acceptance: Optional[str] = None
    output_contract_ref: Optional[str] = None
    external_authority_ref: Optional[str] = None

    def __post_init__(self) -> None:
        raw = {field.name: getattr(self, field.name) for field in fields(self)}
        if self.focus is not None:
            if not isinstance(self.focus, TaskFocus):
                raise ValueError("focus must be a TaskFocus instance or None.")
            raw["focus"] = {
                "questions": self.focus.questions,
                "angles": self.focus.angles,
                "granularity": self.focus.granularity,
            }
        issues = validate_director_task_mapping(raw)
        if issues:
            details = "; ".join(f"{issue.field}: {issue.message}" for issue in issues)
            raise ValueError(f"Invalid DirectorTask: {details}")
        object.__setattr__(self, "input_refs", tuple(self.input_refs))
        object.__setattr__(self, "requirements", tuple(self.requirements))
        if self.target is not None:
            object.__setattr__(self, "target", _immutable_record(self.target))
        object.__setattr__(self, "anchors", tuple(
            _immutable_record(item) for item in self.anchors
        ))
        object.__setattr__(self, "entities", tuple(
            _immutable_record(item) for item in self.entities
        ))

    def semantic_payload(self) -> Mapping[str, object]:
        """Render only authoritative DirectorTask protocol vocabulary."""

        payload: dict[str, object] = {
            "task_id": self.task_id,
            "job_ref": self.job_ref,
            "capability": self.capability,
            "participant_role": self.participant_role,
            "objective": self.objective,
            "input_refs": list(self.input_refs),
        }
        for name in _OPTIONAL_STRINGS:
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        if self.target is not None:
            payload["target"] = dict(self.target)
        if self.anchors:
            payload["anchors"] = [dict(item) for item in self.anchors]
        if self.entities:
            payload["entities"] = [dict(item) for item in self.entities]
        if self.focus is not None:
            payload["focus"] = {
                "questions": list(self.focus.questions),
                "angles": list(self.focus.angles),
                "granularity": self.focus.granularity,
            }
        if self.requirements:
            payload["requirements"] = list(self.requirements)
        return payload


def parse_director_task(data: object) -> DirectorTask:
    """Strictly parse a mapping into a validated immutable DirectorTask."""

    issues = validate_director_task_mapping(data)
    if issues:
        details = "; ".join(f"{issue.field}: {issue.message}" for issue in issues)
        raise ValueError(f"Invalid DirectorTask mapping: {details}")
    assert isinstance(data, Mapping)
    focus_data = data.get("focus")
    focus = None
    if isinstance(focus_data, Mapping):
        focus = TaskFocus(
            questions=tuple(focus_data.get("questions", ())),
            angles=tuple(focus_data.get("angles", ())),
            granularity=focus_data.get("granularity"),
        )
    target = data.get("target")
    return DirectorTask(
        task_id=data["task_id"], job_ref=data["job_ref"],
        capability=data["capability"], participant_role=data["participant_role"],
        objective=data["objective"], input_refs=tuple(data.get("input_refs", ())),
        instruction=data.get("instruction"), work_kind=data.get("work_kind"),
        plan_ref=data.get("plan_ref"), action=data.get("action"),
        target=_immutable_record(target) if isinstance(target, Mapping) else None,
        anchors=tuple(_immutable_record(item) for item in data.get("anchors", ())),
        entities=tuple(_immutable_record(item) for item in data.get("entities", ())),
        focus=focus, reason=data.get("reason"),
        requirements=tuple(data.get("requirements", ())),
        acceptance=data.get("acceptance"),
        output_contract_ref=data.get("output_contract_ref"),
        external_authority_ref=data.get("external_authority_ref"),
    )


assert {field.name for field in fields(DirectorTask)} == DIRECTOR_TASK_FIELD_NAMES


def run_normal_planning(
    frozen_request: str,
    *,
    model_caller: object = None,
    plan_id: Optional[str] = None,
    budget: Optional[Mapping[str, int]] = None,
) -> Mapping[str, object]:
    """Run the fixed reciprocal Normal-planning sequence.

    Four reciprocal-planning calls precede focused Director semantic
    units. Policy-limited completion and conformance repair do not advance
    semantic iteration. This creates no DirectorTask or TaskExecution and does
    not execute the Plan.
    """

    from copy import deepcopy
    from hashlib import sha256
    from uuid import uuid4

    from config import DEFAULT_JOB_BUDGET, NORMAL_PLANNING_CONTEXTS
    from model_client import ModelResponse
    from orchestrator import invoke_model_context, resolve_model_context
    from planning import (
        ARCHITECTURE_ASSESSMENT_SEMANTIC_SHAPE,
        CHANGE_DISPOSITION_SEMANTIC_SHAPE,
        OVERALL_SYNTHESIS_SEMANTIC_SHAPE,
        PLAN_STEPS_SEMANTIC_SHAPE,
        SEMANTIC_BOUNDARY_CORRECTION_SHAPE,
        assemble_assessment,
        assemble_final_plan,
        assemble_proposal,
        architecture_assessment_response_format,
        assessment_response_format,
        certify_final_plan,
        change_disposition_response_format,
        combine_synthesis_semantics,
        conformance_repair_policy,
        overall_synthesis_response_format,
        parse_json_object,
        plan_steps_response_format,
        proposal_response_format,
        render_architecture_assessment_messages,
        render_assessment_messages,
        render_change_disposition_messages,
        render_conformance_repair_messages,
        render_overall_synthesis_messages,
        render_plan_steps_messages,
        render_proposal_messages,
        render_semantic_boundary_correction_messages,
        render_semantic_completion_messages,
        semantic_architecture_acceptance_policy,
        semantic_boundary_correction_policy,
        semantic_boundary_correction_response_format,
        semantic_completion_policy,
        validate_architecture_assessment_semantics,
        validate_assessment,
        validate_assessment_semantics,
        validate_change_disposition_semantics,
        validate_final_plan,
        validate_overall_synthesis_semantics,
        validate_plan_steps_semantics,
        validate_proposal,
        validate_semantic_boundary_correction_semantics,
        validate_proposal_semantics,
    )

    if not isinstance(frozen_request, str) or not frozen_request.strip():
        raise ValueError("frozen_request must be a non-empty string.")
    limits = dict(DEFAULT_JOB_BUDGET if budget is None else budget)
    for name in ("reasoning_tasks", "semantic_iterations"):
        if not isinstance(limits.get(name), int) or limits[name] < 1:
            raise ValueError(f"Budget {name} must be a positive integer.")
    if limits["reasoning_tasks"] < 7 or limits["semantic_iterations"] < 3:
        raise ValueError(
            "Normal planning requires at least seven calls and three "
            "advancements."
        )

    required_stages = {
        "gemma_proposal",
        "qwen_proposal",
        "qwen_assessment",
        "gemma_assessment",
        "director_synthesis",
        "architecture_assessment",
    }
    if set(NORMAL_PLANNING_CONTEXTS) != required_stages:
        raise RuntimeError("Normal-planning context configuration is incomplete.")

    caller = invoke_model_context if model_caller is None else model_caller
    if not callable(caller):
        raise TypeError("model_caller must be callable.")
    reasoning_tasks = 0
    semantic_iterations = 0
    calls: list[dict[str, object]] = []
    advancements: list[dict[str, object]] = []
    conformance_repairs: list[dict[str, object]] = []
    semantic_completions: list[dict[str, object]] = []
    architecture_assessments: list[dict[str, object]] = []
    semantic_boundary_corrections: list[dict[str, object]] = []
    structural_certifications: list[dict[str, object]] = []
    repair_attempts: dict[str, int] = {}
    completion_attempts: dict[str, int] = {}

    def call(
        stage: str,
        messages: tuple[dict[str, str], ...],
        response_format: Mapping[str, object],
        *,
        producer_context: Optional[str] = None,
    ) -> ModelResponse:
        nonlocal reasoning_tasks
        if reasoning_tasks >= limits["reasoning_tasks"]:
            raise RuntimeError("Reasoning-task budget exhausted.")
        context_name = (
            NORMAL_PLANNING_CONTEXTS[stage]
            if producer_context is None
            else producer_context
        )
        assignment = resolve_model_context(context_name)
        assert assignment.model is not None
        reasoning_tasks += 1
        selected_response_format = (
            response_format
            if assignment.model.supports_json_schema
            else None
        )
        chat_template_kwargs = (
            assignment.model.structured_output_chat_template_kwargs
            if selected_response_format is not None
            else None
        )
        response = caller(
            context_name,
            messages,
            response_format=selected_response_format,
            chat_template_kwargs=chat_template_kwargs,
        )
        if not isinstance(response, ModelResponse):
            raise TypeError("Planning model caller must return ModelResponse.")
        calls.append({
            "stage": stage,
            "logical_context": context_name,
            "model_name": assignment.model.model_name,
            "node": assignment.model.node,
            "endpoint_url": assignment.model.endpoint_url,
            "request_id": response.request_id,
            "server_request_id": response.server_request_id,
            "finish_reason": response.finish_reason,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
            "latency_ms": response.latency_ms,
            "reasoning_task": reasoning_tasks,
            "semantic_iteration": semantic_iterations,
            "response_format": (
                None
                if selected_response_format is None
                else selected_response_format["type"]
            ),
            "response_schema_name": (
                None
                if selected_response_format is None
                else selected_response_format["json_schema"]["name"]
            ),
            "chat_template_kwargs": (
                None
                if chat_template_kwargs is None
                else dict(chat_template_kwargs)
            ),
        })
        return response

    def request_conformance_repair(
        *,
        artifact_kind: str,
        producer_context: str,
        invalid_output: str,
        validation_issues: tuple[ValidationIssue, ...],
        valid_references: Mapping[str, object],
        required_output: Mapping[str, object],
        response_format: Mapping[str, object],
    ) -> ModelResponse:
        policy = conformance_repair_policy()
        maximum = policy.get("maximum_attempts_per_artifact")
        if maximum != 1:
            raise RuntimeError(
                "Iteration 2 supports exactly one conformance-repair attempt."
            )
        if (
            policy.get("consumes_reasoning_task") is not True
            or policy.get("advances_semantic_iteration") is not False
            or policy.get("semantic_change_allowed") is not False
        ):
            raise RuntimeError("Unsupported conformance-repair policy.")
        attempt = repair_attempts.get(artifact_kind, 0) + 1
        if attempt > maximum:
            raise ValueError(
                f"{artifact_kind} exhausted its conformance-repair attempt."
            )
        repair_attempts[artifact_kind] = attempt
        messages = render_conformance_repair_messages(
            artifact_kind=artifact_kind,
            invalid_output=invalid_output,
            validation_issues=validation_issues,
            valid_references=valid_references,
            required_output=required_output,
        )
        response = call(
            f"{artifact_kind}_conformance_repair",
            messages,
            response_format,
            producer_context=producer_context,
        )
        conformance_repairs.append({
            "artifact_kind": artifact_kind,
            "attempt": attempt,
            "producer_context": producer_context,
            "invalid_output": invalid_output,
            "validation_issues": [
                {
                    "field": issue.field,
                    "code": issue.code,
                    "message": issue.message,
                }
                for issue in validation_issues
            ],
            "repaired_output": response.text,
        })
        return response

    def request_semantic_completion(
        *,
        artifact_kind: str,
        producer_context: str,
        incomplete_output: str,
        missing_decisions: tuple[ValidationIssue, ...],
        valid_references: Mapping[str, object],
        required_output: Mapping[str, object],
        response_format: Mapping[str, object],
    ) -> ModelResponse:
        policy = semantic_completion_policy()
        maximum = policy.get("maximum_attempts_per_artifact")
        if maximum != 1:
            raise RuntimeError(
                "Iteration 2 supports exactly one semantic-completion attempt."
            )
        if (
            policy.get("consumes_reasoning_task") is not True
            or policy.get("advances_semantic_iteration") is not False
            or policy.get("same_semantic_producer") is not True
            or policy.get("semantic_change_scope") != "missing_decisions_only"
        ):
            raise RuntimeError("Unsupported semantic-completion policy.")
        attempt = completion_attempts.get(artifact_kind, 0) + 1
        if attempt > maximum:
            raise ValueError(
                f"{artifact_kind} exhausted its semantic-completion attempt."
            )
        completion_attempts[artifact_kind] = attempt
        messages = render_semantic_completion_messages(
            artifact_kind=artifact_kind,
            incomplete_output=incomplete_output,
            missing_decisions=missing_decisions,
            valid_references=valid_references,
            required_output=required_output,
        )
        response = call(
            f"{artifact_kind}_semantic_completion",
            messages,
            response_format,
            producer_context=producer_context,
        )
        semantic_completions.append({
            "artifact_kind": artifact_kind,
            "attempt": attempt,
            "producer_context": producer_context,
            "incomplete_output": incomplete_output,
            "missing_semantic_decisions": [
                {
                    "field": issue.field,
                    "code": issue.code,
                    "message": issue.message,
                }
                for issue in missing_decisions
            ],
            "completed_output": response.text,
        })
        return response

    def resolve_semantic_artifact(
        *,
        artifact_kind: str,
        producer_context: str,
        initial_response: ModelResponse,
        valid_references: Mapping[str, object],
        required_output: Mapping[str, object],
        response_format: Mapping[str, object],
        validator: object,
    ) -> dict[str, Any]:
        current_output = initial_response.text
        while True:
            try:
                semantics = parse_json_object(
                    current_output,
                    stage=artifact_kind.replace("_", " ").title(),
                )
                issues = validator(semantics)
            except ValueError as exc:
                semantics = None
                issues = (ValidationIssue(
                    field=artifact_kind,
                    code="invalid_shape",
                    message=str(exc),
                ),)
            missing = tuple(
                issue
                for issue in issues
                if issue.code == "missing_semantic_decision"
            )
            conformance = tuple(
                issue
                for issue in issues
                if issue.code != "missing_semantic_decision"
            )
            if conformance:
                if repair_attempts.get(artifact_kind, 0) >= 1:
                    details = "; ".join(
                        f"{issue.field}: {issue.message}"
                        for issue in conformance
                    )
                    raise ValueError(
                        f"{artifact_kind} remains invalid after one "
                        f"conformance repair: {details}"
                    )
                current_output = request_conformance_repair(
                    artifact_kind=artifact_kind,
                    producer_context=producer_context,
                    invalid_output=current_output,
                    validation_issues=conformance,
                    valid_references=valid_references,
                    required_output=required_output,
                    response_format=response_format,
                ).text
                continue
            if missing:
                if completion_attempts.get(artifact_kind, 0) >= 1:
                    details = "; ".join(
                        f"{issue.field}: {issue.message}"
                        for issue in missing
                    )
                    raise ValueError(
                        f"{artifact_kind} remains incomplete after one "
                        f"semantic completion: {details}"
                    )
                current_output = request_semantic_completion(
                    artifact_kind=artifact_kind,
                    producer_context=producer_context,
                    incomplete_output=current_output,
                    missing_decisions=missing,
                    valid_references=valid_references,
                    required_output=required_output,
                    response_format=response_format,
                ).text
                continue
            assert semantics is not None
            return semantics

    def advance(event: str) -> None:
        nonlocal semantic_iterations
        if semantic_iterations >= limits["semantic_iterations"]:
            raise RuntimeError("Semantic-iteration budget exhausted.")
        semantic_iterations += 1
        advancements.append({
            "iteration": semantic_iterations,
            "event": event,
        })

    gemma_context = NORMAL_PLANNING_CONTEXTS["gemma_proposal"]
    qwen_context = NORMAL_PLANNING_CONTEXTS["qwen_proposal"]
    proposal_messages = render_proposal_messages(frozen_request)
    gemma_response = call(
        "gemma_proposal",
        proposal_messages,
        proposal_response_format(),
    )
    qwen_response = call(
        "qwen_proposal",
        proposal_messages,
        proposal_response_format(),
    )
    gemma_proposal_semantics = parse_json_object(
        gemma_response.text,
        stage="Gemma proposal semantics",
    )
    qwen_proposal_semantics = parse_json_object(
        qwen_response.text,
        stage="Qwen proposal semantics",
    )
    proposal_semantic_issues = (
        *validate_proposal_semantics(gemma_proposal_semantics),
        *validate_proposal_semantics(qwen_proposal_semantics),
    )
    if proposal_semantic_issues:
        details = "; ".join(
            issue.message for issue in proposal_semantic_issues
        )
        raise ValueError(f"Invalid proposal semantics: {details}")
    gemma_proposal = assemble_proposal(
        gemma_proposal_semantics,
        proposal_id="proposal-gemma",
        author_ref=gemma_context,
    )
    qwen_proposal = assemble_proposal(
        qwen_proposal_semantics,
        proposal_id="proposal-qwen",
        author_ref=qwen_context,
    )
    proposal_issues = (
        *validate_proposal(
            gemma_proposal,
            expected_author=gemma_context,
            expected_id="proposal-gemma",
        ),
        *validate_proposal(
            qwen_proposal,
            expected_author=qwen_context,
            expected_id="proposal-qwen",
        ),
    )
    if proposal_issues:
        details = "; ".join(issue.message for issue in proposal_issues)
        raise ValueError(f"Invalid canonical proposals: {details}")
    advance("validated_candidate_set")

    qwen_assessment_messages = render_assessment_messages(
        frozen_request,
        target_proposal=gemma_proposal,
    )
    gemma_assessment_messages = render_assessment_messages(
        frozen_request,
        target_proposal=qwen_proposal,
    )
    qwen_assessment_response = call(
        "qwen_assessment",
        qwen_assessment_messages,
        assessment_response_format(),
    )
    gemma_assessment_response = call(
        "gemma_assessment",
        gemma_assessment_messages,
        assessment_response_format(),
    )
    qwen_assessment_semantics = parse_json_object(
        qwen_assessment_response.text,
        stage="Qwen assessment semantics",
    )
    gemma_assessment_semantics = parse_json_object(
        gemma_assessment_response.text,
        stage="Gemma assessment semantics",
    )
    assessment_semantic_issues = (
        *validate_assessment_semantics(qwen_assessment_semantics),
        *validate_assessment_semantics(gemma_assessment_semantics),
    )
    if assessment_semantic_issues:
        details = "; ".join(
            issue.message for issue in assessment_semantic_issues
        )
        raise ValueError(f"Invalid assessment semantics: {details}")
    qwen_assessment = assemble_assessment(
        qwen_assessment_semantics,
        critique_id="assessment-qwen-of-gemma",
        author_ref=NORMAL_PLANNING_CONTEXTS["qwen_assessment"],
        target_proposal_id=gemma_proposal["id"],
    )
    gemma_assessment = assemble_assessment(
        gemma_assessment_semantics,
        critique_id="assessment-gemma-of-qwen",
        author_ref=NORMAL_PLANNING_CONTEXTS["gemma_assessment"],
        target_proposal_id=qwen_proposal["id"],
    )
    assessment_issues = (
        *validate_assessment(
            qwen_assessment,
            expected_author=NORMAL_PLANNING_CONTEXTS["qwen_assessment"],
            expected_target=gemma_proposal["id"],
            expected_id="assessment-qwen-of-gemma",
        ),
        *validate_assessment(
            gemma_assessment,
            expected_author=NORMAL_PLANNING_CONTEXTS["gemma_assessment"],
            expected_target=qwen_proposal["id"],
            expected_id="assessment-gemma-of-qwen",
        ),
    )
    if assessment_issues:
        details = "; ".join(issue.message for issue in assessment_issues)
        raise ValueError(f"Invalid canonical assessments: {details}")
    advance("validated_deliberation_resolution")

    selected_plan_id = plan_id or f"normal-plan-{uuid4().hex}"
    current_work_ref = "request:" + sha256(
        frozen_request.encode("utf-8")
    ).hexdigest()
    director_ref = NORMAL_PLANNING_CONTEXTS["director_synthesis"]
    suggested_changes = [
        change
        for assessment in (qwen_assessment, gemma_assessment)
        for change in assessment["suggested_changes"]
    ]
    suggested_change_count = len(suggested_changes)
    valid_synthesis_references = {
        "proposals": [
            {"number": 1, "id": gemma_proposal["id"]},
            {"number": 2, "id": qwen_proposal["id"]},
        ],
        "critiques": [
            qwen_assessment["critique"]["id"],
            gemma_assessment["critique"]["id"],
        ],
        "suggested_changes": [
            {"number": number, "id": change["id"]}
            for number, change in enumerate(suggested_changes, start=1)
        ],
    }

    if suggested_changes:
        disposition_response = call(
            "director_change_disposition",
            render_change_disposition_messages(
                frozen_request,
                gemma_proposal=gemma_proposal,
                qwen_proposal=qwen_proposal,
                qwen_assessment=qwen_assessment,
                gemma_assessment=gemma_assessment,
            ),
            change_disposition_response_format(),
            producer_context=director_ref,
        )
        change_dispositions = resolve_semantic_artifact(
            artifact_kind="director_change_disposition",
            producer_context=director_ref,
            initial_response=disposition_response,
            valid_references=valid_synthesis_references,
            required_output=CHANGE_DISPOSITION_SEMANTIC_SHAPE,
            response_format=change_disposition_response_format(),
            validator=lambda semantics: validate_change_disposition_semantics(
                semantics,
                suggested_change_count=suggested_change_count,
            ),
        )
    else:
        change_dispositions = {"dispositions": []}

    overall_response = call(
        "director_overall_synthesis",
        render_overall_synthesis_messages(
            frozen_request,
            gemma_proposal=gemma_proposal,
            qwen_proposal=qwen_proposal,
            qwen_assessment=qwen_assessment,
            gemma_assessment=gemma_assessment,
            change_dispositions=change_dispositions,
        ),
        overall_synthesis_response_format(),
        producer_context=director_ref,
    )
    overall_synthesis = resolve_semantic_artifact(
        artifact_kind="director_overall_synthesis",
        producer_context=director_ref,
        initial_response=overall_response,
        valid_references=valid_synthesis_references,
        required_output=OVERALL_SYNTHESIS_SEMANTIC_SHAPE,
        response_format=overall_synthesis_response_format(),
        validator=validate_overall_synthesis_semantics,
    )

    steps_response = call(
        "director_plan_steps",
        render_plan_steps_messages(
            frozen_request,
            gemma_proposal=gemma_proposal,
            qwen_proposal=qwen_proposal,
            qwen_assessment=qwen_assessment,
            gemma_assessment=gemma_assessment,
            change_dispositions=change_dispositions,
            overall_synthesis=overall_synthesis,
        ),
        plan_steps_response_format(),
        producer_context=director_ref,
    )
    plan_steps = resolve_semantic_artifact(
        artifact_kind="director_plan_steps",
        producer_context=director_ref,
        initial_response=steps_response,
        valid_references=valid_synthesis_references,
        required_output=PLAN_STEPS_SEMANTIC_SHAPE,
        response_format=plan_steps_response_format(),
        validator=validate_plan_steps_semantics,
    )
    synthesis_semantics = combine_synthesis_semantics(
        change_dispositions,
        overall_synthesis,
        plan_steps,
        suggested_change_count=suggested_change_count,
    )

    def structurally_certify_plan(
        semantics: Mapping[str, Any],
        *,
        certification_attempt: int,
    ) -> dict[str, Any]:
        candidate = assemble_final_plan(
            semantics,
            plan_id=selected_plan_id,
            current_work_ref=current_work_ref,
            director_ref=director_ref,
            proposals=(gemma_proposal, qwen_proposal),
            assessments=(qwen_assessment, gemma_assessment),
        )
        plan_issues = validate_final_plan(
            candidate,
            plan_id=selected_plan_id,
            current_work_ref=current_work_ref,
            director_ref=director_ref,
            proposals=(gemma_proposal, qwen_proposal),
            assessments=(qwen_assessment, gemma_assessment),
            require_pending_validation=True,
        )
        if plan_issues:
            details = "; ".join(
                f"{issue.field}: {issue.message}" for issue in plan_issues
            )
            raise ValueError(f"Invalid assembled final Plan: {details}")
        certified = certify_final_plan(candidate)
        structural_certifications.append({
            "attempt": certification_attempt,
            "revision_ref": certified["revision_ref"],
            "valid": True,
            "issues": [],
        })
        return certified

    acceptance_policy = semantic_architecture_acceptance_policy()
    if (
        acceptance_policy.get("requires_structural_certification") is not True
        or acceptance_policy.get("assessor_has_decision_authority") is not False
        or acceptance_policy.get("advances_semantic_iteration") is not False
        or acceptance_policy.get("acceptance_requires_compliant") is not True
    ):
        raise RuntimeError("Unsupported semantic architecture acceptance policy.")
    assessor_context = NORMAL_PLANNING_CONTEXTS["architecture_assessment"]

    def assess_architecture(
        plan: Mapping[str, Any],
        *,
        assessment_attempt: int,
    ) -> dict[str, Any]:
        response = call(
            (
                "architecture_assessment"
                if assessment_attempt == 1
                else "architecture_reassessment"
            ),
            render_architecture_assessment_messages(candidate_plan=plan),
            architecture_assessment_response_format(),
            producer_context=assessor_context,
        )
        semantics = resolve_semantic_artifact(
            artifact_kind=f"architecture_assessment_{assessment_attempt}",
            producer_context=assessor_context,
            initial_response=response,
            valid_references={
                "plan_id": plan["plan_id"],
                "revision_ref": plan["revision_ref"],
                "step_ids": [step["id"] for step in plan["steps"]],
            },
            required_output=ARCHITECTURE_ASSESSMENT_SEMANTIC_SHAPE,
            response_format=architecture_assessment_response_format(),
            validator=validate_architecture_assessment_semantics,
        )
        record = {
            "id": (
                f"{selected_plan_id}:architecture-assessment-"
                f"{assessment_attempt}"
            ),
            "iteration": 2,
            "assessor_ref": assessor_context,
            "candidate_revision_ref": plan["revision_ref"],
            "compliant": semantics["compliant"],
            "violations": deepcopy(semantics["violations"]),
        }
        architecture_assessments.append(record)
        return semantics

    initial_candidate_plan = structurally_certify_plan(
        synthesis_semantics,
        certification_attempt=1,
    )
    architecture_assessment = assess_architecture(
        initial_candidate_plan,
        assessment_attempt=1,
    )
    if architecture_assessment["compliant"]:
        final_plan = initial_candidate_plan
    else:
        correction_policy = semantic_boundary_correction_policy()
        if (
            correction_policy.get("maximum_attempts_per_plan") != 1
            or correction_policy.get("consumes_reasoning_task") is not True
            or correction_policy.get("advances_semantic_iteration") is not False
            or correction_policy.get("same_director") is not True
            or correction_policy.get("semantic_change_scope")
            != "identified_architecture_violations_only"
        ):
            raise RuntimeError("Unsupported semantic boundary correction policy.")
        correction_response = call(
            "director_semantic_boundary_correction",
            render_semantic_boundary_correction_messages(
                candidate_plan=initial_candidate_plan,
                architecture_violations=architecture_assessment[
                    "violations"
                ],
                overall_synthesis=overall_synthesis,
                plan_steps=plan_steps,
            ),
            semantic_boundary_correction_response_format(),
            producer_context=director_ref,
        )
        corrected_semantics = resolve_semantic_artifact(
            artifact_kind="director_semantic_boundary_correction",
            producer_context=director_ref,
            initial_response=correction_response,
            valid_references={
                "plan_id": initial_candidate_plan["plan_id"],
                "revision_ref": initial_candidate_plan["revision_ref"],
                "step_ids": [
                    step["id"] for step in initial_candidate_plan["steps"]
                ],
            },
            required_output=SEMANTIC_BOUNDARY_CORRECTION_SHAPE,
            response_format=semantic_boundary_correction_response_format(),
            validator=validate_semantic_boundary_correction_semantics,
        )
        semantic_boundary_corrections.append({
            "attempt": 1,
            "producer_context": director_ref,
            "violations": deepcopy(architecture_assessment["violations"]),
            "corrected_semantics": deepcopy(corrected_semantics),
        })
        overall_synthesis = corrected_semantics["overall_synthesis"]
        plan_steps = corrected_semantics["plan_steps"]
        synthesis_semantics = combine_synthesis_semantics(
            change_dispositions,
            overall_synthesis,
            plan_steps,
            suggested_change_count=suggested_change_count,
        )
        corrected_candidate_plan = structurally_certify_plan(
            synthesis_semantics,
            certification_attempt=2,
        )
        second_assessment = assess_architecture(
            corrected_candidate_plan,
            assessment_attempt=2,
        )
        if not second_assessment["compliant"]:
            details = "; ".join(
                violation["finding"]
                for violation in second_assessment["violations"]
            )
            raise ValueError(
                "Corrected Plan remains semantically noncompliant after one "
                f"boundary correction: {details}"
            )
        final_plan = corrected_candidate_plan
    advance("validated_final_plan")

    return {
        "frozen_request": frozen_request,
        "gemma_proposal": deepcopy(gemma_proposal),
        "qwen_proposal": deepcopy(qwen_proposal),
        "qwen_assessment": deepcopy(qwen_assessment),
        "gemma_assessment": deepcopy(gemma_assessment),
        "change_dispositions": deepcopy(change_dispositions),
        "overall_synthesis": deepcopy(overall_synthesis),
        "plan_steps": deepcopy(plan_steps),
        "synthesis_semantics": deepcopy(synthesis_semantics),
        "initial_candidate_plan": deepcopy(initial_candidate_plan),
        "final_plan": final_plan,
        "calls": calls,
        "semantic_completions": semantic_completions,
        "conformance_repairs": conformance_repairs,
        "architecture_assessments": architecture_assessments,
        "semantic_boundary_corrections": semantic_boundary_corrections,
        "structural_certifications": structural_certifications,
        "reasoning_task_count": reasoning_tasks,
        "semantic_iteration_count": semantic_iterations,
        "semantic_advancements": advancements,
        "plan_validation": {"valid": True, "issues": []},
        "architecture_acceptance": {
            "compliant": True,
            "assessment_count": len(architecture_assessments),
            "violations": [],
        },
    }
