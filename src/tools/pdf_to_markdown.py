#!/usr/bin/env python3
"""Batch-convert PDFs to Markdown with Benzaiten's working Marker setup."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


DEFAULT_MARKER_EXECUTABLE = Path(
    "/home/vladi/local_ai/marker/.venv/bin/marker_single"
)
MARKER_ENV_DEFAULTS = {
    "VLLM_DOCKER_IMAGE": "vllm/vllm-openai:v0.22.1",
    "VLLM_GPU_MEMORY_UTILIZATION": "0.6",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert one PDF, or every PDF in a directory, with Marker."
    )
    parser.add_argument("input", type=Path, help="PDF file or directory of PDFs")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Output root (default: a sibling directory named <input>_md)",
    )
    parser.add_argument(
        "--marker-executable",
        type=Path,
        default=Path(
            os.environ.get(
                "BENZAITEN_MARKER_EXECUTABLE",
                DEFAULT_MARKER_EXECUTABLE,
            )
        ),
        help="Path to marker_single",
    )
    return parser.parse_args()


def discover_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"Input file is not a PDF: {input_path}")
        return [input_path]
    if input_path.is_dir():
        return sorted(
            path for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        )
    raise FileNotFoundError(f"Input does not exist: {input_path}")


def default_output_root(input_path: Path) -> Path:
    base = input_path if input_path.is_dir() else input_path.parent
    return base.with_name(f"{base.name}_md")


def marker_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name, value in MARKER_ENV_DEFAULTS.items():
        environment.setdefault(name, value)
    return environment


def convert_pdf(
    pdf: Path,
    output_root: Path,
    marker_executable: Path,
    environment: dict[str, str],
) -> Path:
    expected_dir = output_root / pdf.stem
    if expected_dir.exists() and any(expected_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {expected_dir}")

    command = [
        str(marker_executable),
        str(pdf),
        "--output_dir",
        str(output_root),
        "--output_format",
        "markdown",
        "--paginate_output",
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=environment,
    )

    if completed.returncode != 0:
        expected_dir.mkdir(parents=True, exist_ok=True)
        error_log = expected_dir / "marker_error.log"
        error_log.write_text(
            f"Command: {command!r}\n"
            f"Return code: {completed.returncode}\n\n"
            f"STDOUT:\n{completed.stdout}\n\n"
            f"STDERR:\n{completed.stderr}\n",
            encoding="utf-8",
        )
        raise RuntimeError(
            f"Marker exited with {completed.returncode}; log: {error_log}"
        )

    markdown_files = sorted(expected_dir.glob("*.md"))
    if not markdown_files:
        raise RuntimeError(f"Marker produced no Markdown in: {expected_dir}")
    return expected_dir


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    marker_executable = args.marker_executable.expanduser().resolve()

    try:
        pdfs = discover_pdfs(input_path)
        if not pdfs:
            raise ValueError(f"No PDF files found in: {input_path}")
        if not marker_executable.is_file():
            raise FileNotFoundError(
                f"Marker executable does not exist: {marker_executable}"
            )
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    output_root = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else default_output_root(input_path)
    )
    output_root.mkdir(parents=True, exist_ok=True)
    environment = marker_environment()
    successful = 0
    failed = 0

    for index, pdf in enumerate(pdfs, start=1):
        print(f"[{index}/{len(pdfs)}] Processing: {pdf}", flush=True)
        try:
            result_dir = convert_pdf(
                pdf,
                output_root,
                marker_executable,
                environment,
            )
        except Exception as error:
            failed += 1
            print(f"  FAILED: {error}", file=sys.stderr, flush=True)
        else:
            successful += 1
            print(f"  OK: {result_dir}", flush=True)

    print("\nSummary")
    print(f"  processed: {len(pdfs)}")
    print(f"  successful: {successful}")
    print(f"  failed: {failed}")
    print(f"  output: {output_root}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
