"""Thin executable entry point for the Benzaiten PDF preparation stage.

Responsibility: parse arguments, call run_pdf_preparation_stage(), print the
result, and exit with an appropriate status code.

No preparation logic lives here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="run_orchestrator",
        description="Run the Benzaiten PDF preparation stage for one source PDF.",
    )
    parser.add_argument(
        "source_pdf",
        type=Path,
        help="Absolute or relative path to the source PDF file.",
    )
    parser.add_argument(
        "--log-console",
        action="store_true",
        default=False,
        help=(
            "Stream Marker stdout/stderr to the console while it runs "
            "(rather than returning output only after completion)."
        ),
    )
    args = parser.parse_args()

    from orchestrator import run_pdf_preparation_stage

    try:
        result = run_pdf_preparation_stage(
            args.source_pdf,
            log_console=args.log_console,
        )
    except Exception as error:
        print(f"PDF preparation: FAIL: {error}", file=sys.stderr)
        return 1

    print("PDF preparation: PASS")
    print(f"  source_pdf:      {result.source_pdf}")
    print(f"  extraction_dir:  {result.extraction_dir}")
    print(f"  markdown_path:   {result.markdown_path}")
    print(f"  generated_files: {len(result.generated_files)}")
    print(f"  image_files:     {len(result.image_files)}")
    print(f"  table_files:     {len(result.table_files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
