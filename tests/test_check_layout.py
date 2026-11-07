"""check_layout: a connector label skimmed by another connector's line; a connector off the
canvas or out of the box both of its ends are in.

    python3 tests/test_check_layout.py

A connector label sits above its own line (hand drafts as close as 3px) or 8px or more
beside or below it, so a line within 4px of its top or a side is another connector's
(the replication label under the ALB → endpoint line in the ecs-fargate run), while a
line just under its bottom edge is its own.

A connector whose ends are both inside one box (the AWS Cloud, a Region, a VPC) stays in
it: a route out past its border and back in is a detour (LINE LEAVES BOX), and any route
past the canvas edge is cut off in the render (LINE OFF CANVAS). A line between nodes in
different boxes, one ending at a gateway on the border, and a bracket whose stem leads
out of the box are not detours.
"""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_layout as CL  # noqa: E402


def svg(*parts):
    body = "\n".join(parts)
    return ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 300">'
                         f'<rect x="0" y="0" width="600" height="300" fill="#FFFFFF"/>{body}</svg>')


LINE = '<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#232F3E" stroke-width="1.5"/>'
TEXT = '<text x="{x}" y="{y}" font-size="12" text-anchor="{a}" fill="#545B64">{s}</text>'


def near(root):
    return [i.msg for i in CL.run_checks(root) if i.msg.startswith("LINE NEAR TEXT")]


class ConnectorLabelNearLine(unittest.TestCase):
    def setUp(self):
        # A vertical connector at x=300 and its label 10px to the left (anchor end).
        self.own = LINE.format(x1=300, y1=60, x2=300, y2=240)

    def test_line_over_the_top(self):
        """The label's glyph top (y - 9) 2px under a horizontal connector: flagged."""
        msgs = near(svg(self.own, LINE.format(x1=100, y1=154, x2=500, y2=154),
                        TEXT.format(x=290, y=165, a="end", s="replication")))
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("'replication'", msgs[0])

    def test_line_clear_of_the_top(self):
        msgs = near(svg(self.own, LINE.format(x1=100, y1=154, x2=500, y2=154),
                        TEXT.format(x=290, y=168, a="end", s="replication")))
        self.assertEqual(msgs, [])

    def test_line_beside(self):
        """A vertical connector 2px left of the label box (x0 = 217.4): flagged."""
        msgs = near(svg(self.own, LINE.format(x1=215.4, y1=60, x2=215.4, y2=240),
                        TEXT.format(x=290, y=165, a="end", s="replication")))
        self.assertEqual(len(msgs), 1, msgs)

    def test_own_line_just_below(self):
        """A label 6px above its own horizontal line (bottom edge 3px above it): not flagged."""
        msgs = near(svg(LINE.format(x1=100, y1=154, x2=500, y2=154),
                        TEXT.format(x=300, y=148, a="middle", s="HTTPS :443")))
        self.assertEqual(msgs, [])


ICON = '<image href="bundle:service/AWS-Lambda" x="{x}" y="{y}" width="48" height="48"/>'
POLY = '<polyline points="{pts}" fill="none" stroke="#232F3E" stroke-width="1.5" marker-end="url(#arrow)"/>'
BOX = '<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#232F3E" stroke-width="2"/>'
TITLE = '<text x="{x}" y="{y}" font-size="14" font-weight="bold" fill="#232F3E">{s}</text>'
# A box (100,40)–(500,260) titled "AWS Cloud" with two nodes inside it: a at (180,80), b at (180,180).
CLOUD = (BOX.format(x=100, y=40, w=400, h=220), TITLE.format(x=112, y=58, s="AWS Cloud"),
         ICON.format(x=180, y=80), ICON.format(x=180, y=180))


def detours(root, kinds=("LINE OFF CANVAS", "LINE LEAVES BOX")):
    return [i for i in CL.run_checks(root) if i.kind in kinds]


