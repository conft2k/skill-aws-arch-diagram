#!/usr/bin/env python3
"""scripts/rules.py: each rule's predicate on a small draft that keeps it and one that breaks
it (the breaking one names the owner), plus the route-table goldens of the examples.

    python3 tests/test_rules.py

The flow, label and route-table predicates read the draft, so most cases are hand-written
SVG in layout.py's shape (<g id="edge:n"> runs with data-flow, <g id="node:id">,
<g id="group:id">) with just the spec items the predicate reads. R-twin reads the solved
geometry, so its cases build a spec and move one twin's node.
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import layout  # noqa: E402
import layout_const as K  # noqa: E402
import layout_model as M  # noqa: E402
import layout_spec  # noqa: E402
import rules  # noqa: E402

SPECS = ROOT / "docs" / "examples" / "specs"
ICON = "service/Amazon-EC2"
RT = "resource/Amazon-Route-53_Route-Table"


def svg(*parts, w=800, h=600):
    body = "\n".join(parts)
    return (f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
            f'<rect width="{w}" height="{h}" fill="#FFFFFF"/>{body}</svg>').encode()


def node(nid, x, y, label=None, icon=ICON):
    t = f'<text x="{x + 24}" y="{y + 66}" font-size="14" text-anchor="middle" fill="#232F3E">{label}</text>' \
        if label else ""
    return f'<g id="node:{nid}"><image href="bundle:{icon}" x="{x}" y="{y}" width="48" height="48"/>{t}</g>'


def group(gid, x, y, w, h):
    return f'<g id="group:{gid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#8C4FFF" ' \
           f'stroke-width="2"/></g>'


def edge(n, pts, flow=None, end=True, start=False):
    p = " ".join(f"{x},{y}" for x, y in pts)
    heads = (' marker-end="url(#arrow)"' if end else "") + (' marker-start="url(#arrowStart)"' if start else "")
    return (f'<g id="edge:{n}"><polyline points="{p}" fill="none" stroke="#232F3E" stroke-width="1.5"{heads} '
            f'data-flow="{flow if flow is not None else f"{n}.0"}"/></g>')


def label(n, x, y, s="HTTPS", part="label"):
    return f'<g id="edge:{n}:{part}"><text x="{x}" y="{y}" font-size="12" text-anchor="middle" ' \
           f'fill="#232F3E">{s}</text></g>'


def badge(n, cx, cy, digit):
    return (f'<g id="edge:{n}:badge"><circle cx="{cx}" cy="{cy}" r="10" fill="#232F3E"/>'
            f'<text x="{cx}" y="{cy + 4}" font-size="12" text-anchor="middle" fill="#FFFFFF" '
            f'font-weight="700">{digit}</text></g>')


def spec(edges=(), nodes=(), groups=(), steps=0, mode="document"):
    s = M.Spec(name="t", mode=mode)
    for n, (a, b, *kind) in enumerate(edges):
        s.edges.append(M.Edge(n=n, a=a, b=b, op="->", a_kind=kind[0] if kind else "node",
                              b_kind=kind[1] if len(kind) > 1 else "node", line=n))
    for nid in nodes:
        s.nodes[nid] = M.Node(id=nid, icon=ICON, label=nid)
    for gid, typ in groups:
        s.groups[gid] = M.Group(id=gid, type=typ, label=None)
    if steps:
        s.note = M.NoteSpec(steps=[(f"hop {k}", "") for k in range(steps)])
    return s


def codes(viol, code):
    return [v for v in viol if v.code == code]


class FlowRules(unittest.TestCase):
    def run_flow(self, sp, *parts):
        return rules.flow_rules(sp, rules.Drawn.parse(svg(*parts)))

    def test_f0_diagonal(self):
        sp = spec(edges=[("a", "b")], nodes=["a", "b"])
        bad = self.run_flow(sp, node("a", 100, 100), node("b", 400, 300), edge(0, [(152, 124), (396, 324)]))
        self.assertEqual([v.owners for v in codes(bad, "F0")], [("edge:0",)])
        good = self.run_flow(sp, node("a", 100, 100), node("b", 400, 300),
                             edge(0, [(152, 124), (300, 124), (300, 324), (396, 324)]))
        self.assertEqual(codes(good, "F0"), [])

    def test_f1_on_line(self):
        sp = spec(edges=[("a", "b"), ("c", "d")], nodes="abcd")
        parts = [node("a", 50, 100), node("b", 450, 100), node("c", 50, 300), node("d", 450, 300)]
        bad = self.run_flow(sp, *parts, edge(0, [(102, 124), (250, 124), (250, 200), (446, 200), (446, 124)]),
                            edge(1, [(102, 324), (250, 324), (250, 200), (446, 200), (446, 324)]))
        self.assertTrue(any(set(v.owners) == {"edge:0", "edge:1"} for v in codes(bad, "F1")))
        good = self.run_flow(sp, *parts, edge(0, [(102, 124), (250, 124), (250, 188), (420, 188), (420, 124)]),
                             edge(1, [(102, 324), (262, 324), (262, 212), (430, 212), (430, 324)]))
        self.assertEqual(codes(good, "F1"), [])

    def test_f2_in_line(self):
        sp = spec(edges=[("a", "b"), ("a", "c")], nodes="abc")
        parts = [node("a", 300, 100), node("b", 50, 300), node("c", 550, 300)]
        bad = self.run_flow(sp, *parts, edge(0, [(318, 152), (318, 200), (74, 200), (74, 296)]),
                            edge(1, [(330, 152), (330, 200), (574, 200), (574, 296)]))
        self.assertTrue(any(set(v.owners) == {"edge:0", "edge:1"} for v in codes(bad, "F2")))
        good = self.run_flow(sp, *parts, edge(0, [(318, 152), (318, 200), (74, 200), (74, 296)]),
                             edge(1, [(330, 152), (330, 240), (574, 240), (574, 296)]))
        self.assertEqual(codes(good, "F2"), [])

    def test_f3_crossing_at_a_bend(self):
        sp = spec(edges=[("a", "b"), ("c", "d")], nodes="abcd")
        parts = [node("a", 50, 100), node("b", 450, 300), node("c", 50, 400), node("d", 450, 20)]
        # edge 0 turns down at x 300; edge 1's horizontal crosses its vertical 8px below the bend
        bad = self.run_flow(sp, *parts, edge(0, [(102, 124), (300, 124), (300, 324), (446, 324)]),
                            edge(1, [(102, 424), (200, 424), (200, 132), (380, 132), (380, 72), (446, 44)]))
        hit = codes(bad, "F3")
        self.assertEqual([set(v.owners) for v in hit], [{"edge:0", "edge:1"}])
        good = self.run_flow(sp, *parts, edge(0, [(102, 124), (300, 124), (300, 324), (446, 324)]),
                             edge(1, [(102, 424), (200, 424), (200, 220), (380, 220), (380, 44), (446, 44)]))
        self.assertEqual(codes(good, "F3"), [])

    def test_f4_arrow_target(self):
        sp = spec(edges=[("a", "b")], nodes="abc")
        parts = [node("a", 50, 100), node("b", 400, 100), node("c", 400, 300)]
        bad = self.run_flow(sp, *parts, edge(0, [(102, 124), (300, 124), (300, 324), (396, 324)]))
        self.assertEqual([v.owners for v in codes(bad, "F4")], [("edge:0", "node:b")])
        good = self.run_flow(sp, *parts, edge(0, [(102, 124), (396, 124)]))
        self.assertEqual(codes(good, "F4"), [])

    def test_f4_group_end(self):
        sp = spec(edges=[("a", "v", "node", "group")], nodes="a", groups=[("v", "vpc")])
        parts = [node("a", 50, 100), group("v", 300, 50, 200, 200)]
        self.assertEqual(codes(self.run_flow(sp, *parts, edge(0, [(102, 124), (296, 124)])), "F4"), [])
        bad = self.run_flow(sp, *parts, edge(0, [(102, 124), (280, 124)]))
        self.assertEqual([v.owners for v in codes(bad, "F4")], [("edge:0", "group:v")])

    def test_f5_label_attribution(self):
        sp = spec(edges=[("a", "b"), ("c", "d")], nodes="abcd")
        # two lines 22px apart (edge 1 passes under edge 0 between other nodes)
        parts = [node("a", 50, 100), node("b", 450, 100), node("c", 50, 300), node("d", 450, 300),
                 edge(0, [(102, 124), (446, 124)]), edge(1, [(74, 296), (74, 146), (474, 146), (474, 296)])]
        good = self.run_flow(sp, *parts, label(0, 270, 118))
        self.assertEqual(codes(good, "F5"), [])
        # edge 0's label under its line, right above edge 1's: nearer edge 1
        bad = self.run_flow(sp, *parts, label(0, 270, 141))
        self.assertTrue(any(v.owners == ("edge:0", "edge:1") for v in codes(bad, "F5")))
        far = self.run_flow(sp, *parts, label(0, 270, 60))
        self.assertEqual([v.owners for v in codes(far, "F5")], [("edge:0",)])

    def test_f5_spec_placed_label_and_badge_exempt_user_decision(self):
        # user decision 2026-11-07 (rules-design §6): label_at / step_at at a point exempts
        # them from F5 as from L1; the router's own placements stay judged
        sp = spec(edges=[("a", "b")], nodes="ab")
        parts = [node("a", 50, 100), node("b", 450, 100), edge(0, [(102, 124), (446, 124)]),
                 label(0, 270, 60), badge(0, 200, 60, 1)]
        self.assertEqual([v.owners for v in codes(self.run_flow(sp, *parts), "F5")], [("edge:0",), ("edge:0",)])
        sp.edges[0].label_at = M.Place(M.Expr("num", offset=270), M.Expr("num", offset=60))
        sp.edges[0].step_at = M.Place(M.Expr("num", offset=200), M.Expr("num", offset=60))
        self.assertEqual(codes(self.run_flow(sp, *parts), "F5"), [])

    def test_f5_tie_names_the_other_line(self):
        # review repro: edge 0's label 7px from both lines names edge 1, not edge 0 twice
        sp = spec(edges=[("a", "b"), ("c", "d")], nodes="abcd")
        out = self.run_flow(sp, edge(0, [(100, 200), (500, 200)], end=False),
                            edge(1, [(100, 174), (500, 174)], end=False), label(0, 300, 190, s="X"))
        self.assertEqual([v.owners for v in codes(out, "F5")], [("edge:0", "edge:1")])

    def test_f3_measures_to_the_icon_not_its_caption(self):
        # review repro: the crossing is 22 / 30px from the end icons; only the right node's
        # long caption comes within 12px of it
        sp = spec(edges=[("a", "b"), ("c", "d")], nodes="abcd")
        parts = [node("a", 0, 100), node("b", 100, 100, label="a very long caption under b"),
                 edge(0, [(52, 124), (96, 124)]), edge(1, [(70, 52), (70, 141)])]
        self.assertEqual(codes(self.run_flow(sp, *parts), "F3"), [])


class LabelRules(unittest.TestCase):
    def run_label(self, sp, *parts):
        return rules.label_rules(sp, rules.Drawn.parse(svg(*parts)))

    def test_l1_side(self):
        sp = spec(edges=[("a", "b"), ("c", "d")], nodes="abcd")
        parts = [node("a", 50, 100), node("b", 450, 100), node("c", 50, 300), node("d", 50, 500),
                 edge(0, [(102, 124), (446, 124)]), edge(1, [(74, 352), (74, 496)])]
        good = self.run_label(sp, *parts, label(0, 270, 118), label(1, 110, 430))
        self.assertEqual(codes(good, "L1"), [])
        bad = self.run_label(sp, *parts, label(0, 270, 140), label(1, 40, 430))
        self.assertEqual(sorted(v.owners for v in codes(bad, "L1")), [("edge:0",), ("edge:1",)])
        sp.edges[0].label_at = "below"          # asked for: not judged
        self.assertEqual([v.owners for v in codes(self.run_label(sp, *parts, label(0, 270, 140),
                                                                 label(1, 110, 430)), "L1")], [])

    def test_l1_corner_any_nearby_piece_user_decision(self):
        # user decision 2026-11-07 (rules-design §6), latest2-egress edge:8: above the
        # horizontal piece, 5.15px left of the vertical one it turns up into (nearer than the
        # horizontal's 6px) — on the rule side of one of the pieces it sits by: passes
        sp = spec(edges=[("a", "b")], nodes="ab")
        parts = [node("a", 50, 533), node("b", 860, 384), edge(0, [(102, 557), (717.5, 557), (717.5, 408), (856, 408)])]
        self.assertEqual(codes(self.run_label(sp, *parts, label(0, 666.15, 548, s="appliance mode")), "L1"), [])
        # below the horizontal piece and left of the vertical one: on the rule side of neither
        bad = self.run_label(sp, *parts, label(0, 666.15, 572, s="appliance mode"))
        self.assertEqual([v.owners for v in codes(bad, "L1")], [("edge:0",)])

    def test_l1_on_line_over_background(self):
        sp = spec(edges=[("a", "b")], nodes="ab")
        parts = [node("a", 50, 100), node("b", 450, 100), edge(0, [(102, 124), (446, 124)])]
        self.assertEqual(codes(self.run_label(sp, *parts, label(0, 270, 128, part="masked")), "L1"), [])
        bad = self.run_label(sp, *parts, label(0, 270, 170, part="masked"))
        self.assertEqual([v.owners for v in codes(bad, "L1")], [("edge:0",)])

    def test_l2_badges_match_steps(self):
        sp = spec(edges=[("a", "b"), ("b", "c")], nodes="abc", steps=2)
        sp.edges[0].step, sp.edges[1].step = 1, 2
        parts = [node("a", 50, 100), node("b", 250, 100), node("c", 450, 100),
                 edge(0, [(102, 124), (246, 124)]), edge(1, [(302, 124), (446, 124)])]
        good = self.run_label(sp, *parts, badge(0, 170, 110, 1), badge(1, 370, 110, 2))
        self.assertEqual(codes(good, "L2"), [])
        bad = self.run_label(sp, *parts, badge(0, 170, 110, 1), badge(1, 370, 110, 1))
        hit = codes(bad, "L2")
        self.assertEqual(len(hit), 1)
        self.assertIn("edge:1", hit[0].owners)


class FitRules(unittest.TestCase):
    CIDR = '<text x="40" y="40" font-size="12" fill="#232F3E">10.0.0.0/16</text>'

    def test_slide_points(self):
        small = rules.fit_rules(spec(mode="slide"), rules.Drawn.parse(svg(self.CIDR, w=1000, h=500)))
        self.assertEqual(small, [])
        big = rules.fit_rules(spec(mode="slide"), rules.Drawn.parse(svg(self.CIDR, w=2000, h=1000)))
        self.assertEqual([(v.rule, v.tier) for v in big], [("R-fit", rules.TIER_FIT)])
        self.assertGreater(big[0].cost, 0)
        self.assertEqual(rules.fit_rules(spec(), rules.Drawn.parse(svg(self.CIDR, w=2000, h=1000))), [])

    def test_the_smallest_text_drawn_sets_the_points(self):
        """R-fit weighs the smallest text the draft draws, at the size svg2pptx gives it: a
        674 × 550 titled slide takes 14px to 11.45pt (fits) and 12px to 9.82pt (short)."""
        sp = spec(mode="slide")
        fourteen = node("a", 100, 100, label="EC2")
        self.assertEqual(rules.fit_rules(sp, rules.Drawn.parse(svg(fourteen, w=674, h=550))), [])
        short = rules.fit_rules(sp, rules.Drawn.parse(svg(fourteen, self.CIDR, w=674, h=550)))
        self.assertEqual([v.rule for v in short], ["R-fit"])
        self.assertIn("smallest text (12px, '10.0.0.0/16') comes out at 9.82pt", short[0].message)
        self.assertAlmostEqual(short[0].cost, K.SLIDE_MIN_PT - 12 * 450 / 550, places=6)
        self.assertEqual(rules.fit_rules(sp, rules.Drawn.parse(svg(w=2000, h=1000))), [])   # no text at all

    def test_undrawn_text_is_not_weighed(self):
        """A <title> / <desc> (svg2pptx leaves them out) or a text in <defs> is not the slide's
        smallest text: only 'Visible' (14px on 300 × 300, 21pt) counts, no R-fit."""
        sp = spec(mode="slide")
        visible = '<text x="40" y="60" font-size="14">Visible</text>'
        for hidden in ('<text x="10" y="20" font-size="1"><title>tooltip</title></text>',
                       '<text x="10" y="20" font-size="1"><desc>about</desc></text>',
                       '<defs><text x="10" y="20" font-size="1">defs</text></defs>'):
            with self.subTest(hidden=hidden):
                self.assertEqual(rules.fit_rules(sp, rules.Drawn.parse(svg(hidden, visible, w=300, h=300))), [])
        self.assertEqual(len(rules.fit_rules(sp, rules.Drawn.parse(
            svg('<text x="10" y="20" font-size="1">drawn</text>', visible, w=300, h=300)))), 1)


class RouteTableRules(unittest.TestCase):
    def rt_spec(self, ends, edges, extra_nodes=(), hub="tgw", groups=()):
        sp = spec(edges=edges, nodes=["tgw", "rt", *extra_nodes], groups=groups)
        sp.nodes["rt"].icon = RT
        sp.nodes["rt"].assoc = M.Assoc(hub=hub, ends=list(ends),
                                       edges=[e.n for e in sp.edges if hub and {e.a, e.b} & {hub}
                                              and ({e.a, e.b} - {hub}) <= set(ends)])
        return sp

    def run_rt(self, sp, *parts):
        return rules.rt_rules(sp, rules.Drawn.parse(svg(*parts)))

    def bracket_parts(self, rt_x, rt_y):
        # hub at (400, 300); a and b up-left and down-left, c to the right (not associated)
        return [node("tgw", 376, 276), node("a", 100, 100), node("b", 100, 452), node("c", 650, 276),
                node("rt", rt_x - 24, rt_y - 24, icon=RT),
                edge(0, [(372, 292), (250, 292), (250, 124), (152, 124)], flow="0.0"),
                edge(1, [(372, 308), (250, 308), (250, 476), (152, 476)], flow="1.0"),
                edge(2, [(428, 300), (646, 300)], flow="2.0")]

    def test_rt1_bracket(self):
        sp = self.rt_spec(["a", "b"], [("tgw", "a"), ("tgw", "b"), ("tgw", "c")], "abc")
        self.assertEqual(self.run_rt(sp, *self.bracket_parts(200, 300)), [])
        bad = self.run_rt(sp, *self.bracket_parts(520, 200))
        self.assertIn(("node:rt", "node:tgw"), [v.owners for v in codes(bad, "RT1")])

    def test_rt1_hub_only_table_beside_hub_passes_user_decision(self):
        # user decision 2026-11-07 (rules-design §6): every line at the hub associated (its
        # only table) passes within S + sibling_gap of the hub, bracket or not
        sp = self.rt_spec(["a", "b"], [("tgw", "a"), ("tgw", "b")], "ab")
        parts = lambda x, y: [p for p in self.bracket_parts(x, y) if 'id="edge:2"' not in p and 'id="node:c"' not in p]
        self.assertEqual(codes(self.run_rt(sp, *parts(480, 300)), "RT1"), [])       # right of the hub: no bracket
        far = self.run_rt(sp, *parts(700, 300))
        self.assertEqual([v.owners for v in codes(far, "RT1")], [("node:rt", "node:tgw")])
        # with a line at the hub that is not its own, the bracket is needed again
        sp3 = self.rt_spec(["a", "b"], [("tgw", "a"), ("tgw", "b"), ("tgw", "c")], "abc")
        self.assertEqual([v.owners for v in codes(self.run_rt(sp3, *self.bracket_parts(400, 220)), "RT1")],
                         [("node:rt", "node:tgw")])

    def test_rt2_single_line(self):
        sp = self.rt_spec(["c"], [("tgw", "a"), ("tgw", "b"), ("tgw", "c")], "abc")
        self.assertEqual(codes(self.run_rt(sp, *self.bracket_parts(530, 360)), "RT2"), [])
        bad = self.run_rt(sp, *self.bracket_parts(530, 540))
        self.assertEqual([v.owners for v in codes(bad, "RT2")], [("node:rt", "edge:2")])

    def test_rt2_reach_two_icons_user_decision(self):
        # user decision 2026-11-07 (rules-design §6, rt2.png): a one-line table passes within
        # 2S + sibling_gap of its line — document 2·48 + 16 = 112, slide 2·48 + 12 = 108
        for mode, reach in (("document", 112), ("slide", 108)):
            with self.subTest(mode=mode):
                sp = self.rt_spec(["c"], [("tgw", "a"), ("tgw", "b"), ("tgw", "c")], "abc")
                sp.mode = mode
                self.assertEqual(rules.rt2_reach(sp), reach)
                # edge 2 runs along y = 300; the table's footprint top `gap` below it
                at = lambda gap: self.run_rt(sp, *self.bracket_parts(530, 300 + gap + 24))
                self.assertEqual(codes(at(reach), "RT2"), [])
                over = codes(at(reach + 0.01), "RT2")
                self.assertEqual([v.owners for v in over], [("node:rt", "edge:2")])
                self.assertAlmostEqual(over[0].cost, 0.01, places=3)

    def test_rt3_rt4_lines_and_rivals_in_the_way(self):
        sp = self.rt_spec(["a", "b"], [("tgw", "a"), ("tgw", "b"), ("tgw", "c")], "abc")
        # right of the hub past edge 2's end object: crosses nothing but sits nearer c than the hub
        bad = self.run_rt(sp, *self.bracket_parts(740, 300))
        self.assertTrue(codes(bad, "RT4"))
        self.assertIn("node:c", codes(bad, "RT4")[0].owners)
        # below edge 2 with a line of c in the way: the way to the hub crosses it
        parts = self.bracket_parts(520, 340)
        sp3 = self.rt_spec(["a", "b"], [("tgw", "a"), ("tgw", "b"), ("tgw", "c"), ("tgw", "c")], "abc")
        parts.append(edge(3, [(400, 332), (400, 320), (480, 320), (480, 372), (674, 372), (674, 328)], flow="3.0"))
        hit = codes(self.run_rt(sp3, *parts), "RT3")
        self.assertTrue(hit and "edge:3" in hit[0].owners)
        self.assertEqual(codes(self.run_rt(sp, *self.bracket_parts(200, 300)), "RT3"), [])

    def test_rt5_subnet_table(self):
        sp = spec(nodes=["rt"], groups=[("sn1", "private"), ("sn2", "private")])
        sp.nodes["rt"].assoc = M.Assoc(hub=None, ends=["sn1"], edges=[])
        parts = [group("sn1", 50, 50, 200, 150), group("sn2", 300, 50, 200, 150)]
        self.assertEqual(self.run_rt(sp, *parts, node("rt", 100, 100, icon=RT)), [])
        inside = self.run_rt(sp, *parts, node("rt", 350, 100, icon=RT))
        self.assertEqual([v.owners for v in codes(inside, "RT5")], [("node:rt", "group:sn2")])
        between = self.run_rt(sp, *parts, node("rt", 250, 230, icon=RT))
        self.assertTrue(codes(between, "RT5"))


def subnet(gid, x, y, w, h, title="App subnet"):
    """A private subnet as layout.py draws it: border, badge at the top-left corner, title
    at x + 32 on the header row (baseline y + 18)."""
    return (f'<g id="group:{gid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#00A4A6" '
            f'stroke-width="1.5"/><image href="bundle:group/Private-subnet_32" x="{x}" y="{y}" width="24" '
            f'height="24"/><text x="{x + 32}" y="{y + 18}" font-size="14" fill="#00A4A6" font-weight="600">'
            f'{title}</text></g>')


def bands(*parts):
    d = rules.Drawn.parse(svg(*parts))
    return rules.CL.header_bands(d.rects, d.icons, d.texts, d.owner)


class BorderRules(unittest.TestCase):
    """R-border (user decision 2026-11-07, rules-design §6, hug.png)."""

    def run_border(self, *parts):
        return rules.border_rules(rules.Drawn.parse(svg(*parts)))

    def test_b1_hug_is_check_layouts_line_hugs_border(self):
        # a vertical line 12 / 11.99 right of a box's left border (x = 100), alongside it 200px
        for dx, hug in ((12, False), (11.99, True)):
            with self.subTest(dx=dx):
                parts = [group("vpc", 100, 100, 300, 300), edge(0, [(100 + dx, 150), (100 + dx, 350)])]
                got = codes(self.run_border(*parts), "B1")
                self.assertEqual([v.owners for v in got], [("edge:0", "group:vpc")] if hug else [])
                cl = [i.kind for i in rules.CL.run_checks(rules.ET.fromstring(svg(*parts)))]
                self.assertEqual("LINE HUGS BORDER" in cl, hug)
                if hug:
                    self.assertEqual(got[0].tier, rules.TIER_HARD)
                    self.assertAlmostEqual(got[0].cost, 0.01, places=3)

    def test_b2_header_band(self):
        # App subnet at (282, 390): badge 282–306 × 390–414, title from x = 314; the band
        # runs from x = 282 to the title's end, y = 390 to the header's bottom (414)
        sn = subnet("appsn", 282, 390, 124, 106)
        d = rules.Drawn.parse(svg(sn))
        (gid, _, band, marks), = rules.CL.header_bands(d.rects, d.icons, d.texts, d.owner)
        self.assertEqual((gid, band[:2], band[3]), ("group:appsn", (282, 390), 414))
        right = band[2]
        # flowcol/t7-xyref slide: a line down x = 308 between the badge and the title
        between = edge(3, [(308, 282), (308, 442)])
        got = codes(self.run_border(sn, between), "B2")
        self.assertEqual([v.owners for v in got], [("edge:3", "group:appsn")])
        self.assertIn("between its badge and title", got[0].message)
        # check_layout reports the band even in the gap between the badge and title
        cl = {i.kind for i in rules.CL.run_checks(rules.ET.fromstring(svg(sn, between)))}
        self.assertIn("LINE IN HEADER", cl)
        self.assertFalse(cl & {"LINE OVER ICON", "LINE OVER TEXT", "LINE NEAR TEXT"}, cl)
        # inside the band / outside it, on x (past the title's end) and on y (under the header)
        for pts, hit in (([(right - 1, 300), (right - 1, 450)], True), ([(right + 1, 300), (right + 1, 450)], False),
                         ([(250, 413), (450, 413)], True), ([(250, 415), (450, 415)], False),
                         ([(282, 300), (282, 450)], False)):          # on the left border: not in the band
            with self.subTest(pts=pts):
                got = codes(self.run_border(sn, edge(0, pts)), "B2")
                self.assertEqual([v.owners for v in got], [("edge:0", "group:appsn")] if hit else [])
                cl = [i for i in rules.CL.run_checks(rules.ET.fromstring(svg(sn, edge(0, pts))))
                      if i.kind == "LINE IN HEADER"]
                self.assertEqual(len(cl), len(got))
        over = codes(self.run_border(sn, edge(0, [(330, 300), (330, 450)])), "B2")
        self.assertIn("over its title", over[0].message)
        # a box with neither badge nor title has no band
        self.assertEqual(bands(group("g", 100, 100, 200, 200)), [])

    def test_b2_cidr_line_any_family_with_or_without_title(self):
        # the group's own CIDR line (what its <g> draws, not a pattern) is in the band: IPv4,
        # IPv6, and under no title (a plain box: CIDR at x + 12, baseline y + 34)
        def vpc(cidr, title=True):
            t = '<text x="132" y="118" font-size="14" fill="#8C4FFF" font-weight="600">VPC</text>' if title else ""
            return (f'<g id="group:v"><rect x="100" y="100" width="300" height="200" fill="none" stroke="#8C4FFF" '
                    f'stroke-width="2"/>{t}<text x="{132 if title else 112}" y="134" font-size="12" '
                    f'fill="#232F3E">{cidr}</text></g>')
        for cidr, title in (("10.0.0.0/24", True), ("2001:db8:1::/64", True), ("2001:db8:1::/64", False)):
            with self.subTest(cidr=cidr, title=title):
                (_, _, band, marks), = bands(vpc(cidr, title))
                self.assertIn("CIDR line", dict(marks))
                self.assertEqual(band[3], 137)              # the CIDR glyph bottom: 134 + 0.25 · 12
                got = codes(self.run_border(vpc(cidr, title), edge(0, [(90, 136), (420, 136)])), "B2")
                self.assertEqual([v.owners for v in got], [("edge:0", "group:v")])
                self.assertEqual(codes(self.run_border(vpc(cidr, title), edge(0, [(90, 138), (420, 138)])), "B2"), [])

    def test_b2_ipv6_cidr_as_the_engine_draws_it(self):
        # Codex review repro: a line pinned across the VPC's CIDR row (y0 + 32)
        for cidr in ("2001:db8:1::/64", "10.0.0.0/24"):
            with self.subTest(cidr=cidr):
                sp, b = build({"name": "cidr-header", "cols": ["c"], "rows": ["r1", "r2"],
                               "groups": [{"id": "v", "type": "vpc", "label": "Workload network", "cidr": cidr}],
                               "nodes": [{"id": "a", "icon": ICON, "label": "EC2", "in": "v", "at": ["c", "r1"]},
                                         {"id": "b", "icon": ICON, "label": "EC2", "in": "v", "at": ["c", "r2"]}],
                               "edges": [{"e": "a -- b", "points": [["v.x0+26", "v.y0+32"], ["v.x0+170", "v.y0+32"]]}]})
                got = [v for v in rules.check(sp, b.geom, b.svg) if v.code == "B2"]
                self.assertEqual([v.owners for v in got], [("edge:0", "group:v")])


def build(path_or_dict, mode=None):
    sp = layout_spec.load(path_or_dict, mode=mode)
    b = layout.build(sp, [], {}, None, "t")
    return sp, b


class Goldens(unittest.TestCase):
    """rules-design §1 R-rt "Checked on goldens": nfw Spoke / Firewall RT, tgw TGW A RT."""

    def test_examples_route_tables_hold(self):
        for name in ("nfw-reference-architecture", "tgw-reference-architecture", "centralized-egress"):
            for path in (SPECS / f"{name}.layout.yaml", SPECS / "slides" / f"{name}.layout.yaml"):
                if not path.exists():
                    continue
                with self.subTest(path=path.name, dir=path.parent.name):
                    sp, b = build(path)
                    got = [v for v in rules.check(sp, b.geom, b.svg) if v.rule == "R-rt"]
                    # TGW B RT, under TGW B outside its lines' bracket, is the hub's only table
                    # right beside it: passes (user decision 2026-11-07)
                    self.assertEqual(got, [])

    def test_nfw_spoke_rt_moved_out_of_its_bracket(self):
        sp, b = build(SPECS / "nfw-reference-architecture.layout.yaml")
        svg_text = b.svg.decode()
        # the Spoke RT moved left of the spoke VPCs' tips (out of the bracket the spoke lines draw)
        moved = svg_text.replace('<g id="node:rtsp">', '<g id="node:rtsp" transform="translate(-300,0)">')
        self.assertNotEqual(moved, svg_text)
        got = [v for v in rules.check(sp, b.geom, moved.encode()) if v.rule == "R-rt"]
        self.assertTrue(any(v.code == "RT1" and v.owners[0] == "node:rtsp" for v in got), got)


class UserDecisionCases(unittest.TestCase):
    """The cases the user decided on (2026-11-07, rules-design §6), as layout.py draws them
    (its `rule:` lines judge the written draft): each passes its rule."""

    def rule_lines(self, path, mode):
        import io
        import tempfile
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with redirect_stdout(buf):
                layout.main([str(path), "-o", str(Path(tmp) / "d.svg"), "--mode", mode])
        return [ln for ln in buf.getvalue().splitlines() if ln.startswith("rule: ")]

    def test_decided_cases_pass(self):
        corpus = ROOT / "tests" / "corpus"
        cases = [(SPECS / "tgw-reference-architecture.layout.yaml", "document", "R-rt", "rtb"),
                 (SPECS / "slides" / "tgw-reference-architecture.layout.yaml", "slide", "R-rt", "rtb"),
                 (SPECS / "nlb-mtls-reference-architecture.layout.yaml", "document", "R-flow", "edge:3"),
                 (corpus / "bench" / "latest2-egress.layout.yaml", "document", "R-label", "edge:8"),
                 (corpus / "bench" / "v2-1-egress.layout.yaml", "document", "R-label", "edge:8"),
                 (corpus / "lanes" / "j.layout.yaml", "document", "R-label", "edge:23")]
        for path, mode, rule, who in cases:
            with self.subTest(case=f"{path.parent.name}/{path.name}", mode=mode):
                got = [ln for ln in self.rule_lines(path, mode) if ln.startswith(f"rule: {rule} ") and who in ln]
                self.assertEqual(got, [])


TWIN = {
    "name": "twins", "mode": "document", "cols": ["a", "b", "c", "d"], "rows": ["r"],
    "groups": [{"id": "cloud", "type": "cloud"},
               {"id": "v1", "type": "vpc", "label": "VPC 1", "in": "cloud"},
               {"id": "v2", "type": "vpc", "label": "VPC 2", "in": "cloud"}],
    "nodes": [{"id": "x1", "icon": ICON, "label": "EC2", "in": "v1", "at": ["a", "r"]},
              {"id": "y1", "icon": ICON, "label": "EC2", "in": "v1", "at": ["b", "r"]},
              {"id": "x2", "icon": ICON, "label": "EC2", "in": "v2", "at": ["c", "r"]},
              {"id": "y2", "icon": ICON, "label": "EC2", "in": "v2", "at": ["d", "r"]}],
    "edges": [],
}


class TwinRules(unittest.TestCase):
    def test_twins_alike_and_unlike(self):
        sp, b = build(copy.deepcopy(TWIN))
        self.assertTrue(rules.layout_solve.twin_classes(sp))
        self.assertEqual(rules.twin_rules(sp, b.geom), [])
        geom = copy.deepcopy(b.geom)
        ng = geom.nodes["y2"]
        ng.cx += 6
        got = rules.twin_rules(sp, geom)
        self.assertEqual(len(got), 1)
        self.assertEqual(set(got[0].owners), {"group:v1", "group:v2"})
        self.assertAlmostEqual(got[0].cost, 6, places=3)

    def test_not_twins_when_unlike_by_structure(self):
        d = copy.deepcopy(TWIN)
        d["nodes"][3]["icon"] = "service/AWS-Lambda"
        sp, _ = build(d)
        self.assertEqual(rules.layout_solve.twin_classes(sp), [])


class Score(unittest.TestCase):
    def test_hard_violations_first(self):
        geom = M.Geometry(mode="document", S=48, canvas_w=100, canvas_h=100, cols={}, rows={})
        hard = rules.Violation("R-rt", ("node:rt",), "x", 2.0)
        fit = rules.Violation("R-fit", ("canvas",), "y", 1.5, rules.TIER_FIT)
        self.assertLess(rules.score([fit], [1, 2, 3], geom, None, 0), rules.score([hard], [], geom, None, 0))
        self.assertEqual(rules.score([hard, fit], [], geom, None, 1), (1, 2.0, 0, 1.5, 1, 10000.0))


class CorpusTags(unittest.TestCase):
    """tests/run_corpus.py tag_misses: a run whose checker failed leaves its tags unjudged
    (reported as such), never as kept."""

    def test_checker_failure_is_not_a_pass(self):
        sys.path.insert(0, str(ROOT / "tests"))
        import run_corpus
        entry = {"good": ["R-rt"], "bad": {"R-flow": "edge:3"}}
        ok = {"mode": "document", "result": "drawn",
              "violations": [{"rule": "R-flow", "owners": "edge:3,edge:4", "msg": "F1"}]}
        self.assertEqual(run_corpus.tag_misses(entry, [ok]), [])
        broke = {"mode": "slide", "result": "drawn", "violations": [{"rule": "checker-error", "msg": "boom"}]}
        got = run_corpus.tag_misses(entry, [broke])
        self.assertEqual(len(got), 1)
        self.assertIn("not judged", got[0])
        self.assertIn("good R-rt", got[0])


if __name__ == "__main__":
    unittest.main()
