from __future__ import annotations

import json

import yaml

from config import PLAN_PROTOCOL_PATH, PLAN_PROTOCOL_VOCABULARY_PATH


def _placeholder_values(value: str) -> set[str]:
    return {item.strip() for item in value.strip("<> ").split("|")}


def test_plan_template_uses_authoritative_vocabularies() -> None:
    plan = json.loads(PLAN_PROTOCOL_PATH.read_text(encoding="utf-8"))
    vocabulary = yaml.safe_load(
        PLAN_PROTOCOL_VOCABULARY_PATH.read_text(encoding="utf-8")
    )
    deliberation = plan["planning_cycle"]

    assert _placeholder_values(deliberation["critiques"][0]["severity"]) == set(
        vocabulary["severity"]
    )
    assert plan["integrity"]["validation"]["status"] in vocabulary[
        "validation_status"
    ]
    expected_target_kinds = set(vocabulary["reference_target_kind"])
    assert _placeholder_values(
        deliberation["critiques"][0]["target_kind"]
    ) == expected_target_kinds
    assert _placeholder_values(
        deliberation["suggested_changes"][0]["target_kind"]
    ) == expected_target_kinds