class ConnectorOffCanvas(unittest.TestCase):
    def test_past_the_left_edge(self):
        msgs = [i.msg for i in detours(svg(POLY.format(pts="176,104 -6,104 -6,204 176,204")))]
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("LINE OFF CANVAS connector (-6,104)→(-6,204) runs 6px past the left edge of the 600 × 300 "
                      "canvas", msgs[0])

    def test_on_the_edge(self):
        msgs = [i.msg for i in detours(svg(POLY.format(pts="176,104 300,104 300,300")))]
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("runs on the bottom edge", msgs[0])

    def test_inside(self):
        self.assertEqual(detours(svg(POLY.format(pts="176,104 4,104 4,204 176,204"))), [])

    def test_fix_moves_the_outer_run_in(self):
        root = svg(POLY.format(pts="176,104 -6,104 -6,204 176,204"))
        adv = CL.Advisor(root)
        iss, = [i for i in adv.issues if i.kind == "LINE OFF CANVAS"]
        h = adv.hint(iss)
        self.assertIn("move the run polyline segment (-6,104)→(-6,204) right 18px to (12,104)→(12,204)", h.text)
        CL.apply_tree(root, h.edits)
        self.assertEqual(detours(root), [])


class ConnectorLeavesBox(unittest.TestCase):
    def test_detour_past_the_border(self):
        """a → b out past the Cloud's right border and back in: flagged, named by its title."""
        iss = detours(svg(*CLOUD, POLY.format(pts="232,104 540,104 540,204 232,204")))
        self.assertEqual([i.kind for i in iss], ["LINE LEAVES BOX"])
        self.assertIn("connector (540,104)→(540,204) runs 40px out past the right border of 'AWS Cloud' "
                      "(100,40 400×220) and back in — both of its ends are inside that box", iss[0].msg)

    def test_fix_brings_the_run_inside(self):
        root = svg(*CLOUD, POLY.format(pts="232,104 540,104 540,204 232,204"))
        adv = CL.Advisor(root)
        iss, = [i for i in adv.issues if i.kind == "LINE LEAVES BOX"]
        h = adv.hint(iss)
        self.assertIn("move the run polyline segment (540,104)→(540,204) left 52px to (488,104)→(488,204)", h.text)
        self.assertIn("12px inside the right border of rect 'AWS Cloud'", h.text)
        CL.apply_tree(root, h.edits)
        self.assertEqual(detours(root), [])

    def test_route_inside(self):
        self.assertEqual(detours(svg(*CLOUD, POLY.format(pts="232,104 300,104 300,204 232,204"))), [])

    def test_line_to_a_node_outside_crosses_on_purpose(self):
        """b inside the Cloud → a node right of it: the line crosses the border, not a detour."""
        self.assertEqual(detours(svg(*CLOUD, ICON.format(x=530, y=180),
                                     POLY.format(pts="232,204 380,204 380,120 520,120 520,176"))), [])

    def test_gateway_on_the_border(self):
        """An end at a gateway sitting across the border belongs to both sides of it."""
        gw = ('<image href="bundle:resource/Amazon-VPC_Internet-Gateway" x="476" y="120" width="48" '
              'height="48"/>', '<rect x="476" y="120" width="48" height="48" fill="#FFFFFF"/>')
        self.assertEqual(detours(svg(*CLOUD, gw[1], gw[0],
                                     POLY.format(pts="490,116 490,20 206,20 206,76"))), [])

    def test_bracket_stem_leads_out(self):
        """A bracket gathering a and b with its bar outside the box and a stem to a node
        outside it: a net whose ends are not all in the box."""
        bar = '<polyline points="232,104 520,104 520,204 232,204" fill="none" stroke="#232F3E" stroke-width="1.5"/>'
        stem = LINE.format(x1=520, y1=154, x2=540, y2=154)
        self.assertEqual(detours(svg(*CLOUD, ICON.format(x=544, y=130), bar, stem)), [])

    def test_two_edges_out_of_one_node(self):
        """Two edges leaving a at the same point are two edges, not a net joined there: a → b
        is a detour although a's other edge goes to a node left of the box."""
        out = ICON.format(x=20, y=230)
        iss = detours(svg(*CLOUD, out, POLY.format(pts="176,104 80,104 80,204 176,204"),
                          POLY.format(pts="176,104 80,104 80,140 44,140 44,226")))
        self.assertEqual([(i.kind, CL.fmt(i.ctx["s"])) for i in iss], [("LINE LEAVES BOX", "(80,104)→(80,204)")],
                         [i.msg for i in iss])


if __name__ == "__main__":
    unittest.main()
