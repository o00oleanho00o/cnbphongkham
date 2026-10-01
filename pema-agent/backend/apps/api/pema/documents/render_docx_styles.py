# ported from: src/documents/render-docx-styles.ts
"""Standard Vietnamese document typography (in the spirit of Decree 30/2020/ND-CP on administrative
documents - also the look Vietnamese readers take as a "serious document"): Times New Roman 13pt, black
throughout, and NOT the default theme of Word (Calibri + blue headings - one look says "machine generated" and
it is far from a Vietnamese document).

This is the "know-how lives in the renderer" part: the model cannot decide font/colour, so the file always has
the same quality whatever model runs.

Forced deviation: the original passed an ``IStylesOptions`` object to ``docx``; ``python-docx`` starts from a
template document that already carries blue theme styles, so ``apply_docx_styles`` REWRITES the styles of a
``Document`` in place: the document defaults, ``Title``, ``Heading 1-6`` and their linked character styles
(``Heading 1 Char`` ... still blue in the template and would leak the moment someone applies them), and the
page (A4 with the margins below, the template is US Letter). Sizes stay in the original units: half-points for
fonts (26 = 13pt) and twips for spacing (1cm = 567).

The rewrite is raw WordprocessingML: python-docx's style API cannot drop theme attributes, and its oxml layer
sits on ``lxml``, which has no type stubs - the small ``Xml`` helpers below are the one place that admits it
(``Xml`` is ``Any``) so the rest of the package stays strictly typed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final, cast

from docx.document import Document as DocumentObject
from docx.oxml import OxmlElement  # pyright: ignore[reportUnknownVariableType]  # lxml is untyped
from docx.oxml.ns import qn
from docx.shared import Twips

type Xml = Any
"""An lxml element of the oxml tree (lxml is untyped)."""

BODY_SIZE: Final = 26
"""Half-point unit: 26 = 13pt (the standard size of an administrative document)."""
FONT: Final = "Times New Roman"
BLACK: Final = "000000"

PAGE_WIDTH_DXA: Final = 11906
PAGE_HEIGHT_DXA: Final = 16838
"""A4 in twips."""

LINE_SPACING_AUTO: Final = 312
"""Line spacing ~1.3 (lineRule auto: 240 = 1 line), paragraph spacing 6pt (120) - the end of the
"wall of text" look."""
PARAGRAPH_AFTER: Final = 120

PAGE_MARGINS: Final = {"top": 1134, "bottom": 1134, "left": 1701, "right": 850}
"""Page margins of an administrative document (Decree 30): top/bottom 2cm, left 3cm (room for binding), right
1.5cm. Unit twips (1cm = 567)."""

CONTENT_WIDTH_DXA: Final = PAGE_WIDTH_DXA - PAGE_MARGINS["left"] - PAGE_MARGINS["right"]
"""Width of the content area = A4 (11906) minus the 2 margins - tables must add up to this number."""

TABLE_CELL_MARGINS: Final = {"top": 60, "bottom": 60, "left": 108, "right": 108}
"""Padding inside a table cell - without it the text sticks to the border and looks cramped."""

# Children of w:rPr / w:pPr in schema order: a new child goes before the first existing one that must
# follow it
RPR_ORDER: Final = (
    "w:rStyle",
    "w:rFonts",
    "w:b",
    "w:bCs",
    "w:i",
    "w:iCs",
    "w:caps",
    "w:smallCaps",
    "w:strike",
    "w:dstrike",
    "w:outline",
    "w:shadow",
    "w:emboss",
    "w:imprint",
    "w:noProof",
    "w:snapToGrid",
    "w:vanish",
    "w:webHidden",
    "w:color",
    "w:spacing",
    "w:w",
    "w:kern",
    "w:position",
    "w:sz",
    "w:szCs",
    "w:highlight",
    "w:u",
    "w:effect",
    "w:bdr",
    "w:shd",
    "w:fitText",
    "w:vertAlign",
    "w:rtl",
    "w:cs",
    "w:em",
    "w:lang",
    "w:eastAsianLayout",
    "w:specVanish",
    "w:oMath",
)
PPR_ORDER: Final = (
    "w:pStyle",
    "w:keepNext",
    "w:keepLines",
    "w:pageBreakBefore",
    "w:framePr",
    "w:widowControl",
    "w:numPr",
    "w:suppressLineNumbers",
    "w:pBdr",
    "w:shd",
    "w:tabs",
    "w:suppressAutoHyphens",
    "w:kinsoku",
    "w:wordWrap",
    "w:overflowPunct",
    "w:topLinePunct",
    "w:autoSpaceDE",
    "w:autoSpaceDN",
    "w:bidi",
    "w:adjustRightInd",
    "w:snapToGrid",
    "w:spacing",
    "w:ind",
    "w:contextualSpacing",
    "w:mirrorIndents",
    "w:suppressOverlap",
    "w:jc",
    "w:textDirection",
    "w:textAlignment",
    "w:textboxTightWrap",
    "w:outlineLvl",
    "w:divId",
    "w:cnfStyle",
    "w:rPr",
    "w:sectPr",
    "w:pPrChange",
)
_THEME_ATTRS: Final = ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme")


def xml_element(tag: str, **attrs: str) -> Xml:
    """A new ``w:`` element with ``w:`` attributes."""
    element = cast("Xml", OxmlElement(tag))
    for key, value in attrs.items():
        element.set(qn(f"w:{key}"), value)
    return element


def find_child(parent: Xml, tag: str) -> Xml | None:
    return parent.find(qn(tag))


def remove_child(parent: Xml, tag: str) -> None:
    old = find_child(parent, tag)
    if old is not None:
        parent.remove(old)


def set_child(parent: Xml, child: Xml, order: Sequence[str]) -> None:
    """Put ``child`` into ``parent`` in schema order, replacing an existing child with the same tag."""
    old = parent.find(child.tag)
    if old is not None:
        parent.remove(old)
    names = [qn(name) for name in order]
    later = set(names[names.index(child.tag) + 1 :])
    for sibling in parent:
        if sibling.tag in later:
            sibling.addprevious(child)
            return
    parent.append(child)


def _set_fonts(r_pr: Xml) -> None:
    """Times New Roman for every script and NO theme font (a theme attribute wins over ``w:ascii``)."""
    r_fonts = find_child(r_pr, "w:rFonts")
    if r_fonts is None:
        r_fonts = xml_element("w:rFonts")
        set_child(r_pr, r_fonts, RPR_ORDER)
    for attr in _THEME_ATTRS:
        r_fonts.attrib.pop(qn(f"w:{attr}"), None)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        r_fonts.set(qn(f"w:{attr}"), FONT)


def _set_size(r_pr: Xml, half_points: int) -> None:
    set_child(r_pr, xml_element("w:sz", val=str(half_points)), RPR_ORDER)
    set_child(r_pr, xml_element("w:szCs", val=str(half_points)), RPR_ORDER)


def _set_black(r_pr: Xml) -> None:
    """Black, with no theme colour left (``w:themeColor`` / ``w:themeShade`` would win over ``w:val``)."""
    set_child(r_pr, xml_element("w:color", val=BLACK), RPR_ORDER)


def _style_properties(style: Xml, tag: str) -> Xml:
    element: Xml = style.element
    return element.get_or_add_rPr() if tag == "w:rPr" else element.get_or_add_pPr()


def _style_run(style: Xml, size: int | None, *, bold: bool, italic: bool = False) -> None:
    """Run formatting of a style: font, size, black, bold, italic (turned OFF when not asked: the template's
    Heading 4 is italic blue)."""
    r_pr = _style_properties(style, "w:rPr")
    _set_fonts(r_pr)
    if size is not None:
        _set_size(r_pr, size)
    _set_black(r_pr)
    for flag, tags in ((bold, ("w:b", "w:bCs")), (italic, ("w:i", "w:iCs"))):
        for tag in tags:
            if flag:
                set_child(r_pr, xml_element(tag), RPR_ORDER)
            else:
                remove_child(r_pr, tag)


def _style_paragraph(style: Xml, *, before: int | None = None, after: int | None = None) -> None:
    p_pr = _style_properties(style, "w:pPr")
    spacing = find_child(p_pr, "w:spacing")
    if spacing is None:
        spacing = xml_element("w:spacing")
        set_child(p_pr, spacing, PPR_ORDER)
    if before is not None:
        spacing.set(qn("w:before"), str(before))
    if after is not None:
        spacing.set(qn("w:after"), str(after))


def _apply_doc_defaults(document: DocumentObject) -> None:
    styles_element: Xml = document.styles.element
    doc_defaults = find_child(styles_element, "w:docDefaults")
    if doc_defaults is None:
        return
    r_pr_default = find_child(doc_defaults, "w:rPrDefault")
    r_pr = find_child(r_pr_default, "w:rPr") if r_pr_default is not None else None
    if r_pr is not None:
        _set_fonts(r_pr)
        _set_size(r_pr, BODY_SIZE)
        _set_black(r_pr)
    p_pr_default = find_child(doc_defaults, "w:pPrDefault")
    p_pr = find_child(p_pr_default, "w:pPr") if p_pr_default is not None else None
    if p_pr is not None:
        set_child(
            p_pr,
            xml_element(
                "w:spacing", line=str(LINE_SPACING_AUTO), lineRule="auto", after=str(PARAGRAPH_AFTER)
            ),
            PPR_ORDER,
        )


def _style_by_name(document: DocumentObject, name: str) -> Xml:
    for style in document.styles:
        if style.name == name:
            return style
    raise KeyError(name)


def apply_docx_styles(document: DocumentObject) -> None:
    """Rewrite the styles and the page of ``document`` (see the module docstring)."""
    _apply_doc_defaults(document)

    title = _style_by_name(document, "Title")
    _style_run(title, 30, bold=True)
    title_p_pr = _style_properties(title, "w:pPr")
    # The template's Title has a blue bottom border and "contextual spacing"; the original has neither
    for tag in ("w:pBdr", "w:contextualSpacing"):
        remove_child(title_p_pr, tag)
    set_child(title_p_pr, xml_element("w:jc", val="center"), PPR_ORDER)
    set_child(
        title_p_pr,
        xml_element("w:spacing", before="120", after="240", line=str(LINE_SPACING_AUTO), lineRule="auto"),
        PPR_ORDER,
    )

    heading1 = _style_by_name(document, "Heading 1")
    _style_run(heading1, 28, bold=True)
    _style_paragraph(heading1, before=240, after=120)

    heading2 = _style_by_name(document, "Heading 2")
    _style_run(heading2, BODY_SIZE, bold=True)
    _style_paragraph(heading2, before=200, after=120)

    heading3 = _style_by_name(document, "Heading 3")
    _style_run(heading3, BODY_SIZE, bold=True, italic=True)
    _style_paragraph(heading3, before=160, after=100)

    # The renderer does not emit headings 4-6 but their default style still sits in the file with the theme's
    # BLUE - anyone who opens the file and applies Heading 4 gets it. Blacken them too for a one-tone
    # document.
    for level in (4, 5, 6):
        _style_run(_style_by_name(document, f"Heading {level}"), None, bold=True)

    # The linked character styles (Heading 1 Char ...) carry the same blue
    linked = {"Title Char", *(f"Heading {level} Char" for level in range(1, 7))}
    for style in document.styles:
        if style.name in linked:
            r_pr = _style_properties(style, "w:rPr")
            _set_fonts(r_pr)
            _set_black(r_pr)

    section = document.sections[0]
    section.page_width = Twips(PAGE_WIDTH_DXA)
    section.page_height = Twips(PAGE_HEIGHT_DXA)
    section.top_margin = Twips(PAGE_MARGINS["top"])
    section.bottom_margin = Twips(PAGE_MARGINS["bottom"])
    section.left_margin = Twips(PAGE_MARGINS["left"])
    section.right_margin = Twips(PAGE_MARGINS["right"])
