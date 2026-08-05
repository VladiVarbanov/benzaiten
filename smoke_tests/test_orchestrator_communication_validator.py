from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, cast

import pytest

from orchestrator_communication_validator import (
    parse_and_validate_communication,
)


@pytest.fixture
def valid_envelope() -> dict[str, Any]:
    """Return one complete valid Version 0 request envelope."""

    return {
        "protocol": {
            "name": "hub-message",
            "version": "1.0",
        },
        "message": {
            "id": "message-001",
            "kind": "request",
            "created_at": "2026-08-05T11:00:00+03:00",
            "thread_id": "thread-001",
            "reply_to": None,
        },
        "route": {
            "sender": "qwen_agent",
            "receiver": "orchestrator",
        },
        "session": {
            "id": "session-001",
        },
        "agent": {
            "model": "qwen3-30b-a3b-nvfp4",
        },
        "work": {
            "kind": "execution",
            "plan_ref": "plan-001",
            "task": "task-001",
        },
        "task": {
            "action": "extract knowledge",
            "target": {
                "kind": "prepared_markdown",
                "locator": "workspace/artifacts/source/prepared.md",
            },
            "anchors": [],
            "entities": [],
            "methods": [],
            "question": (
                "What knowledge should be extracted from the source?"
            ),
            "reason": (
                "The prepared source must produce an independent OKF Draft."
            ),
            "angles": [],
            "granularity": "coarse",
        },
        "contract": {
            "output": {
                "format": "json",
                "required": [],
                "constraints": [],
            },
            "expected": (
                "A structurally valid independent OKF Draft."
            ),
        },
        "control": {
            "status": "pending",
            "priority": "medium",
            "iteration": {
                "current": 1,
                "max": 2,
            },
            "override": {
                "requested": False,
                "scope": None,
                "proposal": None,
                "justification": None,
            },
        },
        "result": None,
        "error": None,
        "provenance": None,
    }


def serialize(envelope: dict[str, Any]) -> str:
    """Serialize a test envelope exactly as incoming JSON."""

    return json.dumps(envelope)


def test_valid_complete_envelope_is_accepted(
    valid_envelope: dict[str, Any],
) -> None:
    outcome = parse_and_validate_communication(
        serialize(valid_envelope)
    )

    assert outcome.valid is True
    assert outcome.communication is not None
    assert outcome.issues == ()


def test_normalized_envelope_is_immutable(
    valid_envelope: dict[str, Any],
) -> None:
    outcome = parse_and_validate_communication(
        serialize(valid_envelope)
    )

    assert outcome.communication is not None

    with pytest.raises(TypeError):
        outcome.communication.data["protocol"]["name"] = "changed"


def test_malformed_json_returns_controlled_issue() -> None:
    outcome = parse_and_validate_communication("{invalid-json")

    assert outcome.valid is False
    assert outcome.communication is None
    assert any(
        issue.code == "malformed_json"
        for issue in outcome.issues
    )


def test_non_string_input_returns_controlled_issue() -> None:
    outcome = parse_and_validate_communication(
        cast(Any, None)
    )

    assert outcome.valid is False
    assert outcome.communication is None
    assert any(
        issue.code == "invalid_raw_envelope_type"
        for issue in outcome.issues
    )


