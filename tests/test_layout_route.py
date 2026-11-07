#!/usr/bin/env python3
"""The edge router (scripts/layout_route.py) against the reference examples.

    python3 tests/test_layout_route.py

Specs come from docs/examples/specs/*.layout.yaml (layout_spec.load); the Geometry is built
here straight from each example's draft (embed.unembed in memory): node icons, label lines
and masks, group rects and headers, track centers — no solver involved. The router's
lines, labels and badges are then checked against the coordinates the examples use
(DESIGN 3: NFW badges 645 / 929 / 1059, TGW badges 518 / 796 / 1015, nlb-mtls trunk 642,
ALB "아웃바운드"), the shape table, candidate validation on synthetic obstacles, the plan's
requirements on the example geometry, and check_layout.py on a minimal SVG of groups +
nodes + routed edges.
"""
import math
import re
import statistics
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_layout as CL  # noqa: E402
import embed  # noqa: E402
import layout_const as K  # noqa: E402
import layout_model as M  # noqa: E402
import layout_route as R  # noqa: E402
import layout_spec  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"
SPECS = ROOT / "docs/examples/specs"
NAMES = ["alb", "nfw", "tgw", "nlb", "gwlb", "nlb-mtls", "example"]


def draft_path(name):
    return ROOT / "docs/example.svg" if name == "example" else ROOT / f"docs/examples/{name}-reference-architecture.svg"


def spec_path(name):
    return SPECS / ("example.layout.yaml" if name == "example" else f"{name}-reference-architecture.layout.yaml")


# ---------------------------------------------------------------------------------------
# Example draft → Geometry

class Draft:
    """Absolute-coordinate elements of an example (translate applied)."""

    def __init__(self, path):
        out, _, problems = embed.unembed(path.read_text(encoding="utf-8"))
        assert not problems, problems
        self.root = ET.fromstring(out)
        vb = [float(v) for v in self.root.get("viewBox").split()]
        self.w, self.h = vb[2], vb[3]
        self.rects, self.images, self.texts = [], [], []
        self._walk(self.root, 0.0, 0.0)

    def _walk(self, el, ox, oy):
        dx, dy = CL.translate(el)
        ox, oy = ox + dx, oy + dy
        tag = el.tag.replace(NS, "")
        n = lambda k: CL.num(el.get(k))  # noqa: E731
        if tag in ("defs", "marker"):
            return
        if tag == "rect" and el.get("width") and not (n("width") >= self.w and n("height") >= self.h):
            self.rects.append({"box": M.Box.xywh(n("x") + ox, n("y") + oy, n("width"), n("height")),
                               "stroke": el.get("stroke"), "fill": (el.get("fill") or "").lower(),
                               "dash": el.get("stroke-dasharray"), "width": el.get("stroke-width")})
        elif tag == "image":
            href = el.get("href", "")
            self.images.append({"ref": href[len("bundle:"):], "box": M.Box.xywh(n("x") + ox, n("y") + oy, n("width"), n("height"))})
        elif tag == "text":
            s = "".join(el.itertext()).strip()
            if s:
                self.texts.append(M.TextLine(s, n("x") + ox, n("y") + oy, n("font-size"), el.get("fill", ""),
                                             el.get("font-weight", ""), el.get("text-anchor", "start")))
        for c in el:
            self._walk(c, ox, oy)


def geometry(spec, name):
    """The example's Geometry for this spec (ids matched by icon ref and track position)."""
    d = Draft(draft_path(name))
    icons = [i for i in d.images if not i["ref"].startswith("group/")]
    nodes = list(spec.nodes.values())
    by_ref = {}
    for i in icons:
        by_ref.setdefault(i["ref"], []).append(i)
    # nodes sharing an icon ref ↔ the draft's icons of that ref, both in reading order
    # (row index, column index / flow order) vs (cy, cx)
    ci = {t.id: i for i, t in enumerate(spec.cols)}
    ri = {t.id: i for i, t in enumerate(spec.rows)}
    pos = {}
    for ref, imgs in by_ref.items():
        ns = [n for n in nodes if n.icon == ref]
        if len(ns) != len(imgs):
            continue
        ns.sort(key=lambda n: (ri.get(n.row, -1), ci[n.col] if n.col else (n.flow_index or 0)))
        imgs = sorted(imgs, key=lambda i: (round(i["box"].cy), i["box"].cx))
        pos.update({n.id: i for n, i in zip(ns, imgs)})
    cols, rows = {}, {}
    cs, rs = {}, {}
    for n in nodes:
        if n.id not in pos or n.xy is not None:
            continue
        b = pos[n.id]["box"]
        if n.col and not n.col2 and not n.on:
            cs.setdefault(n.col, []).append(b.cx - n.dx)
        if n.row and spec.track(n.row).flow is None:
            rs.setdefault(n.row, []).append(b.cy - n.dy)
    cols.update({k: statistics.median(v) for k, v in cs.items()})
    rows.update({k: statistics.median(v) for k, v in rs.items()})
    missing = [n.id for n in nodes if n.id not in pos]
    assert not missing, f"{name}: no icon for {missing}"
    for t in spec.cols:                 # tracks with only colspan / border nodes
        if t.id not in cols:
            xs = [pos[n.id]["box"].cx for n in nodes if n.col == t.id]
            if xs:
                cols[t.id] = xs[0]
    for t in spec.rows:
        if t.id not in rows:
            ys = [pos[n.id]["box"].cy for n in nodes if n.row == t.id]
            if ys:
                rows[t.id] = ys[0]
    ngeo = {}
    for n in nodes:
        b = pos[n.id]["box"]
        lines, y = [], b.y1 + K.NODE_LABEL_DY
        for t in sorted(d.texts, key=lambda t: t.y):
            if t.anchor == "middle" and abs(t.x - b.cx) < 0.6 and abs(t.y - y) < 0.6:
                lines.append(t)
                y += K.SUB_PITCH
        mask = next((r["box"] for r in d.rects if r["fill"] in ("#ffffff", "white") and not r["stroke"]
                     and abs(r["box"].x0 - b.x0) < 1 and abs(r["box"].y0 - b.y0) < 1), None)
        ngeo[n.id] = M.NodeGeom(n.id, b.cx, b.cy, b, lines, mask, n.side)
    # groups: the smallest rect of the type holding the group's nodes, inside its parent
    boxes = []
    for r in d.rects:
        if r["stroke"] and r["fill"] == "none":
            badge = next((i["ref"] for i in d.images if i["ref"].startswith(("group/", "service/AWS-Cloud-WAN"))
                          and abs(i["box"].x0 - r["box"].x0) < 1 and abs(i["box"].y0 - r["box"].y0) < 1), None)
            r["type"] = K.group_type_of(r["stroke"], r["dash"], badge)
            boxes.append(r)
    ggeo, used = {}, set()

    def members(g):
        if g.overlay:
            return g.over
        return [n.id for n in nodes if g.id in spec.node_chain(n.id) and not (n.on and n.on == g.id)]

    order = sorted(spec.groups.values(), key=lambda g: (g.depth, 0 if members(g) else 1))
    for g in sorted(order, key=lambda g: (0 if members(g) else 1, g.depth)):
        mem = [ngeo[m].icon for m in members(g)]
        parent = ggeo[g.parent].rect if g.parent in ggeo else None
        cand = [r for r in boxes if r["type"] == g.type and id(r) not in used
                and all(r["box"].contains(b, 1) for b in mem)
                and (parent is None or parent.contains(r["box"], 1))]
        if not mem:
            cand.sort(key=lambda r: (r["box"].y0, r["box"].x0))
            k = (g.instance or 1) - 1 if g.instance else 0
            sibl = [s for s in spec.groups.values() if s.parent == g.parent and s.type == g.type and not members(s)]
            k = sibl.index(g) if g in sibl else 0
            pick = cand[min(k, len(cand) - 1)] if cand else None
        else:
            pick = min(cand, key=lambda r: r["box"].w * r["box"].h) if cand else None
        assert pick is not None, f"{name}: no rect for group {g.id}"
        used.add(id(pick))
        rb = pick["box"]
        st = K.style(g.type)
        badge = M.Box.xywh(rb.x0, rb.y0, st.badge_size, st.badge_size) if st.badge else None
        title = next((t for t in d.texts if t.weight == "600" and abs(t.y - (rb.y0 + st.title_dy)) < 1
                      and abs(t.x - (rb.x0 + st.title_dx)) < 1), None)
        cidr = next((t for t in d.texts if title and abs(t.x - title.x) < 1 and abs(t.y - (rb.y0 + K.CIDR_DY)) < 1
                     and t.size == 12), None)
        ggeo[g.id] = M.GroupGeom(g.id, rb, badge, title, cidr)
        pick["gid"] = g.id
    groups = {gid: ggeo[gid] for gid in spec.groups}
    drawing = M.union_all([g.rect for g in groups.values()] + [n.footprint() for n in ngeo.values()])
    geom = M.Geometry(spec.mode, spec.S, d.w, d.h, {t.id: cols[t.id] for t in spec.cols if t.id in cols},
                      {t.id: rows[t.id] for t in spec.rows if t.id in rows}, groups=groups,
                      nodes={n.id: ngeo[n.id] for n in nodes}, drawing=drawing)
    return geom, d, boxes


