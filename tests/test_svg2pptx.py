#!/usr/bin/env python3
"""Tests of scripts/svg2pptx.py: which full-canvas background rect collect() leaves to the slide,
how opacity / fill-opacity / stroke-opacity reach the PPTX as color alpha, which root <svg>
attributes are reported, how render_pptx.py previews that alpha, which <tspan>s are reported,
that hidden elements are reported, how degenerate shapes are left out, and that what collect() accepts converts.

    python3 tests/test_svg2pptx.py
"""
import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

MISSING = [m for m in ("pptx", "cairosvg") if importlib.util.find_spec(m) is None]
if MISSING:  # svg2pptx.py imports them: skip, like test_examples' export column
    raise unittest.SkipTest(f"needs python-pptx and cairosvg (missing: {', '.join(MISSING)})")

import check_layout as CL  # noqa: E402
import render_pptx  # noqa: E402
import svg2pptx  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.oxml.ns import qn  # noqa: E402

TEXT = '<text x="20" y="50" font-size="14" fill="#FFFFFF">Hello</text>'
SHAPE = '<rect x="20" y="20" width="40" height="30" fill="#FF9900"/>'


def svg(body, view="0 0 200 100"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}">{body}</svg>'


def collect(body, view="0 0 200 100"):
    _, items, problems = svg2pptx.collect(ET.fromstring(svg(body, view)))
    assert problems == [], problems
    return items


def problems(body):
    return svg2pptx.collect(ET.fromstring(svg(body)))[2]


def kinds(body, view="0 0 200 100"):
    return [(it["k"], it["box"]) if it["k"] == "rect" else (it["k"], None) for it in collect(body, view)]


def build_deck(body, d):
    """Build a one-slide deck from `body` in directory `d`; return its Presentation."""
    draft, deck = Path(d) / "t.draft.svg", Path(d) / "t.pptx"
    draft.write_text(svg(body), encoding="utf-8")
    with redirect_stdout(StringIO()):
        assert svg2pptx.build([draft], [], deck)
    return Presentation(deck)


def deck_shapes(body):
    """Build a one-slide deck from `body`; return the shapes inside the diagram group."""
    with tempfile.TemporaryDirectory() as d:
        return list(build_deck(body, d).slides[0].shapes[0].shapes)


def preview(body):
    """The SVG render_pptx.py draws for the one-slide deck built from `body`, parsed."""
    with tempfile.TemporaryDirectory() as d:
        prs = build_deck(body, d)
        r = render_pptx.Renderer(prs.slides[0], "sans-serif")
        r.walk(prs.slides[0].shapes, lambda x, y, w, h: (x, y, w, h))
        return ET.fromstring(r.svg(prs.slide_width, prs.slide_height))


def drawn(root, tag):
    return root.findall(f"{svg2pptx.NS}{tag}")


def clr(solid_fill_parent):
    """(srgbClr val, alpha val or None) of the <a:solidFill> under an spPr / ln / rPr, or None."""
    sf = solid_fill_parent.find(qn("a:solidFill"))
    if sf is None:
        return None
    c = sf.find(qn("a:srgbClr"))
    a = c.find(qn("a:alpha"))
    return c.get("val"), (a.get("val") if a is not None else None)


def rpr(shape):
    return shape._element.find(".//" + qn("a:rPr"))


