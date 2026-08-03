from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import Any

from config import (
    OKF_DRAFT_PROTOCOL_PATH,
    OKF_DRAFT_PROTOCOL_VOCABULARY_PATH,
    OKF_TEMPLATE_PATH,
    OKF_VOCABULARY_PATH,
    ORCHESTRATOR_COMMUNICATION_PROTOCOL_PATH,
    ORCHESTRATOR_COMMUNICATION_PROTOCOL_VOCABULARY_PATH,
    ORCHESTRATOR_ROOT,
    PLAN_PROTOCOL_PATH,
    PLAN_PROTOCOL_VOCABULARY_PATH,
    PROMPTS_DIR,
    RUNTIME_LAYOUT_MARKER_PATH,
    SRC_DIR,
    TEMPLATES_DIR,
)


# =====================================================================
# 1. LAYOUT CONTRACT
# =====================================================================

SUPPORTED_LAYOUT_VERSION = 1

FILESYSTEM_SAFE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
)


class LayoutContractError(ValueError):
    """Raised when the runtime layout contract is invalid."""


# =====================================================================
# 2. REQUIRED REPOSITORY RESOURCES
# =====================================================================

# These directories belong to the repository and must already exist.
# Initialization validates them but does not create them.
REQUIRED_RESOURCE_DIRECTORIES = (
    SRC_DIR,
    PROMPTS_DIR,
    TEMPLATES_DIR,
)


# These machine-consumed contracts must already exist.
REQUIRED_CONTRACT_FILES = (
    RUNTIME_LAYOUT_MARKER_PATH,

    OKF_DRAFT_PROTOCOL_PATH,
    OKF_DRAFT_PROTOCOL_VOCABULARY_PATH,
    OKF_TEMPLATE_PATH,
    OKF_VOCABULARY_PATH,

    ORCHESTRATOR_COMMUNICATION_PROTOCOL_PATH,
    ORCHESTRATOR_COMMUNICATION_PROTOCOL_VOCABULARY_PATH,

    PLAN_PROTOCOL_PATH,
    PLAN_PROTOCOL_VOCABULARY_PATH,
)


# =====================================================================
# 3. LAYOUT LOADING
# =====================================================================

