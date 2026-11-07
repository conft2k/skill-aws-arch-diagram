#!/usr/bin/env python3
"""Tests of scripts/svg2pptx.py: which full-canvas background rect collect() leaves to the slide,
and how opacity / fill-opacity / stroke-opacity reach the PPTX as color alpha.

    python3 tests/test_svg2pptx.py
"""
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import svg2pptx  # noqa: E402
    from pptx import Presentation  # noqa: E402
    from pptx.oxml.ns import qn  # noqa: E402
except ImportError as err:  # python-pptx / cairosvg not installed: skip, like test_examples' export column
    raise unittest.SkipTest(f"needs python-pptx and cairosvg ({err})")

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


def deck_shapes(body):
    """Build a one-slide deck from `body`; return the shapes inside the diagram group."""
    with tempfile.TemporaryDirectory() as d:
        draft, deck = Path(d) / "t.draft.svg", Path(d) / "t.pptx"
        draft.write_text(svg(body), encoding="utf-8")
        with redirect_stdout(StringIO()):
            assert svg2pptx.build([draft], [], deck)
        return list(Presentation(deck).slides[0].shapes[0].shapes)


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


if __name__ == "__main__":
    unittest.main(verbosity=1)
