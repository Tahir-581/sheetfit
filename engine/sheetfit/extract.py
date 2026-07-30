"""Extract reading-order content blocks from a PDF."""

from __future__ import annotations

import base64
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import fitz

BlockKind = Literal["heading", "para", "image"]


@dataclass
class ContentBlock:
    kind: BlockKind
    text: str = ""
    image_b64: str | None = None
    image_ext: str = "png"
    width: float = 0.0
    height: float = 0.0
    page_index: int = 0


@dataclass
class ExtractedBook:
    title: str
    author: str
    source_pages: int
    blocks: list[ContentBlock] = field(default_factory=list)
    word_count: int = 0
    image_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "author": self.author,
            "source_pages": self.source_pages,
            "word_count": self.word_count,
            "image_count": self.image_count,
            "blocks": [asdict(b) for b in self.blocks],
        }


_HEADING_RE = re.compile(
    r"^(part\s+[ivxlcdm0-9]+|chapter\s+\d+|prologue|epilogue|foreword|afterword|"
    r"introduction|preface|acknowledgments?|contents|table of contents)$",
    re.I,
)


def page_count(path: str | Path) -> int:
    with fitz.open(path) as doc:
        return doc.page_count


def _is_heading(text: str, font_size: float, body_size: float) -> bool:
    t = text.strip()
    if not t:
        return False
    if len(t) > 120:
        return False
    if font_size >= body_size + 2.5:
        return True
    if _HEADING_RE.match(t):
        return True
    # Short all-caps lines often mark chapter titles in trade PDFs
    letters = [c for c in t if c.isalpha()]
    if 3 <= len(letters) <= 60 and letters and all(c.isupper() for c in letters):
        return True
    return False


def _dominant_body_size(doc: fitz.Document, sample_pages: int = 30) -> float:
    sizes: list[float] = []
    for i in range(min(sample_pages, doc.page_count)):
        page = doc[i]
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    s = float(span.get("size") or 0)
                    text = (span.get("text") or "").strip()
                    if s > 0 and len(text) > 20:
                        sizes.append(round(s, 1))
    if not sizes:
        return 12.0
    # Mode-ish: most common rounded size
    from collections import Counter

    return Counter(sizes).most_common(1)[0][0]


def _merge_lines(block: dict[str, Any]) -> str:
    parts: list[str] = []
    for line in block.get("lines", []):
        spans = line.get("spans", [])
        line_text = "".join(span.get("text") or "" for span in spans).strip()
        if line_text:
            parts.append(line_text)
    return " ".join(parts).strip()


def _max_span_size(block: dict[str, Any]) -> float:
    sizes = [
        float(span.get("size") or 0)
        for line in block.get("lines", [])
        for span in line.get("spans", [])
    ]
    return max(sizes) if sizes else 0.0


def _extract_image_bytes(doc: fitz.Document, xref: int) -> tuple[bytes, str] | None:
    try:
        info = doc.extract_image(xref)
    except Exception:  # noqa: BLE001
        return None
    data = info.get("image")
    if not data:
        return None
    ext = (info.get("ext") or "png").lower()
    if ext == "jpeg":
        ext = "jpg"
    return data, ext


def _pixmap_png(
    page: fitz.Page, rect: fitz.Rect, *, max_edge: float = 1200.0
) -> bytes:
    """Rasterize a region, downscaling very large plates for HTML embed size."""
    scale = min(1.5, max_edge / max(rect.width, rect.height, 1.0))
    scale = max(0.5, scale)
    pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(scale, scale), alpha=False)
    return pix.tobytes("png")


def extract_book(path: str | Path) -> ExtractedBook:
    path = Path(path)
    doc = fitz.open(path)
    try:
        meta = doc.metadata or {}
        title = (meta.get("title") or path.stem).strip() or path.stem
        author = (meta.get("author") or "").strip()
        body_size = _dominant_body_size(doc)

        blocks: list[ContentBlock] = []
        seen_image_xrefs: set[int] = set()

        for page_index in range(doc.page_count):
            page = doc[page_index]
            # Prefer structured text blocks in visual order
            text_dict = page.get_text("dict")
            page_blocks = sorted(
                text_dict.get("blocks", []),
                key=lambda b: (round(b.get("bbox", [0, 0, 0, 0])[1], 1), b.get("bbox", [0])[0]),
            )

            for block in page_blocks:
                if block.get("type") == 0:
                    text = _merge_lines(block)
                    if not text:
                        continue
                    # Skip page numbers / running headers that are tiny single tokens
                    if len(text) <= 4 and text.replace(" ", "").isdigit():
                        continue
                    size = _max_span_size(block)
                    kind: BlockKind = (
                        "heading" if _is_heading(text, size, body_size) else "para"
                    )
                    blocks.append(
                        ContentBlock(kind=kind, text=text, page_index=page_index)
                    )
                elif block.get("type") == 1:
                    # Image block via pixmap of the region (preserves crop)
                    bbox = block.get("bbox")
                    if not bbox:
                        continue
                    rect = fitz.Rect(bbox)
                    # Skip tiny ornaments / rules; keep real illustrations
                    if rect.width < 48 or rect.height < 48:
                        continue
                    if rect.width * rect.height < 80 * 80:
                        continue
                    png = _pixmap_png(page, rect)
                    if len(png) < 4_000:
                        continue
                    blocks.append(
                        ContentBlock(
                            kind="image",
                            image_b64=base64.b64encode(png).decode("ascii"),
                            image_ext="png",
                            width=rect.width,
                            height=rect.height,
                            page_index=page_index,
                        )
                    )
                    # Mark any xrefs on this page as handled to avoid duplicates
                    for img in page.get_images(full=True):
                        seen_image_xrefs.add(int(img[0]))

            # Cover / plate pages with almost no text: pull large embedded images
            page_text = page.get_text().strip()
            if len(page_text) <= 80:
                for img in page.get_images(full=True):
                    xref = int(img[0])
                    if xref in seen_image_xrefs:
                        continue
                    seen_image_xrefs.add(xref)
                    extracted = _extract_image_bytes(doc, xref)
                    if not extracted:
                        continue
                    data, ext = extracted
                    if len(data) < 20_000:
                        continue
                    blocks.append(
                        ContentBlock(
                            kind="image",
                            image_b64=base64.b64encode(data).decode("ascii"),
                            image_ext=ext,
                            page_index=page_index,
                        )
                    )

        # Deduplicate consecutive identical paras (running headers sometimes slip through)
        cleaned: list[ContentBlock] = []
        for b in blocks:
            if (
                cleaned
                and b.kind == cleaned[-1].kind
                and b.kind != "image"
                and b.text == cleaned[-1].text
            ):
                continue
            cleaned.append(b)

        words = sum(len(b.text.split()) for b in cleaned if b.kind != "image")
        images = sum(1 for b in cleaned if b.kind == "image")
        return ExtractedBook(
            title=title,
            author=author,
            source_pages=doc.page_count,
            blocks=cleaned,
            word_count=words,
            image_count=images,
        )
    finally:
        doc.close()