def load(name):
    spec = layout_spec.load(spec_path(name))
    geom, d, boxes = geometry(spec, name)
    return spec, geom, d, boxes


def svg_of(spec, geom, d, boxes, elements):
    """A minimal SVG: the example's group rects (+ badges, headers), nodes (mask, icon,
    label lines) from the Geometry, then the routed elements."""
    out = [f'<svg viewBox="0 0 {M.fmt_num(geom.canvas_w)} {M.fmt_num(geom.canvas_h)}" xmlns="http://www.w3.org/2000/svg" '
           f'font-family="{K.FONT_FAMILY_DEFAULT}">',
           f"<defs>{K.MARKER_ARROW}{K.MARKER_ARROW_START}</defs>",
           f'<rect width="{M.fmt_num(geom.canvas_w)}" height="{M.fmt_num(geom.canvas_h)}" fill="#FFFFFF"/>']
    els = []
    for gid, g in geom.groups.items():
        st = K.style(spec.groups[gid].type)
        els.append(M.el_rect(g.rect, stroke=st.stroke, width=st.width, dash=spec.groups[gid].dash or st.dash))
        if g.badge:
            els.append(M.el_image(st.badge, g.badge))
        for t in (g.title, g.cidr):
            if t:
                els.append(M.el_text(t))
    for nid, n in geom.nodes.items():
        if n.mask:
            els.append(M.el_rect(n.mask, fill="#FFFFFF"))
        els.append(M.el_image(spec.nodes[nid].icon, n.icon))
        els += [M.el_text(t) for t in n.lines]
    for el in sorted(els + list(elements), key=lambda e: e.z):
        out.append(emit(el))
    out.append("</svg>")
    return "\n".join(out)


def emit(el):
    attrs = " ".join(f'{k}="{M.fmt_num(v) if isinstance(v, (int, float)) else esc(str(v))}"' for k, v in el.attrs.items())
    if el.kind == "text":
        return f"<text {attrs}>{esc(el.text)}</text>"
    return f"<{el.kind} {attrs}/>"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def badges_of(elements):
    """{(owner, digit): (cx, cy)} of the step badges."""
    out = {}
    circles = [e for e in elements if e.kind == "circle"]
    digits = [e for e in elements if e.kind == "text" and e.z == K.Z_BADGE]
    for c, t in zip(circles, digits):
        out[int(t.text)] = (c.attrs["cx"], c.attrs["cy"])
    return out


def lines_of(elements, n):
    return [e for e in elements if e.owner == f"edge:{n}" and e.kind in ("line", "polyline")]


def points(el):
    if el.kind == "line":
        a = el.attrs
        return [(a["x1"], a["y1"]), (a["x2"], a["y2"])]
    vals = [float(v) for v in re.split(r"[ ,]+", el.attrs["points"])]
    return list(zip(vals[::2], vals[1::2]))


CACHE = {}


def routed(name):
    if name not in CACHE:
        spec, geom, d, boxes = load(name)
        els, warns = R.draw(spec, geom)
        CACHE[name] = (spec, geom, d, boxes, els, warns)
    return CACHE[name]


# ---------------------------------------------------------------------------------------

EXPECTED_SHAPES = {
    # one entry per expanded edge instance, in Edge.n order
    "alb": ["H", "H", "H", "H", "VH", "H", "H", "V"],
    "nfw": ["HVH", "HVH", "VH", "VH", "H", "H", "H", "H", "HVH", "HVH", "H"],
    "tgw": ["H", "H", "H", "VHV", "VHV", "VHV", "VHV", "H", "H", "V", "V"],
    "nlb": ["H", "H", "H", "VH", "H", "H"],
    "gwlb": ["H", "HVH", "HVH", "HV", "HV", "H", "H", "H"],
    "nlb-mtls": ["V", "H", "H", "HVH", "HVH"],
    "example": ["H", "H"],
}


