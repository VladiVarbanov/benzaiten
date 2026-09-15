"""Validated Python adapter for the authoritative DirectorTask protocol."""

from __future__ import annotations

from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

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


DIRECTOR_TASK_SELECTION_FIELD_NAMES = frozenset({
    "selected_step_number", "capability", "participant_role", "objective",
    "instruction", "action", "anchors", "entities", "focus", "reason",
    "requirements", "acceptance", "selected_input_numbers",
    "output_contract_kind",
})

DIRECTOR_TASK_SELECTION_SEMANTIC_SHAPE: Mapping[str, object] = {
    "selected_step_number": "<number from eligible_steps>",
    "selected_input_numbers": ["<number from available_inputs>"],
    "output_contract_kind": "<text | json_object>",
    "capability": "<DirectorTask capability vocabulary value>",
    "participant_role": "<configured semantic participant role>",
    "objective": "<semantic outcome needed from the selected step>",
    "instruction": "<bounded instruction for this execution>",
    "action": "<DirectorTask semantic operation vocabulary value>",
    "anchors": [{"kind": "<anchor kind>", "value": "<stable point>"}],
    "entities": [{"kind": "<entity kind>", "name": "<named thing>"}],
    "focus": {
        "questions": ["<question>"],
        "angles": ["<angle>"],
        "granularity": "<coarse | medium | fine>",
    },
    "reason": "<why this task should execute now>",
    "requirements": ["<execution requirement>"],
    "acceptance": "<observable acceptance criterion>",
}


def _selection_string(value: object, field: str) -> list[ValidationIssue]:
    if not isinstance(value, str) or not value.strip():
        return [_issue(
            field, "invalid_shape", f"{field} must be a non-empty string.",
        )]
    return []


def validate_director_task_selection_semantics(
    data: object,
    *,
    eligible_step_numbers: Sequence[int],
    available_input_numbers: Sequence[int] = (1,),
    plan_input_number_by_step: Optional[Mapping[int, int]] = None,
    configured_participant_roles: Optional[Sequence[str]] = None,
) -> tuple[ValidationIssue, ...]:
    """Validate only Director-authored step selection and task semantics."""

    if not isinstance(data, Mapping):
        return (_issue(
            "director_task_selection", "invalid_shape",
            "Director task selection must be an object.",
        ),)

    issues: list[ValidationIssue] = []
    keys = set(data)
    for name in sorted(keys - DIRECTOR_TASK_SELECTION_FIELD_NAMES):
        issues.append(_issue(
            f"director_task_selection.{name}", "unknown_field",
            f"Unknown Director task-selection field: {name}",
        ))
    for name in sorted(DIRECTOR_TASK_SELECTION_FIELD_NAMES - keys):
        issues.append(_issue(
            f"director_task_selection.{name}", "required",
            f"Missing Director task-selection field: {name}",
        ))

    selected = data.get("selected_step_number")
    if isinstance(selected, bool) or not isinstance(selected, int):
        issues.append(_issue(
            "director_task_selection.selected_step_number", "invalid_shape",
            "selected_step_number must be an integer.",
        ))
    elif selected not in set(eligible_step_numbers):
        issues.append(_issue(
            "director_task_selection.selected_step_number", "invalid_reference",
            "selected_step_number must identify an eligible Plan step.",
        ))

    selected_inputs = data.get("selected_input_numbers")
    valid_input_numbers = set(available_input_numbers)
    if (
        not isinstance(selected_inputs, list)
        or not selected_inputs
        or any(
            isinstance(number, bool) or not isinstance(number, int)
            for number in selected_inputs
        )
    ):
        issues.append(_issue(
            "director_task_selection.selected_input_numbers",
            "invalid_shape",
            "selected_input_numbers must be a non-empty integer array.",
        ))
    elif len(set(selected_inputs)) != len(selected_inputs):
        issues.append(_issue(
            "director_task_selection.selected_input_numbers",
            "duplicate_reference",
            "selected_input_numbers must not contain duplicates.",
        ))
    else:
        unknown_inputs = set(selected_inputs) - valid_input_numbers
        if unknown_inputs:
            issues.append(_issue(
                "director_task_selection.selected_input_numbers",
                "invalid_reference",
                "selected_input_numbers must identify available inputs.",
            ))
        required_plan_input = (
            plan_input_number_by_step.get(selected)
            if plan_input_number_by_step is not None
            and isinstance(selected, int)
            and selected in plan_input_number_by_step
            else (1 if plan_input_number_by_step is None else None)
        )
        if (
            required_plan_input is not None
            and required_plan_input not in selected_inputs
        ):
            issues.append(_issue(
                "director_task_selection.selected_input_numbers",
                "missing_plan_input",
                "The selected Plan step's target input is required.",
            ))

    for name in ("objective", "instruction", "reason", "acceptance"):
        issues.extend(_selection_string(
            data.get(name), f"director_task_selection.{name}",
        ))
    issues.extend(_validate_string_array(
        data.get("requirements"), "director_task_selection.requirements",
    ))

    for field_name, vocabulary_name in {
        "capability": "capability",
        "participant_role": "participant_role",
        "action": "semantic_operation",
        "output_contract_kind": "output_contract_kind",
    }.items():
        value = data.get(field_name)
        if not isinstance(value, str) or not value.strip():
            issues.append(_issue(
                f"director_task_selection.{field_name}", "invalid_shape",
                f"{field_name} must be a non-empty string.",
            ))
        elif value not in _allowed(vocabulary_name):
            issues.append(_issue(
                f"director_task_selection.{field_name}", "invalid_vocabulary",
                f"{field_name} must be one of "
                f"{sorted(_allowed(vocabulary_name))}.",
            ))

    role = data.get("participant_role")
    if (
        configured_participant_roles is not None
        and isinstance(role, str)
        and role not in set(configured_participant_roles)
    ):
        issues.append(_issue(
            "director_task_selection.participant_role", "unconfigured_role",
            "participant_role must resolve through current configuration.",
        ))

    for field_name, expected in (
        ("anchors", frozenset({"kind", "value"})),
        ("entities", frozenset({"kind", "name"})),
    ):
        value = data.get(field_name)
        if not isinstance(value, list):
            issues.append(_issue(
                f"director_task_selection.{field_name}", "invalid_shape",
                f"{field_name} must be an array.",
            ))
        else:
            for index, item in enumerate(value):
                issues.extend(_validate_record(
                    item,
                    f"director_task_selection.{field_name}[{index}]",
                    expected,
                ))

    focus = data.get("focus")
    if not isinstance(focus, Mapping):
        issues.append(_issue(
            "director_task_selection.focus", "invalid_shape",
            "focus must be an object.",
        ))
    else:
        expected_focus = frozenset({"questions", "angles", "granularity"})
        for name in sorted(set(focus) - expected_focus):
            issues.append(_issue(
                f"director_task_selection.focus.{name}", "unknown_field",
                f"Unknown focus field: {name}",
            ))
        for name in sorted(expected_focus - set(focus)):
            issues.append(_issue(
                f"director_task_selection.focus.{name}", "required",
                f"Missing focus field: {name}",
            ))
        for name in ("questions", "angles"):
            issues.extend(_validate_string_array(
                focus.get(name), f"director_task_selection.focus.{name}",
            ))
        if focus.get("granularity") not in _allowed("granularity"):
            issues.append(_issue(
                "director_task_selection.focus.granularity",
                "invalid_vocabulary",
                "focus.granularity must use the DirectorTask vocabulary.",
            ))
    return tuple(issues)


def _certified_plan_handoff_issues(
    plan: object,
) -> tuple[ValidationIssue, ...]:
    if not isinstance(plan, Mapping):
        return (_issue(
            "plan", "invalid_shape", "Certified Plan must be an object.",
        ),)

    issues: list[ValidationIssue] = []
    revision_ref = plan.get("revision_ref")
    if not isinstance(revision_ref, str) or not revision_ref.strip():
        issues.append(_issue(
            "plan.revision_ref", "required",
            "Certified Plan requires revision_ref.",
        ))
    if plan.get("status") != "final":
        issues.append(_issue(
            "plan.status", "not_final",
            "Only a final Plan may cross into execution.",
        ))
    final = plan.get("final")
    if (
        not isinstance(final, Mapping)
        or final.get("is_final") is not True
        or final.get("selected_revision_ref") != revision_ref
    ):
        issues.append(_issue(
            "plan.final", "not_final",
            "Plan finality must select the current revision.",
        ))
    integrity = plan.get("integrity")
    validation = (
        integrity.get("validation") if isinstance(integrity, Mapping) else None
    )
    if (
        not isinstance(validation, Mapping)
        or validation.get("status") != "valid"
        or validation.get("validated_by_ref")
        != "deterministic_plan_validator"
        or validation.get("errors") != []
    ):
        issues.append(_issue(
            "plan.integrity.validation", "not_certified",
            "Plan must carry valid deterministic structural certification.",
        ))
    if not isinstance(plan.get("steps"), list) or not plan["steps"]:
        issues.append(_issue(
            "plan.steps", "required",
            "Certified Plan requires executable steps.",
        ))
    return tuple(issues)


def eligible_plan_steps(
    certified_plan: object,
    *,
    completed_step_refs: Sequence[str] = (),
) -> tuple[Mapping[str, object], ...]:
    """Mechanically identify steps whose recorded dependencies are complete."""

    issues = _certified_plan_handoff_issues(certified_plan)
    if issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in issues
        )
        raise ValueError(f"Invalid certified Plan handoff: {details}")
    assert isinstance(certified_plan, Mapping)
    completed = set(completed_step_refs)
    eligible = tuple(
        step
        for step in certified_plan["steps"]
        if isinstance(step, Mapping)
        and step.get("status") == "proposed"
        and step.get("task_ref") is None
        and isinstance(step.get("depends_on"), list)
        and all(reference in completed for reference in step["depends_on"])
    )
    if not eligible:
        raise ValueError(
            "Certified Plan has no currently eligible unassigned step."
        )
    return eligible


