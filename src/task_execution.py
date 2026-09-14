"""Deterministic validation for the existing TaskExecution contract."""

from __future__ import annotations

from typing import Mapping

from structures import ValidationIssue


def _issue(field: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(field=field, code=code, message=message)


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