class Shapes(unittest.TestCase):
    def test_table(self):
        total = 0
        for name, want in EXPECTED_SHAPES.items():
            spec = layout_spec.load(spec_path(name))
            got = R.shapes(spec)
            self.assertEqual([got[e.n] for e in spec.edges], want, name)
            total += len({e.line for e in spec.edges})
        self.assertGreaterEqual(total, 26)

    def test_tgw_spokes_without_overrides(self):
        """Rule 5: the hub's sides hold the VPN and peering lines; the lower spokes' VH leg
        would cross TGW A RT, the upper ones are headless hub spokes → VHV either way."""
        spec = layout_spec.load(spec_path("tgw"))
        for e in spec.edges:
            if e.a == "tgwa" and e.b in ("svcs", "prod", "dev", "test"):
                e.shape = None
        got = R.shapes(spec)
        self.assertEqual([got[e.n] for e in spec.edges if e.a == "tgwa" and e.b != "peer"], ["VHV"] * 4)
        topo = R._topology(spec)
        notes = {spec.edges[n].b: t.note for n, t in topo.items()}
        self.assertIn("cross a node", notes["dev"])
        self.assertIn("hub", notes["svcs"])

    def test_fan_of_spokes_mirrors(self):
        """A node with headless spokes up to both its left and its right gets VHV on both,
        even with one horizontal side free (slide tgw TGW B on its own column between DR
        and Analytics VPC, the peering line on its left): not VH on one side and HVH on
        the other. With arrowheads, or spokes to one side only, the old rules stand."""
        spec = layout_spec.load({
            "name": "fan", "mode": "slide", "cols": ["peer", "b1", "bm", "b2"], "rows": ["top", "main"],
            "groups": [{"id": "cloud", "type": "cloud"}, {"id": "rb", "type": "region", "in": "cloud"}],
            "nodes": [{"id": "peer", "icon": "resource/Amazon-VPC_Peering-Connection", "label": "peer", "in": "cloud",
                       "at": ["peer", "main"]},
                      {"id": "tgwb", "icon": "service/AWS-Transit-Gateway", "label": "TGW B", "in": "rb",
                       "at": ["bm", "main"]},
                      {"id": "dr", "icon": "service/Amazon-Virtual-Private-Cloud", "label": "DR", "in": "rb",
                       "at": ["b1", "top"]},
                      {"id": "ana", "icon": "service/Amazon-Virtual-Private-Cloud", "label": "Analytics", "in": "rb",
                       "at": ["b2", "top"]}],
            "edges": [{"e": "peer -- tgwb"}, {"e": "tgwb -- dr"}, {"e": "ana -- tgwb"}]})
        topo = R._topology(spec)
        self.assertEqual([topo[n].shape for n in (1, 2)], ["VHV", "VHV"])
        self.assertIn("fan of spokes", topo[1].note)
        self.assertIn("not VH", topo[1].note)
        for e in spec.edges[1:]:
            e.op = "->"
        self.assertEqual([R._topology(spec)[n].shape for n in (1, 2)], ["VH", "HVH"])

    def test_fan_ignores_a_forced_spoke(self):
        """A spoke forced HVH (shape: or sides) is no fan member: the other spoke keeps its own
        rule instead of flipping to VHV; a spoke forced VHV is a member, and the other
        mirrors it."""
        def topo(force):
            return R._topology(layout_spec.load({
                "name": "fanf", "mode": "slide", "cols": ["a1", "a2", "a3"], "rows": ["top", "main"],
                "groups": [{"id": "cloud", "type": "cloud"}],
                "nodes": [{"id": "hub", "icon": "service/AWS-Transit-Gateway", "label": "Hub", "in": "cloud",
                           "at": ["a2", "main"]},
                          {"id": "l", "icon": "service/Amazon-Virtual-Private-Cloud", "label": "L", "in": "cloud",
                           "at": ["a1", "top"]},
                          {"id": "r", "icon": "service/Amazon-Virtual-Private-Cloud", "label": "R", "in": "cloud",
                           "at": ["a3", "top"]}],
                "edges": [dict({"e": "hub -- l"}, **force), {"e": "hub -- r"}]}))
        for force in ({"shape": "HVH"}, {"from_side": "left", "to_side": "right"}):
            with self.subTest(force=force):
                t = topo(force)
                self.assertEqual((t[0].shape, t[1].shape), ("HVH", "HVH"))
                self.assertNotIn("fan", t[1].note)
        for force in ({"shape": "VHV"}, {"from_side": "top", "to_side": "bottom"}):
            with self.subTest(force=force):
                t = topo(force)
                self.assertEqual((t[0].shape, t[1].shape), ("VHV", "VHV"))
                self.assertIn("fan of spokes", t[1].note)

    def test_users_route53_is_vh(self):
        spec = layout_spec.load(spec_path("alb"))
        self.assertEqual(R.shapes(spec)[4], "VH")

    def test_trunk_roles(self):
        topo = R._topology(layout_spec.load(spec_path("nfw")))
        self.assertEqual((topo[8].trunk, topo[9].trunk, topo[9].first), ("merge", "merge", 8))
        topo = R._topology(layout_spec.load(spec_path("gwlb")))
        self.assertEqual((topo[1].trunk, topo[2].trunk), ("fork", "fork"))
        self.assertIsNone(topo[3].trunk)          # gwlb <-> gwlbe.* is not a trunk: two lines


class Reproduce(unittest.TestCase):
    """Coordinates traced in DESIGN 3 (±8)."""

    def near(self, got, want, msg, tol=8):
        self.assertLessEqual(abs(got - want), tol, f"{msg}: {got} vs {want}")

    def test_nfw_badges(self):
        spec, geom, d, boxes, els, warns = routed("nfw")
        b = badges_of(els)
        for n, x in ((3, 793), (4, 1077), (5, 1207)):
            self.near(b[n][0], x, f"nfw badge {n} x")
            self.near(b[n][1], 208, f"nfw badge {n} cy")

    def test_nfw_trunk_and_ports(self):
        spec, geom, d, boxes, els, warns = routed("nfw")
        first, second = points(lines_of(els, 8)[0]), points(lines_of(els, 9)[0])
        self.assertEqual(first[-1], (1332, 382))                 # one arrow on the IGW's center line
        self.near(first[1][0], 1284, "trunk x")
        self.assertEqual(second[-1], (first[1][0], 382))         # the AZ 2 line stops at the junction
        self.assertNotIn("marker-end", lines_of(els, 9)[0].attrs)
        spokes = [points(lines_of(els, n)[0])[-1][1] for n in (0, 1)]
        self.assertEqual(spokes, [374, 390])                     # ±8 into the TGW's left side

    def test_tgw_badges(self):
        spec, geom, d, boxes, els, warns = routed("tgw")
        b = badges_of(els)
        for n, x in ((3, 796), (4, 1015)):
            self.near(b[n][0], x, f"tgw badge {n} x")
        self.near(b[4][1], 200, "tgw badge 4 cy")
        tops = sorted(points(lines_of(els, n)[0])[0][0] for n in (3, 4))
        self.assertEqual(tops, [606, 626])                       # ±10 on the TGW's top side
        # badge 2 and its label side by side above the line (labels go above a horizontal line)
        label = next(e for e in els if e.owner == "edge:2" and e.kind == "text" and e.z == K.Z_EDGE_LABEL)
        self.assertEqual(label.attrs["y"], 254 - 9)
        self.assertEqual(b[2][1], 254 - K.BADGE_DY)
        self.assertLessEqual(b[2][0] + K.BADGE_R + 4, label.attrs["x"] - M.text_width(label.text, 12) / 2)
        # and badge 1 beside 'IPsec' on the (widened) Internet → VPN piece
        label = next(e for e in els if e.owner == "edge:1" and e.kind == "text" and e.z == K.Z_EDGE_LABEL)
        self.assertEqual(label.attrs["y"], 254 - 9)
        self.assertEqual(b[1][1], 254 - K.BADGE_DY)
        self.assertLessEqual(b[1][0] + K.BADGE_R + 4, label.attrs["x"] - M.text_width(label.text, 12) / 2)

    def test_nlb_mtls_trunk(self):
        spec, geom, d, boxes, els, warns = routed("nlb-mtls")
        trunk_xs = {p[0] for n in (3, 4) for p in points(lines_of(els, n)[0])[1:-1]}
        self.assertEqual(len(trunk_xs), 1)
        self.near(trunk_xs.pop(), 642, "nlb trunk x")

    def test_alb_outbound_labels(self):
        spec, geom, d, boxes, els, warns = routed("alb")
        for n, y in ((5, 334), (6, 634)):
            t = next(e for e in els if e.owner == f"edge:{n}" and e.kind == "text")
            self.assertEqual(t.text, "아웃바운드")
            self.near(t.attrs["x"], 553, "outbound label x")
            self.near(t.attrs["y"], y, "outbound label y")
        t = next(e for e in els if e.owner == "edge:7" and e.kind == "text")
        self.assertEqual((t.attrs.get("text-anchor", "start"), t.attrs["x"]), ("start", 986))  # 10 right of the vertical
        self.near(t.attrs["y"], 481, "replication label y")
        t = next(e for e in els if e.owner == "edge:0" and e.kind == "text")
        self.assertLess(t.attrs["x"] + M.text_width(t.text, 12) / 2, geom.groups["cloud"].rect.x0)  # outside the Cloud

    def test_route53_vh(self):
        spec, geom, d, boxes, els, warns = routed("alb")
        self.assertEqual(points(lines_of(els, 4)[0]), [(40, 449), (40, 112), (175, 112)])