def director_task_selection_response_format(
    *,
    eligible_step_numbers: Sequence[int],
    available_input_numbers: Sequence[int] = (1,),
    configured_participant_roles: Sequence[str],
) -> dict[str, object]:
    """Return the exact JSON Schema for Director-authored task semantics."""

    string_array = {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
    }

    def record_array(second: str) -> dict[str, object]:
        return {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "minLength": 1},
                    second: {"type": "string", "minLength": 1},
                },
                "required": ["kind", second],
                "additionalProperties": False,
            },
        }

    properties: dict[str, object] = {
        "selected_step_number": {
            "type": "integer", "enum": list(eligible_step_numbers),
        },
        "selected_input_numbers": {
            "type": "array",
            "items": {
                "type": "integer", "enum": list(available_input_numbers),
            },
            "minItems": 1,
            "uniqueItems": True,
        },
        "capability": {
            "type": "string", "enum": sorted(_allowed("capability")),
        },
        "participant_role": {
            "type": "string", "enum": sorted(configured_participant_roles),
        },
        "objective": {"type": "string", "minLength": 1},
        "instruction": {"type": "string", "minLength": 1},
        "action": {
            "type": "string",
            "enum": sorted(_allowed("semantic_operation")),
        },
        "output_contract_kind": {
            "type": "string",
            "enum": sorted(_allowed("output_contract_kind")),
        },
        "anchors": record_array("value"),
        "entities": record_array("name"),
        "focus": {
            "type": "object",
            "properties": {
                "questions": string_array,
                "angles": string_array,
                "granularity": {
                    "type": "string",
                    "enum": sorted(_allowed("granularity")),
                },
            },
            "required": ["questions", "angles", "granularity"],
            "additionalProperties": False,
        },
        "reason": {"type": "string", "minLength": 1},
        "requirements": string_array,
        "acceptance": {"type": "string", "minLength": 1},
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "director_task_selection_v0",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": sorted(DIRECTOR_TASK_SELECTION_FIELD_NAMES),
                "additionalProperties": False,
            },
        },
    }


