"""Trusted deterministic Task Executive machinery for Benzaiten.

The historical filename remains temporarily to avoid unnecessary import churn.
This module executes and validates Director-selected work; it does not choose
the next semantic action.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING

from config import (
    ACTIONS,
    AGENTS,
    ARTIFACTS_DIR,
    COMPUTE_NODES,
    DB_PATH,
    DEFAULT_JOB_BUDGET,
    DOCUMENT_PREPARATION_ARTIFACTS_DIR,
    DOCUMENT_PREPARATION_TMP_DIR,
    HOSTS,
    INBOX_DIR,
    KNOWLEDGE_EXTRACTION_ARTIFACTS_DIR,
    KNOWLEDGE_EXTRACTION_TMP_DIR,
    LEGAL_ACTIONS_BY_STATE,
    LOGICAL_CONTEXTS,
    MANAGED_RESOURCE_MAX_BYTES,
    MANAGED_RESOURCE_ROOTS,
    MANAGED_OUTPUT_CONTRACTS,
    MODELS,
    OKF_CONCEPTS_DIR,
    OKF_DIR,
    OKF_PROJECTS_DIR,
    PARTICIPANT_ROLE_CONTEXTS,
    SOURCES_DIR,
    TASK_EXECUTIVE_AGENT,
    TMP_DIR,
    VAULT_DIR,
    WEB_RESEARCH_PROVIDER,
    WORKSPACE_DIR,
)

from director import (
    DirectorTask,
    parse_director_task,
    validate_director_task_for_execution,
)
from model_client import (
    ModelClient,
    ModelClientConfig,
    ModelClientError,
    ModelResponse,
)
from structures import AgentStruct, LogicalContextStruct, ModelStruct, WorkerKind
from task_execution import validate_task_execution_mapping

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


def model_client_config_for_assignment(
    assignment: WorkerAssignment,
) -> ModelClientConfig:
    """Build transport configuration only from a resolved model assignment."""

    if assignment.worker_kind != "model" or assignment.model is None:
        raise ValueError("Managed text execution requires a model assignment.")
    model = assignment.model
    if model.endpoint_url is None:
        raise ValueError(
            "Resolved model assignment has no configured HTTP endpoint."
        )
    api_key = os.environ.get(model.api_key_env) if model.api_key_env else None
    return ModelClientConfig(
        base_url=model.endpoint_url,
        model_name=model.model_name,
        max_completion_tokens=model.output_tokens,
        temperature=model.temperature,
        api_key=api_key,
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
    client_config = model_client_config_for_assignment(assignment)
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
def _schema_for_execution_value(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {
            "type": "object",
            "properties": {
                str(name): _schema_for_execution_value(item)
                for name, item in value.items()
            },
            "required": list(value),
            "additionalProperties": False,
        }
    if isinstance(value, list):
        item_schema = (
            _schema_for_execution_value(value[0])
            if value
            else {}
        )
        return {
            "type": "array",
            "items": item_schema,
            "minItems": len(value),
            "maxItems": len(value),
        }
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if value is None:
        return {"type": "null"}
    raise TypeError(
        f"Unsupported expected-result value: {type(value).__name__}"
    )


def _managed_output_contract_kind(output_contract_ref: object) -> str:
    matches = [
        str(contract["kind"])
        for contract in MANAGED_OUTPUT_CONTRACTS.values()
        if contract.get("ref") == output_contract_ref
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Unconfigured managed output contract: {output_contract_ref!r}"
        )
    return matches[0]


def execution_response_format(
    output_contract_ref: str,
) -> Mapping[str, object] | None:
    """Return transport formatting for a trusted structural contract only."""

    if _managed_output_contract_kind(output_contract_ref) == "json_object":
        return {"type": "json_object"}
    return None


def render_managed_execution_messages(
    *,
    task: Mapping[str, object],
    selected_step: Mapping[str, object],
    resolved_inputs: Mapping[str, object],
) -> tuple[dict[str, str], ...]:
    """Render only the selected task, step contract, and declared inputs."""

    declared_refs = task["input_refs"]
    assert isinstance(declared_refs, list)
    projection = {
        "director_task": deepcopy(dict(task)),
        "selected_plan_step": {
            "id": selected_step["id"],
            "action": selected_step["action"],
            "instructions": selected_step["instructions"],
            "scope_boundary": selected_step["scope_boundary"],
            "expected_result": selected_step["expected_result"],
            "validation": selected_step["validation"],
        },
        "resolved_inputs": [
            {
                "ref": reference,
                "content": deepcopy(resolved_inputs[reference]),
            }
            for reference in declared_refs
        ],
    }
    return (
        {
            "role": "system",
            "content": (
                "Execute the already-selected DirectorTask. Return only the "
                "requested result. Do not select another Plan step, model, "
                "context, endpoint, host, fallback, or evaluation outcome."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(projection, sort_keys=True),
        },
    )


def render_worker_conformance_repair_messages(
    *,
    invalid_output: str,
    validation_detail: str,
    output_contract_ref: str,
) -> tuple[dict[str, str], ...]:
    """Request one representation-only repair from the same worker."""

    return (
        {
            "role": "system",
            "content": (
                "Repair only the representation of your prior result. "
                "Preserve its semantic content exactly. Do not reconsider the "
                "task, add evidence, change conclusions, or choose new work."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "invalid_output": invalid_output,
                "validation_detail": validation_detail,
                "required_output_contract_ref": output_contract_ref,
            }, sort_keys=True),
        },
    )


class ManagedResourceError(ValueError):
    """Mechanical configured-resource failure recorded in TaskExecution."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


