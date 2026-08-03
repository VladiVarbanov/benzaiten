"""Narrow deterministic orchestration for Benzaiten runtime stages."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from config import (
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
    WORKSPACE_DIR, SRC_DIR, PROMPTS_DIR, TEMPLATES_DIR, OKF_DRAFT_PROTOCOL_PATH, OKF_TEMPLATE_PATH,
    OKF_DRAFT_PROTOCOL_VOCABULARY_PATH, OKF_VOCABULARY_PATH, ORCHESTRATOR_COMMUNICATION_PROTOCOL_PATH,
    ORCHESTRATOR_COMMUNICATION_PROTOCOL_VOCABULARY_PATH, PLAN_PROTOCOL_PATH, PLAN_PROTOCOL_VOCABULARY_PATH,
    PLAN_PROTOCOL_NOTES_PATH,
)

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


REQUIRED_RESOURCE_DIRECTORIES = (
    SRC_DIR,
    PROMPTS_DIR,
    TEMPLATES_DIR,
)


REQUIRED_TEMPLATE_FILES = (
    OKF_DRAFT_PROTOCOL_PATH,
    OKF_DRAFT_PROTOCOL_VOCABULARY_PATH,
    OKF_TEMPLATE_PATH,
    OKF_VOCABULARY_PATH,

    ORCHESTRATOR_COMMUNICATION_PROTOCOL_PATH,
    ORCHESTRATOR_COMMUNICATION_PROTOCOL_VOCABULARY_PATH,

    PLAN_PROTOCOL_PATH,
    PLAN_PROTOCOL_VOCABULARY_PATH,
    PLAN_PROTOCOL_NOTES_PATH,
)


ACTIONS = {
    "ingest_file": {
        "enabled": True,
        "input_kinds": ["source_file"],
        "output_kind": "ingested_file",
    },
    "convert_to_md": {
        "enabled": True,
        "input_kinds": ["ingested_file"],
        "output_kind": "markdown",
    },
    "summarize": {
        "enabled": True,
        "model": "qwen",
        "prompt": "summarize.md",
        "input_kinds": ["markdown"],
        "output_kind": "summary",
    },
    "extract_okf": {
        "enabled": True,
        "model": "qwen",
        "prompt": "extract_okf.md",
        "input_kinds": ["summary"],
        "output_kind": "okf_draft",
    },
    "verify_okf": {
        "enabled": True,
        "model": "qwen",
        "prompt": "verify_okf.md",
        "input_kinds": ["okf_draft"],
        "output_kind": "verified_okf",
    },
    "write_okf": {
        "enabled": True,
        "input_kinds": ["verified_okf"],
        "output_kind": "written_okf",
    },
}


STATE_MACHINE = {
    "start_kind": "source_file",
    "done_kind": "written_okf",
    "transitions": {
        "source_file": "ingest_file",
        "ingested_file": "convert_to_md",
        "markdown": "summarize",
        "summary": "extract_okf",
        "okf_draft": "verify_okf",
        "verified_okf": "write_okf",
        "written_okf": "done",
    },
}


def ensure_runtime_directories() -> tuple[Path, ...]:
    """Create the configured runtime directory tree without clearing it."""

    for directory in RUNTIME_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)

    return RUNTIME_DIRECTORIES


def get_next_action(current_kind: str) -> str:
    """Return the configured deterministic transition for an artifact kind."""

    transitions = STATE_MACHINE["transitions"]

    if not isinstance(transitions, dict):
        raise RuntimeError("STATE_MACHINE transitions are invalid.")

    next_action = transitions.get(current_kind)

    if not isinstance(next_action, str):
        raise ValueError(f"No transition exists for kind: {current_kind}")

    if next_action != "done" and next_action not in ACTIONS:
        raise RuntimeError(
            f"Transition for {current_kind} references unknown action: "
            f"{next_action}"
        )

    return next_action


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
