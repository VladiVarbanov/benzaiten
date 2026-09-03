"""Runtime representation of semantic tasks selected by the Director.

The JSON/YAML Director-task protocol is authoritative. These immutable
structures carry that contract in Python and contain no execution mechanics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


def _validate_optional_string(name: str, value: Optional[str]) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be None or a non-empty string.")


def _validate_string_tuple(name: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or not value.strip()
        for value in values
    ):
        raise ValueError(f"{name} must contain non-empty strings.")


@dataclass(frozen=True)
class TaskFocus:
    """Optional semantic focus for one Director-selected task."""

    questions: tuple[str, ...] = ()
    angles: tuple[str, ...] = ()
    granularity: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_string_tuple("questions", self.questions)
        _validate_string_tuple("angles", self.angles)
        _validate_optional_string("granularity", self.granularity)


@dataclass(frozen=True)
class DirectorTask:
    """Minimal semantic request passed from Director to Task Executive."""

    task_id: str
    job_ref: str
    capability: str
    participant_role: str
    objective: str
    input_refs: tuple[str, ...] = ()
    instruction: Optional[str] = None
    focus: Optional[TaskFocus] = None
    requirements: tuple[str, ...] = ()
    acceptance: Optional[str] = None
    output_contract_ref: Optional[str] = None
    external_authority_ref: Optional[str] = None

    def __post_init__(self) -> None:
        required = {
            "task_id": self.task_id,
            "job_ref": self.job_ref,
            "capability": self.capability,
            "participant_role": self.participant_role,
            "objective": self.objective,
        }
        for name, value in required.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")

        _validate_string_tuple("input_refs", self.input_refs)
        _validate_string_tuple("requirements", self.requirements)
        for name in (
            "instruction",
            "acceptance",
            "output_contract_ref",
            "external_authority_ref",
        ):
            _validate_optional_string(name, getattr(self, name))

    def semantic_payload(self) -> Mapping[str, object]:
        """Return semantic data only, omitting unused optional concepts."""

        payload: dict[str, object] = {
            "task_id": self.task_id,
            "job_ref": self.job_ref,
            "capability": self.capability,
            "participant_role": self.participant_role,
            "objective": self.objective,
            "input_refs": list(self.input_refs),
        }
        optional = {
            "instruction": self.instruction,
            "acceptance": self.acceptance,
            "output_contract_ref": self.output_contract_ref,
            "external_authority_ref": self.external_authority_ref,
        }
        payload.update({key: value for key, value in optional.items() if value})
        if self.requirements:
            payload["requirements"] = list(self.requirements)
        if self.focus is not None:
            focus: dict[str, object] = {}
            if self.focus.questions:
                focus["questions"] = list(self.focus.questions)
            if self.focus.angles:
                focus["angles"] = list(self.focus.angles)
            if self.focus.granularity:
                focus["granularity"] = self.focus.granularity
            if focus:
                payload["focus"] = focus
        return payload
