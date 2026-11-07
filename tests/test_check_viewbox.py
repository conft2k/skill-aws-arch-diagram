"""check_layout: the canvas is the viewBox as written — its origin, comma or space separated.

    python3 tests/test_check_viewbox.py

A viewBox is four numbers, min-x min-y width height, separated by spaces and/or commas
("0,0,200,100" and "0, 0 200 100" are the same canvas). The canvas runs from
(min-x, min-y) to (min-x + width, min-y + height): a label or connector inside it is on
the canvas whatever the origin, and one past an edge is OFF CANVAS / LINE OFF CANVAS. A
viewBox that is not four finite numbers with a positive width and height is one BAD
VIEWBOX problem (the canvas checks are skipped), not a traceback. Hints and --fix keep the
drawing's own coordinates: nothing is shifted by the origin.
"""
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_layout as CL  # noqa: E402


def svg(view, *parts, bg=True):
    """An SVG with that viewBox (None: no viewBox attribute) and a white background rect
    over the canvas when it parses."""
    attr = "" if view is None else f' viewBox="{view}"'
    back = ""
    if bg and view is not None:
        try:
            x, y, w, h = (float(v) for v in view.replace(",", " ").split())
            back = f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" fill="#FFFFFF"/>'
        except ValueError:
            pass
    return (f'<svg xmlns="http://www.w3.org/2000/svg"{attr}>{back}' + "".join(parts) + "</svg>")


def root(view, *parts, **kw):
    return ET.fromstring(svg(view, *parts, **kw))


TEXT = '<text x="{x}" y="{y}" font-size="14">{s}</text>'
POLY = '<polyline points="{pts}" fill="none" stroke="#232F3E" stroke-width="1.5" marker-end="url(#arrow)"/>'
BOX = '<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#232F3E" stroke-width="2"/>'
TITLE = '<text x="{x}" y="{y}" font-size="14" font-weight="bold" fill="#232F3E">{s}</text>'


def kinds(r, *ks):
    return [i for i in CL.run_checks(r) if i.kind in ks]


def off_canvas(r):
    return [i.msg for i in kinds(r, "OFF CANVAS")]


def line_off(r):
    return [i.msg for i in kinds(r, "LINE OFF CANVAS")]


class BadgeOnCanvas(unittest.TestCase):
    def badge(self, x=50, y=92, **attrs):
        values = {"cx": str(x), "cy": str(y), "r": "10", "fill": "#232F3E", **attrs}
        return ET.tostring(ET.Element("circle", values), encoding="unicode")

    def test_bottom_clipping_with_digit_inside(self):
        r = root("0 0 200 100", self.badge(),
                 '<text x="50" y="96" text-anchor="middle" font-size="12" fill="#FFFFFF">1</text>')
        self.assertEqual(off_canvas(r), [])
        iss, = kinds(r, "BADGE OFF CANVAS")
        self.assertIn("(50,92)", iss.msg)
        self.assertIn("height 100→102", CL.Advisor(r).hint(iss).text)

    def test_each_edge_and_translated_nonzero_origin(self):
        for x, y in ((109, 150), (291, 150), (150, 109), (150, 191)):
            with self.subTest(x=x, y=y):
                r = root("100 100 200 100",
                         '<g transform="translate(100,100)">' + self.badge(x - 100, y - 100) + '</g>')
                self.assertEqual(len(kinds(r, "BADGE OFF CANVAS")), 1)

    def test_stroke_and_exact_fit(self):
        for y, stroke, count in ((90, "none", 0), (90, "#232F3E", 1), (89, "#232F3E", 0)):
            with self.subTest(y=y, stroke=stroke):
                r = root("0 0 200 100", self.badge(y=y, stroke=stroke, **{"stroke-width": "2"}))
                self.assertEqual(len(kinds(r, "BADGE OFF CANVAS")), count)

    def test_unusable_viewbox_skips_badges(self):
        for view in (None, "0 0 200"):
            with self.subTest(view=view):
                self.assertEqual(kinds(root(view, self.badge()), "BADGE OFF CANVAS"), [])


