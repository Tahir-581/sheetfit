"""Map a generosity scalar to readable typography parameters."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TypographyParams:
    """Book page typography for half-Letter portrait."""

    generosity: float
    font_size_pt: float
    line_height: float
    margin_x_in: float
    margin_y_in: float
    paragraph_spacing_em: float
    chapter_opener_pages: bool

    def to_dict(self) -> dict:
        return asdict(self)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def params_from_generosity(g: float, *, force_openers: bool | None = None) -> TypographyParams:
    """
    g in [0, 1]: 0 = denser (still readable), 1 = max generosity within soft caps.
    Soft caps from the plan: body ≤ ~20pt, leading ≤ ~1.7.
    """
    g = max(0.0, min(1.0, g))
    font = lerp(11.0, 20.0, g)
    leading = lerp(1.35, 1.70, g)
    margin_x = lerp(0.55, 0.95, g)
    margin_y = lerp(0.60, 1.05, g)
    para = lerp(0.35, 0.95, g)
    openers = True if force_openers is None else force_openers
    if force_openers is None:
        openers = g >= 0.35
    return TypographyParams(
        generosity=g,
        font_size_pt=round(font, 2),
        line_height=round(leading, 3),
        margin_x_in=round(margin_x, 3),
        margin_y_in=round(margin_y, 3),
        paragraph_spacing_em=round(para, 3),
        chapter_opener_pages=openers,
    )


def estimate_pages(word_count: int, image_count: int, params: TypographyParams) -> int:
    """
    Rough page estimate used to seed binary search.
    Calibrated for half-Letter with serif body (WeasyPrint).
    """
    # Effective words per page shrinks as type/margins grow.
    # Empirically lower than print norms because of paragraph spacing + openers.
    base_wpp = 220.0
    scale = (11.0 / params.font_size_pt) ** 1.35 * (1.35 / params.line_height)
    margin_penalty = 1.0 - 0.28 * ((params.margin_x_in - 0.55) / 0.40)
    para_penalty = 1.0 - 0.15 * ((params.paragraph_spacing_em - 0.35) / 0.60)
    wpp = max(55.0, base_wpp * scale * margin_penalty * para_penalty)
    text_pages = word_count / wpp
    image_pages = image_count * 0.7
    opener_pages = 0
    if params.chapter_opener_pages:
        opener_pages = max(2, word_count // 2200)
    return max(1, int(round(text_pages + image_pages + opener_pages + 3)))
