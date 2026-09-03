from __future__ import annotations

from config import AGENTS, LOGICAL_CONTEXTS, PARTICIPANT_ROLE_CONTEXTS
from orchestrator import resolve_participant_role
from structures import LogicalContextStruct


def test_reviewer_resolves_to_qwen_model_context() -> None:
    reviewer = resolve_participant_role("reviewer")

    assert reviewer.logical_context.name == "qwen_worker"
    assert reviewer.worker_kind == "model"
    assert reviewer.model is not None
    assert reviewer.agent is None
    assert reviewer.tool_ref is None


def test_agent_context_resolves_only_to_agent(monkeypatch) -> None:
    context = LogicalContextStruct(
        name="agent_test",
        participant_role="agent_test",
        worker_kind="agent",
        worker_ref="qwen_agent",
    )
    monkeypatch.setitem(LOGICAL_CONTEXTS, context.name, context)
    monkeypatch.setitem(
        PARTICIPANT_ROLE_CONTEXTS,
        context.participant_role,
        context.name,
    )

    assignment = resolve_participant_role(context.participant_role)

    assert assignment.worker_kind == "agent"
    assert assignment.agent is AGENTS["qwen_agent"]
    assert assignment.model is None
    assert assignment.tool_ref is None


def test_tool_context_remains_an_unresolved_tool_reference(
    monkeypatch,
) -> None:
    context = LogicalContextStruct(
        name="tool_test",
        participant_role="tool_test",
        worker_kind="tool",
        worker_ref="fetch_url",
    )
    monkeypatch.setitem(LOGICAL_CONTEXTS, context.name, context)
    monkeypatch.setitem(
        PARTICIPANT_ROLE_CONTEXTS,
        context.participant_role,
        context.name,
    )

    assignment = resolve_participant_role(context.participant_role)

    assert assignment.worker_kind == "tool"
    assert assignment.tool_ref == "fetch_url"
    assert assignment.model is None
    assert assignment.agent is None