@lru_cache(maxsize=1)
def load_runtime_layout() -> dict[str, Any]:
    """
    Load and validate the machine-readable Benzaiten layout contract.

    The contract is stored at:

        workspace/.benzaiten_layout.json

    The human-readable architectural source remains benzaiten_layout.md.
    This function does not parse or modify the Markdown document.
    """

    _validate_existing_file(
        RUNTIME_LAYOUT_MARKER_PATH,
        resource_name="Runtime layout contract",
    )

    try:
        raw_content = RUNTIME_LAYOUT_MARKER_PATH.read_text(
            encoding="utf-8"
        )
    except UnicodeDecodeError as exc:
        raise LayoutContractError(
            "Runtime layout contract is not valid UTF-8: "
            f"{RUNTIME_LAYOUT_MARKER_PATH}"
        ) from exc

    if not raw_content.strip():
        raise LayoutContractError(
            "Runtime layout contract is empty: "
            f"{RUNTIME_LAYOUT_MARKER_PATH}"
        )

    try:
        layout = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LayoutContractError(
            "Runtime layout contract contains invalid JSON: "
            f"{RUNTIME_LAYOUT_MARKER_PATH}; "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    validate_runtime_layout_contract(layout)

    return layout


# =====================================================================
# 4. LAYOUT CONTRACT VALIDATION
# =====================================================================

def validate_runtime_layout_contract(
    layout: dict[str, Any],
) -> None:
    """Validate the structure and path safety of the layout contract."""

    if not isinstance(layout, dict):
        raise LayoutContractError(
            "Runtime layout contract must contain a JSON object."
        )

    layout_version = layout.get("layout_version")

    if not isinstance(layout_version, int):
        raise LayoutContractError(
            "Runtime layout contract must contain an integer "
            "'layout_version'."
        )

    if layout_version != SUPPORTED_LAYOUT_VERSION:
        raise LayoutContractError(
            "Unsupported Benzaiten runtime layout version. "
            f"Expected {SUPPORTED_LAYOUT_VERSION}, "
            f"found {layout_version}."
        )

    stable_directories = layout.get("stable_directories")
    dynamic_directories = layout.get("dynamic_directories")
    file_patterns = layout.get("file_patterns")
    placeholders = layout.get("placeholders")

    if not isinstance(stable_directories, dict):
        raise LayoutContractError(
            "'stable_directories' must be a JSON object."
        )

    if not isinstance(dynamic_directories, dict):
        raise LayoutContractError(
            "'dynamic_directories' must be a JSON object."
        )

    if not isinstance(file_patterns, dict):
        raise LayoutContractError(
            "'file_patterns' must be a JSON object."
        )

    if not isinstance(placeholders, dict):
        raise LayoutContractError(
            "'placeholders' must be a JSON object."
        )

    if not stable_directories:
        raise LayoutContractError(
            "'stable_directories' cannot be empty."
        )

    _validate_stable_directory_entries(stable_directories)

    _validate_pattern_entries(
        entries=dynamic_directories,
        section_name="dynamic_directories",
        placeholders=placeholders,
    )

    _validate_pattern_entries(
        entries=file_patterns,
        section_name="file_patterns",
        placeholders=placeholders,
    )

    _validate_placeholder_definitions(placeholders)


def _validate_stable_directory_entries(
    stable_directories: dict[str, Any],
) -> None:
    for key, relative_path in stable_directories.items():
        if not isinstance(key, str) or not key.strip():
            raise LayoutContractError(
                "Stable directory keys must be non-empty strings."
            )

        if not isinstance(relative_path, str) or not relative_path.strip():
            raise LayoutContractError(
                f"Stable directory '{key}' must contain a "
                "non-empty relative path."
            )

        _resolve_safe_relative_path(
            relative_path,
            resource_name=f"Stable directory '{key}'",
        )

        placeholders = _extract_pattern_placeholders(relative_path)

        if placeholders:
            raise LayoutContractError(
                f"Stable directory '{key}' cannot contain placeholders: "
                f"{sorted(placeholders)}"
            )


def _validate_pattern_entries(
    *,
    entries: dict[str, Any],
    section_name: str,
    placeholders: dict[str, Any],
) -> None:
    for key, entry in entries.items():
        if not isinstance(key, str) or not key.strip():
            raise LayoutContractError(
                f"Keys in '{section_name}' must be non-empty strings."
            )

        if not isinstance(entry, dict):
            raise LayoutContractError(
                f"'{section_name}.{key}' must be a JSON object."
            )

        pattern = entry.get("pattern")
        owner = entry.get("owner")

        if not isinstance(pattern, str) or not pattern.strip():
            raise LayoutContractError(
                f"'{section_name}.{key}.pattern' must be a "
                "non-empty string."
            )

        if not isinstance(owner, str) or not owner.strip():
            raise LayoutContractError(
                f"'{section_name}.{key}.owner' must be a "
                "non-empty string."
            )

        _validate_relative_pattern(
            pattern,
            resource_name=f"{section_name}.{key}",
        )

        pattern_placeholders = _extract_pattern_placeholders(pattern)

        for placeholder_name in pattern_placeholders:
            if placeholder_name not in placeholders:
                raise LayoutContractError(
                    f"Pattern '{section_name}.{key}' uses undefined "
                    f"placeholder '{placeholder_name}'."
                )


def _validate_placeholder_definitions(
    placeholders: dict[str, Any],
) -> None:
    for placeholder_name, definition in placeholders.items():
        if (
            not isinstance(placeholder_name, str)
            or not placeholder_name.strip()
        ):
            raise LayoutContractError(
                "Placeholder names must be non-empty strings."
            )

        if not isinstance(definition, dict):
            raise LayoutContractError(
                f"Placeholder '{placeholder_name}' must contain "
                "a JSON object."
            )

        placeholder_type = definition.get("type")

        if placeholder_type != "filesystem_safe_id":
            raise LayoutContractError(
                f"Placeholder '{placeholder_name}' uses unsupported "
                f"type: {placeholder_type!r}"
            )


# =====================================================================
# 5. REPOSITORY RESOURCE VALIDATION
# =====================================================================

def validate_repository_resources() -> None:
    """
    Validate static repository directories and contract files.

    This function performs no filesystem creation.
    """

    for directory in REQUIRED_RESOURCE_DIRECTORIES:
        _validate_existing_directory(
            directory,
            resource_name="Required repository directory",
        )

    for path in REQUIRED_CONTRACT_FILES:
        _validate_existing_file(
            path,
            resource_name="Required contract file",
        )


# =====================================================================
# 6. STABLE RUNTIME DIRECTORIES
# =====================================================================

def get_stable_runtime_directories() -> tuple[Path, ...]:
    """
    Resolve stable runtime directories from the layout contract.

    Only paths from the 'stable_directories' section are returned.
    Dynamic source and work directories are not created here.
    """

    layout = load_runtime_layout()
    stable_directories = layout["stable_directories"]

    resolved_directories: list[Path] = []

    for relative_path in stable_directories.values():
        resolved_path = _resolve_safe_relative_path(
            relative_path,
            resource_name="Stable runtime directory",
        )

        if resolved_path not in resolved_directories:
            resolved_directories.append(resolved_path)

    resolved_directories.sort(
        key=lambda path: (
            len(path.relative_to(ORCHESTRATOR_ROOT).parts),
            str(path),
        )
    )

    return tuple(resolved_directories)


def create_stable_runtime_directories() -> None:
    """
    Create the stable directory structure declared by the layout contract.

    This operation is idempotent. It does not create directories containing
    source IDs, target OKF IDs, or work IDs.
    """

    for directory in get_stable_runtime_directories():
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def validate_stable_runtime_directories() -> None:
    """
    Verify that every stable directory declared by the contract exists.

    This function performs no repair.
    """

    for directory in get_stable_runtime_directories():
        _validate_existing_directory(
            directory,
            resource_name="Required runtime directory",
        )


# =====================================================================
# 7. DYNAMIC PATH RESOLUTION
# =====================================================================

def resolve_layout_path(
    layout_key: str,
    **identifiers: str,
) -> Path:
    """
    Resolve a stable directory, dynamic directory, or file-pattern path.

    Examples:

        resolve_layout_path(
            "document_preparation_tmp_work",
            source_id="source-001",
            preparation_work_id="prepare-001",
        )

        resolve_layout_path(
            "knowledge_extraction_drafts",
            target_okf_id="okf-001",
            extraction_work_id="extract-001",
        )

        resolve_layout_path(
            "authoritative_okf",
            target_okf_id="okf-001",
        )

    All identifiers are validated according to the placeholder definitions
    in the runtime layout contract.
    """

    if not isinstance(layout_key, str) or not layout_key.strip():
        raise ValueError("layout_key cannot be empty.")

    layout = load_runtime_layout()

    pattern = _find_layout_pattern(
        layout,
        layout_key=layout_key,
    )

    required_placeholders = _extract_pattern_placeholders(pattern)
    supplied_placeholders = set(identifiers)

    missing_placeholders = (
        required_placeholders - supplied_placeholders
    )

    unknown_placeholders = (
        supplied_placeholders - required_placeholders
    )

    if missing_placeholders:
        raise ValueError(
            f"Missing identifiers for layout key '{layout_key}': "
            f"{sorted(missing_placeholders)}"
        )

    if unknown_placeholders:
        raise ValueError(
            f"Unexpected identifiers for layout key '{layout_key}': "
            f"{sorted(unknown_placeholders)}"
        )

    for placeholder_name, value in identifiers.items():
        _validate_placeholder_value(
            layout=layout,
            placeholder_name=placeholder_name,
            value=value,
        )

    try:
        relative_path = pattern.format(**identifiers)
    except (KeyError, ValueError) as exc:
        raise LayoutContractError(
            f"Could not resolve layout pattern '{layout_key}'."
        ) from exc

    return _resolve_safe_relative_path(
        relative_path,
        resource_name=f"Resolved layout path '{layout_key}'",
    )


def create_dynamic_directory(
    layout_key: str,
    *,
    exist_ok: bool = False,
    **identifiers: str,
) -> Path:
    """
    Create one directory declared in 'dynamic_directories'.

    File-pattern keys and stable-directory keys are rejected.
    """

    layout = load_runtime_layout()
    dynamic_directories = layout["dynamic_directories"]

    if layout_key not in dynamic_directories:
        raise KeyError(
            f"Layout key is not a dynamic directory: {layout_key}"
        )

    path = resolve_layout_path(
        layout_key,
        **identifiers,
    )

    path.mkdir(
        parents=True,
        exist_ok=exist_ok,
    )

    return path


def resolve_file_pattern(
    layout_key: str,
    **identifiers: str,
) -> Path:
    """Resolve one path declared in the 'file_patterns' section."""

    layout = load_runtime_layout()
    file_patterns = layout["file_patterns"]

    if layout_key not in file_patterns:
        raise KeyError(
            f"Layout key is not a file pattern: {layout_key}"
        )

    return resolve_layout_path(
        layout_key,
        **identifiers,
    )


# =====================================================================
# 8. INITIALIZATION AND STARTUP VALIDATION
# =====================================================================

def initialize_benzaiten() -> None:
    """
    Initialize the Benzaiten filesystem environment.

    Initialization:

    1. validates repository resources
    2. validates the machine-readable layout contract
    3. creates stable runtime directories
    4. verifies the resulting runtime layout

    The operation is explicit and idempotent.
    """

    validate_repository_resources()
    load_runtime_layout()
    create_stable_runtime_directories()
    validate_stable_runtime_directories()


def validate_benzaiten_environment() -> None:
    """
    Validate an already initialized Benzaiten environment.

    Normal orchestrator startup should call this function. It performs
    no filesystem creation or automatic repair.
    """

    validate_repository_resources()
    load_runtime_layout()
    validate_stable_runtime_directories()


# =====================================================================
# 9. INTERNAL PATH HELPERS
# =====================================================================

def _find_layout_pattern(
    layout: dict[str, Any],
    *,
    layout_key: str,
) -> str:
    stable_directories = layout["stable_directories"]
    dynamic_directories = layout["dynamic_directories"]
    file_patterns = layout["file_patterns"]

    matching_sections = 0
    matched_pattern: str | None = None

    if layout_key in stable_directories:
        matching_sections += 1
        matched_pattern = stable_directories[layout_key]

    if layout_key in dynamic_directories:
        matching_sections += 1
        matched_pattern = dynamic_directories[layout_key]["pattern"]

    if layout_key in file_patterns:
        matching_sections += 1
        matched_pattern = file_patterns[layout_key]["pattern"]

    if matching_sections == 0:
        raise KeyError(
            f"Unknown runtime layout key: {layout_key}"
        )

    if matching_sections > 1:
        raise LayoutContractError(
            f"Runtime layout key is declared more than once: "
            f"{layout_key}"
        )

    if not isinstance(matched_pattern, str):
        raise LayoutContractError(
            f"Runtime layout key has no valid pattern: {layout_key}"
        )

    return matched_pattern


def _extract_pattern_placeholders(
    pattern: str,
) -> set[str]:
    placeholders: set[str] = set()

    try:
        parsed_fields = Formatter().parse(pattern)
    except ValueError as exc:
        raise LayoutContractError(
            f"Invalid path pattern: {pattern!r}"
        ) from exc

    for _, field_name, _, _ in parsed_fields:
        if field_name is None:
            continue

        if not field_name:
            raise LayoutContractError(
                f"Empty placeholder in path pattern: {pattern!r}"
            )

        if "." in field_name or "[" in field_name or "]" in field_name:
            raise LayoutContractError(
                "Complex placeholder expressions are not allowed in "
                f"path patterns: {field_name!r}"
            )

        placeholders.add(field_name)

    return placeholders


def _validate_relative_pattern(
    pattern: str,
    *,
    resource_name: str,
) -> None:
    placeholder_names = _extract_pattern_placeholders(pattern)

    temporary_values = {
        placeholder_name: "placeholder"
        for placeholder_name in placeholder_names
    }

    try:
        sample_path = pattern.format(**temporary_values)
    except (KeyError, ValueError) as exc:
        raise LayoutContractError(
            f"{resource_name} contains an invalid pattern: {pattern!r}"
        ) from exc

    _resolve_safe_relative_path(
        sample_path,
        resource_name=resource_name,
    )


def _validate_placeholder_value(
    *,
    layout: dict[str, Any],
    placeholder_name: str,
    value: str,
) -> None:
    placeholder_definitions = layout["placeholders"]

    if placeholder_name not in placeholder_definitions:
        raise LayoutContractError(
            f"Undefined layout placeholder: {placeholder_name}"
        )

    if not isinstance(value, str) or not value:
        raise ValueError(
            f"Identifier '{placeholder_name}' must be a "
            "non-empty string."
        )

    placeholder_type = placeholder_definitions[
        placeholder_name
    ].get("type")

    if placeholder_type != "filesystem_safe_id":
        raise LayoutContractError(
            f"Unsupported placeholder type for '{placeholder_name}': "
            f"{placeholder_type!r}"
        )

    if FILESYSTEM_SAFE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"Identifier '{placeholder_name}' contains unsafe "
            f"filesystem characters: {value!r}"
        )

    if value in {".", ".."}:
        raise ValueError(
            f"Identifier '{placeholder_name}' cannot be {value!r}."
        )


