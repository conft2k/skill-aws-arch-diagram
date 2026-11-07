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

    def test_f5_spec_placed_label_judged_too(self):
        # label_at / step_at a point exempts only L1: F5 judges where it ended up
        sp = spec(edges=[("a", "b")], nodes="ab")
        sp.edges[0].label_at = M.Place(M.Expr("num", offset=270), M.Expr("num", offset=60))
        sp.edges[0].step_at = M.Place(M.Expr("num", offset=200), M.Expr("num", offset=60))
        out = self.run_flow(sp, node("a", 50, 100), node("b", 450, 100), edge(0, [(102, 124), (446, 124)]),
                            label(0, 270, 60), badge(0, 200, 60, 1))
        self.assertEqual([v.owners for v in codes(out, "F5")], [("edge:0",), ("edge:0",)])

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

    def test_l1_judges_the_own_nearest_piece(self):
        # latest2-egress edge:8: above the horizontal piece but nearer the vertical one it
        # turns up into, and left of that one
        sp = spec(edges=[("a", "b")], nodes="ab")
        parts = [node("a", 50, 533), node("b", 860, 384), edge(0, [(102, 557), (717.5, 557), (717.5, 408), (856, 408)])]
        out = self.run_label(sp, *parts, label(0, 666.15, 548, s="appliance mode"))
        self.assertEqual([v.owners for v in codes(out, "L1")], [("edge:0",)])
        # an exact tie between two pieces: the one it spans along
        tie = self.run_label(sp, *parts, label(0, 600, 551, s="appliance mode"))
        self.assertEqual(codes(tie, "L1"), [])

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
    def test_slide_points(self):
        small = rules.fit_rules(spec(mode="slide"), rules.Drawn.parse(svg(w=1000, h=500)))
        self.assertEqual(small, [])
        big = rules.fit_rules(spec(mode="slide"), rules.Drawn.parse(svg(w=2000, h=1000)))
        self.assertEqual([(v.rule, v.tier) for v in big], [("R-fit", rules.TIER_FIT)])
        self.assertGreater(big[0].cost, 0)
        self.assertEqual(rules.fit_rules(spec(), rules.Drawn.parse(svg(w=2000, h=1000))), [])


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

    def test_rt1_hub_only_table_still_needs_its_bracket(self):
        # every line at the hub associated (its only table): no exception, the bracket holds
        sp = self.rt_spec(["a", "b", "c"], [("tgw", "a"), ("tgw", "b"), ("tgw", "c")], "abc")
        self.assertEqual(codes(self.run_rt(sp, *self.bracket_parts(200, 300)), "RT1"), [])
        out = self.run_rt(sp, *self.bracket_parts(600, 150))      # up-right, past the c-a wedge's chord
        self.assertEqual([v.owners for v in codes(out, "RT1")], [("node:rt", "node:tgw")])

    def test_rt2_single_line(self):
        sp = self.rt_spec(["c"], [("tgw", "a"), ("tgw", "b"), ("tgw", "c")], "abc")
        self.assertEqual(codes(self.run_rt(sp, *self.bracket_parts(530, 360)), "RT2"), [])
        bad = self.run_rt(sp, *self.bracket_parts(530, 540))
        self.assertEqual([v.owners for v in codes(bad, "RT2")], [("node:rt", "edge:2")])

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
                    # TGW B RT sits under TGW B, below every line its three associations draw
                    # (outside the bracket: RT1, no exception for a hub's only table)
                    self.assertEqual([v for v in got if v.owners[0] != "node:rtb"], [])
                    if name.startswith("tgw"):
                        self.assertEqual([(v.code, v.owners) for v in got], [("RT1", ("node:rtb", "node:tgwb"))])

    def test_nfw_spoke_rt_moved_out_of_its_bracket(self):
        sp, b = build(SPECS / "nfw-reference-architecture.layout.yaml")
        svg_text = b.svg.decode()
        # the Spoke RT moved left of the spoke VPCs' tips (out of the bracket the spoke lines draw)
        moved = svg_text.replace('<g id="node:rtsp">', '<g id="node:rtsp" transform="translate(-300,0)">')
        self.assertNotEqual(moved, svg_text)
        got = [v for v in rules.check(sp, b.geom, moved.encode()) if v.rule == "R-rt"]
        self.assertTrue(any(v.code == "RT1" and v.owners[0] == "node:rtsp" for v in got), got)


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
