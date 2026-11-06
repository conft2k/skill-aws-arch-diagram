"""check_layout: a connector label skimmed by another connector's line.

    python3 tests/test_check_layout.py

A connector label sits above its own line (hand drafts as close as 3px) or 8px or more
beside or below it, so a line within 4px of its top or a side is another connector's
(the replication label under the ALB → endpoint line in the ecs-fargate run), while a
line just under its bottom edge is its own.
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


if __name__ == "__main__":
    unittest.main()