class Background(unittest.TestCase):
    def test_coloured_background_kept(self):
        self.assertEqual(kinds('<rect width="200" height="100" fill="#232F3E"/>' + TEXT),
                         [("rect", (0, 0, 200, 100)), ("text", None)])

    def test_coloured_background_reaches_the_pptx(self):
        with tempfile.TemporaryDirectory() as d:
            draft, deck = Path(d) / "bg.draft.svg", Path(d) / "bg.pptx"
            draft.write_text(svg('<rect width="200" height="100" fill="#232F3E"/>' + TEXT), encoding="utf-8")
            with redirect_stdout(StringIO()):
                self.assertTrue(svg2pptx.build([draft], [], deck))
            shapes = Presentation(deck).slides[0].shapes[0].shapes
            self.assertEqual([s.shape_type.name for s in shapes], ["AUTO_SHAPE", "TEXT_BOX"])
            self.assertEqual(str(shapes[0].fill.fore_color.rgb), "232F3E")

    def test_first_white_background_dropped(self):
        for fill in ("#FFFFFF", "#fff", "white", "none"):
            with self.subTest(fill=fill):
                self.assertEqual(kinds(f'<rect width="200" height="100" fill="{fill}"/>' + TEXT),
                                 [("text", None)])
        # larger than the canvas, from before its origin, still covers it
        self.assertEqual(kinds('<rect x="-5" y="-5" width="300" height="200" fill="#FFFFFF"/>' + TEXT),
                         [("text", None)])

    def test_viewbox_origin(self):
        # boxes are measured from the viewBox origin, not from (0, 0)
        self.assertEqual(kinds('<rect x="10" y="20" width="200" height="100" fill="#FFFFFF"/>' + TEXT,
                               view="10 20 200 100"), [("text", None)])
        self.assertEqual(kinds('<rect width="200" height="100" fill="#FFFFFF"/>' + TEXT, view="10 20 200 100"),
                         [("rect", (-10, -20, 200, 100)), ("text", None)])

    def test_not_blank_kept(self):
        for attrs, fill, fa in (('fill="#FFFFFF" stroke="#232F3E"', "FFFFFF", 1.0),
                                ('fill="#F2F2F2"', "F2F2F2", 1.0),
                                ('', "000000", 1.0),  # no fill attribute: SVG paints it black
                                # translucent white stays a translucent white shape
                                ('fill="#FFFFFF" opacity="0.5"', "FFFFFF", 0.5),
                                ('fill="#FFFFFF" fill-opacity="0.5"', "FFFFFF", 0.5),
                                ('fill="#FFFFFF" fill-opacity="50%"', "FFFFFF", 0.5)):
            with self.subTest(attrs=attrs):
                items = collect(f'<rect width="200" height="100" {attrs}/>' + TEXT)
                self.assertEqual([it["k"] for it in items], ["rect", "text"])
                self.assertEqual((str(items[0]["fill"]), items[0]["fa"]), (fill, fa))

    def test_backdrop_after_skipped_elements_dropped(self):
        head = ('<title>t</title><desc>d</desc><defs><marker id="a"><rect width="9" height="9" '
                'fill="#000"/></marker></defs>')
        self.assertEqual(kinds(head + '<rect width="200" height="100" fill="#FFFFFF"/>' + TEXT), [("text", None)])

    def test_backdrop_through_parent_translate_dropped(self):
        self.assertEqual(kinds('<g transform="translate(-10,-10)"><rect width="220" height="120" fill="#FFFFFF"/></g>'
                               + TEXT), [("text", None)])

    def test_transparent_backdrop_dropped(self):
        for attrs in ('fill="#000" opacity="0"', 'fill="#000" fill-opacity="0"', 'fill="#232F3E" opacity="0%"',
                      'fill="#FFFFFF" stroke="#000" stroke-opacity="0"', 'fill="#FFFFFF" opacity="100%"'):
            with self.subTest(attrs=attrs):
                self.assertEqual(kinds(f'<rect width="200" height="100" {attrs}/>' + TEXT), [("text", None)])

    def test_canvas_sized_rect_elsewhere_kept(self):
        self.assertEqual(kinds('<rect x="10" width="200" height="100" fill="#FFFFFF"/>' + TEXT),
                         [("rect", (10, 0, 200, 100)), ("text", None)])
        self.assertEqual(kinds('<g transform="translate(0,5)"><rect width="200" height="100" fill="#FFFFFF"/></g>'
                               + TEXT), [("rect", (0, 5, 200, 100)), ("text", None)])

    def test_later_white_mask_kept(self):
        # a white canvas-sized rect drawn over other shapes masks them; it is not the background
        self.assertEqual(kinds(SHAPE + '<rect width="200" height="100" fill="#FFFFFF"/>' + TEXT),
                         [("rect", (20, 20, 40, 30)), ("rect", (0, 0, 200, 100)), ("text", None)])
        # only the first one goes when the background is repeated
        self.assertEqual(kinds('<rect width="200" height="100" fill="#FFFFFF"/>' * 2 + TEXT),
                         [("rect", (0, 0, 200, 100)), ("text", None)])

    def test_examples_white_background_omitted(self):
        svgs = sorted((ROOT / "docs").rglob("*.svg"))
        self.assertGreaterEqual(len(svgs), 15)
        for path in svgs:
            with self.subTest(svg=path.name):
                root = ET.parse(path).getroot()
                (_, _, vw, vh), items, problems = svg2pptx.collect(root)
                _, kept, kept_problems = svg2pptx.collect(root, drop_backdrop=False)
                self.assertEqual((problems, kept_problems), ([], []))
                # exactly the first item, an opaque white full-canvas rect, is left to the slide
                self.assertEqual(items, kept[1:])
                self.assertEqual((kept[0]["k"], kept[0]["box"], str(kept[0]["fill"]), kept[0]["fa"]),
                                 ("rect", (0, 0, vw, vh), "FFFFFF", 1.0))


