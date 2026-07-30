"""Normalize extracted blocks into a book-friendly structure."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .extract import ContentBlock, ExtractedBook

_CHAPTERISH = re.compile(
    r"^(part\s+|chapter\s+|prologue|epilogue|foreword|afterword|introduction|preface)$",
    re.I,
)

_SKIP_HEADING = re.compile(
    r"(copyright|about the author|about the publisher|also by|back ads|contents|"
    r"international acclaim|translated by|hardcover edition|published in|"
    r"warrior of the light|table of contents)",
    re.I,
)


@dataclass
class BookSection:
    title: str | None
    blocks: list[ContentBlock] = field(default_factory=list)
    opener: bool = False


@dataclass
class StructuredBook:
    title: str
    author: str
    source_pages: int
    word_count: int
    image_count: int
    sections: list[BookSection]
    front_images: list[ContentBlock]


def structure_book(book: ExtractedBook) -> StructuredBook:
    front_images: list[ContentBlock] = []
    sections: list[BookSection] = []
    current = BookSection(title=None, opener=False)

    # Treat early full-bleed images as front matter plates
    body_started = False

    for block in book.blocks:
        if not body_started and block.kind == "image" and not current.blocks:
            front_images.append(block)
            continue

        title = block.text.strip()
        if block.kind == "heading":
            if _SKIP_HEADING.search(title):
                # Keep as ordinary text only if it looks like real prose
                if len(title.split()) > 12:
                    current.blocks.append(block)
                continue
            if _CHAPTERISH.match(title) or (
                3 <= len(title) <= 48
                and title.isupper()
                and not any(ch.isdigit() for ch in title)
            ):
                if current.blocks or current.title:
                    sections.append(current)
                current = BookSection(title=title, opener=True, blocks=[])
                body_started = True
                continue
            # Soft heading inside flow
            current.blocks.append(block)
            body_started = True
            continue

        body_started = True
        current.blocks.append(block)

    if current.blocks or current.title:
        sections.append(current)

    if not sections:
        sections = [BookSection(title=None, blocks=list(book.blocks), opener=False)]

    return StructuredBook(
        title=book.title,
        author=book.author,
        source_pages=book.source_pages,
        word_count=book.word_count,
        image_count=book.image_count,
        sections=sections,
        front_images=front_images,
    )
