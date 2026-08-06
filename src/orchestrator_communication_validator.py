"""Validation and normalization for Benzaiten communication envelopes.

This module:

- loads the communication protocol and vocabulary
- parses raw JSON envelopes
- validates all declared protocol sections
- validates vocabulary-constrained values
- returns immutable normalized communication objects
- contains unexpected failures at the public validation boundary

It does not:

- build outgoing messages
- route work
- dispatch capabilities
- call models
- communicate with endpoints
- decide repair, retry, escalation, or rejection policy
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any

from config import (
    ORCHESTRATOR_COMMUNICATION_PROTOCOL_PATH,
    ORCHESTRATOR_COMMUNICATION_PROTOCOL_VOCABULARY_PATH,
)
from structures import (
    CommunicationEnvelope,
    ValidationIssue,
    ValidationOutcome,
    load_json_mapping,
    load_yaml_mapping,
)


# =====================================================================
# INTERNAL VALIDATION HELPERS
# =====================================================================


def _validate_non_empty_string(
    value: Any,
    *,
    field: str,
) -> ValidationIssue | None:
    """Validate one required non-empty string value."""

    if not isinstance(value, str) or not value.strip():
        return ValidationIssue(
            field=field,
            code="missing_or_invalid_field",
            message=f"'{field}' must be a non-empty string.",
        )

    return None


def _validate_nullable_string(
    value: Any,
    *,
    field: str,
) -> ValidationIssue | None:
    """Validate a value that may be null or a non-empty string."""

    if value is None:
        return None

    if not isinstance(value, str) or not value.strip():
        return ValidationIssue(
            field=field,
            code="invalid_optional_field",
            message=(
                f"'{field}' must be null or a non-empty string."
            ),
        )

    return None


def _validate_string_list(
    value: Any,
    *,
    field: str,
) -> tuple[ValidationIssue, ...]:
    """Validate a required list whose entries must be strings.

    The list itself may legitimately be empty.
    """

    if not isinstance(value, list):
        return (
            ValidationIssue(
                field=field,
                code="missing_or_invalid_field",
                message=f"'{field}' must be a list.",
            ),
        )

    issues: list[ValidationIssue] = []

    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            issues.append(
                ValidationIssue(
                    field=f"{field}[{index}]",
                    code="invalid_collection_item",
                    message=(
                        f"'{field}[{index}]' must be a "
                        "non-empty string."
                    ),
                )
            )

    return tuple(issues)


def _validate_timestamp(
    value: Any,
    *,
    field: str,
) -> tuple[ValidationIssue, ...]:
    """Validate a timezone-aware ISO-8601 timestamp."""

    if not isinstance(value, str) or not value.strip():
        return (
            ValidationIssue(
                field=field,
                code="missing_or_invalid_field",
                message=(
                    f"'{field}' must be a non-empty "
                    "ISO-8601 timestamp."
                ),
            ),
        )

    try:
        parsed_timestamp = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return (
            ValidationIssue(
                field=field,
                code="invalid_timestamp",
                message=(
                    f"'{field}' must be a valid "
                    "ISO-8601 timestamp."
                ),
            ),
        )

    if parsed_timestamp.tzinfo is None:
        return (
            ValidationIssue(
                field=field,
                code="missing_timezone",
                message=(
                    f"'{field}' must include timezone information."
                ),
            ),
        )

    return ()


def _validate_vocabulary_value(
    value: Any,
    *,
    vocabulary: Mapping[str, Any],
    vocabulary_key: str,
    field: str,
) -> tuple[ValidationIssue, ...]:
    """Validate a value against one vocabulary list."""

    allowed_values = vocabulary.get(vocabulary_key)

    if not isinstance(allowed_values, list):
        return (
            ValidationIssue(
                field=f"vocabulary.{vocabulary_key}",
                code="invalid_validator_resource",
                message=(
                    "The communication vocabulary must define "
                    f"'{vocabulary_key}' as a list."
                ),
            ),
        )

    if value not in allowed_values:
        return (
            ValidationIssue(
                field=field,
                code="invalid_vocabulary_value",
                message=(
                    f"'{field}' must be one of "
                    f"{allowed_values!r}; received {value!r}."
                ),
            ),
        )

    return ()


def _validate_required_mapping(
    envelope: Mapping[str, Any],
    *,
    section_name: str,
) -> tuple[Mapping[str, Any] | None, tuple[ValidationIssue, ...]]:
    """Read one required top-level mapping section."""

    section = envelope.get(section_name)

    if not isinstance(section, Mapping):
        return (
            None,
            (
                ValidationIssue(
                    field=section_name,
                    code="missing_or_invalid_section",
                    message=(
                        f"The '{section_name}' section "
                        "must be a mapping."
                    ),
                ),
            ),
        )

    return section, ()


def _validate_optional_mapping(
    envelope: Mapping[str, Any],
    *,
    section_name: str,
) -> tuple[Mapping[str, Any] | None, tuple[ValidationIssue, ...]]:
    """Read a required top-level key that may contain null or a mapping."""

    if section_name not in envelope:
        return (
            None,
            (
                ValidationIssue(
                    field=section_name,
                    code="missing_section",
                    message=(
                        f"The envelope must contain the "
                        f"'{section_name}' field."
                    ),
                ),
            ),
        )

    section = envelope.get(section_name)

    if section is None:
        return None, ()

    if not isinstance(section, Mapping):
        return (
            None,
            (
                ValidationIssue(
                    field=section_name,
                    code="invalid_section",
                    message=(
                        f"'{section_name}' must be null "
                        "or a mapping."
                    ),
                ),
            ),
        )

    return section, ()


# =====================================================================
# RAW ENVELOPE PARSING
# =====================================================================


def parse_raw_envelope(
    raw_envelope: str,
) -> tuple[dict[str, Any] | None, tuple[ValidationIssue, ...]]:
    """Parse one raw JSON communication envelope."""

    if not isinstance(raw_envelope, str):
        return (
            None,
            (
                ValidationIssue(
                    field="envelope",
                    code="invalid_raw_envelope_type",
                    message="The raw envelope must be a string.",
                ),
            ),
        )

    if not raw_envelope.strip():
        return (
            None,
            (
                ValidationIssue(
                    field="envelope",
                    code="empty_raw_envelope",
                    message="The raw envelope cannot be empty.",
                ),
            ),
        )

    try:
        parsed = json.loads(raw_envelope)
    except json.JSONDecodeError as exc:
        return (
            None,
            (
                ValidationIssue(
                    field="envelope",
                    code="malformed_json",
                    message=(
                        "The communication envelope is not valid JSON: "
                        f"line {exc.lineno}, column {exc.colno}: "
                        f"{exc.msg}."
                    ),
                ),
            ),
        )

    if not isinstance(parsed, dict):
        return (
            None,
            (
                ValidationIssue(
                    field="envelope",
                    code="invalid_envelope_root",
                    message=(
                        "The communication envelope root "
                        "must be a mapping."
                    ),
                ),
            ),
        )

    return parsed, ()


# =====================================================================
# SECTION VALIDATORS
# =====================================================================


def validate_protocol_section(
    envelope: Mapping[str, Any],
    protocol_template: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate the communication protocol identity."""

    protocol, issues = _validate_required_mapping(
        envelope,
        section_name="protocol",
    )

    if protocol is None:
        return issues

    expected_protocol = protocol_template.get("protocol")

    if not isinstance(expected_protocol, Mapping):
        return (
            ValidationIssue(
                field="protocol_template.protocol",
                code="invalid_validator_resource",
                message=(
                    "The communication protocol template must "
                    "contain a valid 'protocol' mapping."
                ),
            ),
        )

    expected_name = expected_protocol.get("name")
    expected_version = expected_protocol.get("version")

    received_name = protocol.get("name")
    received_version = protocol.get("version")

    validation_issues: list[ValidationIssue] = []

    if received_name != expected_name:
        validation_issues.append(
            ValidationIssue(
                field="protocol.name",
                code="unsupported_protocol",
                message=(
                    f"Expected protocol name {expected_name!r}, "
                    f"received {received_name!r}."
                ),
            )
        )

    if received_version != expected_version:
        validation_issues.append(
            ValidationIssue(
                field="protocol.version",
                code="unsupported_protocol_version",
                message=(
                    f"Expected protocol version {expected_version!r}, "
                    f"received {received_version!r}."
                ),
            )
        )

    return tuple(validation_issues)