class Checker(unittest.TestCase):
    """Groups + nodes + routed edges pass check_layout.py with no problem."""

    def test_examples_layout_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in NAMES:
                spec, geom, d, boxes, els, warns = routed(name)
                self.assertEqual(warns, [], name)
                path = Path(tmp) / f"{name}.draft.svg"
                path.write_text(svg_of(spec, geom, d, boxes, els), encoding="utf-8")
                res = subprocess.run([sys.executable, str(ROOT / "scripts/check_layout.py"), str(path)],
                                     capture_output=True, text=True)
                self.assertEqual(res.stdout.strip().splitlines()[-1], "Layout OK", f"{name}:\n{res.stdout}")

    def test_deterministic(self):
        spec, geom, d, boxes = load("nfw")
        a, b = R.draw(spec, geom), R.draw(spec, geom)
        self.assertEqual([(e.kind, e.attrs, e.text, e.z, e.owner) for e in a[0]],
                         [(e.kind, e.attrs, e.text, e.z, e.owner) for e in b[0]])

    def test_z_and_markers(self):
        spec, geom, d, boxes, els, warns = routed("nfw")
        zs = [e.z for e in els]
        self.assertEqual(zs, sorted(zs))
        two_way = lines_of(els, 4)[0].attrs
        self.assertEqual((two_way["marker-start"], two_way["marker-end"]), (K.MARKER_START_ATTR, K.MARKER_END_ATTR))
        spec, geom, d, boxes, els, warns = routed("alb")
        self.assertEqual(lines_of(els, 4)[0].attrs["stroke-dasharray"], K.DASH_DASHED)
        self.assertNotIn("marker-start", lines_of(els, 4)[0].attrs)