def render_director_task_selection_messages(
    *,
    certified_plan: Mapping[str, object],
    eligible_steps: Sequence[Mapping[str, object]],
    available_inputs: Sequence[Mapping[str, object]],
    revision_evidence: Optional[Mapping[str, object]] = None,
) -> tuple[dict[str, str], ...]:
    """Project only certified Plan facts needed for semantic task selection."""

    import json

    plan_final = certified_plan["final"]
    assert isinstance(plan_final, Mapping)
    projection = {
        "plan_id": certified_plan["plan_id"],
        "revision_ref": certified_plan["revision_ref"],
        "goal": certified_plan["goal"],
        "approach_summary": certified_plan["approach_summary"],
        "current_work_ref": certified_plan["current_work_ref"],
        "final": {
            "selected_revision_ref": plan_final["selected_revision_ref"],
            "unresolved_risks": plan_final["unresolved_risks"],
            "unresolved_questions": plan_final["unresolved_questions"],
        },
        "eligible_steps": [
            {
                "number": step["index"],
                "id": step["id"],
                "action": step["action"],
                "reason": step["reason"],
                "target_ref": step["target_ref"],
                "instructions": step["instructions"],
                "scope_boundary": step["scope_boundary"],
                "expected_result": step["expected_result"],
                "validation": step["validation"],
            }
            for step in eligible_steps
        ],
    }
    user_content: dict[str, object] = {
        "certified_plan_projection": projection,
        "available_inputs": [
            {
                "number": item["number"],
                "kind": item["kind"],
                "name": item["name"],
                "description": item["description"],
            }
            for item in available_inputs
        ],
        "required_output": DIRECTOR_TASK_SELECTION_SEMANTIC_SHAPE,
        "trusted_fields_assigned_by_python": [
            "task_id", "job_ref", "work_kind", "plan_ref",
            "input_refs", "target", "output_contract_ref",
            "external_authority_ref",
        ],
    }
    if revision_evidence is None:
        direction = (
            "Select the semantically appropriate eligible Plan step and "
            "author only its execution-task semantics."
        )
    else:
        direction = (
            "Revise the execution-task semantics for the one supplied Plan "
            "step using only the bounded evidence. Preserve the Plan step and "
            "its expected result."
        )
        user_content["bounded_revision_evidence"] = dict(revision_evidence)

    return (
        {
            "role": "system",
            "content": (
                f"You are the configured Benzaiten Director. {direction} "
                "The Plan is passive. Do not choose a concrete model, logical "
                "context, endpoint, host, fallback, or different Plan step. "
                "Return exactly one JSON object with the required fields and "
                "no prose."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(user_content, sort_keys=True),
        },
    )


def assemble_director_task(
    semantics: Mapping[str, object],
    *,
    certified_plan: Mapping[str, object],
    selected_step: Mapping[str, object],
    available_inputs: Sequence[Mapping[str, object]],
    job_ref: str,
    task_id: str,
) -> dict[str, object]:
    """Wrap Director semantics in trusted DirectorTask protocol identity."""

    from config import MANAGED_OUTPUT_CONTRACTS

    contract_kind = semantics["output_contract_kind"]
    try:
        output_contract_ref = MANAGED_OUTPUT_CONTRACTS[contract_kind]["ref"]
    except KeyError as exc:
        raise ValueError(
            f"Unconfigured managed output contract: {contract_kind}"
        ) from exc

    return {
        "task_id": task_id,
        "job_ref": job_ref,
        "capability": semantics["capability"],
        "participant_role": semantics["participant_role"],
        "objective": semantics["objective"],
        "input_refs": [
            next(
                item["ref"] for item in available_inputs
                if item["number"] == number
            )
            for number in semantics["selected_input_numbers"]
        ],
        "instruction": semantics["instruction"],
        "work_kind": "execution",
        "plan_ref": certified_plan["revision_ref"],
        "action": semantics["action"],
        "target": {
            "kind": "plan_step", "locator": selected_step["id"],
        },
        "anchors": list(semantics["anchors"]),
        "entities": list(semantics["entities"]),
        "focus": dict(semantics["focus"]),
        "reason": semantics["reason"],
        "requirements": list(semantics["requirements"]),
        "acceptance": semantics["acceptance"],
        "output_contract_ref": output_contract_ref,
        "external_authority_ref": None,
    }


def validate_director_task_for_execution(
    task: object,
    *,
    certified_plan: Mapping[str, object],
    selected_step: Mapping[str, object],
    job_ref: str,
    trusted_input_refs: Optional[Sequence[str]] = None,
    trusted_output_contract_ref: Optional[str] = None,
) -> tuple[ValidationIssue, ...]:
    """Validate the DirectorTask protocol plus the active Plan handoff."""

    issues = list(validate_director_task_mapping(task))
    issues.extend(_certified_plan_handoff_issues(certified_plan))
    if not isinstance(task, Mapping):
        return tuple(issues)

    expected_inputs = list(
        [selected_step.get("target_ref")]
        if trusted_input_refs is None
        else trusted_input_refs
    )
    from config import MANAGED_OUTPUT_CONTRACTS

    configured_contract_refs = {
        contract["ref"] for contract in MANAGED_OUTPUT_CONTRACTS.values()
    }
    expected = {
        "job_ref": job_ref,
        "plan_ref": certified_plan.get("revision_ref"),
        "work_kind": "execution",
        "target": {
            "kind": "plan_step", "locator": selected_step.get("id"),
        },
        "input_refs": expected_inputs,
        "external_authority_ref": None,
    }
    for name, value in expected.items():
        if task.get(name) != value:
            issues.append(_issue(
                name, "handoff_mismatch",
                f"{name} must match the trusted selected-Plan-step handoff.",
            ))
    actual_contract_ref = task.get("output_contract_ref")
    if trusted_output_contract_ref is not None:
        if actual_contract_ref != trusted_output_contract_ref:
            issues.append(_issue(
                "output_contract_ref", "handoff_mismatch",
                "output_contract_ref must match Python's trusted mapping.",
            ))
    elif actual_contract_ref not in configured_contract_refs:
        issues.append(_issue(
            "output_contract_ref", "unconfigured_contract",
            "Executable output contract must resolve through configuration.",
        ))
    acceptance = task.get("acceptance")
    if not isinstance(acceptance, str) or not acceptance.strip():
        issues.append(_issue(
            "acceptance", "required_for_execution",
            "Executable managed work requires an acceptance criterion.",
        ))

    from config import PARTICIPANT_ROLE_CONTEXTS
    if task.get("participant_role") not in PARTICIPANT_ROLE_CONTEXTS:
        issues.append(_issue(
            "participant_role", "unconfigured_role",
            "Executable participant role must resolve through configuration.",
        ))
    return tuple(issues)


_RESOURCE_INPUT_KINDS = frozenset({"supplied", "vault", "source", "web"})


def numbered_managed_inputs(
    eligible_steps: Sequence[Mapping[str, object]],
    available_resources: Sequence[Mapping[str, object]] = (),
) -> tuple[dict[str, object], ...]:
    """Assign trusted numbers without exposing resource mechanics to Director."""

    if not eligible_steps:
        raise ValueError("Managed input numbering requires eligible Plan steps.")
    numbered: list[dict[str, object]] = []
    seen: set[str] = set()
    for selected_step in eligible_steps:
        target_ref = selected_step.get("target_ref")
        step_number = selected_step.get("index")
        if (
            not isinstance(target_ref, str)
            or not target_ref.strip()
            or isinstance(step_number, bool)
            or not isinstance(step_number, int)
        ):
            raise ValueError("Eligible Plan step requires index and target_ref.")
        if target_ref in seen:
            raise ValueError("Eligible Plan steps must not reuse target_ref.")
        seen.add(target_ref)
        numbered.append({
            "number": len(numbered) + 1,
            "ref": target_ref,
            "kind": "supplied",
            "name": f"Plan step {step_number} target",
            "description": "The input named by this eligible Plan step.",
            "plan_step_number": step_number,
        })
    expected_fields = {"ref", "kind", "name", "description"}
    for resource in available_resources:
        if not isinstance(resource, Mapping) or set(resource) != expected_fields:
            raise ValueError(
                "Managed resource descriptors require exactly ref, kind, "
                "name, and description."
            )
        if resource.get("kind") not in _RESOURCE_INPUT_KINDS - {"supplied"}:
            raise ValueError("Managed resource kind must be vault, source, or web.")
        if any(
            not isinstance(resource.get(name), str)
            or not resource[name].strip()
            for name in expected_fields
        ):
            raise ValueError("Managed resource descriptor values must be non-empty.")
        reference = str(resource["ref"])
        if reference in seen:
            raise ValueError(f"Duplicate managed resource reference: {reference}")
        if not reference.startswith(f"{resource['kind']}:"):
            raise ValueError(
                "Managed resource reference must use its declared kind prefix."
            )
        seen.add(reference)
        numbered.append({"number": len(numbered) + 1, **dict(resource)})
    return tuple(numbered)


def select_director_task(
    certified_plan: Mapping[str, object],
    *,
    job_ref: str,
    model_caller: object = None,
    completed_step_refs: Sequence[str] = (),
    fixed_step_ref: Optional[str] = None,
    revision_evidence: Optional[Mapping[str, object]] = None,
    available_resources: Sequence[Mapping[str, object]] = (),
    task_id: Optional[str] = None,
    reasoning_task_count: int = 0,
    reasoning_task_limit: Optional[int] = None,
) -> Mapping[str, object]:
    """Ask the configured Director to select a step and emit task semantics."""

    from copy import deepcopy
    from uuid import uuid4

    from config import (
        DEFAULT_JOB_BUDGET,
        DIRECTOR_CONTEXT,
        PARTICIPANT_ROLE_CONTEXTS,
    )
    from model_client import ModelResponse
    from orchestrator import invoke_model_context, resolve_model_context
    from planning import parse_json_object, render_conformance_repair_messages

    if not isinstance(job_ref, str) or not job_ref.strip():
        raise ValueError("job_ref must be a non-empty string.")
    limit = (
        DEFAULT_JOB_BUDGET["reasoning_tasks"]
        if reasoning_task_limit is None
        else reasoning_task_limit
    )
    if (
        isinstance(reasoning_task_count, bool)
        or not isinstance(reasoning_task_count, int)
        or reasoning_task_count < 0
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
    ):
        raise ValueError(
            "Reasoning-task counts must be non-negative integers."
        )

    candidates = eligible_plan_steps(
        certified_plan, completed_step_refs=completed_step_refs,
    )
    if revision_evidence is not None and fixed_step_ref is None:
        raise ValueError(
            "Bounded task revision requires one fixed selected step."
        )
    if fixed_step_ref is not None:
        candidates = tuple(
            step for step in candidates if step.get("id") == fixed_step_ref
        )
        if len(candidates) != 1:
            raise ValueError(
                "Fixed revision step must be one currently eligible Plan step."
            )
    artifact_kind = (
        "director_task_revision"
        if revision_evidence is not None
        else "director_task_selection"
    )
    candidate_numbers = tuple(int(step["index"]) for step in candidates)
    input_catalog = numbered_managed_inputs(candidates, available_resources)
    input_numbers = tuple(int(item["number"]) for item in input_catalog)
    plan_input_numbers = {
        int(item["plan_step_number"]): int(item["number"])
        for item in input_catalog
        if "plan_step_number" in item
    }
    configured_roles = tuple(sorted(PARTICIPANT_ROLE_CONTEXTS))
    response_format = director_task_selection_response_format(
        eligible_step_numbers=candidate_numbers,
        available_input_numbers=input_numbers,
        configured_participant_roles=configured_roles,
    )
    messages = render_director_task_selection_messages(
        certified_plan=certified_plan,
        eligible_steps=candidates,
        available_inputs=input_catalog,
        revision_evidence=revision_evidence,
    )
    caller = invoke_model_context if model_caller is None else model_caller
    if not callable(caller):
        raise TypeError("model_caller must be callable.")

    assignment = resolve_model_context(DIRECTOR_CONTEXT)
    assert assignment.model is not None
    calls: list[dict[str, object]] = []
    repairs: list[dict[str, object]] = []

    def call(
        stage: str,
        selected_messages: tuple[dict[str, str], ...],
    ) -> ModelResponse:
        nonlocal reasoning_task_count
        if reasoning_task_count >= limit:
            raise RuntimeError("Reasoning-task budget exhausted.")
        reasoning_task_count += 1
        selected_format = (
            response_format if assignment.model.supports_json_schema else None
        )
        template_kwargs = (
            assignment.model.structured_output_chat_template_kwargs
            if selected_format is not None
            else None
        )
        response = caller(
            DIRECTOR_CONTEXT,
            selected_messages,
            response_format=selected_format,
            chat_template_kwargs=template_kwargs,
        )
        if not isinstance(response, ModelResponse):
            raise TypeError("Director model caller must return ModelResponse.")
        calls.append({
            "stage": stage,
            "logical_context": DIRECTOR_CONTEXT,
            "model_name": assignment.model.model_name,
            "node": assignment.model.node,
            "endpoint_url": assignment.model.endpoint_url,
            "request_id": response.request_id,
            "reasoning_task": reasoning_task_count,
        })
        return response

    current_response = call(artifact_kind, messages)
    attempt = 0
    while True:
        try:
            semantics = parse_json_object(
                current_response.text,
                stage="Director task selection",
            )
            semantic_issues = validate_director_task_selection_semantics(
                semantics,
                eligible_step_numbers=candidate_numbers,
                available_input_numbers=input_numbers,
                plan_input_number_by_step=plan_input_numbers,
                configured_participant_roles=configured_roles,
            )
        except ValueError as exc:
            semantics = None
            semantic_issues = (_issue(
                "director_task_selection", "invalid_shape", str(exc),
            ),)
        if not semantic_issues:
            assert semantics is not None
            break
        if attempt >= 1:
            details = "; ".join(
                f"{item.field}: {item.message}" for item in semantic_issues
            )
            raise ValueError(
                "Director task selection remains invalid after one "
                f"conformance repair: {details}"
            )

        attempt += 1
        repair_messages = render_conformance_repair_messages(
            artifact_kind=artifact_kind,
            invalid_output=current_response.text,
            validation_issues=semantic_issues,
            valid_references={
                "eligible_steps": [
                    {"number": step["index"], "id": step["id"]}
                    for step in candidates
                ],
                "configured_participant_roles": list(configured_roles),
                "available_inputs": [
                    {
                        "number": item["number"],
                        "kind": item["kind"],
                        "name": item["name"],
                    }
                    for item in input_catalog
                ],
            },
            required_output=DIRECTOR_TASK_SELECTION_SEMANTIC_SHAPE,
        )
        repaired = call(
            f"{artifact_kind}_conformance_repair",
            repair_messages,
        )
        repairs.append({
            "artifact_kind": artifact_kind,
            "attempt": attempt,
            "producer_context": DIRECTOR_CONTEXT,
            "invalid_output": current_response.text,
            "validation_issues": [
                {
                    "field": item.field,
                    "code": item.code,
                    "message": item.message,
                }
                for item in semantic_issues
            ],
            "repaired_output": repaired.text,
        })
        current_response = repaired

    selected_step = next(
        step for step in candidates
        if step["index"] == semantics["selected_step_number"]
    )
    selected_task_id = task_id or f"{job_ref}:task-{uuid4().hex}"
    task = assemble_director_task(
        semantics,
        certified_plan=certified_plan,
        selected_step=selected_step,
        available_inputs=input_catalog,
        job_ref=job_ref,
        task_id=selected_task_id,
    )
    task_issues = validate_director_task_for_execution(
        task,
        certified_plan=certified_plan,
        selected_step=selected_step,
        job_ref=job_ref,
        trusted_input_refs=task["input_refs"],
        trusted_output_contract_ref=task["output_contract_ref"],
    )
    if task_issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in task_issues
        )
        raise ValueError(f"Invalid assembled DirectorTask: {details}")
    parse_director_task(task)
    return {
        "selected_step": deepcopy(dict(selected_step)),
        "director_task": deepcopy(task),
        "selection_semantics": deepcopy(dict(semantics)),
        "available_inputs": deepcopy(input_catalog),
        "trusted_input_refs": list(task["input_refs"]),
        "trusted_output_contract_ref": task["output_contract_ref"],
        "calls": calls,
        "conformance_repairs": repairs,
        "reasoning_task_count": reasoning_task_count,
    }


DIRECTOR_EVALUATION_FIELD_NAMES = frozenset({
    "decision", "reason", "evidence_numbers", "continue_work",
    "backtrack_checkpoint_number", "guidance",
})

DIRECTOR_GUIDANCE_FIELD_NAMES = frozenset({
    "hurdle", "materiality", "attempts", "remaining_unresolved",
    "evidence_numbers", "options", "recommendation", "question",
    "target",
})
DIRECTOR_GUIDANCE_SEMANTIC_SHAPE: Mapping[str, object] = {
    "hurdle": "<material semantic hurdle>",
    "materiality": "<why the hurdle blocks responsible continuation>",
    "attempts": [{
        "description": "<reasonable attempt already made>",
        "established": "<what the attempt established>",
        "evidence_numbers": [1],
    }],
    "remaining_unresolved": "<smallest unresolved issue>",
    "evidence_numbers": [1],
    "options": ["<plausible option>"],
    "recommendation": "<Director recommendation>",
    "question": "<smallest useful question>",
    "target": "<user | frontier>",
}