class Opacity(unittest.TestCase):
    def test_values(self):
        for v, a in (("", 1.0), ("1", 1.0), ("0.5", 0.5), (".5", 0.5), ("50%", 0.5), (" 8% ", 0.08),
                     ("0", 0.0), ("0%", 0.0), ("1.5", 1.0), ("-1", 0.0), ("150%", 1.0)):
            with self.subTest(v=v):
                self.assertAlmostEqual(svg2pptx.alpha(v), a)
        for v in ("abc", "50 %", "nan", "inf", "%"):
            with self.subTest(v=v):
                self.assertRaises(ValueError, svg2pptx.alpha, v)

    def test_combined(self):
        rect = collect('<rect x="10" y="10" width="20" height="20" fill="#FF9900" stroke="#232F3E" '
                       'opacity="50%" fill-opacity="0.5" stroke-opacity="40%"/>')[0]
        self.assertAlmostEqual(rect["fa"], 0.25)
        self.assertAlmostEqual(rect["sa"], 0.2)

    def test_bad_value_reported(self):
        self.assertTrue(any("opacity" in p for p in problems('<rect width="9" height="9" opacity="half"/>')))

    def test_unsupported_owners_reported(self):
        img = '<image href="bundle:service/AWS-Lambda" x="0" y="0" width="48" height="48" opacity="0.5"/>'
        self.assertTrue(any("<image>" in p and "opacity" in p for p in problems(img)))
        self.assertEqual(problems(img.replace(' opacity="0.5"', ' opacity="1"')), [])
        self.assertTrue(any("<g>" in p and "opacity" in p for p in problems(f'<g opacity="0.5">{SHAPE}</g>')))
        root = ET.fromstring(svg(SHAPE).replace("<svg ", '<svg opacity="0.5" ', 1))
        self.assertTrue(any("<svg>" in p for p in svg2pptx.collect(root)[2]))

    def test_bad_root_opacity_reported(self):
        # parsed with the other root checks: a problem, not an uncaught ValueError
        for v in ("50 %", "half"):
            with self.subTest(v=v):
                root = ET.fromstring(svg(SHAPE).replace("<svg ", f'<svg opacity="{v}" ', 1))
                found = svg2pptx.collect(root)[2]
                self.assertTrue(any(p.startswith("<svg>") and "opacity" in p for p in found), found)

    def test_translucent_coloured_background(self):
        body = '<rect width="200" height="100" fill="#232F3E" fill-opacity="0.08"/>' + TEXT.replace("#FFFFFF", "#232F3E")
        self.assertEqual(kinds(body), [("rect", (0, 0, 200, 100)), ("text", None)])
        bg, text = deck_shapes(body)
        self.assertEqual(clr(bg._element.spPr), ("232F3E", "8000"))
        self.assertEqual(clr(rpr(text)), ("232F3E", None))  # the label stays fully opaque

    def test_alpha_on_every_shape(self):
        bg, oval, line, poly, text = deck_shapes(
            '<rect x="10" y="10" width="40" height="30" fill="#FF9900" fill-opacity="0.5" stroke="#232F3E" '
            'stroke-opacity="25%"/>'
            '<circle cx="80" cy="30" r="10" fill="#FF9900" opacity="0.4"/>'
            '<line x1="10" y1="60" x2="100" y2="60" stroke="#232F3E" stroke-opacity="0.3"/>'
            '<polyline points="10,70 50,70 50,90" fill="none" stroke="#232F3E" opacity="60%"/>'
            '<text x="120" y="50" font-size="14" fill="#232F3E" fill-opacity="0.7">Hi</text>')
        self.assertEqual(clr(bg._element.spPr), ("FF9900", "50000"))
        self.assertEqual(clr(bg._element.spPr.find(qn("a:ln"))), ("232F3E", "25000"))
        self.assertEqual(clr(oval._element.spPr), ("FF9900", "40000"))
        self.assertEqual(clr(line._element.spPr.find(qn("a:ln"))), ("232F3E", "30000"))
        self.assertEqual(clr(poly._element.spPr.find(qn("a:ln"))), ("232F3E", "60000"))
        self.assertEqual(clr(rpr(text)), ("232F3E", "70000"))

    def test_opaque_has_no_alpha(self):
        rect, = deck_shapes(SHAPE.replace("/>", ' stroke="#232F3E" opacity="1" fill-opacity="100%"/>'))
        self.assertEqual(clr(rect._element.spPr), ("FF9900", None))
        self.assertEqual(clr(rect._element.spPr.find(qn("a:ln"))), ("232F3E", None))

    def test_zero_is_no_fill_or_line(self):
        rect, line, text = deck_shapes(
            '<rect x="10" y="10" width="40" height="30" fill="#FF9900" stroke="#232F3E" opacity="0"/>'
            '<line x1="10" y1="60" x2="100" y2="60" stroke="#232F3E" stroke-opacity="0%"/>'
            '<text x="120" y="50" font-size="14" fill="#232F3E" fill-opacity="0">Hi</text>')
        self.assertIsNone(clr(rect._element.spPr))
        self.assertIsNotNone(rect._element.spPr.find(qn("a:noFill")))
        self.assertIsNotNone(rect._element.spPr.find(qn("a:ln")).find(qn("a:noFill")))
        self.assertIsNotNone(line._element.spPr.find(qn("a:ln")).find(qn("a:noFill")))
        self.assertIsNone(clr(rpr(text)))
        self.assertIsNotNone(rpr(text).find(qn("a:noFill")))

    def test_transparent_stroke_on_text_is_no_halo(self):
        body = '<text x="20" y="50" font-size="14" stroke="#FFFFFF" stroke-opacity="0">Hi</text>'
        self.assertEqual(problems(body), [])
        self.assertTrue(problems(body.replace(' stroke-opacity="0"', "")))