class Plan(unittest.TestCase):
    def value(self, geom, var, axis):
        if var == "origin":
            return 0.0
        kind, _, rest = var.partition(":")
        if kind == "node":
            n = geom.nodes[rest]
            return n.cx if axis == "x" else n.cy
        if kind in ("col", "row"):
            return geom.track(rest)
        gid, _, edge = rest.rpartition(".")
        return geom.groups[gid].rect.get({"L": "x0", "R": "x1", "T": "y0", "B": "y1"}[edge])

    def test_hard_requirements_hold_on_examples(self):
        for name in NAMES:
            spec, geom, d, boxes = load(name)
            for r in R.plan(spec):
                if r.soft:
                    continue
                got = self.value(geom, r.b, r.axis) - self.value(geom, r.a, r.axis)
                slack = 0.01
                if r.why.startswith("label"):       # reserved at 0.6 em; the examples used 0.55 em
                    text = re.search(r"'(.*)'", r.why).group(1)
                    slack += M.layout_text_width(text, 12) - M.text_width(text, 12)
                self.assertGreaterEqual(got + slack, r.d, f"{name}: {r}")

    def test_nfw_trunk_corridor(self):
        reqs = R.plan(layout_spec.load(spec_path("nfw")))
        corr = [r for r in reqs if r.owner == "edge:8" and r.b == "node:igw" and r.axis == "x"]
        self.assertEqual(sorted((r.soft, r.d) for r in corr), [(False, 60.0), (True, 104.0)])
        self.assertTrue(all(r.a == "group:az.1.R" for r in corr))

    def test_label_room_outside_cloud(self):
        reqs = R.plan(layout_spec.load(spec_path("alb")))
        lab = [r for r in reqs if r.owner == "edge:0" and r.why.startswith("label")]
        self.assertEqual([(r.a, r.b) for r in lab], [("node:users", "group:cloud.L"), ("node:users", "node:igw")])
        self.assertEqual(lab[0].d, 24 + 8 + M.layout_text_width("HTTPS :443", 12) + 8)
        # a verb (attachment type) has no outside-the-Cloud piece: tgw's sits in the Region
        reqs = R.plan(layout_spec.load(spec_path("tgw")))
        self.assertFalse([r for r in reqs if r.owner == "edge:2" and "outside" in r.why])


    def test_bend_gutter_past_the_source_labels(self):
        """A HVH that leaves a node sideways and drops past its label stack keeps the
        node's whole footprint (its widest line) a sibling gap from the next node on its
        row (bedrock-dx PC → Internet past 고객 라우터): the solver's line-by-line spacing
        would let the router's neighbour come closer than the vertical leg needs."""
        spec = layout_spec.load(SPECS / "bedrock-dx-reference-architecture.layout.yaml")
        gut = [r for r in R.plan(spec) if "bend gutter past" in r.why]
        self.assertEqual([(r.a, r.b, r.owner) for r in gut], [("node:pc", "node:rtr", "edge:0")])
        want = 16 + math.ceil(M.layout_text_width("CLAUDE_CODE_USE_BEDROCK=1", 12) / 2) + \
            math.ceil(M.layout_text_width("고객 라우터", 14) / 2)
        self.assertEqual(gut[0].d, want)
        self.assertFalse(gut[0].soft)
        # only the nearest sibling toward the other end: the leg drops before it
        ec2 = "service/Amazon-EC2"
        spec = layout_spec.load({
            "name": "gut", "cols": ["a", "b", "c", "d"], "rows": ["top", "bot"],
            "nodes": [{"id": "x", "icon": ec2, "label": "X", "sub": ["a long line under the source"], "at": ["a", "top"]},
                      {"id": "s1", "icon": ec2, "label": "S1", "at": ["b", "top"]},
                      {"id": "s2", "icon": ec2, "label": "S2", "at": ["c", "top"]},
                      {"id": "t", "icon": ec2, "label": "T", "at": ["d", "bot"]}],
            "edges": [{"e": "x -> t"}]})
        self.assertEqual(R.shapes(spec)[0], "HVH")
        gut = [(r.a, r.b) for r in R.plan(spec) if "bend gutter past" in r.why]
        self.assertEqual(gut, [("node:x", "node:s1")])
        # a VHV's labelled horizontal piece asks for its label run in a document only
        spec = layout_spec.load(spec_path("tgw"))
        run = [r for r in R.plan(spec) if r.why.startswith("label 'VPC attachment' run on the bend")]
        self.assertEqual([(r.a, r.b, r.soft) for r in run], [("node:svcs", "node:tgwa", True)])
        spec = layout_spec.load(SPECS / "slides/tgw-reference-architecture.layout.yaml")
        self.assertFalse([r for r in R.plan(spec) if "run on the bend" in r.why])

    def test_vhv_label_run_solved(self):
        """The document's soft VHV label run takes effect: svcs ↔ tgwa grows from the 112 the
        rest asks to the label + 8 each side past the split port, and the router sets "VPC
        attachment" on that horizontal piece with 8 to spare at both ends."""
        import layout_solve as LS
        spec = layout_spec.load(spec_path("tgw"))
        reqs = R.plan(spec)
        run = [r for r in reqs if r.why.startswith("label 'VPC attachment' run on the bend")]
        self.assertEqual(len(run), 1)
        pitch = lambda g: g.nodes["tgwa"].cx - g.nodes["svcs"].cx
        without = LS.solve(spec, [r for r in reqs if r not in run])
        geom = LS.solve(spec, reqs)
        self.assertLess(pitch(without), run[0].d)
        self.assertAlmostEqual(pitch(geom), run[0].d, places=6)
        n = run[0].owner.split(":")[1]
        els, _ = R.draw(spec, geom)
        pts = points(lines_of(els, int(n))[0])
        horiz = [(p, q) for p, q in zip(pts, pts[1:]) if abs(p[1] - q[1]) < 1e-6]
        self.assertEqual(len(horiz), 1)
        (x0, y), (x1, _) = horiz[0]
        x0, x1 = sorted((x0, x1))
        text = [e for e in els if e.owner == run[0].owner and e.kind == "text"]
        self.assertEqual([t.text for t in text], ["VPC attachment"])
        half = M.layout_text_width("VPC attachment", 12) / 2
        self.assertGreaterEqual(text[0].attrs["x"] - half - x0, K.LABEL_CLEAR - 1e-6)
        self.assertGreaterEqual(x1 - text[0].attrs["x"] - half, K.LABEL_CLEAR - 1e-6)
        self.assertLess(abs(text[0].attrs["y"] - y), 12)                 # on that piece, not beside a leg