def _resource_catalog_by_ref(
    resource_catalog: tuple[Mapping[str, object], ...]
    | list[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    expected = {"ref", "kind", "name", "description"}
    resources: dict[str, Mapping[str, object]] = {}
    for item in resource_catalog:
        if not isinstance(item, Mapping) or set(item) != expected:
            raise ValueError(
                "Managed resource descriptors require exactly ref, kind, "
                "name, and description."
            )
        if any(
            not isinstance(item.get(name), str) or not item[name].strip()
            for name in expected
        ):
            raise ValueError("Managed resource descriptor values must be non-empty.")
        kind = str(item["kind"])
        reference = str(item["ref"])
        if kind not in {"vault", "source", "web"}:
            raise ValueError("Managed resource kind must be vault, source, or web.")
        if not reference.startswith(f"{kind}:"):
            raise ValueError(
                "Managed resource reference must use its declared kind prefix."
            )
        if reference in resources:
            raise ValueError(f"Duplicate managed resource reference: {reference}")
        resources[reference] = item
    return resources


def _read_managed_resource(reference: str, *, kind: str) -> str:
    root = Path(MANAGED_RESOURCE_ROOTS[kind]).resolve()
    locator = reference.split(":", 1)[1]
    candidate = (root / locator).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ManagedResourceError(
            "resource_outside_configured_root",
            f"Resource reference escapes configured {kind} root.",
        ) from exc
    if not candidate.is_file():
        raise ManagedResourceError(
            "resource_unavailable",
            f"Configured {kind} resource is unavailable: {reference}",
        )
    size = candidate.stat().st_size
    if size > MANAGED_RESOURCE_MAX_BYTES:
        raise ManagedResourceError(
            "resource_too_large",
            f"Configured resource exceeds {MANAGED_RESOURCE_MAX_BYTES} bytes.",
        )
    try:
        return candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ManagedResourceError(
            "resource_not_text",
            f"Configured resource is not UTF-8 text: {reference}",
        ) from exc


def _resolve_managed_inputs(
    *,
    task: Mapping[str, object],
    resolved_inputs: Mapping[str, object],
    resource_catalog: tuple[Mapping[str, object], ...]
    | list[Mapping[str, object]],
    web_caller: object = None,
) -> dict[str, object]:
    """Resolve declared refs mechanically; make no semantic routing choice."""

    resources = _resource_catalog_by_ref(resource_catalog)
    declared = task["input_refs"]
    assert isinstance(declared, list)
    selected: dict[str, object] = {}
    for reference in declared:
        assert isinstance(reference, str)
        descriptor = resources.get(reference)
        if descriptor is None:
            if reference not in resolved_inputs:
                raise ValueError(
                    f"Declared DirectorTask inputs are unavailable: [{reference!r}]"
                )
            selected[reference] = deepcopy(resolved_inputs[reference])
            continue

        kind = str(descriptor["kind"])
        if kind in MANAGED_RESOURCE_ROOTS:
            selected[reference] = _read_managed_resource(
                reference, kind=kind,
            )
            continue
        if kind == "web":
            if WEB_RESEARCH_PROVIDER is None or not callable(web_caller):
                raise ManagedResourceError(
                    "web_provider_unavailable",
                    "No configured web research provider is available.",
                )
            result = web_caller(
                WEB_RESEARCH_PROVIDER,
                {
                    "objective": task["objective"],
                    "instruction": task["instruction"],
                    "resource": deepcopy(dict(descriptor)),
                },
            )
            if result is None:
                raise ManagedResourceError(
                    "web_result_empty",
                    "Configured web research provider returned no result.",
                )
            selected[reference] = result
            continue
        raise ManagedResourceError(
            "resource_kind_unavailable",
            f"No configured resolver exists for resource kind {kind!r}.",
        )
    return selected


def _validate_worker_result(
    text: str, output_contract_ref: str,
) -> tuple[object, str, str | None]:
    """Validate representation only; Director judges semantic adequacy."""

    from planning import parse_json_object

    contract_kind = _managed_output_contract_kind(output_contract_ref)
    if contract_kind == "text":
        actual = text.strip()
        if actual:
            return actual, "passed", None
        return (
            actual,
            "failed",
            "Worker result must be non-empty text.",
        )
    if contract_kind == "json_object":
        try:
            actual = parse_json_object(text, stage="Managed worker execution")
        except ValueError as exc:
            return text, "failed", str(exc)
        return actual, "passed", None
    raise RuntimeError(f"Unsupported managed output contract: {contract_kind}")


def _normalized_execution_error(error: Exception) -> dict[str, object]:
    if isinstance(error, ManagedResourceError):
        return {
            "code": error.code,
            "category": "execution",
            "detail": str(error),
            "retryable": False,
            "source": "tool",
        }
    if isinstance(error, ModelClientError):
        if error.kind == "timeout":
            category = "timeout"
        elif error.kind in {"authentication", "rate_limit"}:
            category = "rejection"
        elif error.kind in {
            "bad_request", "context_length", "protocol_error",
            "empty_response",
        }:
            category = "validation"
        else:
            category = "execution"
        return {
            "code": f"model_{error.kind}",
            "category": category,
            "detail": str(error),
            "retryable": error.retryable,
            "source": "model",
        }
    return {
        "code": "task_executive_internal_error",
        "category": "execution",
        "detail": str(error) or type(error).__name__,
        "retryable": False,
        "source": "task_executive",
    }


def _build_task_execution(
    *,
    execution_id: str,
    task: Mapping[str, object],
    selected_step: Mapping[str, object],
    assignment: WorkerAssignment,
    timestamp: str,
    response: ModelResponse | None,
    tool_result: object | None,
    error: Exception | None,
) -> dict[str, object]:
    """Build one authoritative TaskExecution without another result class."""

    model = assignment.model
    if assignment.worker_kind == "model":
        assert model is not None
        deployment_agent = None
        deployment_model = model.model_name
        deployment_node = model.node
    elif assignment.worker_kind == "tool":
        executive_agent = AGENTS[TASK_EXECUTIVE_AGENT]
        deployment_agent = executive_agent.name
        deployment_model = None
        deployment_node = executive_agent.node
    else:
        raise ValueError(
            "Managed V0 execution does not yet configure agent mechanics."
        )
    try:
        compute_node = COMPUTE_NODES[deployment_node]
        host = HOSTS[compute_node.phys_host]
    except KeyError as exc:
        raise ValueError(
            f"Resolved deployment metadata is unavailable: {exc.args[0]}"
        ) from exc

    if error is None:
        if response is not None:
            raw_result = response.text
        elif tool_result is not None:
            raw_result = json.dumps(tool_result, ensure_ascii=False)
        else:
            raise ValueError("Successful execution requires worker content.")
        content, validation_outcome, deviation = _validate_worker_result(
            raw_result, str(task["output_contract_ref"]),
        )
        result = {
            "status": (
                "complete" if validation_outcome == "passed" else "partial"
            ),
            "content": content,
            "artifact_refs": [],
            "notes": (
                "Result conforms to the trusted structural output contract."
                if validation_outcome == "passed"
                else "Result captured; structural validation did not pass."
            ),
        }
        normalized_error = None
        status = "completed"
        achieved_result = deepcopy(content)
        if response is not None:
            session = response.request_id
            events = [{
                "type": "model_call_completed",
                "request_id": response.request_id,
                "server_request_id": response.server_request_id,
                "finish_reason": response.finish_reason,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
                "latency_ms": response.latency_ms,
            }]
        else:
            session = execution_id
            events = [{
                "type": "configured_resource_execution_completed",
                "session": session,
            }]
    else:
        result = None
        normalized_error = _normalized_execution_error(error)
        status = "failed"
        achieved_result = None
        validation_outcome = "inconclusive"
        deviation = normalized_error["detail"]
        session = (
            error.request_id
            if isinstance(error, ModelClientError)
            else execution_id
        )
        events = [{
            "type": (
                "model_call_failed"
                if isinstance(error, ModelClientError)
                else "configured_resource_execution_failed"
            ),
            "request_id": session,
            "error_code": normalized_error["code"],
        }]

    plan_ref = task["plan_ref"]
    step_ref = selected_step["id"]
    output_contract_ref = task["output_contract_ref"]
    execution = {
        "execution_id": execution_id,
        "task_ref": task["task_id"],
        "job_ref": task["job_ref"],
        "control": {
            "status": status,
            "priority": "medium",
            "attempt": {"current": 1, "maximum": 1},
        },
        "resolved": {
            "participant_role": task["participant_role"],
            "logical_context": assignment.logical_context.name,
            "worker_kind": assignment.worker_kind,
            "worker_ref": assignment.logical_context.worker_ref,
            "requirements": list(task["requirements"]),
        },
        "output_contract_ref": output_contract_ref,
        "result": result,
        "error": normalized_error,
        "provenance": {
            "prompt_artifact_ref": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        "persistence": {"save": False, "location": None},
        "trace": {
            "resolved_by": "task_executive",
            "resolved_at": timestamp,
            "deployment": {
                "agent": deployment_agent,
                "session": session,
                "model": deployment_model,
                "compute_node": compute_node.node,
                "host": host.phys_host,
            },
            "events": events,
        },
        "plan_execution": {
            "plan_ref": plan_ref,
            "execution_authorizer": TASK_EXECUTIVE_AGENT,
            "steps": [{
                "step_ref": step_ref,
                "on_failure": {
                    "policy": "stop",
                    "max_retries": 0,
                    "fallback_step_ref": None,
                    "record_failure": True,
                },
            }],
            "authorization": {
                "authorized": True,
                "authorizer_ref": TASK_EXECUTIVE_AGENT,
                "authorization_record_ref": f"{execution_id}:authorization",
                "authorized_at": timestamp,
            },
            "current_step_ref": step_ref,
            "next_step_ref": None,
            "expected_result_ref": f"{step_ref}#expected_result",
            "expected_result_snapshot": selected_step["expected_result"],
            "achieved_result": achieved_result,
            "deviation": deviation,
            "validation_outcome": validation_outcome,
            "validation_evidence_refs": [],
            "replan_requested": False,
            "replan_reason": None,
            "outcomes": [],
            "persistence": {
                "save": False,
                "location": None,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        },
        "artifact_record": None,
    }
    issues = validate_task_execution_mapping(execution)
    if issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in issues
        )
        raise ValueError(f"Invalid assembled TaskExecution: {details}")
    return execution


def execute_managed_director_task(
    task: Mapping[str, object],
    *,
    job_ref: str,
    certified_plan: Mapping[str, object],
    selected_step: Mapping[str, object],
    resolved_inputs: Mapping[str, object],
    resource_catalog: tuple[Mapping[str, object], ...]
    | list[Mapping[str, object]] = (),
    trusted_input_refs: tuple[str, ...] | list[str] | None = None,
    trusted_output_contract_ref: str | None = None,
    model_caller: object = None,
    web_caller: object = None,
    execution_id: str | None = None,
    timestamp: str | None = None,
    reasoning_task_count: int = 0,
    reasoning_task_limit: int | None = None,
) -> Mapping[str, object]:
    """Validate, resolve, invoke, and record one selected managed task."""

    from uuid import uuid4

    issues = validate_director_task_for_execution(
        task,
        certified_plan=certified_plan,
        selected_step=selected_step,
        job_ref=job_ref,
        trusted_input_refs=trusted_input_refs,
        trusted_output_contract_ref=trusted_output_contract_ref,
    )
    if issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in issues
        )
        raise ValueError(
            f"Task Executive rejected DirectorTask before resolution: {details}"
        )
    parsed_task = parse_director_task(task)
    prepared = prepare_managed_director_task(parsed_task)
    assignment = prepared["resolved_participant"]
    assert isinstance(assignment, WorkerAssignment)
    if assignment.worker_kind == "agent":
        raise ValueError(
            "Managed V0 agent execution mechanics are not configured."
        )
    if assignment.worker_kind == "model":
        model_client_config_for_assignment(assignment)
    elif assignment.worker_kind != "tool":
        raise ValueError(
            f"Unsupported managed worker kind: {assignment.worker_kind}"
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
        raise ValueError(
            "Reasoning-task counts must be non-negative integers."
        )
    selected_execution_id = execution_id or f"execution-{uuid4().hex}"
    selected_timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    selected_inputs: dict[str, object] = {}
    resource_error: Exception | None = None
    try:
        selected_inputs = _resolve_managed_inputs(
            task=task,
            resolved_inputs=resolved_inputs,
            resource_catalog=resource_catalog,
            web_caller=web_caller,
        )
    except ManagedResourceError as exc:
        resource_error = exc

    messages: tuple[dict[str, str], ...] = ()
    response: ModelResponse | None = None
    tool_result: object | None = None
    call_error = resource_error
    reasoning_call_number: int | None = None
    worker_calls: list[dict[str, object]] = []
    conformance_repairs: list[dict[str, object]] = []
    if resource_error is None and assignment.worker_kind == "model":
        caller = invoke_model_context if model_caller is None else model_caller
        if not callable(caller):
            raise TypeError("model_caller must be callable.")
        assert assignment.model is not None
        response_format = (
            execution_response_format(str(task["output_contract_ref"]))
            if assignment.model.supports_json_schema
            else None
        )
        template_kwargs = (
            assignment.model.structured_output_chat_template_kwargs
            if response_format is not None
            else None
        )
        messages = render_managed_execution_messages(
            task=task,
            selected_step=selected_step,
            resolved_inputs=selected_inputs,
        )

        def call_worker(
            stage: str,
            selected_messages: tuple[dict[str, str], ...],
        ) -> tuple[ModelResponse | None, Exception | None]:
            nonlocal reasoning_task_count, reasoning_call_number
            if reasoning_task_count >= limit:
                raise RuntimeError("Reasoning-task budget exhausted.")
            reasoning_task_count += 1
            reasoning_call_number = reasoning_task_count
            selected_response: ModelResponse | None = None
            selected_error: Exception | None = None
            try:
                raw_response = caller(
                    assignment.logical_context.name,
                    selected_messages,
                    response_format=response_format,
                    chat_template_kwargs=template_kwargs,
                )
                if not isinstance(raw_response, ModelResponse):
                    raise TypeError(
                        "Managed worker caller must return ModelResponse."
                    )
                selected_response = raw_response
            except Exception as exc:
                selected_error = exc
            worker_calls.append({
                "stage": stage,
                "logical_context": assignment.logical_context.name,
                "model_name": assignment.model.model_name,
                "node": assignment.model.node,
                "endpoint_url": assignment.model.endpoint_url,
                "request_id": (
                    selected_response.request_id
                    if selected_response is not None
                    else (
                        selected_error.request_id
                        if isinstance(selected_error, ModelClientError)
                        else selected_execution_id
                    )
                ),
                "reasoning_task": reasoning_call_number,
            })
            return selected_response, selected_error

        response, call_error = call_worker(
            "configured_worker_execution", messages,
        )
        if response is not None and call_error is None:
            _, structural_outcome, structural_detail = _validate_worker_result(
                response.text, str(task["output_contract_ref"]),
            )
            if structural_outcome == "failed":
                repair_messages = render_worker_conformance_repair_messages(
                    invalid_output=response.text,
                    validation_detail=structural_detail or "invalid structure",
                    output_contract_ref=str(task["output_contract_ref"]),
                )
                invalid_response = response
                response, call_error = call_worker(
                    "configured_worker_conformance_repair", repair_messages,
                )
                conformance_repairs.append({
                    "artifact_kind": "managed_worker_result",
                    "attempt": 1,
                    "producer_context": assignment.logical_context.name,
                    "invalid_output": invalid_response.text,
                    "validation_detail": structural_detail,
                    "repaired_output": (
                        response.text if response is not None else None
                    ),
                })
    elif resource_error is None:
        tool_result = {
            "resources": [
                {"ref": reference, "content": deepcopy(content)}
                for reference, content in selected_inputs.items()
            ],
        }

    execution = _build_task_execution(
        execution_id=selected_execution_id,
        task=task,
        selected_step=selected_step,
        assignment=assignment,
        timestamp=selected_timestamp,
        response=response,
        tool_result=tool_result,
        error=call_error,
    )
    if conformance_repairs:
        execution["trace"]["events"].append({
            "type": "worker_conformance_repair",
            "attempt": 1,
            "producer_context": assignment.logical_context.name,
        })
    model = assignment.model
    mechanical_call_record = {
        "stage": (
            "configured_worker_execution"
            if assignment.worker_kind == "model" and resource_error is None
            else "configured_resource_execution"
        ),
        "logical_context": assignment.logical_context.name,
        "model_name": model.model_name if model is not None else None,
        "node": (
            model.node
            if model is not None
            else AGENTS[TASK_EXECUTIVE_AGENT].node
        ),
        "endpoint_url": model.endpoint_url if model is not None else None,
        "request_id": (
            response.request_id
            if response is not None
            else (
                call_error.request_id
                if isinstance(call_error, ModelClientError)
                else selected_execution_id
            )
        ),
        "reasoning_task": reasoning_call_number,
    }
    call_records = worker_calls or [mechanical_call_record]
    call_record = call_records[-1]
    return {
        "task_execution": execution,
        "execution_messages": messages,
        "resolved_participant": assignment,
        "call": call_record,
        "calls": call_records,
        "conformance_repairs": conformance_repairs,
        "reasoning_task_count": reasoning_task_count,
    }


MANAGED_WORK_RESUME_FIELDS = frozenset({
    "job_ref", "current_plan_ref", "accepted_checkpoint_ref",
    "pending_guidance_outcome_ref", "status", "guidance_policy",
    "frontier_authorized", "updated_at",
})
MANAGED_WORK_RESUME_STATUSES = frozenset({
    "active", "awaiting_guidance", "completed", "unresolved",
})
_ARTIFACT_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
GUIDANCE_POLICIES = frozenset({
    "USER_ONLY", "ASK_BEFORE_FRONTIER", "FRONTIER_ALLOWED",
})


def validate_guidance_authorization(
    guidance_policy: object,
    frontier_authorized: object,
) -> tuple[str, ...]:
    """Validate user-owned operational frontier authorization."""

    errors: list[str] = []
    if guidance_policy not in GUIDANCE_POLICIES:
        errors.append("invalid guidance_policy")
    if not isinstance(frontier_authorized, bool):
        errors.append("frontier_authorized must be boolean")
    elif guidance_policy == "USER_ONLY" and frontier_authorized:
        errors.append("USER_ONLY cannot authorize frontier guidance")
    elif guidance_policy == "FRONTIER_ALLOWED" and not frontier_authorized:
        errors.append(
            "FRONTIER_ALLOWED requires explicit persisted authorization"
        )
    return tuple(errors)


def resolve_guidance_target(
    requested_target: str,
    *,
    guidance_policy: str,
    frontier_authorized: bool,
    frontier_provider_ref: str | None,
) -> str:
    """Resolve user/frontier target mechanically from persisted authority."""

    errors = validate_guidance_authorization(
        guidance_policy, frontier_authorized,
    )
    if errors:
        raise ValueError("; ".join(errors))
    if requested_target not in {"user", "frontier"}:
        raise ValueError("Guidance target must be user or frontier.")
    if frontier_provider_ref is not None and (
        not isinstance(frontier_provider_ref, str)
        or not frontier_provider_ref.strip()
    ):
        raise ValueError(
            "frontier_provider_ref must be null or a non-empty configured ref."
        )
    if requested_target == "user":
        return "user"
    if (
        frontier_authorized
        and guidance_policy in {
            "ASK_BEFORE_FRONTIER", "FRONTIER_ALLOWED",
        }
        and frontier_provider_ref is not None
    ):
        return "frontier"
    return "user"


def _managed_artifact_component(value: str) -> str:
    """Map a trusted protocol reference to one collision-resistant filename."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("Managed-work artifact identity must be non-empty.")
    if _ARTIFACT_COMPONENT.fullmatch(value):
        return value
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    if not stem:
        stem = "artifact"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{stem[:48]}-{digest}"


def managed_work_artifact_paths(
    job_ref: str,
    *,
    artifact_root: Path | None = None,
) -> dict[str, Path]:
    """Resolve passive managed-work paths without creating semantic state."""

    base = (
        ARTIFACTS_DIR / "managed_work"
        if artifact_root is None
        else Path(artifact_root)
    )
    job = base / _managed_artifact_component(job_ref)
    return {
        "root": job,
        "request": job / "request.json",
        "plans": job / "plans",
        "tasks": job / "tasks",
        "executions": job / "executions",
        "calls": job / "calls",
        "resume": job / "resume.json",
    }


def _json_text(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True,
    ) + "\n"


def _write_json_once(path: Path, value: object) -> None:
    """Write one immutable JSON artifact or prove an identical prior write."""

    serialized = _json_text(value)
    if path.exists():
        if path.read_text(encoding="utf-8") != serialized:
            raise FileExistsError(
                f"Immutable managed-work artifact already differs: {path}"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(serialized)


def _replace_json_atomically(path: Path, value: object) -> None:
    """Replace only the passive resume pointer atomically."""

    from uuid import uuid4

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(_json_text(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _resume_checkpoint_ref(
    accepted_checkpoints: object,
) -> str:
    if not isinstance(accepted_checkpoints, list) or not accepted_checkpoints:
        raise ValueError("Managed-work state requires the root checkpoint.")
    checkpoint = accepted_checkpoints[-1]
    if not isinstance(checkpoint, Mapping):
        raise ValueError("Managed-work checkpoint must be an object.")
    if checkpoint.get("kind") == "execution":
        value = checkpoint.get("outcome_ref")
    elif checkpoint.get("kind") == "root":
        value = checkpoint.get("revision_ref")
    else:
        value = None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Managed-work checkpoint identity is incomplete.")
    return value


def validate_managed_work_resume(
    resume: object,
) -> tuple[str, ...]:
    """Validate the passive operational resume pointer shape."""

    if not isinstance(resume, Mapping):
        return ("resume must be an object",)
    errors: list[str] = []
    unknown = set(resume) - MANAGED_WORK_RESUME_FIELDS
    missing = MANAGED_WORK_RESUME_FIELDS - set(resume)
    if unknown:
        errors.append(f"unknown resume fields: {sorted(unknown)}")
    if missing:
        errors.append(f"missing resume fields: {sorted(missing)}")
    for name in (
        "job_ref", "current_plan_ref", "accepted_checkpoint_ref",
        "updated_at",
    ):
        if not isinstance(resume.get(name), str) or not resume[name].strip():
            errors.append(f"{name} must be a non-empty string")
    pending = resume.get("pending_guidance_outcome_ref")
    if pending is not None and (
        not isinstance(pending, str) or not pending.strip()
    ):
        errors.append(
            "pending_guidance_outcome_ref must be null or a non-empty string"
        )
    if resume.get("status") not in MANAGED_WORK_RESUME_STATUSES:
        errors.append("invalid managed-work resume status")
    errors.extend(validate_guidance_authorization(
        resume.get("guidance_policy"),
        resume.get("frontier_authorized"),
    ))
    if (
        resume.get("status") == "awaiting_guidance"
        and pending is None
    ):
        errors.append("awaiting_guidance requires a pending outcome")
    if (
        resume.get("status") != "awaiting_guidance"
        and pending is not None
    ):
        errors.append("only awaiting_guidance may retain a pending outcome")
    return tuple(errors)


def resolve_original_request(
    root_plan: Mapping[str, object],
    resolved_inputs: Mapping[str, object],
) -> str:
    """Resolve immutable mandate contents; verify identity, never meaning."""

    reference = root_plan.get("current_work_ref")
    if not isinstance(resolved_inputs, Mapping):
        raise ValueError("Original request input mapping is unavailable.")
    if not isinstance(reference, str):
        raise ValueError("Root Plan lacks an original request reference.")
    request = resolved_inputs.get(reference)
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Original request contents are unavailable; Plan summaries cannot replace the mandate.")
    # Normal planning creates request:<sha256>; other trusted callers may use
    # opaque references. Never reinterpret either as a semantic summary.
    digest = reference.removeprefix("request:")
    if reference.startswith("request:") and len(digest) == 64:
        if hashlib.sha256(request.encode("utf-8")).hexdigest() != digest:
            raise ValueError("Original request digest does not match the root Plan reference.")
    return request


def persist_managed_work_run(
    run_result: Mapping[str, object],
    *,
    job_ref: str,
    resolved_inputs: Mapping[str, object],
    artifact_root: Path | None = None,
    timestamp: str | None = None,
) -> Mapping[str, object]:
    """Persist immutable run artifacts and atomically advance resume.json."""

    from task_execution import validate_task_execution_mapping

    plans = run_result.get("plan_history")
    if not isinstance(plans, list) or not plans:
        raise ValueError("Managed-work result lacks immutable Plan history.")
    if not isinstance(plans[0], Mapping):
        raise ValueError("Managed-work Plan history contains a non-object.")
    resolve_original_request(plans[0], resolved_inputs)

    paths = managed_work_artifact_paths(
        job_ref, artifact_root=artifact_root,
    )
    for name in ("plans", "tasks", "executions", "calls"):
        paths[name].mkdir(parents=True, exist_ok=True)

    written_at = timestamp or datetime.now(timezone.utc).isoformat()
    request = {
        "job_ref": job_ref,
        "resolved_inputs": deepcopy(dict(resolved_inputs)),
        "available_resources": deepcopy(
            list(run_result.get("available_resources", []))
        ),
    }
    _write_json_once(paths["request"], request)

    plan_paths: dict[str, Path] = {}
    for plan in plans:
        if not isinstance(plan, Mapping):
            raise ValueError("Managed-work Plan history contains a non-object.")
        revision = plan.get("revision")
        revision_ref = plan.get("revision_ref")
        if (
            isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
            or not isinstance(revision_ref, str)
        ):
            raise ValueError("Managed-work Plan revision identity is invalid.")
        path = paths["plans"] / f"rev-{revision:04d}.json"
        _write_json_once(path, plan)
        plan_paths[revision_ref] = path

    tasks = run_result.get("director_tasks")
    if not isinstance(tasks, list):
        raise ValueError("Managed-work result tasks must be an array.")
    for task in tasks:
        if not isinstance(task, Mapping):
            raise ValueError("Managed-work task artifact must be an object.")
        task_id = task.get("task_id")
        path = paths["tasks"] / (
            f"{_managed_artifact_component(str(task_id))}.json"
        )
        _write_json_once(path, task)

    executions = run_result.get("task_executions")
    if not isinstance(executions, list):
        raise ValueError("Managed-work executions must be an array.")
    persisted_executions: list[dict[str, object]] = []
    for execution in executions:
        if not isinstance(execution, Mapping):
            raise ValueError("TaskExecution artifact must be an object.")
        persisted = deepcopy(dict(execution))
        execution_id = persisted.get("execution_id")
        execution_path = paths["executions"] / (
            f"{_managed_artifact_component(str(execution_id))}.json"
        )
        persisted["persistence"] = {
            "save": True,
            "location": str(execution_path),
        }
        plan_execution = persisted["plan_execution"]
        plan_ref = plan_execution["plan_ref"]
        plan_execution["persistence"] = {
            "save": True,
            "location": str(plan_paths[plan_ref]),
            "created_at": plan_execution["persistence"]["created_at"],
            "updated_at": written_at,
        }
        persisted["provenance"]["updated_at"] = written_at
        issues = validate_task_execution_mapping(persisted)
        if issues:
            details = "; ".join(
                f"{item.field}: {item.message}" for item in issues
            )
            raise ValueError(
                f"Cannot persist invalid TaskExecution: {details}"
            )
        _write_json_once(execution_path, persisted)
        persisted_executions.append(persisted)

    calls = run_result.get("calls")
    if not isinstance(calls, list):
        raise ValueError("Managed-work reasoning calls must be an array.")
    for index, call in enumerate(calls, start=1):
        if not isinstance(call, Mapping):
            raise ValueError("Managed-work call record must be an object.")
        call_identity = (
            str(call.get("request_id") or call.get("stage") or index)
        )
        call_file = (
            f"{index:04d}-{_managed_artifact_component(call_identity)}"
        )
        request_record = {
            "stage": call.get("stage"),
            "logical_context": call.get("logical_context"),
            "reasoning_task": call.get("reasoning_task"),
        }
        response_record = {
            key: deepcopy(value)
            for key, value in call.items()
            if key not in request_record
        }
        _write_json_once(
            paths["calls"] / f"{call_file}.request.json",
            request_record,
        )
        _write_json_once(
            paths["calls"] / f"{call_file}.response.json",
            response_record,
        )

    run_status = run_result.get("status")
    pending_guidance_ref = None
    if run_status == "accepted":
        resume_status = "completed"
    elif run_status == "awaiting_guidance":
        resume_status = "awaiting_guidance"
        for execution in reversed(persisted_executions):
            outcomes = execution["plan_execution"]["outcomes"]
            if outcomes and outcomes[-1]["decision"] == "ASK_GUIDANCE":
                pending_guidance_ref = outcomes[-1]["id"]
                break
        if pending_guidance_ref is None:
            raise ValueError(
                "awaiting_guidance requires a persisted ASK_GUIDANCE outcome."
            )
    elif run_status in {"execution_transition_budget_exhausted", "semantic_plan_unresolved"}:
        resume_status = "unresolved"
    else:
        resume_status = "active"

    resume = {
        "job_ref": job_ref,
        "current_plan_ref": plans[-1]["revision_ref"],
        "accepted_checkpoint_ref": _resume_checkpoint_ref(
            run_result.get("accepted_checkpoints")
        ),
        "pending_guidance_outcome_ref": pending_guidance_ref,
        "status": resume_status,
        "guidance_policy": run_result.get(
            "guidance_policy", "USER_ONLY",
        ),
        "frontier_authorized": run_result.get(
            "frontier_authorized", False,
        ),
        "updated_at": written_at,
    }
    resume_errors = validate_managed_work_resume(resume)
    if resume_errors:
        raise ValueError(
            "Invalid managed-work resume state: " + "; ".join(resume_errors)
        )
    _replace_json_atomically(paths["resume"], resume)

    persisted_result = deepcopy(dict(run_result))
    persisted_result["task_executions"] = persisted_executions
    persisted_result["resume_state"] = resume
    persisted_result["artifact_root"] = str(paths["root"])
    return persisted_result


def update_managed_work_guidance_policy(
    job_ref: str,
    *,
    guidance_policy: str,
    frontier_authorized: bool,
    artifact_root: Path | None = None,
    timestamp: str | None = None,
) -> Mapping[str, object]:
    """Atomically replace only user-owned authorization in resume.json."""

    errors = validate_guidance_authorization(
        guidance_policy, frontier_authorized,
    )
    if errors:
        raise ValueError("Invalid guidance authorization: " + "; ".join(errors))
    paths = managed_work_artifact_paths(
        job_ref, artifact_root=artifact_root,
    )
    resume = json.loads(paths["resume"].read_text(encoding="utf-8"))
    resume_errors = validate_managed_work_resume(resume)
    if resume_errors:
        raise ValueError(
            "Invalid persisted resume state: " + "; ".join(resume_errors)
        )
    if resume["job_ref"] != job_ref:
        raise ValueError("Persisted resume job_ref does not match the request.")
    updated = deepcopy(dict(resume))
    updated["guidance_policy"] = guidance_policy
    updated["frontier_authorized"] = frontier_authorized
    updated["updated_at"] = (
        timestamp or datetime.now(timezone.utc).isoformat()
    )
    final_errors = validate_managed_work_resume(updated)
    if final_errors:
        raise ValueError(
            "Invalid updated guidance authorization: "
            + "; ".join(final_errors)
        )
    _replace_json_atomically(paths["resume"], updated)
    return updated


def load_managed_work_state(
    job_ref: str,
    *,
    artifact_root: Path | None = None,
) -> Mapping[str, object]:
    """Reload and validate a passive persisted managed-work state."""

    from planning import execution_transition_budget_state
    from task_execution import (
        validate_task_execution_checkpoint_context,
        validate_task_execution_mapping,
    )

    paths = managed_work_artifact_paths(
        job_ref, artifact_root=artifact_root,
    )

    def read_json(path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))

    resume = read_json(paths["resume"])
    resume_errors = validate_managed_work_resume(resume)
    if resume_errors:
        raise ValueError(
            "Invalid persisted resume state: " + "; ".join(resume_errors)
        )
    if resume["job_ref"] != job_ref:
        raise ValueError("Persisted resume job_ref does not match the request.")

    plans = [
        read_json(path)
        for path in sorted(paths["plans"].glob("rev-*.json"))
    ]
    transition_state = execution_transition_budget_state(plans)
    plans_by_ref = {
        plan["revision_ref"]: plan for plan in plans
        if isinstance(plan, Mapping)
    }
    if resume["current_plan_ref"] != plans[-1]["revision_ref"]:
        raise ValueError(
            "Persisted resume does not select the latest chronological Plan."
        )

    tasks = [
        read_json(path)
        for path in sorted(paths["tasks"].glob("*.json"))
    ]
    executions = [
        read_json(path)
        for path in sorted(paths["executions"].glob("*.json"))
    ]
    accepted_outcomes: dict[str, Mapping[str, object]] = {}
    all_outcomes: dict[str, Mapping[str, object]] = {}
    for execution in executions:
        issues = validate_task_execution_mapping(execution)
        if issues:
            details = "; ".join(
                f"{item.field}: {item.message}" for item in issues
            )
            raise ValueError(
                f"Invalid persisted TaskExecution: {details}"
            )
        for outcome in execution["plan_execution"]["outcomes"]:
            all_outcomes[outcome["id"]] = outcome
            if outcome["decision"] == "ACCEPT":
                accepted_outcomes[outcome["id"]] = outcome
    for execution in executions:
        issues = validate_task_execution_checkpoint_context(
            execution,
            plans_by_ref=plans_by_ref,
            accepted_outcomes_by_ref=accepted_outcomes,
        )
        if issues:
            details = "; ".join(
                f"{item.field}: {item.message}" for item in issues
            )
            raise ValueError(
                f"Invalid persisted checkpoint lineage: {details}"
            )

    accepted_checkpoint_ref = resume["accepted_checkpoint_ref"]
    if (
        accepted_checkpoint_ref != plans[0]["revision_ref"]
        and accepted_checkpoint_ref not in accepted_outcomes
    ):
        raise ValueError(
            "Persisted accepted checkpoint does not resolve to root or ACCEPT."
        )
    pending_ref = resume["pending_guidance_outcome_ref"]
    if pending_ref is not None and (
        pending_ref not in all_outcomes
        or all_outcomes[pending_ref]["decision"] != "ASK_GUIDANCE"
    ):
        raise ValueError(
            "Persisted pending guidance does not resolve to ASK_GUIDANCE."
        )

    request_state = read_json(paths["request"])
    if not isinstance(request_state, Mapping):
        raise ValueError("Persisted managed-work request must be an object.")
    resolve_original_request(plans[0], request_state.get("resolved_inputs", {}))
    call_requests = [
        read_json(path)
        for path in sorted(paths["calls"].glob("*.request.json"))
    ]
    reasoning_numbers = [
        record.get("reasoning_task")
        for record in call_requests
        if isinstance(record, Mapping)
        and isinstance(record.get("reasoning_task"), int)
        and not isinstance(record.get("reasoning_task"), bool)
    ]
    return {
        "resume_state": resume,
        "plan_history": plans,
        "director_tasks": tasks,
        "task_executions": executions,
        "execution_transition_state": transition_state,
        "reasoning_task_count": max(reasoning_numbers, default=0),
        "resolved_inputs": deepcopy(
            dict(request_state.get("resolved_inputs", {}))
        ),
        "available_resources": deepcopy(
            list(request_state.get("available_resources", []))
        ),
        "artifact_root": str(paths["root"]),
    }