class RootAttributes(unittest.TestCase):
    """SVG passes paint / text attributes on the root <svg> down to every child; the slide
    shapes would not, so they are reported like the same attributes on a <g>."""

    def root_problems(self, attrs):
        return svg2pptx.collect(ET.fromstring(svg(SHAPE + TEXT).replace("<svg ", f"<svg {attrs} ", 1)))[2]

    def test_inherited_reported(self):
        for attrs in ('fill-opacity="0.5"', 'stroke-opacity="50%"', 'fill="#232F3E"', 'stroke="#000"',
                      'stroke-width="2"', 'font-size="20"', 'text-anchor="middle"'):
            with self.subTest(attrs=attrs):
                found = self.root_problems(attrs)
                name = attrs.partition("=")[0]
                self.assertTrue(any(p.startswith("<svg> carries") and name in p for p in found), found)

    def test_layout_root_attributes_accepted(self):
        # what layout.py writes on the root: viewBox and font-family (the deck's font is --font)
        self.assertEqual(self.root_problems('width="200" height="100" font-family="Arial"'), [])


def converts(test, body):
    """collect() reports nothing for `body`; build() turns it into a deck without a traceback.
    Returns the shapes inside the diagram group."""
    test.assertEqual(problems(body), [])
    return deck_shapes(body)


class TextRun(unittest.TestCase):
    """A <text> becomes one run in one format: a <tspan> that would change part of it is
    reported before anything is written; a plain one only joins its characters."""

    def test_formatting_tspan_reported(self):
        for attrs in ('fill="#FF0000"', 'font-weight="bold"', 'font-size="20"', 'fill-opacity="0.5"',
                      'font-style="italic"', 'text-decoration="underline"', 'display="none"',
                      'visibility="hidden"', 'baseline-shift="super"'):
            with self.subTest(attrs=attrs):
                found = problems(f'<text x="20" y="50" font-size="14" fill="#000000">A<tspan {attrs}>B</tspan>C</text>')
                name = attrs.partition("=")[0]
                self.assertTrue(any(p.startswith("<tspan> 'B' sets") and name in p for p in found), found)

    def test_review_repro_reported(self):
        found = problems('<text x="20" y="50" font-size="14" fill="#000000">A<tspan fill="#FF0000" '
                         'font-weight="bold">B</tspan>C</text>')
        self.assertTrue(any("fill, font-weight" in p for p in found), found)
        with tempfile.TemporaryDirectory() as d:
            draft, deck = Path(d) / "t.draft.svg", Path(d) / "t.pptx"
            draft.write_text(svg('<text x="20" y="50" font-size="14">A<tspan fill="#FF0000">B</tspan>C</text>'),
                             encoding="utf-8")
            with redirect_stdout(StringIO()):
                self.assertFalse(svg2pptx.build([draft], [], deck))
            self.assertFalse(deck.exists())

    def test_style_and_class_on_tspan_reported(self):
        for attrs in ('style="fill:#FF0000"', 'class="hot"'):
            with self.subTest(attrs=attrs):
                found = problems(f'<text x="20" y="50" font-size="14">A<tspan {attrs}>B</tspan>C</text>')
                self.assertTrue(any(p.startswith("<tspan> uses style=/class=") for p in found), found)

    def test_nested_tspan_checked(self):
        found = problems('<text x="20" y="50" font-size="14">A<tspan>B<tspan font-weight="bold">C</tspan></tspan></text>')
        self.assertTrue(any(p.startswith("<tspan> 'C' sets font-weight") for p in found), found)

    def test_positioning_tspan_still_reported(self):
        found = problems('<text x="20" y="50" font-size="14">A<tspan x="20" dy="16">B</tspan></text>')
        self.assertTrue(any(p.startswith("<tspan> positions text") for p in found), found)

    def test_other_child_reported(self):
        found = problems('<text x="20" y="50" font-size="14">A<a href="#x">B</a></text>')
        self.assertTrue(any(p.startswith("<a> inside <text>") for p in found), found)

    def test_plain_tspan_joins_text(self):
        text, = collect('<text x="20" y="50" font-size="14" fill="#232F3E">A<tspan>B</tspan>'
                        '<tspan id="c">C</tspan>D</text>')
        self.assertEqual(text["s"], "ABCD")
        box, = converts(self, '<text x="20" y="50" font-size="14">A<tspan>B</tspan>C</text>')
        self.assertEqual(box.text_frame.text, "ABC")

    def test_title_inside_text_not_drawn(self):
        text, = collect('<text x="20" y="50" font-size="14">Hi<title>tooltip</title></text>')
        self.assertEqual(text["s"], "Hi")