def test_missing_required_task_action_is_rejected(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    del envelope["task"]["action"]

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False
    assert any(
        issue.field == "task.action"
        for issue in outcome.issues
    )


def test_invalid_message_kind_is_rejected(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["message"]["kind"] = "telepathy"

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False
    assert any(
        issue.field == "message.kind"
        and issue.code == "invalid_vocabulary_value"
        for issue in outcome.issues
    )


def test_empty_collection_fields_are_valid(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)

    envelope["task"]["anchors"] = []
    envelope["task"]["entities"] = []
    envelope["task"]["methods"] = []
    envelope["task"]["angles"] = []
    envelope["contract"]["output"]["required"] = []
    envelope["contract"]["output"]["constraints"] = []

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is True
    assert outcome.issues == ()


def test_invalid_collection_item_is_rejected(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["task"]["methods"] = [42]

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False
    assert any(
        issue.field == "task.methods[0]"
        and issue.code == "invalid_collection_item"
        for issue in outcome.issues
    )


def test_timestamp_without_timezone_is_rejected(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["message"]["created_at"] = "2026-08-05T11:00:00"

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False
    assert any(
        issue.field == "message.created_at"
        and issue.code == "missing_timezone"
        for issue in outcome.issues
    )


def test_iteration_current_cannot_exceed_maximum(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["control"]["iteration"] = {
        "current": 3,
        "max": 2,
    }

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False
    assert any(
        issue.code == "invalid_iteration_bounds"
        for issue in outcome.issues
    )


def test_unsupported_protocol_version_is_rejected(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["protocol"]["version"] = "2.0"

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False
    assert any(
        issue.code == "unsupported_protocol_version"
        for issue in outcome.issues
    )

def test_response_requires_reply_reference_and_result(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["message"]["kind"] = "response"
    envelope["message"]["reply_to"] = None
    envelope["result"] = None

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False

    assert any(
        issue.field == "message.reply_to"
        and issue.code == "missing_required_reference"
        for issue in outcome.issues
    )

    assert any(
        issue.field == "result"
        and issue.code == "missing_required_section"
        for issue in outcome.issues
    )


def test_valid_response_is_accepted(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["message"]["kind"] = "response"
    envelope["message"]["reply_to"] = "message-000"
    envelope["result"] = {
        "status": "complete",
        "content": {
            "draft_id": "draft-001",
        },
        "notes": "",
    }

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is True
    assert outcome.issues == ()


def test_error_message_requires_reply_reference_and_error_section(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["message"]["kind"] = "error"
    envelope["message"]["reply_to"] = None
    envelope["error"] = None

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False

    assert any(
        issue.field == "message.reply_to"
        and issue.code == "missing_required_reference"
        for issue in outcome.issues
    )

    assert any(
        issue.field == "error"
        and issue.code == "missing_required_section"
        for issue in outcome.issues
    )


def test_valid_error_message_is_accepted(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["message"]["kind"] = "error"
    envelope["message"]["reply_to"] = "message-000"
    envelope["error"] = {
        "code": "MODEL_TIMEOUT",
        "category": "timeout",
        "source": "agent",
        "detail": "The model endpoint did not respond in time.",
        "retryable": True,
    }

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is True
    assert outcome.issues == ()


def test_request_cannot_contain_result(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["result"] = {
        "status": "complete",
        "content": {},
        "notes": "",
    }

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False

    assert any(
        issue.field == "result"
        and issue.code == "inapplicable_section"
        for issue in outcome.issues
    )


def test_execution_work_requires_plan_reference(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["work"]["kind"] = "execution"
    envelope["work"]["plan_ref"] = None

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False

    assert any(
        issue.field == "work.plan_ref"
        and issue.code == "missing_required_reference"
        for issue in outcome.issues
    )


def test_requested_override_requires_all_details(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["control"]["override"] = {
        "requested": True,
        "scope": None,
        "proposal": None,
        "justification": None,
    }

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is False

    missing_fields = {
        issue.field
        for issue in outcome.issues
        if issue.code == "missing_override_detail"
    }

    assert missing_fields == {
        "control.override.scope",
        "control.override.proposal",
        "control.override.justification",
    }


def test_complete_requested_override_is_accepted(
    valid_envelope: dict[str, Any],
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["control"]["override"] = {
        "requested": True,
        "scope": "task.granularity",
        "proposal": "Change granularity from coarse to fine.",
        "justification": (
            "The source requires detailed extraction."
        ),
    }

    outcome = parse_and_validate_communication(
        serialize(envelope)
    )

    assert outcome.valid is True
    assert outcome.issues == ()