"""CLI entry point: sheetfit expand ..."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import DEFAULT_TARGET_PAGES, DEFAULT_THRESHOLD, __version__
from .expand import expand_pdf
from .extract import page_count


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sheetfit",
        description="Expand short book PDFs to ~400 pages for 100-sheet print.",
    )
    p.add_argument("--version", action="version", version=f"sheetfit {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    info = sub.add_parser("info", help="Show page count for a PDF")
    info.add_argument("input", type=Path)

    exp = sub.add_parser("expand", help="Retypeset / pad a PDF toward target pages")
    exp.add_argument("input", type=Path)
    exp.add_argument("-o", "--output", type=Path, required=True)
    exp.add_argument("--target", type=int, default=DEFAULT_TARGET_PAGES)
    exp.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    exp.add_argument("--report", type=Path, default=None)
    exp.add_argument("-q", "--quiet", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "info":
        pages = page_count(args.input)
        print(json.dumps({"path": str(args.input), "pages": pages}, indent=2))
        return 0

    if args.command == "expand":
        def progress(stage: str, data: dict) -> None:
            if args.quiet:
                return
            extra = " ".join(f"{k}={v}" for k, v in data.items() if k != "params")
            print(f"[{stage}] {extra}", file=sys.stderr)

        report = expand_pdf(
            args.input,
            args.output,
            target_pages=args.target,
            threshold=args.threshold,
            report_path=args.report,
            progress=None if args.quiet else progress,
        )
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
