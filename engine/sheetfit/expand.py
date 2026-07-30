"""High-level expand pipeline: extract → structure → search typography → render."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import fitz

from . import DEFAULT_TARGET_PAGES, DEFAULT_THRESHOLD
from .extract import extract_book, page_count
from .render import pdf_page_count_from_bytes, render_pdf_bytes
from .structure import structure_book
from .typography import estimate_pages, params_from_generosity

ProgressCb = Callable[[str, dict[str, Any]], None]


@dataclass
class ExpandReport:
    input_path: str
    output_path: str
    source_pages: int
    output_pages: int
    target_pages: int
    threshold: int
    action: str
    word_count: int
    image_count: int
    title: str
    author: str
    params: dict[str, Any]
    blank_pages_added: int
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pad_pdf_to_pages(src: Path, dest: Path, target: int) -> int:
    """Copy PDF and append blank pages until page count == target."""
    doc = fitz.open(src)
    try:
        current = doc.page_count
        if current >= target:
            if src.resolve() != dest.resolve():
                shutil.copyfile(src, dest)
            return 0
        w, h = doc[0].rect.width, doc[0].rect.height
        added = 0
        while doc.page_count < target:
            doc.new_page(width=w, height=h)
            added += 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        doc.save(dest)
        return added
    finally:
        doc.close()


def _seed_generosity(word_count: int, image_count: int, target: int) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(20):
        mid = (lo + hi) / 2
        est = estimate_pages(word_count, image_count, params_from_generosity(mid))
        if est < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def expand_pdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    target_pages: int = DEFAULT_TARGET_PAGES,
    threshold: int = DEFAULT_THRESHOLD,
    report_path: str | Path | None = None,
    progress: ProgressCb | None = None,
    max_render_iters: int = 5,
) -> ExpandReport:
    input_path = Path(input_path)
    output_path = Path(output_path)
    notes: list[str] = []

    def emit(stage: str, **kwargs: Any) -> None:
        if progress:
            progress(stage, kwargs)

    src_pages = page_count(input_path)
    emit("counted", source_pages=src_pages)

    if src_pages >= threshold:
        if src_pages < target_pages:
            emit("padding", reason="between_threshold_and_target")
            added = _pad_pdf_to_pages(input_path, output_path, target_pages)
            report = ExpandReport(
                input_path=str(input_path),
                output_path=str(output_path),
                source_pages=src_pages,
                output_pages=target_pages,
                target_pages=target_pages,
                threshold=threshold,
                action="pad_only",
                word_count=0,
                image_count=0,
                title=input_path.stem,
                author="",
                params={},
                blank_pages_added=added,
                notes=["Source pages >= threshold; padded with blank pages only."],
            )
        else:
            emit("passthrough", reason="already_long_enough")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if input_path.resolve() != output_path.resolve():
                shutil.copyfile(input_path, output_path)
            report = ExpandReport(
                input_path=str(input_path),
                output_path=str(output_path),
                source_pages=src_pages,
                output_pages=src_pages,
                target_pages=target_pages,
                threshold=threshold,
                action="passthrough",
                word_count=0,
                image_count=0,
                title=input_path.stem,
                author="",
                params={},
                blank_pages_added=0,
                notes=["Source pages >= target; no expansion applied."],
            )
        if report_path:
            Path(report_path).write_text(
                json.dumps(report.to_dict(), indent=2), encoding="utf-8"
            )
        return report

    emit("extracting")
    extracted = extract_book(input_path)
    emit(
        "extracted",
        word_count=extracted.word_count,
        image_count=extracted.image_count,
        blocks=len(extracted.blocks),
    )
    structured = structure_book(extracted)
    img_total = structured.image_count + len(structured.front_images)
    emit("structured", sections=len(structured.sections))

    seed = _seed_generosity(structured.word_count, img_total, target_pages)
    emit("seed_generosity", generosity=round(seed, 3))

    lo, hi = 0.0, 1.0
    best_g = seed
    best_pages = 0
    best_params = params_from_generosity(seed)
    best_bytes: bytes | None = None
    g = seed

    for i in range(max_render_iters):
        params = params_from_generosity(g)
        emit(
            "rendering",
            iteration=i + 1,
            generosity=round(g, 3),
            font_size_pt=params.font_size_pt,
        )
        pdf_bytes = render_pdf_bytes(structured, params, blank_pages=0)
        pages = pdf_page_count_from_bytes(pdf_bytes)
        emit("rendered", iteration=i + 1, pages=pages)

        score = abs(pages - target_pages)
        best_score = abs(best_pages - target_pages) if best_bytes else 10**9
        prefer = score < best_score or (
            score == best_score and pages <= target_pages and best_pages > target_pages
        )
        if prefer or best_bytes is None:
            best_bytes = pdf_bytes
            best_pages = pages
            best_g = g
            best_params = params

        if target_pages <= pages <= target_pages + 4:
            notes.append(f"Hit target band on iteration {i + 1}.")
            break

        # Close enough under target — pad blanks instead of more search iters
        if target_pages - 20 <= pages < target_pages:
            notes.append(
                f"Within pad range on iteration {i + 1} ({pages} pages)."
            )
            break

        # Narrow bracket using measured pages
        if pages < target_pages:
            lo = g
        else:
            hi = g

        # Ratio-guided jump for faster convergence on first steps
        if i == 0 and pages > 0:
            ratio = target_pages / pages
            g = max(0.0, min(1.0, g * (ratio ** 0.85)))
            g = max(lo, min(hi, g)) if hi > lo else g
            # After first measured jump, reset bracket around new guess
            lo = max(0.0, g - 0.2)
            hi = min(1.0, g + 0.2)
        else:
            g = (lo + hi) / 2

        if hi - lo < 0.025:
            notes.append("Generosity search converged.")
            break

    assert best_bytes is not None

    blank_added = 0
    final_pages = best_pages

    if best_pages < target_pages:
        deficit = target_pages - best_pages
        # If already close, pad blanks — never jump to max-generosity overshoot.
        # Only try max generosity when still far under the target.
        if deficit > 40 and best_g < 0.98:
            params = params_from_generosity(1.0, force_openers=True)
            emit("rendering_max", font_size_pt=params.font_size_pt)
            candidate = render_pdf_bytes(structured, params, blank_pages=0)
            cand_pages = pdf_page_count_from_bytes(candidate)
            # Accept max only if it lands closer without huge overshoot
            if cand_pages <= target_pages + 4 and abs(cand_pages - target_pages) < deficit:
                best_bytes = candidate
                best_pages = cand_pages
                best_params = params
                best_g = 1.0
                notes.append("Applied max-generosity render with chapter openers.")
            else:
                notes.append(
                    f"Skipped max-generosity ({cand_pages} pages); "
                    f"keeping {best_pages}-page layout and padding."
                )

        if best_pages < target_pages:
            blank_added = target_pages - best_pages
            best_bytes = render_pdf_bytes(
                structured, best_params, blank_pages=blank_added
            )
            final_pages = pdf_page_count_from_bytes(best_bytes)
            notes.append(
                f"Added {blank_added} blank page(s) to reach {target_pages} pages."
            )
        else:
            final_pages = best_pages
            notes.append(
                f"Closest layout is {best_pages} pages (target {target_pages})."
            )
    elif best_pages > target_pages + 4:
        notes.append(
            f"Closest layout is {best_pages} pages (target {target_pages}). "
            "Keeping closest render without blank padding."
        )
        final_pages = best_pages
    else:
        final_pages = best_pages

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(best_bytes)
    emit("written", output_path=str(output_path), pages=final_pages)

    report = ExpandReport(
        input_path=str(input_path),
        output_path=str(output_path),
        source_pages=src_pages,
        output_pages=final_pages,
        target_pages=target_pages,
        threshold=threshold,
        action="retypeset",
        word_count=structured.word_count,
        image_count=img_total,
        title=structured.title,
        author=structured.author,
        params=best_params.to_dict(),
        blank_pages_added=blank_added,
        notes=notes,
    )
    if report_path:
        Path(report_path).write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
    return report