DIRECTOR_EVALUATION_SEMANTIC_SHAPE: Mapping[str, object] = {
    "decision": "<ACCEPT | REVISE | ASK_GUIDANCE>",
    "reason": "<concise evidence-based judgment>",
    "evidence_numbers": [1],
    "continue_work": False,
    "backtrack_checkpoint_number": None,
    "guidance": DIRECTOR_GUIDANCE_SEMANTIC_SHAPE,
}


def director_evaluation_response_format(
    *,
    valid_evidence_numbers: Sequence[int] = (1,),
    valid_checkpoint_numbers: Sequence[int] = (1,),
    allow_ask_guidance: bool = False,
) -> dict[str, object]:
    """Return exact structured output for the Director evidence judgment."""

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "managed_work_director_evaluation_v0",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "decision": {
                        "type": "string",
                        "enum": [
                            "ACCEPT", "REVISE",
                            *(["ASK_GUIDANCE"] if allow_ask_guidance else []),
                        ],
                    },
                    "reason": {"type": "string", "minLength": 1},
                    "evidence_numbers": {
                        "type": "array",
                        "items": {
                            "type": "integer",
                            "enum": list(valid_evidence_numbers),
                        },
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                    "continue_work": {"type": "boolean"},
                    "backtrack_checkpoint_number": {
                        "anyOf": [
                            {
                                "type": "integer",
                                "enum": list(valid_checkpoint_numbers),
                            },
                            {"type": "null"},
                        ],
                    },
                    "guidance": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "hurdle": {"type": "string", "minLength": 1},
                                    "materiality": {"type": "string", "minLength": 1},
                                    "attempts": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "description": {
                                                    "type": "string", "minLength": 1,
                                                },
                                                "established": {
                                                    "type": "string", "minLength": 1,
                                                },
                                                "evidence_numbers": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "integer",
                                                        "enum": list(valid_evidence_numbers),
                                                    },
                                                    "uniqueItems": True,
                                                },
                                            },
                                            "required": [
                                                "description", "established",
                                                "evidence_numbers",
                                            ],
                                            "additionalProperties": False,
                                        },
                                    },
                                    "remaining_unresolved": {
                                        "type": "string", "minLength": 1,
                                    },
                                    "evidence_numbers": {
                                        "type": "array",
                                        "items": {
                                            "type": "integer",
                                            "enum": list(valid_evidence_numbers),
                                        },
                                        "uniqueItems": True,
                                    },
                                    "options": {
                                        "type": "array",
                                        "items": {"type": "string", "minLength": 1},
                                    },
                                    "recommendation": {
                                        "type": "string", "minLength": 1,
                                    },
                                    "question": {"type": "string", "minLength": 1},
                                    "target": {
                                        "type": "string",
                                        "enum": ["user", "frontier"],
                                    },
                                },
                                "required": sorted(DIRECTOR_GUIDANCE_FIELD_NAMES),
                                "additionalProperties": False,
                            },
                            {"type": "null"},
                        ],
                    },
                },
                "required": sorted(DIRECTOR_EVALUATION_FIELD_NAMES),
                "additionalProperties": False,
            },
        },
    }


def validate_director_evaluation_semantics(
    data: object,
    *,
    valid_evidence_numbers: Sequence[int] = (1,),
    valid_checkpoint_numbers: Sequence[int] = (1,),
    allow_ask_guidance: bool = False,
) -> tuple[ValidationIssue, ...]:
    """Validate only the Director-authored ACCEPT/REVISE judgment."""

    if not isinstance(data, Mapping):
        return (_issue(
            "director_evaluation", "invalid_shape",
            "Director evaluation must be an object.",
        ),)
    issues: list[ValidationIssue] = []
    for name in sorted(set(data) - DIRECTOR_EVALUATION_FIELD_NAMES):
        issues.append(_issue(
            f"director_evaluation.{name}", "unknown_field",
            f"Unknown Director evaluation field: {name}",
        ))
    for name in sorted(DIRECTOR_EVALUATION_FIELD_NAMES - set(data)):
        issues.append(_issue(
            f"director_evaluation.{name}", "required",
            f"Missing Director evaluation field: {name}",
        ))

    decision = data.get("decision")
    allowed_decisions = {"ACCEPT", "REVISE"}
    if allow_ask_guidance:
        allowed_decisions.add("ASK_GUIDANCE")
    if decision not in allowed_decisions:
        issues.append(_issue(
            "director_evaluation.decision", "invalid_vocabulary",
            "decision is not enabled for this managed-work seam.",
        ))
    issues.extend(_selection_string(data.get("reason"), "director_evaluation.reason"))
    evidence_numbers = data.get("evidence_numbers")
    valid_evidence = set(valid_evidence_numbers)
    if (
        not isinstance(evidence_numbers, list)
        or not evidence_numbers
        or any(
            isinstance(number, bool) or not isinstance(number, int)
            for number in evidence_numbers
        )
    ):
        issues.append(_issue(
            "director_evaluation.evidence_numbers", "invalid_shape",
            "evidence_numbers must be a non-empty integer array.",
        ))
    elif (
        len(evidence_numbers) != len(set(evidence_numbers))
        or any(number not in valid_evidence for number in evidence_numbers)
    ):
        issues.append(_issue(
            "director_evaluation.evidence_numbers", "invalid_reference",
            "evidence_numbers must uniquely identify supplied evidence.",
        ))
    continue_work = data.get("continue_work")
    if not isinstance(continue_work, bool):
        issues.append(_issue(
            "director_evaluation.continue_work", "invalid_shape",
            "continue_work must be boolean.",
        ))
    backtrack_number = data.get("backtrack_checkpoint_number")
    if decision == "REVISE":
        if (
            isinstance(backtrack_number, bool)
            or not isinstance(backtrack_number, int)
            or backtrack_number not in set(valid_checkpoint_numbers)
        ):
            issues.append(_issue(
                "director_evaluation.backtrack_checkpoint_number",
                "invalid_reference",
                "REVISE must select one supplied accepted checkpoint.",
            ))
        if continue_work is not True:
            issues.append(_issue(
                "director_evaluation.continue_work", "invalid_semantics",
                "REVISE always requests successor Plan semantics.",
            ))
    elif backtrack_number is not None:
        issues.append(_issue(
            "director_evaluation.backtrack_checkpoint_number",
            "invalid_semantics",
            "ACCEPT and ASK_GUIDANCE must not select a backtracking checkpoint.",
        ))
    guidance = data.get("guidance")
    if decision == "ASK_GUIDANCE":
        if continue_work is not False:
            issues.append(_issue(
                "director_evaluation.continue_work", "invalid_semantics",
                "ASK_GUIDANCE pauses without creating a successor Plan.",
            ))
        issues.extend(_validate_director_guidance_semantics(
            guidance,
            valid_evidence_numbers=valid_evidence_numbers,
        ))
    elif guidance is not None:
        issues.append(_issue(
            "director_evaluation.guidance", "invalid_semantics",
            "Only ASK_GUIDANCE may contain guidance semantics.",
        ))
    return tuple(issues)


def _validate_director_guidance_semantics(
    guidance: object,
    *,
    valid_evidence_numbers: Sequence[int],
) -> tuple[ValidationIssue, ...]:
    field = "director_evaluation.guidance"
    if not isinstance(guidance, Mapping):
        return (_issue(
            field, "invalid_shape", "ASK_GUIDANCE guidance must be an object.",
        ),)
    issues: list[ValidationIssue] = []
    for name in sorted(set(guidance) - DIRECTOR_GUIDANCE_FIELD_NAMES):
        issues.append(_issue(
            f"{field}.{name}", "unknown_field",
            f"Unknown guidance field: {name}",
        ))
    for name in sorted(DIRECTOR_GUIDANCE_FIELD_NAMES - set(guidance)):
        issues.append(_issue(
            f"{field}.{name}", "required",
            f"Missing required guidance field: {name}",
        ))
    for name in (
        "hurdle", "materiality", "remaining_unresolved",
        "recommendation", "question",
    ):
        issues.extend(_selection_string(guidance.get(name), f"{field}.{name}"))
    options = guidance.get("options")
    if not isinstance(options, list) or any(
        not isinstance(item, str) or not item.strip() for item in options
    ):
        issues.append(_issue(
            f"{field}.options", "invalid_shape",
            "Guidance options must be an array of non-empty strings.",
        ))
    valid_numbers = set(valid_evidence_numbers)

    def validate_numbers(value: object, number_field: str) -> None:
        if not isinstance(value, list) or any(
            isinstance(number, bool) or not isinstance(number, int)
            for number in value
        ):
            issues.append(_issue(
                number_field, "invalid_shape",
                "Evidence numbers must be an integer array.",
            ))
        elif (
            len(value) != len(set(value))
            or any(number not in valid_numbers for number in value)
        ):
            issues.append(_issue(
                number_field, "invalid_reference",
                "Evidence numbers must uniquely identify supplied evidence.",
            ))

    validate_numbers(
        guidance.get("evidence_numbers"), f"{field}.evidence_numbers",
    )
    attempts = guidance.get("attempts")
    if not isinstance(attempts, list):
        issues.append(_issue(
            f"{field}.attempts", "invalid_shape",
            "Guidance attempts must be an array.",
        ))
    else:
        expected_attempt_fields = frozenset({
            "description", "established", "evidence_numbers",
        })
        for index, attempt in enumerate(attempts):
            attempt_field = f"{field}.attempts[{index}]"
            if not isinstance(attempt, Mapping):
                issues.append(_issue(
                    attempt_field, "invalid_shape",
                    "Guidance attempt must be an object.",
                ))
                continue
            for name in sorted(set(attempt) - expected_attempt_fields):
                issues.append(_issue(
                    f"{attempt_field}.{name}", "unknown_field",
                    f"Unknown guidance attempt field: {name}",
                ))
            for name in sorted(expected_attempt_fields - set(attempt)):
                issues.append(_issue(
                    f"{attempt_field}.{name}", "required",
                    f"Missing guidance attempt field: {name}",
                ))
            for name in ("description", "established"):
                issues.extend(_selection_string(
                    attempt.get(name), f"{attempt_field}.{name}",
                ))
            validate_numbers(
                attempt.get("evidence_numbers"),
                f"{attempt_field}.evidence_numbers",
            )
    if guidance.get("target") not in {"user", "frontier"}:
        issues.append(_issue(
            f"{field}.target", "invalid_vocabulary",
            "Guidance target must be user or frontier.",
        ))
    return tuple(issues)


