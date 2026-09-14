"""Trusted deterministic Task Executive machinery for Benzaiten.

The historical filename remains temporarily to avoid unnecessary import churn.
This module executes and validates Director-selected work; it does not choose
the next semantic action.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
from typing import TYPE_CHECKING

from config import (
    ACTIONS,
    AGENTS,
    LEGAL_ACTIONS_BY_STATE,
    LOGICAL_CONTEXTS,
    MODELS,
    PARTICIPANT_ROLE_CONTEXTS,
    ARTIFACTS_DIR,
    DB_PATH,
    INBOX_DIR,
    OKF_CONCEPTS_DIR,
    OKF_DIR,
    OKF_PROJECTS_DIR,
    DOCUMENT_PREPARATION_TMP_DIR,
    DOCUMENT_PREPARATION_ARTIFACTS_DIR,
    KNOWLEDGE_EXTRACTION_TMP_DIR,
    KNOWLEDGE_EXTRACTION_ARTIFACTS_DIR,

    SOURCES_DIR,
    TMP_DIR,
    VAULT_DIR,
    WORKSPACE_DIR,
)

from director import DirectorTask
from model_client import ModelClient, ModelClientConfig, ModelResponse
from structures import AgentStruct, LogicalContextStruct, ModelStruct, WorkerKind

if TYPE_CHECKING:
    from document_preparation import PDFPreparationResult

# =====================================================================
# RUNTIME FILESYSTEM CONTRACT
# =====================================================================

RUNTIME_DIRECTORIES = (
    DB_PATH.parent,

    WORKSPACE_DIR,
    INBOX_DIR,
    TMP_DIR,
    ARTIFACTS_DIR,

    DOCUMENT_PREPARATION_TMP_DIR,
    DOCUMENT_PREPARATION_ARTIFACTS_DIR,

    KNOWLEDGE_EXTRACTION_TMP_DIR,
    KNOWLEDGE_EXTRACTION_ARTIFACTS_DIR,

    VAULT_DIR,
    SOURCES_DIR,
    OKF_DIR,
    OKF_PROJECTS_DIR,
    OKF_CONCEPTS_DIR,
)


def ensure_runtime_directories() -> tuple[Path, ...]:
    """Create the configured runtime directory tree without clearing it."""

    for directory in RUNTIME_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)

    return RUNTIME_DIRECTORIES


def get_legal_actions(current_kind: str) -> tuple[str, ...]:
    """Return what may happen without selecting what should happen."""

    try:
        legal_actions = LEGAL_ACTIONS_BY_STATE[current_kind]
    except KeyError as exc:
        raise ValueError(f"Unknown execution state: {current_kind}") from exc

    unknown_actions = set(legal_actions) - set(ACTIONS)
    if unknown_actions:
        raise RuntimeError(
            "Legal state references unregistered actions: "
            f"{sorted(unknown_actions)}"
        )
    return legal_actions


def validate_selected_action(current_kind: str, action: str) -> None:
    """Validate an action already selected by the Director."""

    if action not in get_legal_actions(current_kind):
        raise ValueError(
            f"Action {action!r} is not legal from state {current_kind!r}."
        )
    if not ACTIONS[action].get("enabled", False):
        raise RuntimeError(f"Action is registered but unavailable: {action}")


@dataclass(frozen=True)
class WorkerAssignment:
    """Concrete worker selected by Task Executive for a semantic role."""

    participant_role: str
    logical_context: LogicalContextStruct
    worker_kind: WorkerKind
    model: ModelStruct | None = None
    agent: AgentStruct | None = None
    tool_ref: str | None = None


def resolve_participant_role(participant_role: str) -> WorkerAssignment:
    """Resolve a semantic role according to its configured worker kind."""

    try:
        context_name = PARTICIPANT_ROLE_CONTEXTS[participant_role]
        context = LOGICAL_CONTEXTS[context_name]
    except KeyError as exc:
        raise ValueError(
            f"No configured participant for role: {participant_role}"
        ) from exc

    try:
        if context.worker_kind == "model":
            return WorkerAssignment(
                participant_role=participant_role,
                logical_context=context,
                worker_kind="model",
                model=MODELS[context.worker_ref],
            )
        if context.worker_kind == "agent":
            return WorkerAssignment(
                participant_role=participant_role,
                logical_context=context,
                worker_kind="agent",
                agent=AGENTS[context.worker_ref],
            )
    except KeyError as exc:
        raise ValueError(
            f"Configured {context.worker_kind} is unavailable: "
            f"{context.worker_ref}"
        ) from exc

    if context.worker_kind == "tool":
        # Version 0 has no tool registry. Preserve the distinct reference so
        # later Task Executive machinery can resolve it without conflation.
        return WorkerAssignment(
            participant_role=participant_role,
            logical_context=context,
            worker_kind="tool",
            tool_ref=context.worker_ref,
        )

    raise RuntimeError(f"Unsupported worker kind: {context.worker_kind}")


def resolve_model_context(context_name: str) -> WorkerAssignment:
    """Resolve an already-selected logical context to a configured model."""

    try:
        context = LOGICAL_CONTEXTS[context_name]
    except KeyError as exc:
        raise ValueError(f"Unknown logical context: {context_name}") from exc
    if context.worker_kind != "model":
        raise ValueError(f"Logical context is not model-backed: {context_name}")
    try:
        model = MODELS[context.worker_ref]
    except KeyError as exc:
        raise ValueError(
            f"Configured model is unavailable: {context.worker_ref}"
        ) from exc
    return WorkerAssignment(
        participant_role=context.participant_role,
        logical_context=context,
        worker_kind="model",
        model=model,
    )


def invoke_model_context(
    context_name: str,
    messages: tuple[dict[str, str], ...],
    *,
    response_format: Mapping[str, object] | None = None,
    chat_template_kwargs: Mapping[str, object] | None = None,
) -> ModelResponse:
    """Invoke a Director-selected model context through generic transport."""

    assignment = resolve_model_context(context_name)
    assert assignment.model is not None
    model = assignment.model
    if model.endpoint_url is None:
        raise ValueError(f"Model context has no HTTP endpoint: {context_name}")
    api_key = os.environ.get(model.api_key_env) if model.api_key_env else None
    client_config = ModelClientConfig(
        base_url=model.endpoint_url,
        model_name=model.model_name,
        max_completion_tokens=model.output_tokens,
        temperature=model.temperature,
        api_key=api_key,
    )
    with ModelClient(client_config) as client:
        return client.call_model(
            messages,
            response_format=response_format,
            chat_template_kwargs=chat_template_kwargs,
        )


def prepare_director_task(
    task: DirectorTask,
    *,
    current_kind: str,
    action: str,
) -> dict[str, object]:
    """Prepare a legacy action-state task; retained for the PDF pipeline."""

    validate_selected_action(current_kind, action)
    resolved = resolve_participant_role(task.participant_role)
    return {
        "task": task,
        "action": action,
        "action_definition": ACTIONS[action],
        "resolved_participant": resolved,
    }


def run_pdf_preparation_stage(
    source_pdf: Path,
    *,
    log_console: bool = True,
) -> PDFPreparationResult:
    """Initialize runtime paths and run the existing PDF preparation stage."""

    from document_preparation import run_pdf_preparation_pipeline

    ensure_runtime_directories()

    return run_pdf_preparation_pipeline(
        source_pdf=source_pdf,
        log_console=log_console,
    )


def prepare_managed_director_task(task: DirectorTask) -> dict[str, object]:
    """Prepare validated managed work using the task's semantic action only."""

    if task.work_kind != "execution" or task.action is None:
        raise ValueError("Managed execution requires DirectorTask work_kind/action.")
    resolved = resolve_participant_role(task.participant_role)
    return {
        "task": task,
        "action": task.action,
        "resolved_participant": resolved,
    }