class ParseViewBox(unittest.TestCase):
    def test_space_and_comma_separators(self):
        for view in ("100 100 200 100", "100,100,200,100", "100, 100 200,100", " 100 ,100\t200\n100 ",
                     "1e2 1E2 2e2 1e2", "+100 100 200. 100.0"):
            with self.subTest(view=view):
                self.assertEqual(CL.viewbox(root(view)), ((100.0, 100.0, 200.0, 100.0), None))

    def test_negative_origin(self):
        self.assertEqual(CL.viewbox(root("-300,-100 600 300")), ((-300.0, -100.0, 600.0, 300.0), None))

    def test_no_viewbox(self):
        """No viewBox: no canvas to check against, and no problem."""
        self.assertEqual(CL.viewbox(root(None)), (None, None))

    def test_malformed(self):
        for view, why in (("0 0 200", "4 numbers"), ("0 0 200 100 5", "4 numbers"), ("", "4 numbers"),
                          ("0 0 2OO 100", "'2OO' is not a number"), ("0;0;200;100", "is not a number"),
                          ("0 0 nan 100", "finite"), ("0 0 200 inf", "finite"), ("-inf 0 200 100", "finite"),
                          ("0 0 0 100", "width and height must be positive"),
                          ("0 0 200 -100", "width and height must be positive"),
                          ("0,,0,200,100", "is not a number"), (",0 0 200 100", "is not a number")):
            with self.subTest(view=view):
                box, problem = CL.viewbox(root(view))
                self.assertIsNone(box)
                self.assertIn(why, problem)
                self.assertIn(repr(view), problem)

    def test_collect_returns_the_origin(self):
        self.assertEqual(CL.collect(root("-50 20 400 300"))[4], (-50.0, 20.0, 400.0, 300.0))
        self.assertEqual(CL.collect(root("0 0 400 300"))[4], (0.0, 0.0, 400.0, 300.0))
        self.assertEqual(CL.collect(root(None))[4], (0.0, 0.0, 0.0, 0.0))
        self.assertEqual(CL.collect(root("0 0 400"))[4], (0.0, 0.0, 0.0, 0.0))


class TextOnCanvas(unittest.TestCase):
    """'Hi' at 14px is 15.4px wide; its glyph box runs y - 10.5 .. y + 3.5."""

    def test_inside_a_positive_origin(self):
        """The review's repro: x = 100..300, y = 100..200, 'Hi' at (150,150) is on it."""
        self.assertEqual(off_canvas(root("100 100 200 100", TEXT.format(x=150, y=150, s="Hi"))), [])

    def test_inside_with_commas(self):
        for view in ("100,100,200,100", "100, 100 200 100"):
            with self.subTest(view=view):
                self.assertEqual(off_canvas(root(view, TEXT.format(x=150, y=150, s="Hi"))), [])

    def test_inside_the_zero_canvas_but_left_of_the_origin(self):
        """(50,50) is inside 0..200 × 0..100 but above and left of a canvas that starts at (100,100)."""
        msgs = off_canvas(root("100 100 200 100", TEXT.format(x=50, y=50, s="Hi")))
        self.assertEqual(msgs, ["OFF CANVAS      'Hi' runs past the 200 × 100 canvas at (100,100)"])

    def test_past_each_edge_of_a_positive_origin(self):
        for x, y in ((95, 150), (290, 150), (150, 105), (150, 200)):
            with self.subTest(x=x, y=y):
                self.assertEqual(len(off_canvas(root("100 100 200 100", TEXT.format(x=x, y=y, s="Hi")))), 1)

    def test_negative_origin(self):
        """viewBox -300 -100 600 300: x = -300..300, y = -100..200."""
        view = "-300 -100 600 300"
        self.assertEqual(off_canvas(root(view, TEXT.format(x=-290, y=-80, s="Hi"),
                                         TEXT.format(x=270, y=190, s="Hi"))), [])
        for x, y in ((-305, 0), (290, 0), (0, -95), (0, 199)):
            with self.subTest(x=x, y=y):
                msgs = off_canvas(root(view, TEXT.format(x=x, y=y, s="Hi")))
                self.assertEqual(msgs, ["OFF CANVAS      'Hi' runs past the 600 × 300 canvas at (-300,-100)"])

    def test_zero_origin_message_unchanged(self):
        msgs = off_canvas(root("0 0 200 100", TEXT.format(x=190, y=50, s="Hi")))
        self.assertEqual(msgs, ["OFF CANVAS      'Hi' runs past the 200 × 100 canvas"])

    def test_hint_moves_in_drawing_coordinates(self):
        """Past the right edge (x1 = 305.4 > 300): left 10px to x = 280, or a width of 210;
        past the bottom (y1 = 203.5 > 200): up 8px to y = 192, or a height of 108."""
        r = root("100 100 200 100", TEXT.format(x=290, y=150, s="Hi"))
        adv = CL.Advisor(r)
        iss, = [i for i in adv.issues if i.kind == "OFF CANVAS"]
        h = adv.hint(iss)
        self.assertIn("move text 'Hi' left 10px: x=290→280", h.text)
        self.assertIn("grow the viewBox width 200→210", h.text)
        CL.apply_tree(r, h.edits)
        self.assertEqual(off_canvas(r), [])
        r = root("100 100 200 100", TEXT.format(x=150, y=200, s="Hi"))
        adv = CL.Advisor(r)
        iss, = [i for i in adv.issues if i.kind == "OFF CANVAS"]
        h = adv.hint(iss)
        self.assertIn("move text 'Hi' up 8px: y=200→192", h.text)
        self.assertIn("grow the viewBox height 100→108", h.text)

    def test_hint_left_of_a_negative_origin(self):
        """x0 = -305 < -300: right 9px to x = -296 (4px inside the left edge)."""
        r = root("-300 -100 600 300", TEXT.format(x=-305, y=0, s="Hi"))
        adv = CL.Advisor(r)
        iss, = [i for i in adv.issues if i.kind == "OFF CANVAS"]
        h = adv.hint(iss)
        self.assertIn("move text 'Hi' right 9px: x=-305→-296", h.text)
        self.assertNotIn("grow the viewBox", h.text)
        CL.apply_tree(r, h.edits)
        self.assertEqual(off_canvas(r), [])


