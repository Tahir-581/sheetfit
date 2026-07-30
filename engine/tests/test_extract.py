"""Smoke tests for extract + typography helpers."""

from pathlib import Path

import pytest

from sheetfit.extract import extract_book, page_count
from sheetfit.structure import structure_book
from sheetfit.typography import estimate_pages, params_from_generosity

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "3-The-Alchemist-Paulo-Coelho.pdf"
)


@pytest.mark.skipif(not FIXTURE.is_file(), reason="Alchemist fixture missing")
def test_alchemist_page_count():
    assert page_count(FIXTURE) == 136


@pytest.mark.skipif(not FIXTURE.is_file(), reason="Alchemist fixture missing")
def test_alchemist_extract_has_text():
    book = extract_book(FIXTURE)
    assert book.word_count > 10_000
    assert book.source_pages == 136
    structured = structure_book(book)
    assert structured.sections
    assert any(b.kind == "para" for sec in structured.sections for b in sec.blocks)


def test_params_monotonic():
    dense = params_from_generosity(0.0)
    roomy = params_from_generosity(1.0)
    assert roomy.font_size_pt > dense.font_size_pt
    assert roomy.margin_x_in >= dense.margin_x_in
    est_dense = estimate_pages(40_000, 5, dense)
    est_roomy = estimate_pages(40_000, 5, roomy)
    assert est_roomy > est_dense
