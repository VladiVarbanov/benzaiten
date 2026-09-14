from __future__ import annotations

from config import PLANNING_POLICY_PATH
from initialization import REQUIRED_CONTRACT_FILES, load_runtime_layout


def test_active_planning_policy_is_required_without_obsolete_layout() -> None:
    assert PLANNING_POLICY_PATH in REQUIRED_CONTRACT_FILES
    stable = load_runtime_layout()["stable_directories"]
    assert "planning_protocols_old" not in stable
    assert all(path != "protocols/planning/old" for path in stable.values())