def render_director_evaluation_messages(
    *,
    certified_plan: Mapping[str, object],
    selected_step: Mapping[str, object],
    director_task: Mapping[str, object],
    task_execution: Mapping[str, object],
    numbered_evidence: Sequence[Mapping[str, object]],
    numbered_accepted_checkpoints: Sequence[Mapping[str, object]],
    allow_ask_guidance: bool = False,
) -> tuple[dict[str, str], ...]:
    """Project only evidence needed for the Director judgment."""

    import json

    plan_execution = task_execution["plan_execution"]
    assert isinstance(plan_execution, Mapping)
    required_output = dict(DIRECTOR_EVALUATION_SEMANTIC_SHAPE)
    if not allow_ask_guidance:
        required_output["decision"] = "<ACCEPT | REVISE>"
        required_output["guidance"] = None
    projection = {
        "certified_plan": {
            "plan_id": certified_plan["plan_id"],
            "revision_ref": certified_plan["revision_ref"],
            "goal": certified_plan["goal"],
        },
        "selected_step": {
            "id": selected_step["id"],
            "action": selected_step["action"],
            "instructions": selected_step["instructions"],
            "scope_boundary": selected_step["scope_boundary"],
            "expected_result": selected_step["expected_result"],
            "validation": selected_step["validation"],
        },
        "director_task": {
            "task_id": director_task["task_id"],
            "objective": director_task["objective"],
            "input_refs": director_task["input_refs"],
            "instruction": director_task["instruction"],
            "action": director_task["action"],
            "target": director_task["target"],
            "requirements": director_task["requirements"],
            "acceptance": director_task["acceptance"],
            "output_contract_ref": director_task["output_contract_ref"],
        },
        "task_execution": {
            "execution_id": task_execution["execution_id"],
            "control": task_execution["control"],
            "resolved": task_execution["resolved"],
            "result": task_execution["result"],
            "error": task_execution["error"],
            "achieved_result": plan_execution["achieved_result"],
            "deviation": plan_execution["deviation"],
            "validation_outcome": plan_execution["validation_outcome"],
            "validation_evidence_refs": (
                plan_execution["validation_evidence_refs"]
            ),
        },
        "numbered_evidence": [dict(item) for item in numbered_evidence],
        "numbered_accepted_checkpoints": [
            dict(item) for item in numbered_accepted_checkpoints
        ],
        "required_output": required_output,
    }
    return (
        {
            "role": "system",
            "content": (
                "You are the configured Benzaiten Director. Judge the selected "
                "TaskExecution evidence against the certified Plan step. Return "
                "ACCEPT or REVISE and a concise reason. Select evidence only by "
                "its supplied number. ACCEPT may stop or request continued "
                "semantic work. REVISE is semantic, always requests a successor "
                "Plan, and must select one supplied accepted checkpoint by "
                "number. REVISE is not representation repair or transport retry. "
                + (
                    "ASK_GUIDANCE is available only for a material unresolved "
                    "hurdle, pauses without a successor, and requires the complete "
                    "guidance record. "
                    if allow_ask_guidance else
                    "ASK_GUIDANCE is unavailable because no persistence seam was supplied. "
                )
                +
                "Do not choose a model, context, endpoint, host, or fallback. "
                "Return exactly one JSON object with no prose."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(projection, sort_keys=True),
        },
    )


def _task_execution_handoff_issues(
    task_execution: object,
    *,
    director_task: Mapping[str, object],
    certified_plan: Mapping[str, object],
    selected_step: Mapping[str, object],
) -> tuple[ValidationIssue, ...]:
    from task_execution import validate_task_execution_mapping

    issues = list(validate_task_execution_mapping(task_execution))
    if not isinstance(task_execution, Mapping):
        return tuple(issues)
    plan_execution = task_execution.get("plan_execution")
    expected = {
        "task_ref": director_task.get("task_id"),
        "job_ref": director_task.get("job_ref"),
    }
    for name, value in expected.items():
        if task_execution.get(name) != value:
            issues.append(_issue(
                f"task_execution.{name}", "reference_mismatch",
                f"TaskExecution {name} does not match the DirectorTask.",
            ))
    if isinstance(plan_execution, Mapping):
        if plan_execution.get("plan_ref") != certified_plan.get(
            "revision_ref"
        ):
            issues.append(_issue(
                "task_execution.plan_execution.plan_ref",
                "reference_mismatch",
                "TaskExecution does not identify the certified Plan revision.",
            ))
        if plan_execution.get("current_step_ref") != selected_step.get("id"):
            issues.append(_issue(
                "task_execution.plan_execution.current_step_ref",
                "reference_mismatch",
                "TaskExecution does not identify the selected Plan step.",
            ))
    return tuple(issues)


def evaluate_task_execution(
    task_execution: Mapping[str, object],
    *,
    certified_plan: Mapping[str, object],
    selected_step: Mapping[str, object],
    director_task: Mapping[str, object],
    plan_history: Optional[Sequence[Mapping[str, object]]] = None,
    accepted_checkpoints: Optional[
        Sequence[Mapping[str, object]]
    ] = None,
    accepted_outcomes_by_ref: Optional[
        Mapping[str, Mapping[str, object]]
    ] = None,
    allow_ask_guidance: bool = False,
    guidance_policy: str = "USER_ONLY",
    frontier_authorized: bool = False,
    model_caller: object = None,
    outcome_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    reasoning_task_count: int = 0,
    reasoning_task_limit: Optional[int] = None,
) -> Mapping[str, object]:
    """Obtain and record one configured Director execution judgment."""

    from copy import deepcopy
    from datetime import datetime, timezone
    from uuid import uuid4

    from config import (
        DEFAULT_JOB_BUDGET,
        DIRECTOR_CONTEXT,
        FRONTIER_GUIDANCE_PROVIDER,
    )
    from model_client import ModelResponse
    from orchestrator import (
        invoke_model_context,
        resolve_guidance_target,
        resolve_model_context,
        validate_guidance_authorization,
    )
    from planning import (
        parse_json_object,
        render_conformance_repair_messages,
        root_checkpoint_evidence_refs,
        validate_planning_root_checkpoint,
    )
    from task_execution import (
        validate_task_execution_checkpoint_context,
        validate_task_execution_mapping,
    )

    issues = _task_execution_handoff_issues(
        task_execution,
        director_task=director_task,
        certified_plan=certified_plan,
        selected_step=selected_step,
    )
    if issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in issues
        )
        raise ValueError(
            f"Director evaluation rejected TaskExecution evidence: {details}"
        )
    authorization_errors = validate_guidance_authorization(
        guidance_policy, frontier_authorized,
    )
    if authorization_errors:
        raise ValueError(
            "Invalid guidance authorization: "
            + "; ".join(authorization_errors)
        )

    history = tuple(plan_history or (certified_plan,))
    if not history or history[-1].get("revision_ref") != certified_plan.get(
        "revision_ref"
    ):
        raise ValueError(
            "Director evaluation Plan history must end at the evaluated Plan."
        )
    plans_by_ref = {
        str(plan["revision_ref"]): plan
        for plan in history
        if isinstance(plan.get("revision_ref"), str)
    }
    accepted_outcomes = dict(accepted_outcomes_by_ref or {})
    if accepted_checkpoints is None:
        root = history[0]
        root_issues = validate_planning_root_checkpoint(root)
        if root_issues:
            details = "; ".join(
                f"{item.field}: {item.message}" for item in root_issues
            )
            raise ValueError(
                f"Director evaluation lacks a valid root checkpoint: {details}"
            )
        checkpoint_records = [{
            "kind": "root",
            "revision_ref": root["revision_ref"],
            "outcome_ref": None,
            "evidence_refs": list(root_checkpoint_evidence_refs(root)),
        }]
    else:
        checkpoint_records = [
            deepcopy(dict(item)) for item in accepted_checkpoints
        ]
    if not checkpoint_records:
        raise ValueError(
            "Director evaluation requires at least the certified root checkpoint."
        )
    for index, checkpoint in enumerate(checkpoint_records, start=1):
        if set(checkpoint) != {
            "kind", "revision_ref", "outcome_ref", "evidence_refs",
        }:
            raise ValueError(
                f"Accepted checkpoint {index} has an invalid trusted shape."
            )
        revision_ref = checkpoint["revision_ref"]
        if revision_ref not in plans_by_ref:
            raise ValueError(
                f"Accepted checkpoint {index} references unknown Plan history."
            )
        outcome_ref = checkpoint["outcome_ref"]
        if outcome_ref is None:
            root_issues = validate_planning_root_checkpoint(
                plans_by_ref[revision_ref]
            )
            if root_issues or checkpoint["kind"] != "root":
                raise ValueError(
                    "Only the planning-certified @r1 may be a root checkpoint."
                )
            required = set(root_checkpoint_evidence_refs(
                plans_by_ref[revision_ref]
            ))
            if not required.issubset(checkpoint["evidence_refs"]):
                raise ValueError(
                    "Root checkpoint lacks planning certification evidence."
                )
        else:
            accepted = accepted_outcomes.get(outcome_ref)
            if (
                checkpoint["kind"] != "execution"
                or not isinstance(accepted, Mapping)
                or accepted.get("decision") != "ACCEPT"
                or accepted.get("checkpoint_revision_ref") != revision_ref
            ):
                raise ValueError(
                    "Execution checkpoint must resolve to a real ACCEPT outcome."
                )

    numbered_checkpoints = [
        {
            "number": index,
            "kind": checkpoint["kind"],
            "revision_ref": checkpoint["revision_ref"],
            "outcome_ref": checkpoint["outcome_ref"],
            "evidence_refs": list(checkpoint["evidence_refs"]),
        }
        for index, checkpoint in enumerate(checkpoint_records, start=1)
    ]
    numbered_evidence = [{
        "number": 1,
        "kind": "task_execution",
        "ref": task_execution["execution_id"],
    }]
    evidence_refs_by_number = {
        int(item["number"]): str(item["ref"])
        for item in numbered_evidence
    }

    limit = (
        DEFAULT_JOB_BUDGET["reasoning_tasks"]
        if reasoning_task_limit is None
        else reasoning_task_limit
    )
    if (
        isinstance(reasoning_task_count, bool)
        or not isinstance(reasoning_task_count, int)
        or reasoning_task_count < 0
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
    ):
        raise ValueError(
            "Reasoning-task counts must be non-negative integers."
        )
    caller = invoke_model_context if model_caller is None else model_caller
    if not callable(caller):
        raise TypeError("model_caller must be callable.")

    assignment = resolve_model_context(DIRECTOR_CONTEXT)
    assert assignment.model is not None
    valid_evidence_numbers = tuple(evidence_refs_by_number)
    valid_checkpoint_numbers = tuple(
        int(item["number"]) for item in numbered_checkpoints
    )
    response_format = director_evaluation_response_format(
        valid_evidence_numbers=valid_evidence_numbers,
        valid_checkpoint_numbers=valid_checkpoint_numbers,
        allow_ask_guidance=allow_ask_guidance,
    )
    messages = render_director_evaluation_messages(
        certified_plan=certified_plan,
        selected_step=selected_step,
        director_task=director_task,
        task_execution=task_execution,
        numbered_evidence=numbered_evidence,
        numbered_accepted_checkpoints=numbered_checkpoints,
        allow_ask_guidance=allow_ask_guidance,
    )
    calls: list[dict[str, object]] = []
    repairs: list[dict[str, object]] = []

    def call(
        stage: str,
        selected_messages: tuple[dict[str, str], ...],
    ) -> ModelResponse:
        nonlocal reasoning_task_count
        if reasoning_task_count >= limit:
            raise RuntimeError("Reasoning-task budget exhausted.")
        reasoning_task_count += 1
        selected_format = (
            response_format if assignment.model.supports_json_schema else None
        )
        template_kwargs = (
            assignment.model.structured_output_chat_template_kwargs
            if selected_format is not None
            else None
        )
        response = caller(
            DIRECTOR_CONTEXT,
            selected_messages,
            response_format=selected_format,
            chat_template_kwargs=template_kwargs,
        )
        if not isinstance(response, ModelResponse):
            raise TypeError(
                "Director evaluation caller must return ModelResponse."
            )
        calls.append({
            "stage": stage,
            "logical_context": DIRECTOR_CONTEXT,
            "model_name": assignment.model.model_name,
            "node": assignment.model.node,
            "endpoint_url": assignment.model.endpoint_url,
            "request_id": response.request_id,
            "reasoning_task": reasoning_task_count,
        })
        return response

    current_response = call("director_execution_evaluation", messages)
    attempt = 0
    while True:
        try:
            semantics = parse_json_object(
                current_response.text,
                stage="Director execution evaluation",
            )
            evaluation_issues = validate_director_evaluation_semantics(
                semantics,
                valid_evidence_numbers=valid_evidence_numbers,
                valid_checkpoint_numbers=valid_checkpoint_numbers,
                allow_ask_guidance=allow_ask_guidance,
            )
        except ValueError as exc:
            semantics = None
            evaluation_issues = (_issue(
                "director_evaluation", "invalid_shape", str(exc),
            ),)
        if not evaluation_issues:
            assert semantics is not None
            break
        if attempt >= 1:
            details = "; ".join(
                f"{item.field}: {item.message}"
                for item in evaluation_issues
            )
            raise ValueError(
                "Director evaluation remains invalid after one "
                f"conformance repair: {details}"
            )

        attempt += 1
        repair_messages = render_conformance_repair_messages(
            artifact_kind="director_execution_evaluation",
            invalid_output=current_response.text,
            validation_issues=evaluation_issues,
            valid_references={
                "plan_ref": certified_plan["revision_ref"],
                "step_ref": selected_step["id"],
                "task_ref": director_task["task_id"],
                "execution_ref": task_execution["execution_id"],
                "evidence": numbered_evidence,
                "accepted_checkpoints": numbered_checkpoints,
            },
            required_output={
                **DIRECTOR_EVALUATION_SEMANTIC_SHAPE,
                **({} if allow_ask_guidance else {
                    "decision": "<ACCEPT | REVISE>",
                    "guidance": None,
                }),
            },
        )
        repaired = call(
            "director_execution_evaluation_conformance_repair",
            repair_messages,
        )
        repairs.append({
            "artifact_kind": "director_execution_evaluation",
            "attempt": attempt,
            "producer_context": DIRECTOR_CONTEXT,
            "invalid_output": current_response.text,
            "validation_issues": [
                {
                    "field": item.field,
                    "code": item.code,
                    "message": item.message,
                }
                for item in evaluation_issues
            ],
            "repaired_output": repaired.text,
        })
        current_response = repaired

    decided_at = (
        timestamp or datetime.now(timezone.utc).isoformat()
    )
    evaluated = deepcopy(dict(task_execution))
    plan_execution = evaluated["plan_execution"]
    selected_outcome_id = (
        outcome_id
        or f"{task_execution['execution_id']}:outcome-{uuid4().hex}"
    )
    selected_evidence_refs = [
        evidence_refs_by_number[number]
        for number in semantics["evidence_numbers"]
    ]
    if semantics["decision"] == "ACCEPT":
        evidence_refs = selected_evidence_refs
        checkpoint_revision_ref = certified_plan["revision_ref"]
        checkpoint_outcome_ref = selected_outcome_id
        guidance_record = None
    elif semantics["decision"] == "REVISE":
        checkpoint = checkpoint_records[
            semantics["backtrack_checkpoint_number"] - 1
        ]
        checkpoint_revision_ref = checkpoint["revision_ref"]
        checkpoint_outcome_ref = checkpoint["outcome_ref"]
        evidence_refs = list(dict.fromkeys([
            *selected_evidence_refs,
            *checkpoint["evidence_refs"],
        ]))
        guidance_record = None
    else:
        checkpoint = checkpoint_records[-1]
        checkpoint_revision_ref = checkpoint["revision_ref"]
        checkpoint_outcome_ref = checkpoint["outcome_ref"]
        evidence_refs = list(dict.fromkeys([
            *selected_evidence_refs,
            *checkpoint["evidence_refs"],
        ]))
        guidance_semantics = semantics["guidance"]

        def mapped_evidence(numbers: Sequence[int]) -> list[str]:
            return [
                evidence_refs_by_number[number] for number in numbers
            ]

        guidance_record = {
            "hurdle": guidance_semantics["hurdle"],
            "materiality": guidance_semantics["materiality"],
            "attempts": [
                {
                    "description": attempt["description"],
                    "established": attempt["established"],
                    "evidence_refs": mapped_evidence(
                        attempt["evidence_numbers"]
                    ),
                }
                for attempt in guidance_semantics["attempts"]
            ],
            "remaining_unresolved": guidance_semantics[
                "remaining_unresolved"
            ],
            "evidence_refs": mapped_evidence(
                guidance_semantics["evidence_numbers"]
            ),
            "options": list(guidance_semantics["options"]),
            "recommendation": guidance_semantics["recommendation"],
            "question": guidance_semantics["question"],
            "target": resolve_guidance_target(
                guidance_semantics["target"],
                guidance_policy=guidance_policy,
                frontier_authorized=frontier_authorized,
                frontier_provider_ref=FRONTIER_GUIDANCE_PROVIDER,
            ),
            "policy": guidance_policy,
            "frontier_authorized": frontier_authorized,
        }
    plan_execution["outcomes"].append({
        "id": selected_outcome_id,
        "decision": semantics["decision"],
        "reason": semantics["reason"],
        "evidence_refs": evidence_refs,
        "checkpoint_revision_ref": checkpoint_revision_ref,
        "checkpoint_outcome_ref": checkpoint_outcome_ref,
        "resulting_plan_ref": None,
        "guidance": guidance_record,
        "decided_by_ref": DIRECTOR_CONTEXT,
        "created_at": decided_at,
        "task_ref": director_task["task_id"],
        "execution_ref": task_execution["execution_id"],
    })
    plan_execution["replan_requested"] = semantics["decision"] == "REVISE"
    plan_execution["replan_reason"] = (
        semantics["reason"] if semantics["decision"] == "REVISE" else None
    )
    plan_execution["persistence"]["updated_at"] = decided_at
    evaluated["provenance"]["updated_at"] = decided_at

    final_issues = validate_task_execution_mapping(evaluated)
    if final_issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in final_issues
        )
        raise ValueError(
            f"Invalid evaluated TaskExecution: {details}"
        )
    checkpoint_issues = validate_task_execution_checkpoint_context(
        evaluated,
        plans_by_ref=plans_by_ref,
        accepted_outcomes_by_ref=accepted_outcomes,
    )
    if checkpoint_issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in checkpoint_issues
        )
        raise ValueError(
            f"Invalid evaluated TaskExecution checkpoint: {details}"
        )
    if semantics["decision"] == "ACCEPT":
        disposition = (
            "accepted_continue"
            if semantics["continue_work"]
            else "accepted"
        )
    elif semantics["decision"] == "REVISE":
        disposition = "revise"
    else:
        disposition = "awaiting_guidance"
    return {
        "task_execution": evaluated,
        "evaluation_semantics": deepcopy(dict(semantics)),
        "disposition": disposition,
        "calls": calls,
        "conformance_repairs": repairs,
        "reasoning_task_count": reasoning_task_count,
        "semantic_iteration_advanced": False,
    }