class Synthetic(unittest.TestCase):
    """Candidate validation on a tiny hand-made geometry."""

    def setup(self, blocker=True):
        spec = M.Spec("t", cols=[M.Track("a", "col", 0), M.Track("m", "col", 1), M.Track("b", "col", 2)],
                      rows=[M.Track("r", "row", 0), M.Track("s", "row", 1)])
        spec.nodes = {"x": M.Node("x", "service/Amazon-EC2", "X", col="a", row="r"),
                      "y": M.Node("y", "service/Amazon-EC2", "Y", col="b", row="r")}
        if blocker:
            spec.nodes["z"] = M.Node("z", "service/Amazon-S3", "Z", col="m", row="r")
        spec.edges = [M.Edge(0, "x", "y", "->")]
        cols, rows = {"a": 100, "m": 300, "b": 500}, {"r": 200, "s": 400}
        nodes = {}
        for nid, n in spec.nodes.items():
            cx, cy = cols[n.col], rows[n.row]
            icon = M.Box(cx - 24, cy - 24, cx + 24, cy + 24)
            nodes[nid] = M.NodeGeom(nid, cx, cy, icon, [M.TextLine(n.label, cx, icon.y1 + 18, 14, K.INK, "", "middle")])
        geom = M.Geometry("document", 48, 700, 500, cols, rows, nodes=nodes)
        return spec, geom

    def test_straight_blocked_by_icon(self):
        spec, geom = self.setup()
        els, warns = R.draw(spec, geom)
        pts = points(lines_of(els, 0)[0])
        self.assertGreater(len(pts), 2)                          # not the straight line through Z
        for p, q in zip(pts, pts[1:]):
            for nid in geom.nodes:
                self.assertFalse(CL.seg_hits_box(p, q, geom.nodes[nid].icon.t()), (p, q, nid))
        self.assertTrue(any("instead of H" in w for w in warns))

    def test_straight_when_clear(self):
        spec, geom = self.setup(blocker=False)
        els, warns = R.draw(spec, geom)
        self.assertEqual(points(lines_of(els, 0)[0]), [(128, 200), (472, 200)])
        self.assertEqual(warns, [])

    def test_skip_takes_next_candidate(self):
        spec, geom = self.setup()
        a = points(lines_of(R.draw(spec, geom)[0], 0)[0])
        b = points(lines_of(R.draw(spec, geom, skip={0: 1})[0], 0)[0])
        self.assertNotEqual(a, b)

    def test_refused_shape_says_why(self):
        """A requested shape the router cannot draw clean is replaced, and the warning says
        it was the spec's own request, what blocked it and the bend that would work."""
        spec, geom = self.setup(blocker=False)
        spec.nodes["y"].row = "s"
        geom.nodes["y"] = M.NodeGeom("y", 500, 400, M.Box(476, 376, 524, 424),
                                     [M.TextLine("Y", 500, 442, 14, K.INK, "", "middle")])
        spec.nodes["z"] = M.Node("z", "service/Amazon-S3", "Z", xy=(300.0, 320.0))
        geom.nodes["z"] = M.NodeGeom("z", 300, 320, M.Box(276, 296, 324, 344),
                                     [M.TextLine("Z", 300, 362, 14, K.INK, "", "middle")])
        spec.edges = [M.Edge(0, "x", "y", "--", src="edges[0]", shape="VHV", bend_y=M.Expr("num", offset=320))]
        els, warns = R.draw(spec, geom)
        w = [m for m in warns if "refusing the requested shape: VHV" in m]
        self.assertEqual(len(w), 1, warns)
        self.assertIn("bend_y 320 = 320: LINE OVER ICON of z", w[0])
        self.assertRegex(w[0], r"try bend_y: \d+")
        self.assertRegex(w[0], r"^edges\[0\][^:]*: drew \S+ instead of VHV")    # layout.py's feedback still reads it
        # the bend it suggests draws the VHV clean
        v = float(re.search(r"try bend_y: (\d+(?:\.\d+)?)", w[0]).group(1))
        spec.edges[0].bend_y = M.Expr("num", offset=v)
        els, warns = R.draw(spec, geom)
        self.assertEqual(warns, [])
        self.assertEqual(len(points(lines_of(els, 0)[0])), 4)

    def test_refused_shape_without_a_hint(self):
        """No bend hint: the warning names what blocks every bend of the shape and asks for a
        wider gap instead of a bend value."""
        spec, geom = self.setup(blocker=False)
        spec.nodes["y"].row = "s"
        geom.nodes["y"] = M.NodeGeom("y", 500, 400, M.Box(476, 376, 524, 424),
                                     [M.TextLine("Y", 500, 442, 14, K.INK, "", "middle")])
        for i, cy in enumerate((262, 334)):            # two icons with wide labels fill the gutter
            nid = f"z{i}"
            spec.nodes[nid] = M.Node(nid, "service/Amazon-S3", "Z", xy=(300.0, float(cy)))
            geom.nodes[nid] = M.NodeGeom(nid, 300, cy, M.Box(276, cy - 24, 324, cy + 24),
                                         [M.TextLine("a wide label for z", 300, cy + 42, 14, K.INK, "", "middle")])
        spec.edges = [M.Edge(0, "x", "y", "--", src="edges[0]", shape="VHV")]
        warns = R.draw(spec, geom)[1]
        w = [m for m in warns if "refusing the requested shape: VHV" in m]
        self.assertEqual(len(w), 1, warns)
        self.assertRegex(w[0], r"^edges\[0\][^:]*: drew \S+ instead of VHV, refusing the requested shape: VHV — "
                               r"LINE OVER (ICON|TEXT)")
        self.assertNotIn("bend_y", w[0])
        self.assertIn("try widen the gap between the ends (min_gap_before / pad) so a VHV has a clean bend", w[0])

    def test_refused_shape_that_cannot_fit(self):
        """Ends too close for the shape's bend (no candidate of it at all): the warning says
        none fits; with from_side / to_side the request is named as such."""
        spec, geom = self.setup(blocker=False)
        spec.nodes["y"].row = "s"
        geom.nodes["y"] = M.NodeGeom("y", 500, 288, M.Box(476, 264, 524, 312),
                                     [M.TextLine("Y", 500, 330, 14, K.INK, "", "middle")])
        for kw, asked in (({"shape": "VHV"}, "shape: VHV"),
                          ({"from_side": "bottom", "to_side": "top"}, "from_side / to_side → VHV")):
            with self.subTest(asked=asked):
                spec.edges = [M.Edge(0, "x", "y", "--", src="edges[0]", **kw)]
                warns = R.draw(spec, geom)[1]
                w = [m for m in warns if "refusing" in m]
                self.assertEqual(len(w), 1, warns)
                self.assertIn(f"refusing the requested {asked} — no VHV fits between the two ends "
                              f"(no free stretch for its bend); try widen the gap", w[0])

    def test_bend_avoids_label(self):
        """HVH: the vertical leg keeps out of a label standing in the gutter."""
        spec, geom = self.setup(blocker=False)
        spec.nodes["y"].row = "s"
        geom.nodes["y"] = M.NodeGeom("y", 500, 400, M.Box(476, 376, 524, 424), [M.TextLine("Y", 500, 442, 14, K.INK, "", "middle")])
        geom.nodes["w"] = M.NodeGeom("w", 380, 300, M.Box(356, 276, 404, 324),
                                     [M.TextLine("a wide label here", 380, 342, 14, K.INK, "", "middle")])
        spec.nodes["w"] = M.Node("w", "service/Amazon-S3", "a wide label here", col="m", row="r", xy=(380, 300))
        els, warns = R.draw(spec, geom)
        pts = points(lines_of(els, 0)[0])
        self.assertEqual(R.shapes(spec)[0], "HVH")
        x = pts[1][0]
        lab = geom.nodes["w"].lines[0].box()
        self.assertFalse(lab.x0 - 4 < x < lab.x1 + 4 or 352 < x < 408, x)
        self.assertEqual(warns, [])

    def test_same_side_hvh_out_and_back(self):
        """HVH right → right between two nodes of one column, no bend_x: the line goes out
        of both right sides and back, its leg clear of the wide label and HUG_CLEAR inside
        the box holding both ends (not a U round the other side)."""
        spec, geom = self.setup(blocker=False)
        spec.groups = {"sn": M.Group("sn", "private", label=None, nodes=["x", "y"])}
        spec.nodes["x"].parent = spec.nodes["y"].parent = "sn"
        spec.nodes["x"].label = "a very wide label"
        spec.nodes["y"].col, spec.nodes["y"].row = "a", "s"
        geom.groups = {"sn": M.GroupGeom("sn", M.Box(40, 150, 220, 470))}
        geom.nodes["x"].lines = [M.TextLine("a very wide label", 100, 242, 14, K.INK, "", "middle")]
        geom.nodes["y"] = M.NodeGeom("y", 100, 400, M.Box(76, 376, 124, 424),
                                     [M.TextLine("Y", 100, 442, 14, K.INK, "", "middle")])
        spec.edges = [M.Edge(0, "x", "y", "->", shape="HVH", from_side="right", to_side="right")]
        els, warns = R.draw(spec, geom)
        pts = points(lines_of(els, 0)[0])
        self.assertEqual(len(pts), 4, pts)
        port = 124 + K.END_GAP
        self.assertEqual((pts[0], pts[-1]), ((port, 200), (port, 400)))
        bend = pts[1][0]
        self.assertEqual(pts[2][0], bend)
        self.assertGreaterEqual(bend, port + K.MIN_ARROW)
        self.assertGreaterEqual(bend, geom.nodes["x"].lines[0].box(conservative=True).x1 + 4)
        self.assertLessEqual(bend, 220 - K.HUG_CLEAR)
        self.assertFalse(any("instead of" in w for w in warns), warns)
        # a box edge 196: the leg still fits past the label, HUG_CLEAR off the border
        geom.groups["sn"] = M.GroupGeom("sn", M.Box(40, 150, 196, 470))
        pts = points(lines_of(R.draw(spec, geom)[0], 0)[0])
        self.assertEqual(pts[1][0], bend)
        self.assertLessEqual(bend, 196 - K.HUG_CLEAR)
        # 180: no spot past the label 12 inside the border, so no out-and-back is drawn
        # (not one hugging the border or crossing the label); the warning says which pad
        # gives the leg room, not "widen the gap between the ends"
        geom.groups["sn"] = M.GroupGeom("sn", M.Box(40, 150, 180, 470))
        els, warns = R.draw(spec, geom)
        pts = points(lines_of(els, 0)[0])
        self.assertTrue(all(p[0] <= 180 - K.HUG_CLEAR for p in pts), pts)
        self.assertNotEqual(len(pts), 4, pts)
        w, = [w for w in warns if "instead of HVH" in w]
        self.assertIn("no room right of both ends inside sn", w)
        self.assertIn("give sn pad_right", w)
        self.assertNotIn("between the ends", w)

    def test_same_side_needs_a_side_along_the_shape(self):
        """An out-and-back only on a side the shape's end pieces leave along: HVH top / top
        is no out-and-back (the loader rejects it; a Spec built by hand gets the plain HVH
        search, no horizontal piece off a top port)."""
        spec, _ = self.setup(blocker=False)
        spec.nodes["y"].col, spec.nodes["y"].row = "a", "s"
        spec.edges = [M.Edge(0, "x", "y", "->", shape="HVH", from_side="top", to_side="top")]
        self.assertFalse(R._same_side("HVH", "top", "top"))
        self.assertFalse(R._same_side("VHV", "left", "left"))
        self.assertTrue(R._same_side("VHV", "bottom", "bottom"))
        self.assertEqual([r for r in R.plan(spec) if "out-and-back" in r.why], [])

    def test_same_side_needs_ends_apart_along_the_leg(self):
        """A HVH right / right whose ends share a row (VHV top / top sharing a column) has no
        leg to run out and back: no out-and-back, no room for one in plan(), and a Spec built
        by hand (the loader rejects it: same_side_problems) gets no 'move the ends off the
        canvas right edge' hint for a leg that cannot exist."""
        self.assertFalse(R._same_side("HVH", "right", "right", 0))
        self.assertFalse(R._same_side("VHV", "top", "top", 0))
        self.assertTrue(R._same_side("HVH", "right", "right", 1))
        self.assertTrue(R._same_side("VHV", "top", "top", -1))
        self.assertTrue(R._same_side("HVH", "right", "right", None))      # position unknown: as before
        spec, geom = self.setup(blocker=False)
        spec.edges = [M.Edge(0, "x", "y", "->", shape="HVH", from_side="right", to_side="right", src="edges[0]")]
        self.assertEqual([r for r in R.plan(spec) if "out-and-back" in r.why], [])
        (where, msg), = R.same_side_problems(spec)
        self.assertEqual(where, "edges[0] x -> y")
        self.assertIn("needs ends on different rows, but x and y share a row", msg)
        _, warns = R.draw(spec, geom)
        self.assertFalse([w for w in warns if "off the canvas" in w or "pad_right" in w], warns)
        # on different rows: an out-and-back, and nothing for the loader to report
        spec.nodes["y"].col, spec.nodes["y"].row = "a", "s"
        self.assertEqual(R.same_side_problems(spec), [])
        self.assertTrue([r for r in R.plan(spec) if "out-and-back" in r.why])



