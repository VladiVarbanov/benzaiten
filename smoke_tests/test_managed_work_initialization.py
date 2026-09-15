from __future__ import annotations

from config import PLANNING_POLICY_PATH
from initialization import (
    REQUIRED_CONTRACT_FILES,
    load_runtime_layout,
    resolve_layout_path,
)


def test_active_planning_policy_is_required_without_obsolete_layout() -> None:
    assert PLANNING_POLICY_PATH in REQUIRED_CONTRACT_FILES
    stable = load_runtime_layout()["stable_directories"]
    assert "planning_protocols_old" not in stable
    assert all(path != "protocols/planning/old" for path in stable.values())


def test_managed_work_artifact_and_resume_paths_are_declared() -> None:
    layout = load_runtime_layout()

    assert layout["stable_directories"]["managed_work_artifacts"] == (
        "workspace/artifacts/managed_work"
    )
    assert resolve_layout_path(
        "managed_work_plan",
        job_ref="job-001",
        revision_file="rev-0001",
    ).as_posix().endswith(
        "workspace/artifacts/managed_work/job-001/plans/rev-0001.json"
    )
    assert resolve_layout_path(
        "managed_work_resume", job_ref="job-001",
    ).as_posix().endswith(
        "workspace/artifacts/managed_work/job-001/resume.json"
    )