class ConnectorOnCanvas(unittest.TestCase):
    """viewBox -100 -50 600 300: x = -100..500, y = -50..250 (test_check_layout's 0 0 600 300
    cases moved by (-100,-50))."""
    VIEW = "-100 -50 600 300"

    def test_inside(self):
        self.assertEqual(line_off(root(self.VIEW, POLY.format(pts="76,54 -96,54 -96,154 76,154"))), [])

    def test_inside_a_positive_origin(self):
        """Every point is past x = 0 and y = 0 of a 0-origin canvas the same size; none past this one."""
        self.assertEqual(line_off(root("1000 500 600 300", POLY.format(pts="1176,604 1004,604 1004,704 1176,704"))),
                         [])

    def test_past_the_left_edge(self):
        msgs = line_off(root(self.VIEW, POLY.format(pts="76,54 -106,54 -106,154 76,154")))
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("LINE OFF CANVAS connector (-106,54)→(-106,154) runs 6px past the left edge of the 600 × 300 "
                      "canvas at (-100,-50)", msgs[0])

    def test_on_the_bottom_edge(self):
        msgs = line_off(root(self.VIEW, POLY.format(pts="76,54 200,54 200,250")))
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("runs on the bottom edge", msgs[0])

    def test_past_the_right_edge_of_a_positive_origin(self):
        msgs = line_off(root("100 100 600 300", POLY.format(pts="300,150 710,150 710,250 300,250")))
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("runs 10px past the right edge of the 600 × 300 canvas at (100,100)", msgs[0])

    def test_comma_viewbox(self):
        self.assertEqual(line_off(root("-100,-50,600,300", POLY.format(pts="76,54 -96,54 -96,154 76,154"))), [])
        self.assertEqual(len(line_off(root("-100,-50,600,300", POLY.format(pts="76,54 -106,54 -106,154 76,154")))),
                         1)

    def test_hint_moves_the_run_to_12px_inside_the_edge(self):
        """The run goes to x = -100 + 12 = -88, written as the polyline's own points."""
        r = root(self.VIEW, POLY.format(pts="76,54 -106,54 -106,154 76,154"))
        adv = CL.Advisor(r)
        iss, = [i for i in adv.issues if i.kind == "LINE OFF CANVAS"]
        h = adv.hint(iss)
        self.assertIn("move the run polyline segment (-106,54)→(-106,154) right 18px to (-88,54)→(-88,154)", h.text)
        self.assertIn("x=-88, 12px inside the left edge of the 600 × 300 canvas at (-100,-50)", h.text)
        CL.apply_tree(r, h.edits)
        self.assertEqual([e.get("points") for e in r.iter() if e.tag.endswith("polyline")],
                         ["76,54 -88,54 -88,154 76,154"])
        self.assertEqual(line_off(r), [])

    def test_grow_hint_is_a_size(self):
        """Past the right edge of x = 100..700 by 10px: the width grows to 600 + 10 + 16."""
        r = root("100 100 600 300", POLY.format(pts="300,150 710,150 710,250 300,250"))
        adv = CL.Advisor(r)
        iss, = [i for i in adv.issues if i.kind == "LINE OFF CANVAS"]
        self.assertIn("grow the viewBox width to 626", adv.hint(iss).text)