class SlideTexts(unittest.TestCase):
    """check_layout.slide_texts (what SLIDE TOO SMALL and R-fit weigh) is the set of texts
    collect() puts on the slide: no <title> / <desc> characters, nothing in defs / marker /
    title / desc or an element it does not convert, <tspan> parts joined, a missing or
    unit-carrying font-size 16, blank text and font-size 0 left out."""

    @staticmethod
    def collected(root):
        return sorted((it["fs"], it["s"]) for it in svg2pptx.collect(root)[1] if it["k"] == "text")

    def test_same_texts_as_collect(self):
        body = ('<text x="10" y="20" font-size="1"><title>tooltip</title></text>'
                '<text x="10" y="30" font-size="2"><desc>about</desc></text>'
                '<text x="10" y="40" font-size="3">a<title>t</title>b</text>'
                '<text x="40" y="60" font-size="14">Visible</text>'
                '<text x="40" y="70" font-size="12">one <tspan>run</tspan> joined</text>'
                '<text x="40" y="80">no size</text>'
                '<text x="40" y="90" font-size="0">zero</text>'
                '<text x="40" y="95" font-size="9">  </text>'
                '<defs><text x="0" y="0" font-size="4">in defs</text></defs>'
                '<marker id="m"><text font-size="5">in marker</text></marker>'
                '<g id="x"><text x="5" y="5" font-size="13">in a g</text></g>'
                '<foreignObject><text font-size="6">not converted</text></foreignObject>')
        root = ET.fromstring(svg(body, "0 0 300 300"))
        got = sorted(CL.slide_texts(root))
        self.assertEqual(got, self.collected(root))
        self.assertEqual(got, [(3.0, "ab"), (12.0, "one run joined"), (13.0, "in a g"),
                               (14.0, "Visible"), (16.0, "no size")])

    def test_same_texts_on_the_examples(self):
        for path in sorted((ROOT / "docs" / "examples").glob("**/*.svg")):
            with self.subTest(path.name):
                root = ET.parse(path).getroot()
                self.assertEqual(sorted(CL.slide_texts(root)), self.collected(root))


