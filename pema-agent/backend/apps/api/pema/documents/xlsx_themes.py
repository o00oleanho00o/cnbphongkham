# ported from: src/documents/xlsx-themes.ts
"""Colour themes of the .xlsx file: the MODEL picks one by document context, it never writes a free hex.

Why not one hard-coded colour: 10 reports turning into 10 identical files looks like a mass printer. Why not
let the model choose a hex: it will produce white-on-light pairs that cannot be read.

Every background below was measured against WHITE text with the WCAG 2.1 formula and passes AA for normal
text (>= 4.5:1); the measured ratio is written next to each theme. Light orange (ED7D31, 2.77:1) and yellow
(FFC000, 1.64:1) were dropped because they fail.

No forced deviation: ``as const satisfies Record`` became a frozen dataclass plus a dict,
``keyof typeof`` became a ``Literal``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, get_args


@dataclass(frozen=True)
class XlsxTheme:
    header: str
    """Background of the title banner + table header (white text on top)."""
    number: str
    """Text colour of hand-typed numbers: dark, same hue, not a harsh pure blue."""
    border: str
    """Cell border: light, same hue, so the table does not look dry."""
    stripe: str
    """Alternating background of even rows, very light."""


XlsxThemeName = Literal["navy", "blue", "green", "burgundy", "slate", "teal"]

XLSX_THEMES: Final[dict[XlsxThemeName, XlsxTheme]] = {
    # 11.62:1 - formal, default for summary reports
    "navy": XlsxTheme(header="FF1F3864", number="FF1F3864", border="FF8496B0", stripe="FFF2F5FA"),
    # 8.66:1 - finance, business, quotes
    "blue": XlsxTheme(header="FF1F4E79", number="FF1F4E79", border="FF8EAADB", stripe="FFF2F7FC"),
    # 6.52:1 - growth, agriculture, environment, good results
    "green": XlsxTheme(header="FF1E6B3A", number="FF1E6B3A", border="FF8FBC9B", stripe="FFF1F8F3"),
    # 8.65:1 - warnings, risk, legal, incidents
    "burgundy": XlsxTheme(header="FF8B2635", number="FF8B2635", border="FFD4A0A8", stripe="FFFCF3F4"),
    # 7.71:1 - technical, operations, neutral
    "slate": XlsxTheme(header="FF44546A", number="FF44546A", border="FFAEB8C6", stripe="FFF4F6F8"),
    # 6.84:1 - health, education, services
    "teal": XlsxTheme(header="FF17646B", number="FF17646B", border="FF8FC0C4", stripe="FFF0F8F8"),
}

XLSX_THEME_NAMES: Final[tuple[XlsxThemeName, ...]] = get_args(XlsxThemeName)

DEFAULT_XLSX_THEME: Final[XlsxThemeName] = "navy"


def resolve_theme(name: XlsxThemeName | None) -> XlsxTheme:
    return XLSX_THEMES[name or DEFAULT_XLSX_THEME]
