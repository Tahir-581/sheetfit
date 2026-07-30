"""Render a structured book to a half-Letter PDF via WeasyPrint."""

from __future__ import annotations

import html
import io
from pathlib import Path

from weasyprint import HTML

from . import PAGE_HEIGHT_PT, PAGE_WIDTH_PT
from .structure import StructuredBook
from .typography import TypographyParams

# Page size in inches for CSS @page
PAGE_W_IN = PAGE_WIDTH_PT / 72.0
PAGE_H_IN = PAGE_HEIGHT_PT / 72.0


def _css(params: TypographyParams) -> str:
    return f"""
@page {{
  size: {PAGE_W_IN:.4f}in {PAGE_H_IN:.4f}in;
  margin: {params.margin_y_in}in {params.margin_x_in}in;
  @bottom-center {{
    content: counter(page);
    font-family: "Libre Baskerville", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
    font-size: 9pt;
    color: #444;
  }}
}}
html, body {{
  margin: 0;
  padding: 0;
}}
body {{
  font-family: "Libre Baskerville", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  font-size: {params.font_size_pt}pt;
  line-height: {params.line_height};
  color: #1a1a1a;
  hyphens: auto;
  text-align: justify;
}}
h1.title {{
  font-size: {params.font_size_pt * 1.8:.2f}pt;
  line-height: 1.2;
  text-align: center;
  margin: 28% 0 0.6em;
  font-weight: 700;
  page-break-after: avoid;
}}
p.author {{
  text-align: center;
  font-size: {params.font_size_pt * 1.1:.2f}pt;
  font-style: italic;
  margin: 0 0 2em;
}}
.section-opener {{
  page-break-before: always;
  break-before: page;
  min-height: 70vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
}}
.section-opener h2 {{
  font-size: {params.font_size_pt * 1.45:.2f}pt;
  text-align: center;
  font-weight: 700;
  margin: 0;
  line-height: 1.25;
}}
.section-opener .ornament {{
  text-align: center;
  margin-top: 1.2em;
  letter-spacing: 0.35em;
  color: #666;
  font-size: {params.font_size_pt * 0.85:.2f}pt;
}}
h2.inline-heading {{
  font-size: {params.font_size_pt * 1.2:.2f}pt;
  margin: 1.4em 0 0.6em;
  page-break-after: avoid;
  text-align: left;
}}
p {{
  margin: 0 0 {params.paragraph_spacing_em}em;
  text-indent: 1.15em;
}}
p.no-indent {{
  text-indent: 0;
}}
figure {{
  margin: 1.2em 0;
  text-align: center;
  page-break-inside: avoid;
}}
figure.plate {{
  page-break-before: always;
  page-break-after: always;
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80vh;
}}
img {{
  max-width: 100%;
  height: auto;
}}
.blank-page {{
  page-break-before: always;
  break-before: page;
  height: 1px;
}}
"""


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def book_to_html(book: StructuredBook, params: TypographyParams, *, blank_pages: int = 0) -> str:
    parts: list[str] = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<style>{_css(params)}</style></head><body>",
    ]

    # Title page
    parts.append("<section class='section-opener'>")
    parts.append(f"<h1 class='title'>{_escape(book.title)}</h1>")
    if book.author:
        parts.append(f"<p class='author'>{_escape(book.author)}</p>")
    parts.append("<div class='ornament'>* * *</div>")
    parts.append("</section>")

    for img in book.front_images:
        if not img.image_b64:
            continue
        mime = "image/jpeg" if img.image_ext in ("jpg", "jpeg") else f"image/{img.image_ext}"
        parts.append("<figure class='plate'>")
        parts.append(
            f"<img src='data:{mime};base64,{img.image_b64}' alt='Front plate'/>"
        )
        parts.append("</figure>")

    first_body = True
    for section in book.sections:
        if params.chapter_opener_pages and section.opener and section.title:
            parts.append("<section class='section-opener'>")
            parts.append(f"<h2>{_escape(section.title)}</h2>")
            parts.append("<div class='ornament'>* * *</div>")
            parts.append("</section>")
        elif section.title:
            parts.append(f"<h2 class='inline-heading'>{_escape(section.title)}</h2>")

        para_index = 0
        for block in section.blocks:
            if block.kind == "image" and block.image_b64:
                mime = (
                    "image/jpeg"
                    if block.image_ext in ("jpg", "jpeg")
                    else f"image/{block.image_ext}"
                )
                # Large-ish images get their own breathing room
                cls = "plate" if (block.height and block.height > 280) else ""
                parts.append(f"<figure class='{cls}'>")
                parts.append(
                    f"<img src='data:{mime};base64,{block.image_b64}' alt=''/>"
                )
                parts.append("</figure>")
                para_index = 0
            elif block.kind == "heading":
                parts.append(
                    f"<h2 class='inline-heading'>{_escape(block.text)}</h2>"
                )
                para_index = 0
            else:
                cls = "no-indent" if para_index == 0 or first_body else ""
                parts.append(f"<p class='{cls}'>{_escape(block.text)}</p>")
                para_index += 1
                first_body = False

    for _ in range(max(0, blank_pages)):
        parts.append("<div class='blank-page'></div>")

    parts.append("</body></html>")
    return "\n".join(parts)


def render_pdf_bytes(
    book: StructuredBook,
    params: TypographyParams,
    *,
    blank_pages: int = 0,
) -> bytes:
    html_doc = book_to_html(book, params, blank_pages=blank_pages)
    pdf = HTML(string=html_doc, base_url=".").write_pdf()
    if not isinstance(pdf, (bytes, bytearray)):
        raise RuntimeError("WeasyPrint did not return PDF bytes")
    return bytes(pdf)


def render_pdf_to_path(
    book: StructuredBook,
    params: TypographyParams,
    output: str | Path,
    *,
    blank_pages: int = 0,
) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    data = render_pdf_bytes(book, params, blank_pages=blank_pages)
    output.write_bytes(data)
    return output


def pdf_page_count_from_bytes(data: bytes) -> int:
    import fitz

    doc = fitz.open(stream=io.BytesIO(data), filetype="pdf")
    try:
        return doc.page_count
    finally:
        doc.close()
