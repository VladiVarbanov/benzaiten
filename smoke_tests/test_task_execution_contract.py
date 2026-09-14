from __future__ import annotations

import yaml

from config import TASK_EXECUTION_VOCABULARY_PATH
from task_execution import validate_task_execution_terminal_profile


def test_success_requires_result_and_clears_error() -> None:
    valid = {"control": {"status": "completed"}, "result": {"status": "complete"}}
    conflicting = {**valid, "error": {"code": "failure"}}

    assert validate_task_execution_terminal_profile(valid) == ()
    assert {issue.code for issue in validate_task_execution_terminal_profile(conflicting)} == {
        "forbidden_for_success"
    }


def test_failure_requires_error_and_clears_result() -> None:
    valid = {"control": {"status": "failed"}, "error": {"code": "execution"}}
    masquerading = {**valid, "result": {"status": "complete"}}

    assert validate_task_execution_terminal_profile(valid) == ()
    assert {issue.code for issue in validate_task_execution_terminal_profile(masquerading)} == {
        "forbidden_for_failure"
    }


def test_artifact_record_is_optional_and_conditionally_structured() -> None:
    base = {"control": {"status": "completed"}, "result": {"status": "complete"}}

    assert validate_task_execution_terminal_profile(base) == ()
    assert validate_task_execution_terminal_profile({**base, "artifact_record": None}) == ()
    assert validate_task_execution_terminal_profile({**base, "artifact_record": {}}) == ()
    assert validate_task_execution_terminal_profile({**base, "artifact_record": "artifact"})[0].field == "artifact_record"

    vocabulary = yaml.safe_load(
        TASK_EXECUTION_VOCABULARY_PATH.read_text(encoding="utf-8")
    )
    assert "Optional and conditional" in vocabulary["semantics"]["artifact_record"]["description"]