class Hidden(unittest.TestCase):
    """An element hidden with display="none" or visibility="hidden" / "collapse" is reported
    before anything is written: style= / class= can show it again, and CairoSVG still draws
    a hidden <image> and visibility="collapse" into the PNG, so the formats would disagree."""

    IMG = '<image href="bundle:service/AWS-Lambda" x="10" y="10" width="32" height="32"/>'
    LINE = '<line x1="0" y1="0" x2="50" y2="0" stroke="#000"/>'
    CIRCLE = '<circle cx="20" cy="20" r="5" fill="#000"/>'
    HIDING = ('display="none"', 'visibility="hidden"', 'visibility="collapse"', 'visibility=" Hidden "')

    @staticmethod
    def with_attr(el, attr):
        return el.replace("/>", f" {attr}/>", 1) if el.endswith("/>") else el.replace(">", f" {attr}>", 1)

    def assert_hidden_reported(self, body, tag):
        found = problems(body)
        hits = [p for p in found if p.startswith(f"<{tag}> has ") and "delete the element" in p]
        self.assertTrue(hits, found)
        with tempfile.TemporaryDirectory() as d:
            draft, deck = Path(d) / "t.draft.svg", Path(d) / "t.pptx"
            draft.write_text(svg(body), encoding="utf-8")
            with redirect_stdout(StringIO()):
                self.assertFalse(svg2pptx.build([draft], [], deck))
            self.assertFalse(deck.exists())
        return found

    def test_every_element_reported(self):
        for attr in self.HIDING:
            for tag, el in (("rect", SHAPE), ("text", TEXT), ("image", self.IMG), ("line", self.LINE),
                            ("circle", self.CIRCLE), ("polyline", '<polyline points="0,0 9,9" fill="none" '
                                                                 'stroke="#000"/>'),
                            ("g", f"<g>{SHAPE}</g>")):
                with self.subTest(attr=attr, tag=tag):
                    self.assert_hidden_reported(self.with_attr(el, attr) + SHAPE, tag)

    def test_review_repro_style_overrides_display(self):
        # display="none" used to end the walk before style= was looked at: SVG / PNG drew
        # the red square (CSS display:inline wins), the slide was empty
        for tag, body in (
                ("rect", '<rect x="10" y="10" width="20" height="20" fill="#FF0000" display="none" '
                         'style="display:inline"/>'),
                ("g", f'<g display="none" style="display:inline">{SHAPE}</g>'),
                ("text", '<text x="20" y="50" font-size="14" display="none" style="display:inline">Hi</text>')):
            with self.subTest(tag=tag):
                found = self.assert_hidden_reported(body, tag)
                self.assertTrue(any(p.startswith(f"<{tag}> uses style=/class=") for p in found), found)
        found = problems(f'<rect x="10" y="10" width="20" height="20" display="none" class="on"/>')
        self.assertTrue(any(p.startswith("<rect> uses style=/class=") for p in found), found)

    def test_review_repro_hidden_image(self):
        # CairoSVG draws these icons into the PNG while the slide would leave them out
        for attr in ('display="none"', 'visibility="hidden"', 'visibility="collapse"'):
            with self.subTest(attr=attr):
                self.assert_hidden_reported('<image x="10" y="10" width="32" height="32" '
                                            f'href="bundle:service/AWS-Lambda" {attr}/>', "image")

    def test_collapse_rect_and_text(self):
        self.assert_hidden_reported(SHAPE.replace("/>", ' visibility="collapse"/>'), "rect")
        self.assert_hidden_reported(TEXT.replace("<text ", '<text visibility="collapse" '), "text")

    def test_hidden_group_and_root(self):
        found = self.assert_hidden_reported(f'<g id="a" display="none">{SHAPE}{TEXT}<g>{self.IMG}</g></g>', "g")
        self.assertFalse(any("carries" in p for p in found), found)  # one message, not two
        self.assert_hidden_reported(f'<g visibility="hidden">{SHAPE}<rect x="0" y="0" width="5" '
                                    f'height="5" fill="#000" visibility="visible"/></g>', "g")
        root = ET.fromstring(svg(SHAPE + TEXT).replace("<svg ", '<svg visibility="hidden" ', 1))
        found = svg2pptx.collect(root)[2]
        self.assertTrue(any(p.startswith("<svg> has visibility='hidden'") for p in found), found)

    def test_defaults_convert(self):
        for attr in ('display="inline"', 'display="inherit"', 'visibility="visible"', 'visibility="inherit"',
                     'display=" Inline "'):
            for el in (SHAPE, TEXT, self.IMG, f"<g>{SHAPE}</g>"):
                with self.subTest(attr=attr, el=el):
                    self.assertEqual(problems(self.with_attr(el, attr)), [])
                    self.assertEqual(collect(self.with_attr(el, attr)), collect(el))
        shown = TEXT.replace("<text ", '<text display="inline" ')
        self.assertEqual(len(converts(self, f'<g visibility="visible">{SHAPE}</g>{shown}')), 2)

    def test_other_values_reported(self):
        found = problems(SHAPE.replace("/>", ' visibility="maybe"/>'))
        self.assertTrue(any("visibility='maybe' is not supported" in p for p in found), found)
        found = problems(f'<g display="block">{SHAPE}</g>')
        self.assertTrue(any("display='block' is not supported" in p for p in found), found)