def validate_message_section(
    envelope: Mapping[str, Any],
    vocabulary: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate communication message metadata."""

    message, issues = _validate_required_mapping(
        envelope,
        section_name="message",
    )

    if message is None:
        return issues

    validation_issues: list[ValidationIssue] = []

    issue = _validate_non_empty_string(
        message.get("id"),
        field="message.id",
    )
    if issue:
        validation_issues.append(issue)

    validation_issues.extend(
        _validate_vocabulary_value(
            message.get("kind"),
            vocabulary=vocabulary,
            vocabulary_key="message_kind",
            field="message.kind",
        )
    )

    validation_issues.extend(
        _validate_timestamp(
            message.get("created_at"),
            field="message.created_at",
        )
    )

    issue = _validate_non_empty_string(
        message.get("thread_id"),
        field="message.thread_id",
    )
    if issue:
        validation_issues.append(issue)

    issue = _validate_nullable_string(
        message.get("reply_to"),
        field="message.reply_to",
    )
    if issue:
        validation_issues.append(issue)

    return tuple(validation_issues)


def validate_route_section(
    envelope: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate sender and receiver identifiers."""

    route, issues = _validate_required_mapping(
        envelope,
        section_name="route",
    )

    if route is None:
        return issues

    validation_issues: list[ValidationIssue] = []

    for field_name in ("sender", "receiver"):
        issue = _validate_non_empty_string(
            route.get(field_name),
            field=f"route.{field_name}",
        )
        if issue:
            validation_issues.append(issue)

    return tuple(validation_issues)


def validate_session_section(
    envelope: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate the session reference."""

    session, issues = _validate_required_mapping(
        envelope,
        section_name="session",
    )

    if session is None:
        return issues

    issue = _validate_non_empty_string(
        session.get("id"),
        field="session.id",
    )

    return (issue,) if issue else ()


def validate_agent_section(
    envelope: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate the declared model identity."""

    agent, issues = _validate_required_mapping(
        envelope,
        section_name="agent",
    )

    if agent is None:
        return issues

    issue = _validate_non_empty_string(
        agent.get("model"),
        field="agent.model",
    )

    return (issue,) if issue else ()


def validate_work_section(
    envelope: Mapping[str, Any],
    vocabulary: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate the work classification and references."""

    work, issues = _validate_required_mapping(
        envelope,
        section_name="work",
    )

    if work is None:
        return issues

    validation_issues: list[ValidationIssue] = []

    validation_issues.extend(
        _validate_vocabulary_value(
            work.get("kind"),
            vocabulary=vocabulary,
            vocabulary_key="work_kind",
            field="work.kind",
        )
    )

    issue = _validate_nullable_string(
        work.get("plan_ref"),
        field="work.plan_ref",
    )
    if issue:
        validation_issues.append(issue)

    issue = _validate_non_empty_string(
        work.get("task"),
        field="work.task",
    )
    if issue:
        validation_issues.append(issue)

    return tuple(validation_issues)


def validate_task_section(
    envelope: Mapping[str, Any],
    vocabulary: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate the task description and analytical context."""

    task, issues = _validate_required_mapping(
        envelope,
        section_name="task",
    )

    if task is None:
        return issues

    validation_issues: list[ValidationIssue] = []

    for field_name in ("action", "question", "reason"):
        issue = _validate_non_empty_string(
            task.get(field_name),
            field=f"task.{field_name}",
        )
        if issue:
            validation_issues.append(issue)

    target = task.get("target")

    if not isinstance(target, Mapping):
        validation_issues.append(
            ValidationIssue(
                field="task.target",
                code="missing_or_invalid_field",
                message="'task.target' must be a mapping.",
            )
        )
    else:
        for field_name in ("kind", "locator"):
            issue = _validate_non_empty_string(
                target.get(field_name),
                field=f"task.target.{field_name}",
            )
            if issue:
                validation_issues.append(issue)

    anchors = task.get("anchors")

    if not isinstance(anchors, list):
        validation_issues.append(
            ValidationIssue(
                field="task.anchors",
                code="missing_or_invalid_field",
                message="'task.anchors' must be a list.",
            )
        )
    else:
        for index, anchor in enumerate(anchors):
            if not isinstance(anchor, Mapping):
                validation_issues.append(
                    ValidationIssue(
                        field=f"task.anchors[{index}]",
                        code="invalid_collection_item",
                        message=(
                            f"'task.anchors[{index}]' must be a mapping."
                        ),
                    )
                )
                continue

            for field_name in ("kind", "value"):
                issue = _validate_non_empty_string(
                    anchor.get(field_name),
                    field=(
                        f"task.anchors[{index}].{field_name}"
                    ),
                )
                if issue:
                    validation_issues.append(issue)

    entities = task.get("entities")

    if not isinstance(entities, list):
        validation_issues.append(
            ValidationIssue(
                field="task.entities",
                code="missing_or_invalid_field",
                message="'task.entities' must be a list.",
            )
        )
    else:
        for index, entity in enumerate(entities):
            if not isinstance(entity, Mapping):
                validation_issues.append(
                    ValidationIssue(
                        field=f"task.entities[{index}]",
                        code="invalid_collection_item",
                        message=(
                            f"'task.entities[{index}]' must be a mapping."
                        ),
                    )
                )
                continue

            for field_name in ("kind", "name"):
                issue = _validate_non_empty_string(
                    entity.get(field_name),
                    field=(
                        f"task.entities[{index}].{field_name}"
                    ),
                )
                if issue:
                    validation_issues.append(issue)

    validation_issues.extend(
        _validate_string_list(
            task.get("methods"),
            field="task.methods",
        )
    )

    validation_issues.extend(
        _validate_string_list(
            task.get("angles"),
            field="task.angles",
        )
    )

    validation_issues.extend(
        _validate_vocabulary_value(
            task.get("granularity"),
            vocabulary=vocabulary,
            vocabulary_key="granularity",
            field="task.granularity",
        )
    )

    return tuple(validation_issues)


def validate_contract_section(
    envelope: Mapping[str, Any],
    vocabulary: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate the requested output contract."""

    contract, issues = _validate_required_mapping(
        envelope,
        section_name="contract",
    )

    if contract is None:
        return issues

    validation_issues: list[ValidationIssue] = []

    output = contract.get("output")

    if not isinstance(output, Mapping):
        validation_issues.append(
            ValidationIssue(
                field="contract.output",
                code="missing_or_invalid_field",
                message="'contract.output' must be a mapping.",
            )
        )
    else:
        validation_issues.extend(
            _validate_vocabulary_value(
                output.get("format"),
                vocabulary=vocabulary,
                vocabulary_key="output_format",
                field="contract.output.format",
            )
        )

        validation_issues.extend(
            _validate_string_list(
                output.get("required"),
                field="contract.output.required",
            )
        )

        validation_issues.extend(
            _validate_string_list(
                output.get("constraints"),
                field="contract.output.constraints",
            )
        )

    issue = _validate_non_empty_string(
        contract.get("expected"),
        field="contract.expected",
    )
    if issue:
        validation_issues.append(issue)

    return tuple(validation_issues)


def validate_control_section(
    envelope: Mapping[str, Any],
    vocabulary: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate status, priority, iteration, and override controls."""

    control, issues = _validate_required_mapping(
        envelope,
        section_name="control",
    )

    if control is None:
        return issues

    validation_issues: list[ValidationIssue] = []

    validation_issues.extend(
        _validate_vocabulary_value(
            control.get("status"),
            vocabulary=vocabulary,
            vocabulary_key="control_status",
            field="control.status",
        )
    )

    validation_issues.extend(
        _validate_vocabulary_value(
            control.get("priority"),
            vocabulary=vocabulary,
            vocabulary_key="priority",
            field="control.priority",
        )
    )

    iteration = control.get("iteration")

    if not isinstance(iteration, Mapping):
        validation_issues.append(
            ValidationIssue(
                field="control.iteration",
                code="missing_or_invalid_field",
                message="'control.iteration' must be a mapping.",
            )
        )
    else:
        current = iteration.get("current")
        maximum = iteration.get("max")

        if type(current) is not int or current < 1:
            validation_issues.append(
                ValidationIssue(
                    field="control.iteration.current",
                    code="missing_or_invalid_field",
                    message=(
                        "'control.iteration.current' must be "
                        "an integer greater than or equal to 1."
                    ),
                )
            )

        if type(maximum) is not int or maximum < 1:
            validation_issues.append(
                ValidationIssue(
                    field="control.iteration.max",
                    code="missing_or_invalid_field",
                    message=(
                        "'control.iteration.max' must be "
                        "an integer greater than or equal to 1."
                    ),
                )
            )

        if (
            type(current) is int
            and type(maximum) is int
            and current > maximum
        ):
            validation_issues.append(
                ValidationIssue(
                    field="control.iteration",
                    code="invalid_iteration_bounds",
                    message=(
                        "'control.iteration.current' cannot "
                        "exceed 'control.iteration.max'."
                    ),
                )
            )

    override = control.get("override")

    if not isinstance(override, Mapping):
        validation_issues.append(
            ValidationIssue(
                field="control.override",
                code="missing_or_invalid_field",
                message="'control.override' must be a mapping.",
            )
        )
    else:
        requested = override.get("requested")

        if not isinstance(requested, bool):
            validation_issues.append(
                ValidationIssue(
                    field="control.override.requested",
                    code="missing_or_invalid_field",
                    message=(
                        "'control.override.requested' "
                        "must be a boolean."
                    ),
                )
            )

        for field_name in (
            "scope",
            "proposal",
            "justification",
        ):
            issue = _validate_nullable_string(
                override.get(field_name),
                field=f"control.override.{field_name}",
            )
            if issue:
                validation_issues.append(issue)

    return tuple(validation_issues)


def validate_result_section(
    envelope: Mapping[str, Any],
    vocabulary: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate a populated result section.

    The top-level result field must exist but may be null when the
    message does not carry a result.
    """

    result, issues = _validate_optional_mapping(
        envelope,
        section_name="result",
    )

    if issues or result is None:
        return issues

    validation_issues: list[ValidationIssue] = []

    validation_issues.extend(
        _validate_vocabulary_value(
            result.get("status"),
            vocabulary=vocabulary,
            vocabulary_key="result_status",
            field="result.status",
        )
    )

    if "content" not in result:
        validation_issues.append(
            ValidationIssue(
                field="result.content",
                code="missing_required_field",
                message="'result.content' must be present.",
            )
        )

    notes = result.get("notes")

    if not isinstance(notes, str):
        validation_issues.append(
            ValidationIssue(
                field="result.notes",
                code="missing_or_invalid_field",
                message="'result.notes' must be a string.",
            )
        )

    return tuple(validation_issues)


def validate_error_section(
    envelope: Mapping[str, Any],
    vocabulary: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate a populated error section.

    The top-level error field must exist but may be null when the
    message does not report an error.
    """

    error, issues = _validate_optional_mapping(
        envelope,
        section_name="error",
    )

    if issues or error is None:
        return issues

    validation_issues: list[ValidationIssue] = []

    for field_name in ("code", "detail"):
        issue = _validate_non_empty_string(
            error.get(field_name),
            field=f"error.{field_name}",
        )
        if issue:
            validation_issues.append(issue)

    validation_issues.extend(
        _validate_vocabulary_value(
            error.get("category"),
            vocabulary=vocabulary,
            vocabulary_key="error_category",
            field="error.category",
        )
    )

    validation_issues.extend(
        _validate_vocabulary_value(
            error.get("source"),
            vocabulary=vocabulary,
            vocabulary_key="error_source",
            field="error.source",
        )
    )

    if not isinstance(error.get("retryable"), bool):
        validation_issues.append(
            ValidationIssue(
                field="error.retryable",
                code="missing_or_invalid_field",
                message="'error.retryable' must be a boolean.",
            )
        )

    return tuple(validation_issues)


def validate_provenance_section(
    envelope: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate a populated provenance section.

    The field may be null until authoritative provenance is resolved.
    """

    provenance, issues = _validate_optional_mapping(
        envelope,
        section_name="provenance",
    )

    if issues or provenance is None:
        return issues

    validation_issues: list[ValidationIssue] = []

    issue = _validate_non_empty_string(
        provenance.get("resolved_by"),
        field="provenance.resolved_by",
    )
    if issue:
        validation_issues.append(issue)

    validation_issues.extend(
        _validate_timestamp(
            provenance.get("resolved_at"),
            field="provenance.resolved_at",
        )
    )

    chain = provenance.get("chain")

    if not isinstance(chain, Mapping):
        validation_issues.append(
            ValidationIssue(
                field="provenance.chain",
                code="missing_or_invalid_field",
                message="'provenance.chain' must be a mapping.",
            )
        )
    else:
        for field_name in (
            "agent",
            "session",
            "model",
            "compute_node",
            "host",
        ):
            issue = _validate_non_empty_string(
                chain.get(field_name),
                field=f"provenance.chain.{field_name}",
            )
            if issue:
                validation_issues.append(issue)

    return tuple(validation_issues)


# =====================================================================
# ENVELOPE-LEVEL VALIDATION
# =====================================================================


def validate_communication_mapping(
    envelope: Mapping[str, Any],
    protocol_template: Mapping[str, Any],
    vocabulary: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Run all Version 0 structural and vocabulary validations."""

    issues: list[ValidationIssue] = []

    issues.extend(
        validate_protocol_section(
            envelope,
            protocol_template,
        )
    )
    issues.extend(
        validate_message_section(
            envelope,
            vocabulary,
        )
    )
    issues.extend(validate_route_section(envelope))
    issues.extend(validate_session_section(envelope))
    issues.extend(validate_agent_section(envelope))
    issues.extend(
        validate_work_section(
            envelope,
            vocabulary,
        )
    )
    issues.extend(
        validate_task_section(
            envelope,
            vocabulary,
        )
    )
    issues.extend(
        validate_contract_section(
            envelope,
            vocabulary,
        )
    )
    issues.extend(
        validate_control_section(
            envelope,
            vocabulary,
        )
    )
    issues.extend(
        validate_result_section(
            envelope,
            vocabulary,
        )
    )
    issues.extend(
        validate_error_section(
            envelope,
            vocabulary,
        )
    )
    issues.extend(validate_provenance_section(envelope))
    issues.extend(validate_message_consistency(envelope))

    return tuple(issues)


# =====================================================================
# IMMUTABLE NORMALIZATION
# =====================================================================


def _freeze_value(value: Any) -> Any:
    """Recursively convert mappings and lists into immutable values."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: _freeze_value(nested_value)
                for key, nested_value in value.items()
            }
        )

    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)

    return value


def normalize_communication(
    envelope: Mapping[str, Any],
) -> CommunicationEnvelope:
    """Return an immutable normalized communication envelope."""

    normalized = _freeze_value(envelope)

    return CommunicationEnvelope(data=normalized)


# =====================================================================
# PUBLIC FAULT-CONTAINMENT BOUNDARY
# =====================================================================


def parse_and_validate_communication(
    raw_envelope: str,
) -> ValidationOutcome:
    """Parse, validate, and normalize one communication envelope.

    Expected malformed input becomes ValidationIssue objects.

    Unexpected resource or implementation failures are contained at
    this outer boundary so that the orchestration process remains alive.
    Recovery and escalation policy are intentionally left to a later
    orchestration layer.
    """

    try:
        protocol_template = load_json_mapping(
            ORCHESTRATOR_COMMUNICATION_PROTOCOL_PATH
        )
        vocabulary = load_yaml_mapping(
            ORCHESTRATOR_COMMUNICATION_PROTOCOL_VOCABULARY_PATH
        )

        envelope, parse_issues = parse_raw_envelope(raw_envelope)

        if envelope is None:
            return ValidationOutcome(
                valid=False,
                communication=None,
                issues=parse_issues,
            )

        validation_issues = validate_communication_mapping(
            envelope,
            protocol_template,
            vocabulary,
        )

        if validation_issues:
            return ValidationOutcome(
                valid=False,
                communication=None,
                issues=validation_issues,
            )

        communication = normalize_communication(envelope)

        return ValidationOutcome(
            valid=True,
            communication=communication,
            issues=(),
        )

    except Exception as exc:
        return ValidationOutcome(
            valid=False,
            communication=None,
            issues=(
                ValidationIssue(
                    field="validator",
                    code="unexpected_validation_failure",
                    message=(
                        "Unexpected communication validation "
                        f"failure: {type(exc).__name__}: {exc}"
                    ),
                ),
            ),
        )


def validate_message_consistency(
    envelope: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate relationships between communication sections."""

    issues: list[ValidationIssue] = []

    message = envelope.get("message")
    work = envelope.get("work")
    control = envelope.get("control")

    message_kind = (
        message.get("kind")
        if isinstance(message, Mapping)
        else None
    )

    reply_to = (
        message.get("reply_to")
        if isinstance(message, Mapping)
        else None
    )

    result = envelope.get("result")
    error = envelope.get("error")

    # Responses and errors must reference the message they answer.
    if message_kind in {"response", "error"}:
        if not isinstance(reply_to, str) or not reply_to.strip():
            issues.append(
                ValidationIssue(
                    field="message.reply_to",
                    code="missing_required_reference",
                    message=(
                        "'message.reply_to' must be a non-empty "
                        "message reference for response and error messages."
                    ),
                )
            )

    # Request and order messages do not carry completed results or errors.
    if message_kind in {"request", "order"}:
        if result is not None:
            issues.append(
                ValidationIssue(
                    field="result",
                    code="inapplicable_section",
                    message=(
                        "'result' must be null for request "
                        "and order messages."
                    ),
                )
            )

        if error is not None:
            issues.append(
                ValidationIssue(
                    field="error",
                    code="inapplicable_section",
                    message=(
                        "'error' must be null for request "
                        "and order messages."
                    ),
                )
            )

    # A response carries a result and must not carry an error.
    if message_kind == "response":
        if result is None:
            issues.append(
                ValidationIssue(
                    field="result",
                    code="missing_required_section",
                    message=(
                        "'result' must be populated for "
                        "a response message."
                    ),
                )
            )

        if error is not None:
            issues.append(
                ValidationIssue(
                    field="error",
                    code="inapplicable_section",
                    message=(
                        "'error' must be null for a response message."
                    ),
                )
            )

    # An error message carries an error and must not carry a result.
    if message_kind == "error":
        if error is None:
            issues.append(
                ValidationIssue(
                    field="error",
                    code="missing_required_section",
                    message=(
                        "'error' must be populated for "
                        "an error message."
                    ),
                )
            )

        if result is not None:
            issues.append(
                ValidationIssue(
                    field="result",
                    code="inapplicable_section",
                    message=(
                        "'result' must be null for an error message."
                    ),
                )
            )

    # Work after the planning stage must reference its parent plan.
    if isinstance(work, Mapping):
        work_kind = work.get("kind")
        plan_ref = work.get("plan_ref")

        if work_kind in {"execution", "review", "synthesis"}:
            if not isinstance(plan_ref, str) or not plan_ref.strip():
                issues.append(
                    ValidationIssue(
                        field="work.plan_ref",
                        code="missing_required_reference",
                        message=(
                            "'work.plan_ref' must be a non-empty "
                            "plan reference for execution, review, "
                            "and synthesis work."
                        ),
                    )
                )

    # A requested override must explain the proposed change.
    if isinstance(control, Mapping):
        override = control.get("override")

        if isinstance(override, Mapping):
            override_requested = override.get("requested")

            if override_requested is True:
                for field_name in (
                    "scope",
                    "proposal",
                    "justification",
                ):
                    value = override.get(field_name)

                    if not isinstance(value, str) or not value.strip():
                        issues.append(
                            ValidationIssue(
                                field=(
                                    f"control.override.{field_name}"
                                ),
                                code="missing_override_detail",
                                message=(
                                    f"'control.override.{field_name}' "
                                    "must be a non-empty string when "
                                    "an override is requested."
                                ),
                            )
                        )

    return tuple(issues)