def _revision_evidence_projection(
    *,
    director_task: Mapping[str, object],
    evaluated_execution: Mapping[str, object],
) -> dict[str, object]:
    plan_execution = evaluated_execution["plan_execution"]
    assert isinstance(plan_execution, Mapping)
    outcomes = plan_execution["outcomes"]
    assert isinstance(outcomes, list) and outcomes
    return {
        "prior_director_task": {
            "task_id": director_task["task_id"],
            "objective": director_task["objective"],
            "instruction": director_task["instruction"],
            "action": director_task["action"],
            "requirements": director_task["requirements"],
            "acceptance": director_task["acceptance"],
        },
        "prior_task_execution": {
            "execution_id": evaluated_execution["execution_id"],
            "control": evaluated_execution["control"],
            "result": evaluated_execution["result"],
            "error": evaluated_execution["error"],
            "achieved_result": plan_execution["achieved_result"],
            "deviation": plan_execution["deviation"],
            "validation_outcome": plan_execution["validation_outcome"],
        },
        "director_evaluation": dict(outcomes[-1]),
    }


def request_successor_plan_semantics(
    *,
    current_plan: Mapping[str, object],
    checkpoint_plan: Mapping[str, object],
    evaluated_execution: Mapping[str, object],
    evaluation_outcome: Mapping[str, object],
    model_caller: object = None,
    reasoning_task_count: int = 0,
    reasoning_task_limit: Optional[int] = None,
) -> Mapping[str, object]:
    """Ask the Director for semantics of one immutable successor Plan node."""

    import json

    from config import DEFAULT_JOB_BUDGET, DIRECTOR_CONTEXT
    from model_client import ModelResponse
    from orchestrator import invoke_model_context, resolve_model_context
    from planning import (
        OVERALL_SYNTHESIS_SEMANTIC_SHAPE,
        PLAN_STEPS_SEMANTIC_SHAPE,
        parse_json_object,
        render_conformance_repair_messages,
        successor_plan_response_format,
        validate_successor_plan_semantics,
    )

    limit = (
        DEFAULT_JOB_BUDGET["reasoning_tasks"]
        if reasoning_task_limit is None
        else reasoning_task_limit
    )
    if (
        isinstance(reasoning_task_count, bool)
        or not isinstance(reasoning_task_count, int)
        or reasoning_task_count < 0
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
    ):
        raise ValueError("Reasoning-task counts must be non-negative integers.")
    caller = invoke_model_context if model_caller is None else model_caller
    if not callable(caller):
        raise TypeError("model_caller must be callable.")
    assignment = resolve_model_context(DIRECTOR_CONTEXT)
    assert assignment.model is not None
    response_format = successor_plan_response_format()
    required_output = {
        "overall_synthesis": OVERALL_SYNTHESIS_SEMANTIC_SHAPE,
        "plan_steps": PLAN_STEPS_SEMANTIC_SHAPE,
    }
    plan_execution = evaluated_execution["plan_execution"]
    projection = {
        "current_plan": {
            "plan_id": current_plan["plan_id"],
            "revision_ref": current_plan["revision_ref"],
            "goal": current_plan["goal"],
            "approach_summary": current_plan["approach_summary"],
            "steps": current_plan["steps"],
        },
        "selected_checkpoint": {
            "revision_ref": checkpoint_plan["revision_ref"],
            "goal": checkpoint_plan["goal"],
            "approach_summary": checkpoint_plan["approach_summary"],
            "steps": checkpoint_plan["steps"],
        },
        "triggering_execution": {
            "execution_id": evaluated_execution["execution_id"],
            "result": evaluated_execution["result"],
            "error": evaluated_execution["error"],
            "achieved_result": plan_execution["achieved_result"],
            "deviation": plan_execution["deviation"],
            "validation_outcome": plan_execution["validation_outcome"],
        },
        "triggering_outcome": dict(evaluation_outcome),
        "required_output": required_output,
    }
    messages = (
        {
            "role": "system",
            "content": (
                "You are the configured Benzaiten Director. Create only the "
                "semantic content for one successor Plan state using the "
                "selected accepted checkpoint and execution evidence. Preserve "
                "the managed mandate. Do not assign IDs, revision numbers, "
                "references, timestamps, models, contexts, endpoints, hosts, "
                "fallbacks, or persistence. rejected_alternatives must be an "
                "empty array unless one of the two original proposal branches "
                "is semantically rejected. Return exactly one JSON object with "
                "overall_synthesis and plan_steps and no prose."
            ),
        },
        {"role": "user", "content": json.dumps(projection, sort_keys=True)},
    )
    calls: list[dict[str, object]] = []
    repairs: list[dict[str, object]] = []

    def call(
        stage: str,
        selected_messages: tuple[dict[str, str], ...],
    ) -> ModelResponse:
        nonlocal reasoning_task_count
        if reasoning_task_count >= limit:
            raise RuntimeError("Reasoning-task budget exhausted.")
        reasoning_task_count += 1
        selected_format = (
            response_format if assignment.model.supports_json_schema else None
        )
        template_kwargs = (
            assignment.model.structured_output_chat_template_kwargs
            if selected_format is not None
            else None
        )
        response = caller(
            DIRECTOR_CONTEXT,
            selected_messages,
            response_format=selected_format,
            chat_template_kwargs=template_kwargs,
        )
        if not isinstance(response, ModelResponse):
            raise TypeError(
                "Successor Plan caller must return ModelResponse."
            )
        calls.append({
            "stage": stage,
            "logical_context": DIRECTOR_CONTEXT,
            "model_name": assignment.model.model_name,
            "node": assignment.model.node,
            "endpoint_url": assignment.model.endpoint_url,
            "request_id": response.request_id,
            "reasoning_task": reasoning_task_count,
        })
        return response

    current_response = call("director_successor_plan", messages)
    attempt = 0
    while True:
        try:
            semantics = parse_json_object(
                current_response.text, stage="Director successor Plan",
            )
            semantic_issues = validate_successor_plan_semantics(semantics)
        except ValueError as exc:
            semantics = None
            semantic_issues = (_issue(
                "successor_plan_semantics", "invalid_shape", str(exc),
            ),)
        if not semantic_issues:
            assert semantics is not None
            break
        if attempt >= 1:
            details = "; ".join(
                f"{item.field}: {item.message}" for item in semantic_issues
            )
            raise ValueError(
                "Director successor Plan remains invalid after one "
                f"conformance repair: {details}"
            )
        attempt += 1
        repair_messages = render_conformance_repair_messages(
            artifact_kind="director_successor_plan",
            invalid_output=current_response.text,
            validation_issues=semantic_issues,
            valid_references={
                "current_plan_ref": current_plan["revision_ref"],
                "checkpoint_revision_ref": checkpoint_plan["revision_ref"],
                "execution_ref": evaluated_execution["execution_id"],
                "outcome_ref": evaluation_outcome["id"],
            },
            required_output=required_output,
        )
        repaired = call(
            "director_successor_plan_conformance_repair", repair_messages,
        )
        repairs.append({
            "artifact_kind": "director_successor_plan",
            "attempt": attempt,
            "producer_context": DIRECTOR_CONTEXT,
            "invalid_output": current_response.text,
            "validation_issues": [
                {
                    "field": item.field,
                    "code": item.code,
                    "message": item.message,
                }
                for item in semantic_issues
            ],
            "repaired_output": repaired.text,
        })
        current_response = repaired

    return {
        "successor_semantics": semantics,
        "calls": calls,
        "conformance_repairs": repairs,
        "reasoning_task_count": reasoning_task_count,
    }