class Lanes(unittest.TestCase):
    """Instances of one `.*` line whose legs would share a bend run in lanes of their own
    (review: EC2 ×2 → a bottom-aligned flow-column CloudWatch, both legs on x=462 for
    272px); a `trunk: true` line still merges on one leg."""

    def setup(self, **edge):
        spec = M.Spec("t", cols=[M.Track("a", "col", 0), M.Track("b", "col", 1)],
                      rows=[M.Track("r", "row", 0), M.Track("s", "row", 1), M.Track("t", "row", 2)])
        spec.nodes = {"x1": M.Node("x1", "service/Amazon-EC2", "X1", col="a", row="r"),
                      "x2": M.Node("x2", "service/Amazon-EC2", "X2", col="a", row="s"),
                      "y": M.Node("y", "service/Amazon-CloudWatch", "Y", col="b", row="t")}
        spec.edges = [M.Edge(0, "x1", "y", "..>", line=0, k=0, src="edges[0]", **edge),
                      M.Edge(1, "x2", "y", "..>", line=0, k=1, src="edges[0]", **edge)]
        cols, rows = {"a": 100, "b": 400}, {"r": 100, "s": 250, "t": 400}
        nodes = {}
        for nid, n in spec.nodes.items():
            cx, cy = cols[n.col], rows[n.row]
            icon = M.Box(cx - 24, cy - 24, cx + 24, cy + 24)
            nodes[nid] = M.NodeGeom(nid, cx, cy, icon, [M.TextLine(n.label, cx, icon.y1 + 18, 14, K.INK, "", "middle")])
        return spec, M.Geometry("document", 48, 520, 500, cols, rows, nodes=nodes)

    def legs(self, els):
        return [points(lines_of(els, n)[0]) for n in (0, 1)]

    def test_each_instance_its_own_lane(self):
        spec, geom = self.setup()
        self.assertEqual(R.shapes(spec), {0: "HVH", 1: "HVH"})
        els, warns = R.draw(spec, geom)
        a, b = self.legs(els)
        self.assertEqual(len(a), 4)
        self.assertEqual(len(b), 4)
        self.assertEqual(abs(a[1][0] - b[1][0]), R.LANE_PITCH, (a, b))
        # ordered so they don't cross: the upper source's leg runs outside (nearer the target)
        self.assertGreater(a[1][0], b[1][0])
        self.assertEqual(R._crossings([a, b]), 0)
        self.assertFalse([w for w in warns if "instead of" in w], warns)
        root = ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 500">'
                             + "".join(f'<polyline points="{" ".join(f"{x:g},{y:g}" for x, y in p)}" fill="none" '
                                       'stroke="#232F3E"/>' for p in (a, b)) + "</svg>")
        self.assertEqual([i for i in CL.run_checks(root) if i.kind == "LINE ON LINE"], [])

    def test_trunk_instances_merge(self):
        spec, geom = self.setup(trunk=True)
        a, b = self.legs(R.draw(spec, geom)[0])
        self.assertEqual(a[1][0], b[1][0])                  # one leg: the follower stops on it
        self.assertEqual(b[-1], (a[1][0], a[-1][1]))

    def test_plan_reserves_the_lanes(self):
        spec, _ = self.setup()
        self.assertEqual(R.lane_counts(spec), {0: 2, 1: 2})
        with_lanes = {r.why: r.d for r in R.plan(spec) if "bend gutter" in r.why and not r.soft}
        with unittest.mock.patch.object(R, "lane_counts", return_value={}):
            without = {r.why: r.d for r in R.plan(spec) if "bend gutter" in r.why and not r.soft}
        self.assertEqual(sorted(with_lanes), sorted(without))
        for why, d in with_lanes.items():
            self.assertEqual(d, without[why] + R.LANE_PITCH, why)
        spec.edges = [M.Edge(e.n, e.a, e.b, e.op, line=e.line, k=e.k, trunk=True) for e in spec.edges]
        self.assertEqual(R.lane_counts(spec), {})

    def test_fan_to_both_sides_shares_its_bend(self):
        """One source to targets above and below: the legs meet only at the source, one bend."""
        spec, geom = self.setup()
        spec.edges = [M.Edge(0, "x2", "x1", "->", line=0, k=0), M.Edge(1, "x2", "y", "->", line=0, k=1)]
        spec.nodes["x1"].col = "b"
        geom.nodes["x1"] = M.NodeGeom("x1", 400, 100, M.Box(376, 76, 424, 124),
                                      [M.TextLine("X1", 400, 142, 14, K.INK, "", "middle")])
        self.assertEqual(R.lane_counts(spec), {})
        a, b = self.legs(R.draw(spec, geom)[0])
        self.assertEqual(a[1][0], b[1][0])