class Degenerate(unittest.TestCase):
    """Shapes SVG draws nothing of are left out, and everything collect() accepts converts."""

    def test_zero_width_stroke_is_no_line(self):
        for dash in ("", ' stroke-dasharray="4,4"'):
            with self.subTest(dash=dash):
                rect, = converts(self, '<rect x="10" y="10" width="20" height="20" fill="#FF0000" '
                                       f'stroke="#000000" stroke-width="0"{dash}/>')
                ln = rect._element.spPr.find(qn("a:ln"))
                self.assertIsNotNone(ln.find(qn("a:noFill")))
                self.assertIsNone(ln.find(qn("a:custDash")))
                self.assertEqual(clr(rect._element.spPr), ("FF0000", None))
                line, poly, oval = converts(
                    self, f'<line x1="10" y1="60" x2="100" y2="60" stroke="#000" stroke-width="0"{dash} '
                          'marker-end="url(#a)"/>'
                          f'<polyline points="10,70 50,70 50,90" fill="none" stroke="#000" stroke-width="0.0"{dash}/>'
                          f'<circle cx="150" cy="50" r="10" fill="#FF9900" stroke="#000" stroke-width="0"{dash}/>')
                for shape in (line, poly, oval):
                    ln = shape._element.spPr.find(qn("a:ln"))
                    self.assertIsNotNone(ln.find(qn("a:noFill")))
                    self.assertIsNone(ln.find(qn("a:tailEnd")))

    def test_zero_width_stroke_rect_can_be_the_backdrop(self):
        self.assertEqual(kinds('<rect width="200" height="100" fill="#FFFFFF" stroke="#000" stroke-width="0"/>'
                               + TEXT), [("text", None)])

    def test_zero_width_text_stroke_is_no_halo(self):
        self.assertEqual(problems('<text x="20" y="50" font-size="14" stroke="#FFF" stroke-width="0">Hi</text>'), [])

    def test_dash_patterns(self):
        self.assertEqual(svg2pptx.dashes("4,4"), [4, 4])
        self.assertEqual(svg2pptx.dashes(" 5 3 1 "), [5, 3, 1, 5, 3, 1])
        for v in ("", None, "none", "0", "0,0"):  # SVG draws these solid
            with self.subTest(v=v):
                self.assertEqual(svg2pptx.dashes(v), [])
        rect, = converts(self, SHAPE.replace("/>", ' stroke="#000" stroke-dasharray="0 0"/>'))
        self.assertEqual(rect._element.spPr.find(qn("a:ln")).find(qn("a:prstDash")).get("val"), "solid")
        for v in ("-4,4", "nan", "inf", "4px", "a"):
            with self.subTest(v=v):
                found = problems(f'<line x1="0" y1="0" x2="50" y2="0" stroke="#000" stroke-dasharray="{v}"/>')
                self.assertTrue(any(p.startswith("<line>: stroke-dasharray") for p in found), found)

    def test_negative_stroke_width_reported(self):
        found = problems(SHAPE.replace("/>", ' stroke="#000" stroke-width="-1"/>'))
        self.assertTrue(any("stroke-width='-1' is negative" in p for p in found), found)

    def test_short_polylines_left_out(self):
        for pts in ("", " ", "5,5", "5 5 6"):
            with self.subTest(points=pts):
                body = f'<polyline points="{pts}" fill="none" stroke="#000000"/>'
                self.assertEqual(collect(body), [])
                self.assertEqual(converts(self, body), [])
        self.assertEqual(converts(self, '<polyline fill="none" stroke="#000"/>'), [])

    def test_normal_polylines_convert(self):
        two, three = converts(self, '<polyline points="10,10 50,10" fill="none" stroke="#000"/>'
                                    '<polyline points="10,20 50,20 50,60" fill="none" stroke="#000"/>')
        self.assertEqual(two.shape_type.name, "LINE")
        self.assertEqual(three.shape_type.name, "FREEFORM")
        self.assertEqual(len(collect('<polyline points="1,1 2,2 3" fill="none" stroke="#000"/>')[0]["pts"]), 2)

    def test_bad_points_reported(self):
        for pts in ("1,1 2,nan", "1,1 2,x", "1,1 inf,2"):
            with self.subTest(points=pts):
                found = problems(f'<polyline points="{pts}" fill="none" stroke="#000"/>')
                self.assertTrue(any(p.startswith("<polyline>: points=") for p in found), found)

    def test_zero_size_shapes_left_out(self):
        for el in ('<rect x="10" y="10" width="0" height="20" rx="4" fill="#FF0000"/>',
                   '<rect x="10" y="10" width="20" height="0" fill="#FF0000" stroke="#000"/>',
                   '<rect x="10" y="10" fill="#FF0000"/>',
                   '<circle cx="10" cy="10" r="0" fill="#000"/>',
                   '<image href="bundle:service/AWS-Lambda" x="0" y="0" width="0" height="48"/>',
                   '<text x="20" y="50" font-size="0">Hi</text>'):
            with self.subTest(el=el):
                self.assertEqual(collect(el), [])
                self.assertEqual(converts(self, el), [])

    def test_negative_sizes_reported(self):
        for el, attr in (('<rect x="0" y="0" width="-5" height="5"/>', "width"),
                         ('<rect x="0" y="0" width="5" height="5" rx="-2"/>', "rx"),
                         ('<circle cx="5" cy="5" r="-1"/>', "r"),
                         ('<image href="bundle:service/AWS-Lambda" x="0" y="0" width="48" height="-1"/>', "height")):
            with self.subTest(el=el):
                found = problems(el)
                self.assertTrue(any(f"{attr}=" in p and "negative" in p for p in found), found)

    def test_image_without_size_reported(self):
        found = problems('<image href="bundle:service/AWS-Lambda" x="0" y="0"/>')
        self.assertTrue(any("needs width= and height=" in p for p in found), found)

    def test_non_finite_numbers_reported(self):
        for el in ('<rect x="nan" y="0" width="5" height="5"/>', '<rect x="0" y="0" width="inf" height="5"/>',
                   '<line x1="0" y1="0" x2="1e999" y2="0" stroke="#000"/>', '<circle cx="5" cy="5" r="nan"/>',
                   '<text x="nan" y="50" font-size="14">Hi</text>', '<rect x="0" y="0" width="5" height="5" '
                   'stroke="#000" stroke-width="nan"/>', '<rect x="10px" y="0" width="5" height="5"/>'):
            with self.subTest(el=el):
                self.assertTrue(problems(el))

    def test_bad_viewbox_reported(self):
        for view in ("0 0 nan 100", "0 0 inf 100", "nan 0 200 100"):
            with self.subTest(view=view):
                found = svg2pptx.collect(ET.fromstring(svg(SHAPE, view)))[2]
                self.assertTrue(any("viewBox" in p for p in found), found)

    def test_bad_translate_reported(self):
        found = problems(f'<g transform="translate(1.2.3, 4)">{SHAPE}</g>')
        self.assertTrue(any(p.startswith("<g>: translate x=") for p in found), found)
        self.assertEqual(kinds(f'<g transform="translate(5)">{SHAPE}</g>'), [("rect", (25, 20, 40, 30))])

    def test_font_size_out_of_powerpoint_range(self):
        # PowerPoint runs are 1-4000pt: a label that scales outside it converts at the limit
        for view, fs, want in (("0 0 1 1", "14", 400000), ("0 0 20000 10000", "0.5", 100)):
            with self.subTest(view=view, fs=fs):
                body = f'<text x="0.5" y="0.5" font-size="{fs}">Hi</text>'
                root = ET.fromstring(svg(body, view))
                self.assertEqual(svg2pptx.collect(root)[2], [])
                with tempfile.TemporaryDirectory() as d:
                    draft, deck = Path(d) / "t.draft.svg", Path(d) / "t.pptx"
                    draft.write_text(svg(body, view), encoding="utf-8")
                    with redirect_stdout(StringIO()):
                        self.assertTrue(svg2pptx.build([draft], [], deck))
                    box, = Presentation(deck).slides[0].shapes[0].shapes
                    self.assertEqual(int(rpr(box).get("sz")), want)


