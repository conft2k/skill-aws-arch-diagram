#!/usr/bin/env python3
"""Tests of scripts/svg2pptx.py: which full-canvas background rect collect() leaves to the slide.

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

import svg2pptx  # noqa: E402
from pptx import Presentation  # noqa: E402

TEXT = '<text x="20" y="50" font-size="14" fill="#FFFFFF">Hello</text>'
SHAPE = '<rect x="20" y="20" width="40" height="30" fill="#FF9900"/>'


def svg(body, view="0 0 200 100"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}">{body}</svg>'


def kinds(body, view="0 0 200 100"):
    _, items, problems = svg2pptx.collect(ET.fromstring(svg(body, view)))
    assert problems == [], problems
    return [(it["k"], it["box"]) if it["k"] == "rect" else (it["k"], None) for it in items]


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
        for attrs in ('fill="#FFFFFF" stroke="#232F3E"', 'fill="#FFFFFF" opacity="0.5"',
                      'fill="#FFFFFF" fill-opacity="0.5"', 'fill="#F2F2F2"'):
            with self.subTest(attrs=attrs):
                self.assertEqual(kinds(f'<rect width="200" height="100" {attrs}/>' + TEXT),
                                 [("rect", (0, 0, 200, 100)), ("text", None)])

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
                first = next(el for el in root.iter() if el.tag in (svg2pptx.NS + "rect", svg2pptx.NS + "text",
                                                                      svg2pptx.NS + "image", svg2pptx.NS + "line"))
                self.assertEqual((first.tag, first.get("fill")), (svg2pptx.NS + "rect", "#FFFFFF"))
                (_, _, vw, vh), items, problems = svg2pptx.collect(root)
                self.assertEqual(problems, [])
                self.assertFalse(any(it["k"] == "rect" and it["box"] == (0, 0, vw, vh) for it in items))
                drawn = sum(1 for el in root.iter() if el.tag in (svg2pptx.NS + "rect", svg2pptx.NS + "image",
                                                                    svg2pptx.NS + "line", svg2pptx.NS + "polyline",
                                                                    svg2pptx.NS + "circle"))
                self.assertEqual(sum(1 for it in items if it["k"] != "text"), drawn - 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