def run_iteration_3(
    certified_plan: Mapping[str, object],
    *,
    job_ref: str,
    resolved_inputs: Mapping[str, object],
    available_resources: Sequence[Mapping[str, object]] = (),
    model_caller: object = None,
    web_caller: object = None,
    reasoning_task_count: int = 0,
    reasoning_task_limit: Optional[int] = None,
    semantic_iteration_count: int = 3,
    task_ids: Sequence[str] = (),
    execution_ids: Sequence[str] = (),
    outcome_ids: Sequence[str] = (),
    timestamp: Optional[str] = None,
    artifact_root: Optional[Path] = None,
    guidance_policy: str = "USER_ONLY",
    frontier_authorized: bool = False,
) -> Mapping[str, object]:
    """Run revision-bounded managed execution over immutable Plan nodes."""

    from copy import deepcopy

    from config import DEFAULT_JOB_BUDGET, DIRECTOR_CONTEXT
    from orchestrator import (
        execute_managed_director_task,
        persist_managed_work_run,
        validate_guidance_authorization,
    )
    from planning import (
        assemble_successor_plan,
        certify_final_plan,
        execution_transition_budget_state,
        root_checkpoint_evidence_refs,
        validate_planning_root_checkpoint,
        validate_successor_plan,
    )
    from task_execution import (
        validate_task_execution_checkpoint_context,
        validate_task_execution_mapping,
    )

    if semantic_iteration_count != DEFAULT_JOB_BUDGET[
        "semantic_iterations"
    ]:
        raise ValueError(
            "Iteration 3 requires the certified Plan at semantic iteration 3."
        )
    authorization_errors = validate_guidance_authorization(
        guidance_policy, frontier_authorized,
    )
    if authorization_errors:
        raise ValueError(
            "Invalid guidance authorization: "
            + "; ".join(authorization_errors)
        )
    if artifact_root is None and (
        guidance_policy != "USER_ONLY"
        or frontier_authorized
    ):
        raise ValueError(
            "Non-default frontier policy requires persisted managed-work state."
        )
    selected_task_ids = tuple(task_ids)
    selected_execution_ids = tuple(execution_ids)
    selected_outcome_ids = tuple(outcome_ids)

    def requested_id(values: Sequence[str], index: int) -> Optional[str]:
        return values[index] if index < len(values) else None

    calls: list[dict[str, object]] = []
    repairs: list[dict[str, object]] = []
    tasks: list[dict[str, object]] = []
    executions: list[dict[str, object]] = []
    evaluations: list[dict[str, object]] = []
    plan_history: list[dict[str, object]] = [
        deepcopy(dict(certified_plan))
    ]
    root_issues = validate_planning_root_checkpoint(plan_history[0])
    if root_issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in root_issues
        )
        raise ValueError(
            f"Iteration 3 requires a planning-certified @r1 root: {details}"
        )
    accepted_checkpoints: list[dict[str, object]] = [{
        "kind": "root",
        "revision_ref": plan_history[0]["revision_ref"],
        "outcome_ref": None,
        "evidence_refs": list(root_checkpoint_evidence_refs(plan_history[0])),
    }]
    accepted_outcomes: dict[str, dict[str, object]] = {}
    selected_step: Mapping[str, object] | None = None
    work_index = 0

    while True:
        current_plan = plan_history[-1]
        selection = select_director_task(
            current_plan,
            job_ref=job_ref,
            model_caller=model_caller,
            available_resources=available_resources,
            task_id=requested_id(selected_task_ids, work_index),
            reasoning_task_count=reasoning_task_count,
            reasoning_task_limit=reasoning_task_limit,
        )
        reasoning_task_count = selection["reasoning_task_count"]
        selected_step = selection["selected_step"]
        current_task = selection["director_task"]
        tasks.append(deepcopy(current_task))
        calls.extend(selection["calls"])
        repairs.extend(selection["conformance_repairs"])

        execution_result = execute_managed_director_task(
            current_task,
            job_ref=job_ref,
            certified_plan=current_plan,
            selected_step=selected_step,
            resolved_inputs=resolved_inputs,
            resource_catalog=list(available_resources),
            trusted_input_refs=selection["trusted_input_refs"],
            trusted_output_contract_ref=selection[
                "trusted_output_contract_ref"
            ],
            model_caller=model_caller,
            web_caller=web_caller,
            execution_id=requested_id(
                selected_execution_ids, work_index,
            ),
            timestamp=timestamp,
            reasoning_task_count=reasoning_task_count,
            reasoning_task_limit=reasoning_task_limit,
        )
        reasoning_task_count = execution_result["reasoning_task_count"]
        calls.extend(execution_result["calls"])
        repairs.extend(execution_result["conformance_repairs"])

        evaluation = evaluate_task_execution(
            execution_result["task_execution"],
            certified_plan=current_plan,
            selected_step=selected_step,
            director_task=current_task,
            plan_history=plan_history,
            accepted_checkpoints=accepted_checkpoints,
            accepted_outcomes_by_ref=accepted_outcomes,
            allow_ask_guidance=artifact_root is not None,
            guidance_policy=guidance_policy,
            frontier_authorized=frontier_authorized,
            model_caller=model_caller,
            outcome_id=requested_id(selected_outcome_ids, work_index),
            timestamp=timestamp,
            reasoning_task_count=reasoning_task_count,
            reasoning_task_limit=reasoning_task_limit,
        )
        reasoning_task_count = evaluation["reasoning_task_count"]
        calls.extend(evaluation["calls"])
        repairs.extend(evaluation["conformance_repairs"])
        evaluated_execution = evaluation["task_execution"]
        executions.append(deepcopy(evaluated_execution))
        evaluations.append({
            "plan_ref": current_plan["revision_ref"],
            "disposition": evaluation["disposition"],
            "semantics": deepcopy(evaluation["evaluation_semantics"]),
        })

        if evaluation["disposition"] == "accepted":
            status = "accepted"
            outcome = evaluated_execution["plan_execution"]["outcomes"][-1]
            accepted_outcomes[outcome["id"]] = deepcopy(outcome)
            accepted_checkpoints.append({
                "kind": "execution",
                "revision_ref": current_plan["revision_ref"],
                "outcome_ref": outcome["id"],
                "evidence_refs": list(dict.fromkeys([
                    outcome["id"],
                    *outcome["evidence_refs"],
                ])),
            })
            break
        if evaluation["disposition"] == "awaiting_guidance":
            status = "awaiting_guidance"
            break

        outcome = evaluated_execution["plan_execution"]["outcomes"][-1]
        if evaluation["disposition"] == "accepted_continue":
            accepted_outcomes[outcome["id"]] = deepcopy(outcome)
            accepted_checkpoints.append({
                "kind": "execution",
                "revision_ref": current_plan["revision_ref"],
                "outcome_ref": outcome["id"],
                "evidence_refs": list(dict.fromkeys([
                    outcome["id"],
                    *outcome["evidence_refs"],
                ])),
            })
        elif evaluation["disposition"] != "revise":
            raise RuntimeError(
                f"Unsupported Director disposition: {evaluation['disposition']}"
            )

        transition_state = execution_transition_budget_state(plan_history)
        if not transition_state["can_create_successor"]:
            status = "execution_transition_budget_exhausted"
            break

        checkpoint_revision_ref = outcome["checkpoint_revision_ref"]
        checkpoint_outcome_ref = outcome["checkpoint_outcome_ref"]
        checkpoint_plan = next(
            plan for plan in plan_history
            if plan["revision_ref"] == checkpoint_revision_ref
        )
        successor_request = request_successor_plan_semantics(
            current_plan=current_plan,
            checkpoint_plan=checkpoint_plan,
            evaluated_execution=evaluated_execution,
            evaluation_outcome=outcome,
            model_caller=model_caller,
            reasoning_task_count=reasoning_task_count,
            reasoning_task_limit=reasoning_task_limit,
        )
        reasoning_task_count = successor_request["reasoning_task_count"]
        calls.extend(successor_request["calls"])
        repairs.extend(successor_request["conformance_repairs"])
        successor_candidate = assemble_successor_plan(
            plan_history,
            checkpoint_revision_ref=checkpoint_revision_ref,
            checkpoint_outcome_ref=checkpoint_outcome_ref,
            accepted_outcomes_by_ref=accepted_outcomes,
            successor_semantics=successor_request["successor_semantics"],
            triggering_execution_ref=evaluated_execution["execution_id"],
            triggering_outcome_ref=outcome["id"],
            director_ref=DIRECTOR_CONTEXT,
            timestamp=timestamp,
        )
        successor = certify_final_plan(successor_candidate)
        successor_issues = validate_successor_plan(
            successor,
            prior_plan_history=plan_history,
            checkpoint_revision_ref=checkpoint_revision_ref,
            checkpoint_outcome_ref=checkpoint_outcome_ref,
            accepted_outcomes_by_ref=accepted_outcomes,
            triggering_execution_ref=evaluated_execution["execution_id"],
            triggering_outcome_ref=outcome["id"],
            director_ref=DIRECTOR_CONTEXT,
        )
        if successor_issues:
            details = "; ".join(
                f"{item.field}: {item.message}" for item in successor_issues
            )
            raise ValueError(
                f"Certified successor Plan is invalid: {details}"
            )

        outcome["resulting_plan_ref"] = successor["revision_ref"]
        evaluated_execution["plan_execution"]["persistence"][
            "updated_at"
        ] = timestamp or evaluated_execution["provenance"]["updated_at"]
        execution_issues = validate_task_execution_mapping(
            evaluated_execution
        )
        checkpoint_issues = validate_task_execution_checkpoint_context(
            evaluated_execution,
            plans_by_ref={
                str(plan["revision_ref"]): plan for plan in plan_history
            },
            accepted_outcomes_by_ref=accepted_outcomes,
        )
        if execution_issues or checkpoint_issues:
            details = "; ".join(
                f"{item.field}: {item.message}"
                for item in (*execution_issues, *checkpoint_issues)
            )
            raise ValueError(
                f"Successor-linked TaskExecution is invalid: {details}"
            )
        executions[-1] = deepcopy(evaluated_execution)
        evaluations[-1]["resulting_plan_ref"] = successor["revision_ref"]
        plan_history.append(deepcopy(successor))
        work_index += 1

    result = {
        "status": status,
        "certified_plan": deepcopy(plan_history[-1]),
        "plan_history": deepcopy(plan_history),
        "selected_step": deepcopy(dict(selected_step)),
        "director_tasks": tasks,
        "task_executions": executions,
        "evaluations": evaluations,
        "calls": calls,
        "conformance_repairs": repairs,
        "reasoning_task_count": reasoning_task_count,
        "semantic_iteration_count": semantic_iteration_count,
        "semantic_iteration_advanced": False,
        "execution_transition_state": execution_transition_budget_state(
            plan_history
        ),
        "accepted_checkpoints": deepcopy(accepted_checkpoints),
        "guidance_policy": guidance_policy,
        "frontier_authorized": frontier_authorized,
        "available_resources": [
            deepcopy(dict(resource)) for resource in available_resources
        ],
    }
    if artifact_root is not None:
        return persist_managed_work_run(
            result,
            job_ref=job_ref,
            resolved_inputs=resolved_inputs,
            artifact_root=artifact_root,
            timestamp=timestamp,
        )
    return result


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