class BadViewBox(unittest.TestCase):
    def test_reported_once_not_raised(self):
        for view in ("0 0 200", "0 0 -200 100", "0 0 nan 100", "zero zero 200 100", ""):
            with self.subTest(view=view):
                r = root(view, TEXT.format(x=500, y=500, s="Hi"), POLY.format(pts="0,0 900,0"))
                iss = CL.run_checks(r)
                bad = [i for i in iss if i.kind == "BAD VIEWBOX"]
                self.assertEqual(len(bad), 1, [i.msg for i in iss])
                self.assertTrue(bad[0].msg.startswith("BAD VIEWBOX     viewBox=" + repr(view)), bad[0].msg)
                # no canvas to judge against: the canvas checks are skipped
                self.assertEqual([i for i in iss if i.kind in ("OFF CANVAS", "LINE OFF CANVAS")], [])

    def test_no_viewbox_is_no_problem(self):
        self.assertEqual(kinds(root(None, TEXT.format(x=500, y=500, s="Hi")), "BAD VIEWBOX", "OFF CANVAS"), [])

    def test_run_file_reports_it(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.svg"
            p.write_text(svg("0,0,200", TEXT.format(x=50, y=50, s="Hi")))
            for fix in (False, True):
                with self.subTest(fix=fix):
                    lines, n = CL.run_file(p, fix)
                    self.assertEqual(n, 1, lines)
                    self.assertTrue(any(ln.startswith("BAD VIEWBOX     viewBox='0,0,200'") for ln in lines), lines)
                    self.assertTrue(any("min-x min-y width height" in ln for ln in lines), lines)
            self.assertIn('viewBox="0,0,200"', p.read_text())


class FixKeepsDrawingCoordinates(unittest.TestCase):
    """--fix writes the drawing's own coordinates under a non-zero origin."""

    def drawing(self, view, ox, oy):
        # a box at (ox+50, oy+40) whose title sits 4px low (box.y + 22, not + 18)
        bx, by = ox + 50, oy + 40
        return svg(view, BOX.format(x=bx, y=by, w=400, h=200),
                   TITLE.format(x=bx + CL.K.TITLE_DX_PLAIN, y=by + CL.K.TITLE_DY + 4, s="VPC"),
                   TEXT.format(x=bx + 100, y=by + 120, s="inside"))

    def test_title_offset_fixed_in_place(self):
        for view, ox, oy in (("-300 -200 600 300", -300, -200), ("1000,500,600,300", 1000, 500),
                             ("0 0 600 300", 0, 0)):
            with self.subTest(view=view):
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / "a.svg"
                    p.write_text(self.drawing(view, ox, oy))
                    before, n = CL.run_file(p, False)
                    self.assertEqual(n, 1, before)
                    self.assertTrue(before[0].startswith("TITLE OFFSET"), before)
                    lines, n = CL.run_file(p, True)
                    self.assertEqual(n, 0, lines)
                    self.assertEqual(lines[-1], "Layout OK")
                    out = ET.fromstring(p.read_text())
                    title, = [e for e in out.iter() if e.tag.endswith("text") and e.text == "VPC"]
                    self.assertEqual((title.get("x"), title.get("y")),
                                     (f"{ox + 50 + CL.K.TITLE_DX_PLAIN:g}", f"{oy + 40 + CL.K.TITLE_DY:g}"))
                    other, = [e for e in out.iter() if e.tag.endswith("text") and e.text == "inside"]
                    self.assertEqual((other.get("x"), other.get("y")), (f"{ox + 150:g}", f"{oy + 160:g}"))
                    self.assertEqual(out.get("viewBox"), view)


if __name__ == "__main__":
    unittest.main()
