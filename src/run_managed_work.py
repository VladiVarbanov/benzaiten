"""Thin synchronous launcher for one managed-work execution cycle.

This module loads passive persisted inputs and delegates all semantic work to
the existing Iteration-3 controller. It does not select a Plan step, resolve a
worker, or judge execution evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _load_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Cannot read {label} at {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {label} at {path}: {error}") from error


def load_certified_plan(path: Path) -> dict[str, object]:
    """Load and prove one passive planning-certified root Plan artifact."""

    from planning import validate_planning_root_checkpoint

    value = _load_json(Path(path), label="certified Plan")
    if not isinstance(value, Mapping):
        raise ValueError("Certified Plan artifact must contain one JSON object.")
    plan = dict(value)
    issues = validate_planning_root_checkpoint(plan)
    if issues:
        details = "; ".join(
            f"{item.field}: {item.message}" for item in issues
        )
        raise ValueError(
            f"Managed-work bootstrap requires a certified @r1 Plan: {details}"
        )
    return plan


def load_resolved_inputs(path: Path) -> dict[str, object]:
    """Load the trusted reference-to-value input mapping for the Plan."""

    value = _load_json(Path(path), label="resolved inputs")
    if not isinstance(value, Mapping):
        raise ValueError("Resolved inputs artifact must contain one JSON object.")
    return dict(value)


def load_available_resources(path: Path | None) -> tuple[dict[str, object], ...]:
    """Load optional semantic resource descriptors; mechanics remain configured."""

    if path is None:
        return ()
    value = _load_json(Path(path), label="available resources")
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or any(not isinstance(item, Mapping) for item in value)
    ):
        raise ValueError(
            "Available resources artifact must contain a JSON array of objects."
        )
    return tuple(dict(item) for item in value)


def run_managed_work(
    certified_plan_path: Path,
    *,
    job_ref: str,
    resolved_inputs: Mapping[str, object],
    available_resources: Sequence[Mapping[str, object]] = (),
    artifact_root: Path | None = None,
    guidance_policy: str = "USER_ONLY",
    frontier_authorized: bool = False,
    reasoning_task_count: int | None = None,
) -> Mapping[str, object]:
    """Load one certified Plan and delegate one fresh job to Iteration 3."""

    from director import run_iteration_3
    from orchestrator import (
        load_managed_work_state,
        managed_work_artifact_paths,
    )

    if not isinstance(job_ref, str) or not job_ref.strip():
        raise ValueError("job_ref must be a non-empty string.")
    if (
        isinstance(reasoning_task_count, bool)
        or not isinstance(reasoning_task_count, int)
        or reasoning_task_count < 0
    ):
        raise ValueError(
            "Prior planning reasoning-call consumption is required. Supply "
            "--reasoning-task-count from the trusted planning trace; "
            "planning iteration 3 is not a model-call count."
        )
    plan = load_certified_plan(Path(certified_plan_path))
    base = (
        managed_work_artifact_paths(job_ref)["root"].parent
        if artifact_root is None
        else Path(artifact_root)
    )
    paths = managed_work_artifact_paths(job_ref, artifact_root=base)
    if paths["resume"].exists():
        state = load_managed_work_state(job_ref, artifact_root=base)
        resume = state["resume_state"]
        raise RuntimeError(
            "Managed-work job already has validated persisted state "
            f"({resume['status']}, current Plan "
            f"{resume['current_plan_ref']}); implicit replay is forbidden."
        )

    return run_iteration_3(
        plan,
        job_ref=job_ref,
        resolved_inputs=dict(resolved_inputs),
        available_resources=tuple(dict(item) for item in available_resources),
        artifact_root=base,
        guidance_policy=guidance_policy,
        frontier_authorized=frontier_authorized,
        reasoning_task_count=reasoning_task_count,
    )


def _proof_projection(result: Mapping[str, object]) -> dict[str, object]:
    """Project the evidence needed to inspect one live vertical proof."""

    plans = result.get("plan_history", [])
    return {
        "status": result.get("status"),
        "selected_certified_plan_ref": (
            plans[0].get("revision_ref")
            if isinstance(plans, list) and plans
            and isinstance(plans[0], Mapping)
            else None
        ),
        "director_selections": result.get("director_selections", []),
        "director_tasks": result.get("director_tasks", []),
        "calls": result.get("calls", []),
        "task_executions": result.get("task_executions", []),
        "evaluations": result.get("evaluations", []),
        "semantic_plan_assessments": result.get("semantic_plan_assessments", []),
        "semantic_boundary_corrections": result.get("semantic_boundary_corrections", []),
        "semantic_plan_error": result.get("semantic_plan_error"),
        "conformance_repairs": result.get("conformance_repairs", []),
        "accepted_checkpoints": result.get("accepted_checkpoints", []),
        "execution_transition_state": result.get(
            "execution_transition_state"
        ),
        "resume_state": result.get("resume_state"),
        "artifact_root": result.get("artifact_root"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="run_managed_work",
        description=(
            "Run one persisted certified Plan through the configured "
            "Managed-Work V0 execution boundary."
        ),
    )
    parser.add_argument("certified_plan", type=Path)
    parser.add_argument("--job-ref", required=True)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--resources", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument(
        "--guidance-policy",
        choices=("USER_ONLY", "ASK_BEFORE_FRONTIER", "FRONTIER_ALLOWED"),
        default="USER_ONLY",
    )
    parser.add_argument("--frontier-authorized", action="store_true")
    parser.add_argument(
        "--reasoning-task-count",
        type=int,
        default=None,
        help=(
            "Reasoning calls already consumed while producing the certified "
            "Plan; the execution controller continues from this count."
        ),
    )
    args = parser.parse_args()

    try:
        result = run_managed_work(
            args.certified_plan,
            job_ref=args.job_ref,
            resolved_inputs=load_resolved_inputs(args.inputs),
            available_resources=load_available_resources(args.resources),
            artifact_root=args.artifact_root,
            guidance_policy=args.guidance_policy,
            frontier_authorized=args.frontier_authorized,
            reasoning_task_count=args.reasoning_task_count,
        )
    except Exception as error:
        print(f"Managed work: FAIL: {error}", file=sys.stderr)
        return 1

    print(json.dumps(_proof_projection(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