class Preview(unittest.TestCase):
    """render_pptx.py reads the color alpha back out of the deck."""

    def test_paint(self):
        sf = ET.fromstring('<a:solidFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                           '<a:srgbClr val="FF9900"><a:alpha val="25000"/></a:srgbClr></a:solidFill>')
        self.assertEqual(render_pptx.paint(sf), ("FF9900", 0.25))
        sf.find(qn("a:srgbClr")).remove(sf.find(qn("a:srgbClr"))[0])
        self.assertEqual(render_pptx.paint(sf), ("FF9900", 1.0))

    def test_fill_and_stroke_alpha(self):
        root = preview('<rect x="10" y="10" width="40" height="30" fill="#FF9900" fill-opacity="0.5" '
                       'stroke="#232F3E" stroke-opacity="25%"/>'
                       '<text x="120" y="50" font-size="14" fill="#232F3E" fill-opacity="0.7">Hi</text>')
        rect = drawn(root, "rect")[1]  # [0] is the preview's white slide
        self.assertEqual((rect.get("fill"), rect.get("fill-opacity")), ("#FF9900", "0.5"))
        self.assertEqual((rect.get("stroke"), rect.get("stroke-opacity")), ("#232F3E", "0.25"))
        text, = drawn(root, "text")
        self.assertEqual((text.get("fill"), text.get("fill-opacity")), ("#232F3E", "0.7"))

    def test_marker_per_alpha(self):
        root = preview('<line x1="10" y1="20" x2="100" y2="20" stroke="#232F3E" marker-end="url(#a)"/>'
                       '<line x1="10" y1="40" x2="100" y2="40" stroke="#232F3E" stroke-opacity="0.5" '
                       'marker-end="url(#a)"/>'
                       '<line x1="10" y1="60" x2="100" y2="60" stroke="#232F3E" opacity="0.5" '
                       'marker-end="url(#a)"/>')
        markers = {m.get("id"): m[0].get("fill-opacity") for m in root.iter(f"{svg2pptx.NS}marker")}
        self.assertEqual(markers, {"arr-232F3E-end": None, "arr-232F3E-end-0.5": "0.5"})
        self.assertEqual([l.get("marker-end") for l in drawn(root, "line")],
                         ["url(#arr-232F3E-end)", "url(#arr-232F3E-end-0.5)", "url(#arr-232F3E-end-0.5)"])

    def test_no_fill_text_is_not_drawn_black(self):
        root = preview('<text x="20" y="50" font-size="14" fill="#232F3E" fill-opacity="0">Hi</text>')
        text, = drawn(root, "text")
        self.assertEqual(text.get("fill"), "none")


if __name__ == "__main__":
    unittest.main(verbosity=1)