class DetourPorts(unittest.TestCase):
    """A detour (U) or alternative shape ending on a side another edge's chosen shape uses
    takes a port of its own there, not the center (review: alb -> ec2.2's UHVH came back
    into EC2's right side at (382,426), the point ec2.2 ..> cw leaves from, 48px on top of
    it: the solid line read as carrying on as the dashed one)."""

    def setup(self):
        spec = M.Spec("t", cols=[M.Track("a", "col", 0), M.Track("m", "col", 1), M.Track("b", "col", 2),
                                 M.Track("c", "col", 3)],
                      rows=[M.Track("r", "row", 0)])
        spec.nodes = {i: M.Node(i, "service/Amazon-EC2", i.upper(), col=c, row="r")
                      for i, c in (("x", "a"), ("z", "m"), ("y", "b"), ("w", "c"))}
        spec.edges = [M.Edge(0, "x", "y", "->", line=0), M.Edge(1, "y", "w", "..>", line=1)]
        cols, rows = {"a": 100, "m": 300, "b": 500, "c": 700}, {"r": 200}
        nodes = {}
        for nid, n in spec.nodes.items():
            cx, cy = cols[n.col], rows[n.row]
            icon = M.Box(cx - 24, cy - 24, cx + 24, cy + 24)
            nodes[nid] = M.NodeGeom(nid, cx, cy, icon, [M.TextLine(n.label, cx, icon.y1 + 18, 14, K.INK, "", "middle")])
        geom = M.Geometry("document", 48, 800, 400, cols, rows, nodes=nodes)
        ctx = R._Ctx(spec, geom)
        topo = R._topology(spec)
        xs = {e.n: R._Edge(ctx, e, topo[e.n]) for e in spec.edges}
        ports = R._assign_ports(ctx, xs)
        ctx.side_use = R._side_use(xs, ports)
        return ctx, xs, ports

    def test_u_end_beside_the_next_flows_port(self):
        ctx, xs, ports = self.setup()
        x = xs[0]
        self.assertEqual(ctx.side_use[("y", "right")], [(1, "a", 0.0, 1, False)])
        us = {}
        for shape, pa, pb, bend in R._detours(ctx, x, ports):
            us.setdefault((shape, pb[0] > 524), (pa, pb))
        pa, pb = us[("UHVH", True)]                     # right / right: into y's right side
        self.assertEqual(pb, (528, 200 - K.PORT_PITCH))  # y → w leaves from (528, 200)
        pa, pb = us[("UHVH", False)]                    # left / left: y's left is x → y's own side
        self.assertEqual(pb[1], 200)
        self.assertTrue(R._u_taken(ctx, x, "UHVH", (128, 200), (528, 188)))
        self.assertFalse(R._u_taken(ctx, x, "UVHV", (100, 172), (500, 172)))

    def test_drawn_detour_never_lands_on_the_next_flows_start(self):
        """Every candidate x → y has: none ends where y → w starts."""
        ctx, xs, ports = self.setup()
        for shape, pa, pb, bend in R._candidates(ctx, xs[0], ports):
            self.assertNotEqual(pb, (528, 200), shape)

    def test_side_offset_falls_back_inside_the_icon(self):
        ctx, xs, ports = self.setup()
        ctx.side_use[("y", "right")] = [(1, "a", -12.0, 1, False), (2, "a", 12.0, 2, False)]
        self.assertEqual(R._end_off(ctx, xs[0], "b", "right", ports), 0.0)    # ±24 is off the icon
        ctx.side_use[("y", "right")] = [(1, "a", -8.0, 1, False)]
        self.assertEqual(R._end_off(ctx, xs[0], "b", "right", ports), -20.0)
        ctx.side_use[("y", "right")] = [(1, "a", -16.0, 1, False)]
        self.assertEqual(R._end_off(ctx, xs[0], "b", "right", ports), -4.0)

    def test_drawn_fallbacks_count_and_trunk_mates_do_not(self):
        """A port a route already drew on a side its chosen shape does not use (drawn_use)
        is taken like a planned one; the instances of x's own trunk line share it."""
        ctx, xs, ports = self.setup()
        x = xs[0]
        ctx.drawn_use[("y", "top")] = [(5, "a", 0.0, 5, False)]
        self.assertEqual(R._side_taken(ctx, x, "b", "top"), [0.0])
        self.assertNotEqual(R._end_off(ctx, x, "b", "top", ports), 0.0)
        x.e.trunk = True
        ctx.drawn_use[("y", "top")] = [(5, "a", 0.0, x.e.line, True)]
        self.assertEqual(R._side_taken(ctx, x, "b", "top"), [])
        self.assertEqual(R._end_off(ctx, x, "b", "top", ports), 0.0)

    def test_crowded_side_finds_a_free_spot(self):
        """The fourth line onto a 48px side (0, then ±12 taken, ±24 off the icon) takes the
        widest free gap, never a taken port."""
        ctx, xs, ports = self.setup()
        ctx.drawn_use[("y", "top")] = [(5, "a", 0.0, 5, False), (6, "a", 12.0, 6, False), (7, "a", -12.0, 7, False)]
        self.assertEqual(R._end_off(ctx, xs[0], "b", "top", ports), -20.0)     # toward x (left)
        # a pitch clear of every port: the center between ±12 ...
        ctx.drawn_use[("y", "top")] = [(6, "a", 12.0, 6, False), (7, "a", -12.0, 7, False)]
        self.assertEqual(R._end_off(ctx, xs[0], "b", "top", ports), 0.0)
        # ... or, packed tighter than a pitch, the widest gap, never a taken port
        taken = [float(v) for v in range(-18, 19, 3)]
        ctx.drawn_use[("y", "top")] = [(10 + i, "a", o, 10 + i, False) for i, o in enumerate(taken)]
        v = R._end_off(ctx, xs[0], "b", "top", ports)
        self.assertEqual(v, -20.0)
        ctx.drawn_use[("y", "top")] = [(10 + i, "a", o, 10 + i, False)
                                       for i, o in enumerate([-20.0, -16.0, -8.0, 0.0, 8.0, 16.0, 20.0])]
        v = R._end_off(ctx, xs[0], "b", "top", ports)
        self.assertEqual(v, -4.0)                       # gaps of 8: the middle nearest the center, toward x


if __name__ == "__main__":
    unittest.main(verbosity=2)