def _resolve_safe_relative_path(
    relative_path: str,
    *,
    resource_name: str,
) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise LayoutContractError(
            f"{resource_name} must contain a non-empty path."
        )

    candidate = Path(relative_path)

    if candidate.is_absolute():
        raise LayoutContractError(
            f"{resource_name} must use a relative path: "
            f"{relative_path!r}"
        )

    if any(part == ".." for part in candidate.parts):
        raise LayoutContractError(
            f"{resource_name} cannot contain parent traversal: "
            f"{relative_path!r}"
        )

    resolved_root = ORCHESTRATOR_ROOT.resolve()
    resolved_path = (
        resolved_root / candidate
    ).resolve()

    if not resolved_path.is_relative_to(resolved_root):
        raise LayoutContractError(
            f"{resource_name} resolves outside ORCHESTRATOR_ROOT: "
            f"{relative_path!r}"
        )

    return resolved_path


# =====================================================================
# 10. INTERNAL RESOURCE HELPERS
# =====================================================================

def _validate_existing_directory(
    path: Path,
    *,
    resource_name: str,
) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"{resource_name} does not exist: {path}"
        )

    if not path.is_dir():
        raise NotADirectoryError(
            f"{resource_name} is not a directory: {path}"
        )


def _validate_existing_file(
    path: Path,
    *,
    resource_name: str,
) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"{resource_name} does not exist: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"{resource_name} is not a file: {path}"
        )


# =====================================================================
# 11. COMMAND-LINE ENTRY POINT
# =====================================================================

def main() -> None:
    initialize_benzaiten()

    layout = load_runtime_layout()

    print(
        "Benzaiten filesystem initialized successfully "
        f"with layout version {layout['layout_version']}."
    )


if __name__ == "__main__":
    main()