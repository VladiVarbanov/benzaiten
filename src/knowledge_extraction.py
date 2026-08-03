from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from config import (
    KNOWLEDGE_EXTRACTION_ARTIFACTS_DIR,
    KNOWLEDGE_EXTRACTION_TMP_DIR,
    OKF_DIR,
)


@dataclass(frozen=True)
class ExtractionContext:
    source_ref: str
    source_kind: str
    prepared_markdown_path: Path

    target_okf_ref: str
    target_okf_id: str

    work_ref: str
    work_id: str

    temporary_dir: Path
    artifacts_dir: Path
    target_okf_path: Path


def create_extraction_context(
    *,
    source_ref: str,
    source_kind: str,
    prepared_markdown_path: Path,
    target_okf_ref: str,
    target_okf_id: str,
    work_ref: str,
    work_id: str,
) -> ExtractionContext:
    """Create the immutable runtime context for one extraction workflow."""

    string_values = {
        "source_ref": source_ref,
        "source_kind": source_kind,
        "target_okf_ref": target_okf_ref,
        "target_okf_id": target_okf_id,
        "work_ref": work_ref,
        "work_id": work_id,
    }

    for field_name, value in string_values.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} cannot be empty.")

    safe_id_pattern = r"[A-Za-z0-9][A-Za-z0-9._-]*"

    for field_name, value in {
        "target_okf_id": target_okf_id,
        "work_id": work_id,
    }.items():
        if re.fullmatch(safe_id_pattern, value) is None:
            raise ValueError(
                f"{field_name} contains characters that are unsafe "
                f"for filesystem paths: {value!r}"
            )

    prepared_markdown_path = prepared_markdown_path.resolve()

    if not prepared_markdown_path.exists():
        raise FileNotFoundError(
            f"Prepared Markdown does not exist: "
            f"{prepared_markdown_path}"
        )

    if not prepared_markdown_path.is_file():
        raise ValueError(
            f"Prepared Markdown path is not a file: "
            f"{prepared_markdown_path}"
        )

    if prepared_markdown_path.suffix.lower() != ".md":
        raise ValueError(
            f"Prepared source must be a Markdown file: "
            f"{prepared_markdown_path}"
        )

    if prepared_markdown_path.stat().st_size == 0:
        raise ValueError(
            f"Prepared Markdown is empty: "
            f"{prepared_markdown_path}"
        )

    temporary_dir = (
        KNOWLEDGE_EXTRACTION_TMP_DIR
        / target_okf_id
        / work_id
    )

    artifacts_dir = (
        KNOWLEDGE_EXTRACTION_ARTIFACTS_DIR
        / target_okf_id
        / work_id
    )

    target_okf_path = OKF_DIR / f"{target_okf_id}.md"

    return ExtractionContext(
        source_ref=source_ref,
        source_kind=source_kind,
        prepared_markdown_path=prepared_markdown_path,
        target_okf_ref=target_okf_ref,
        target_okf_id=target_okf_id,
        work_ref=work_ref,
        work_id=work_id,
        temporary_dir=temporary_dir,
        artifacts_dir=artifacts_dir,
        target_okf_path=target_okf_path,
    )

def prepare_extraction_workspace(
    context: ExtractionContext,
) -> None:
    """Create an empty workspace for one extraction workflow."""

    created_paths: list[Path] = []

    try:
        context.temporary_dir.mkdir(
            parents=True,
            exist_ok=False,
        )
        created_paths.append(context.temporary_dir)

        context.artifacts_dir.mkdir(
            parents=True,
            exist_ok=False,
        )
        created_paths.append(context.artifacts_dir)

        for directory_name in (
            "drafts",
            "responses",
            "synthesis",
        ):
            directory = context.artifacts_dir / directory_name
            directory.mkdir()
            created_paths.append(directory)

    except Exception:
        for path in reversed(created_paths):
            try:
                path.rmdir()
            except OSError:
                pass

        raise