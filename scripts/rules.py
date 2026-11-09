#!/usr/bin/env python3
"""Judge a layout.py draft against the user's rules — report only (nothing here changes a
draft or the engine's choices).

    import rules
    rules.check(spec, geom, draft) -> [Violation]      # spec: layout_model.Spec, geom: its
                                                       # Geometry, draft: the written SVG bytes

The rules (tests/corpus/MANIFEST.yaml names them; the design is rules-design.md §1):

  R-flow   the flow reads as the spec says. F0 every connector piece is horizontal or
           vertical. F1 two connectors of different nets run on top of each other
           (check_layout.lines_on_lines) and F2 two spec lines lie on one line through a gap
           (check_layout.lines_in_line) — check_layout reports both as LINE ON LINE too.
           F3 two connectors of different flows (data-flow) cross within JUNCTION_REACH of a
           bend of either or of a node either ends at (read as a junction or a turn). F4 an
           arrowhead ends on what the spec points it at: a node's footprint (end_icon) with no
           other footprint within ICON_CLEAR, or a group's border within END_REACH with no
           other border nearer than BORDER_CLEAR. F5 an edge's label set and each badge sit
           within LABEL_REACH of its net (check_layout.joined: a trunk, a bus and its drops),
           and no other line is within TEXT_GAP of as close; a label or badge the spec places
           (label_at / step_at a point) is exempt (user decision). F3 measures to the end
           nodes' icon boxes. F6 a connector runs over a node's icon body or its name block
           (label and sub lines) — LINE OVER ICON / LINE OVER TEXT's boxes, owned by (edge,
           node), one per pair, with a `try:` value; the edge's own end nodes are exempt only
           for the attach piece (the one ending on that node) while it runs at most
           ATTACH_DEPTH into the icon. Group titles / CIDR lines (B2), edge labels and badges
           (F5, R-label) are not counted (user decision 2026-11-09, line-cross spec).
  R-rt     a route table with `for:` (Node.assoc) sits beside what it is associated with.
           With a hub (the TGW) and associated lines A, the others at the hub N: RT1 (|A| ≥
           2) its centre is inside the bracket A's lines draw (bracket()), or, when every line
           at the hub is associated with it (the hub's only table), it is within S +
           sibling_gap of the hub (user decision); RT2 (|A| = 1) its footprint is within
           rt2_reach (2S + sibling_gap, user decision) of that line, reached without crossing
           another line; RT3 the segment
           from its centre to the hub's crosses no line of N nor of another hub (except
           within RT_HUB_CLEAR of the hub's icon); RT4 it is nearer the hub than any other
           hub and any far end of N. A subnet association (no hub, every end a subnet box):
           RT5 nearer each associated subnet than any other subnet by RT_SUBNET_MARGIN, and
           inside none of the others. A table without `for:`, or without a hub and with
           other ends, is not judged.
  R-twin   twins (layout_solve.twin_classes: boxes of one structure) are drawn alike: each
           measure, and each node centre from the twin's left / top edge, within TWIN_TOL
           (TW). TWR boxes that would be twins but for the order of their rows
           (layout_solve.twin_row_orders: the engine keeps the spec's row order), with the
           row order to write; one per box out of the majority order (user decision
           2026-11-08, after timing-mirrored-az-rows).
  R-label  L1 a connector label set (auto-placed: no label_at) sits above a horizontal or
           right of a vertical own piece it is within LABEL_REACH of (else the nearest), or
           on one over a background — any of them near a corner (user decision); L2 the step
           badges drawn are the edges' resolved steps (each note row once, or on each
           instance with step_each / steps), and every note row has one.
  R-border a connector does not read as part of a group's box. B1 a piece runs alongside a
           container border closer than HUG_CLEAR for more than HUG_OVERLAP (read as the
           border): check_layout.line_hugs, the predicate of its LINE HUGS BORDER. B2 a piece
           passes through a group's header band (header_bands: from the box's left edge to
           the end of what its <g> draws — badge, title, CIDR line — top border to their bottom),
           most often between the badge and the title, where check_layout's LINE OVER ICON,
           LINE OVER TEXT and LINE NEAR TEXT do not reach (flowcol/t7-xyref slide: ALB →
           AZ2 EC2 at x=308 between the App subnet's badge and its title). Both predicates
           come from check_layout, which reports B2 as LINE IN HEADER for engine feedback.
           B3 a node/group lies outside its declared parent; B4 a node/group intersects
           a sibling container. Overlays and nodes deliberately on: a border are exempt.
  R-fit    the smallest drawn text meets its medium's target (slide pt / document px;
           effective_text, tier 2; cost: the size short).

User decisions (2026-11-07, rules-design §6, after the tgw / nlb-mtls / latest2 cases): the
RT1 only-table pass, the F5 exemption for spec-placed labels and badges and L1's any-nearby-
piece side test above; after rt2.png the RT2 reach of 2S + sibling_gap (was S + sibling_gap);
after hug.png the border hug and the header band crossing as the tier-0 rule R-border.

Violation(rule, owners, message, cost, tier, code): owners are draft element ids (edge:3,
node:rtsp, group:vpca, canvas, note); tier 0 a hard rule, 2 the slide fit. score() orders
candidate drafts with critical canvas clipping first, for selection and later stages. corpus() is tests/run_corpus.py's
--rule-checker hook. Thresholds and helpers come from check_layout / layout_const; only the
concepts new here are defined here.
"""
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_layout as CL  # noqa: E402
import layout_const as K  # noqa: E402
from layout_text import scaled_spec  # noqa: E402
import layout_model as M  # noqa: E402
import layout_solve  # noqa: E402
from layout_spec import SUBNET_TYPES  # noqa: E402

TIER_HARD = 0
TIER_FIT = 2
# F3: a crossing this close to a bend or an end node reads as a junction (one port pitch).
JUNCTION_REACH = K.PORT_PITCH
# RT3: crossings this close to the hub's icon are its ports' own fan, not in the way.
RT_HUB_CLEAR = K.PORT_PITCH
# RT5: a subnet table is nearer its own subnet than any other by at least this much.
RT_SUBNET_MARGIN = 8
# R-twin: twins' measures may differ by rounding only (layout_solve twins_unlike's 0.5).
TWIN_TOL = 0.5
# a piece is horizontal / vertical when it is off by less than this (check_layout's 0.5)
STRAIGHT = 0.5
# RT2: a table with one associated line is within this many icon sizes S, plus sibling_gap,
# of that line (document 2·48 + 16 = 112, slide 2·48 + 12 = 108). User decision 2026-11-07
# (rules-design §6, after rt2.png): was 1 (64 / 60); rt/single 88 and rt/hub 97 pass, the
# rt/nd-single document's 135 stays a violation.
RT2_REACH_ICONS = 2
# F6: the piece that reaches its own end's icon may run this far inside the (2px-shrunk)
# icon box, where it attaches. On main 601099d every attach piece in the corpus runs 0px in
# but privatelink edge:12 (44px, through its own S3), so 4 (LINE_CLEAR) lets a hand-placed
# end sit a few px in and still catches a line drawn to the icon's middle
# (docs/dev/line-cross/results/01-report-line-over-node.md).
ATTACH_DEPTH = K.LINE_CLEAR
# F6 try: a moved piece keeps this far from the crossed node's footprint (ICON_CLEAR).
OVER_CLEAR = CL.ICON_CLEAR

Pt = Tuple[float, float]
BoxT = Tuple[float, float, float, float]


@dataclass(frozen=True)
class Violation:
    rule: str                   # R-flow | R-rt | R-twin | R-label | R-border | R-fit
    owners: Tuple[str, ...]     # draft element ids it names ("edge:3", "node:rtsp", "group:vpca", "canvas")
    message: str
    cost: float = 1.0           # how far off (px, pt, or 1 for a yes/no predicate)
    tier: int = TIER_HARD       # 0 hard, 2 slide fit
    code: str = ""              # the predicate (F1, RT1, L2, ...)
    # F6: (p, q, footprint box) of the piece over the crossed node and that node's footprint
    # (icon and name block), for selection's channel-widening move; not part of the identity.
    at: Tuple = field(default=(), compare=False)

    def as_dict(self) -> dict:
        return {"rule": self.rule, "code": self.code, "owners": ",".join(self.owners),
                "msg": self.message, "cost": round(self.cost, 2), "tier": self.tier}


def _f(v: float) -> str:
    return CL.fnum(v)


# =======================================================================================
# The drawn draft: check_layout.collect once, with each element's owner (<g id>)

class Drawn:
    """What a draft draws, by owner: connectors (paths: id(element) → segments, each path's
    edge number), edge labels / on-line labels / badges per edge, node icons and footprints,
    group rects."""

    def __init__(self, root: ET.Element):
        self.root = root
        self.texts, self.segs, self.masks, self.icons, self.canvas = CL.collect(root)
        owner = CL.group_owners(root)
        self.owner = owner
        self.paths: Dict[int, List[dict]] = {}
        for s in self.segs:
            if s["kind"] == "connector":
                self.paths.setdefault(id(s["el"]), []).append(s)
        self.path_edge: Dict[int, Optional[int]] = {}
        self.edge_paths: Dict[int, List[int]] = {}
        for pid, run in self.paths.items():
            kind, ref, _ = _split(owner.get(pid, ""))
            n = int(ref) if kind == "edge" and ref.isdigit() else None
            self.path_edge[pid] = n
            if n is not None:
                self.edge_paths.setdefault(n, []).append(pid)
        self.labels: Dict[int, List[dict]] = {}      # edge:n:label texts
        self.on_line: Dict[int, List[dict]] = {}     # edge:n:masked texts (on the line over a background)
        self.badges: Dict[int, List[Tuple[BoxT, str]]] = {}   # edge:n:badge (circle box, digit)
        for t in self.texts:
            kind, ref, part = _split(owner.get(id(t["el"]), ""))
            if kind != "edge" or not ref.isdigit():
                continue
            if part == "label":
                self.labels.setdefault(int(ref), []).append(t)
            elif part == "masked":
                self.on_line.setdefault(int(ref), []).append(t)
        self.node_icon: Dict[str, dict] = {}
        for i in self.icons:
            kind, ref, part = _split(owner.get(id(i["el"]), ""))
            if kind == "edge" and part == "badge" and ref.isdigit() and i["el"].tag == CL.NS + "circle":
                digit = "".join(t["s"] for t in self.texts if owner.get(id(t["el"])) == owner[id(i["el"])]
                                and CL.contains(i["box"], t["box"], 2))
                self.badges.setdefault(int(ref), []).append((i["box"], digit))
            elif kind == "node" and not i["badge"] and not part:
                self.node_icon.setdefault(ref, i)
        # as check_layout.run_checks: a connector end attaches to a node's footprint over all of
        # its lines; its own lines are node_stacks
        self.feet = CL.footprints(self.icons, self.texts)
        self.stacks = CL.node_stacks(self.icons, self.texts, self.segs, feet=self.feet)
        node_of = {id(i): nid for nid, i in self.node_icon.items()}
        self.foot: Dict[str, BoxT] = {node_of[id(i)]: b for i, b in self.feet if id(i) in node_of}
        self.icon_node = {id(i): nid for nid, i in self.node_icon.items()}
        self.net = CL.joined(self.paths)          # id(element) → net number (check_layout's joins)
        self.rects = CL.container_rects(root)
        self.group_rect: Dict[str, BoxT] = {}
        for r in self.rects:
            kind, ref, part = _split(owner.get(id(r[4]), ""))
            if kind == "group" and not part:
                self.group_rect.setdefault(ref, (r[0], r[1], r[0] + r[2], r[1] + r[3]))

    @classmethod
    def parse(cls, draft: bytes) -> "Drawn":
        return cls(ET.fromstring(draft))

    def eid(self, pid: int) -> str:
        """The owner id of a connector (its <g id>, "edge:n"), or "?"."""
        return self.owner.get(pid, "?")

    def points(self, pid: int) -> List[Pt]:
        run = self.paths[pid]
        return [run[0]["p"]] + [s["q"] for s in run]

    def edge_segs(self, n: int) -> List[dict]:
        return [s for pid in self.edge_paths.get(n, ()) for s in self.paths[pid]]


def _split(gid: str) -> Tuple[str, str, str]:
    parts = gid.split(":")
    return (parts[0], parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else "")


# =======================================================================================
# geometry

def _pt_box(p: Pt, b: BoxT) -> float:
    return math.hypot(max(b[0] - p[0], 0, p[0] - b[2]), max(b[1] - p[1], 0, p[1] - b[3]))


def _box_box(a: BoxT, b: BoxT) -> float:
    return math.hypot(max(b[0] - a[2], 0, a[0] - b[2]), max(b[1] - a[3], 0, a[1] - b[3]))


def _pt_seg(p: Pt, a: Pt, b: Pt) -> Tuple[float, Pt]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy or 1.0)))
    q = (a[0] + t * dx, a[1] + t * dy)
    return math.hypot(q[0] - p[0], q[1] - p[1]), q


def _box_seg(b: BoxT, s: dict) -> float:
    p, q = s["p"], s["q"]
    if CL.seg_hits_box(p, q, b) or CL.contains(b, (*p, *p), 0) or CL.contains(b, (*q, *q), 0):
        return 0.0
    corners = ((b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3]))
    return min([_pt_box(p, b), _pt_box(q, b)] + [_pt_seg(c, p, q)[0] for c in corners])


def _border_dist(p: Pt, r: BoxT) -> float:
    """Distance from p to rect r's border (from inside or outside)."""
    if r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]:
        return min(p[0] - r[0], r[2] - p[0], p[1] - r[1], r[3] - p[1])
    return _pt_box(p, r)


def rt2_reach(spec) -> float:
    """RT2's limit: RT2_REACH_ICONS × S + sibling_gap (user decision 2026-11-07)."""
    return RT2_REACH_ICONS * spec.S + spec.const.sibling_gap


def _centre(b: BoxT) -> Pt:
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def _corners(b: BoxT) -> List[Pt]:
    return [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])]


def _horiz(s: dict) -> bool:
    return abs(s["p"][1] - s["q"][1]) < STRAIGHT and abs(s["p"][0] - s["q"][0]) >= STRAIGHT


def _vert(s: dict) -> bool:
    return abs(s["p"][0] - s["q"][0]) < STRAIGHT and abs(s["p"][1] - s["q"][1]) >= STRAIGHT


def ortho_cross(s: dict, o: dict) -> Optional[Pt]:
    """Where a horizontal and a vertical piece cross, strictly inside both (layout_route
    _crossings' test), else None."""
    for v, h in ((s, o), (o, s)):
        if _vert(v) and _horiz(h):
            x, y = v["p"][0], h["p"][1]
            if min(h["p"][0], h["q"][0]) + STRAIGHT < x < max(h["p"][0], h["q"][0]) - STRAIGHT \
                    and min(v["p"][1], v["q"][1]) + STRAIGHT < y < max(v["p"][1], v["q"][1]) - STRAIGHT:
                return (x, y)
    return None


def seg_cross(a: Pt, b: Pt, c: Pt, d: Pt) -> Optional[Pt]:
    """Where segments a–b and c–d meet (any angle; touching counts, collinear does not)."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (a[0] + t * r[0], a[1] + t * r[1])
    return None


def inside(p: Pt, poly: Sequence[Pt]) -> bool:
    """Even-odd point in polygon."""
    x, y = p
    n, hit = len(poly), False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def hull(pts: Sequence[Pt]) -> List[Pt]:
    """Convex hull (monotone chain), counter-clockwise; fewer than 3 points come back as given."""
    ps = sorted(set(pts))
    if len(ps) < 3:
        return ps

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, hi = [], []
    for p in ps:
        while len(lo) >= 2 and turn(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(ps):
        while len(hi) >= 2 and turn(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


# =======================================================================================
# R-flow

def _flow(d: Drawn, pid: int) -> Optional[str]:
    return CL.flow_of(d.paths[pid])


def flow_rules(spec, d: Drawn) -> List[Violation]:
    out: List[Violation] = []
    # F0: right-angle connectors only
    for pid, run in d.paths.items():
        bad = [s for s in run if not (_horiz(s) or _vert(s))
               and math.hypot(s["q"][0] - s["p"][0], s["q"][1] - s["p"][1]) >= STRAIGHT]
        if bad:
            s = bad[0]
            out.append(Violation("R-flow", (d.eid(pid),), f"F0 {_name(spec, d.eid(pid))}: diagonal piece "
                                 f"{CL.fmt(s)} — "
                                 "connectors run horizontal and vertical only", len(bad), code="F0"))
    # F1 / F2: check_layout's own LINE ON LINE predicates (masked runs aside, as it does)
    on = CL.lines_on_lines(d.paths)
    for s, o, dd in on:
        if _masked(d, s, o):
            continue
        a, b = d.eid(id(s["el"])), d.eid(id(o["el"]))
        out.append(Violation("R-flow", (a, b), f"F1 {_name(spec, a)} runs on top of {_name(spec, b)} "
                             f"for {_f(dd)}px "
                             f"({CL.fmt(s)} / {CL.fmt(o)}): two flows read as one line", dd, code="F1"))
    seen = {(id(s["el"]), id(o["el"])) for s, o, _ in on}
    for s, o, dd in CL.lines_in_line(d.paths, seen):
        if _masked(d, s, o):
            continue
        a, b = d.eid(id(s["el"])), d.eid(id(o["el"]))
        out.append(Violation("R-flow", (a, b), f"F2 {_name(spec, a)} lies on one line with {_name(spec, b)}, "
                             f"{_f(dd)}px apart "
                             f"({CL.fmt(s)} / {CL.fmt(o)}): read as one line through the gap", 1.0, code="F2"))
    out += _junctions(spec, d)
    out += _tips(spec, d)
    out += _attribution(spec, d)
    out += _over_nodes(spec, d)
    return out


def _masked(d: Drawn, s: dict, o: dict) -> bool:
    box = CL.union(CL.seg_box(s), CL.seg_box(o))
    return CL.masked((box[0], box[1], box[2] + 0.1, box[3] + 0.1), min(s["o"], o["o"]), d.masks)


def _end_boxes(d: Drawn, pid: int) -> List[BoxT]:
    """The icon boxes of the nodes a connector ends at (found by end_icon on the footprints;
    F3 measures to the icon, not its caption)."""
    pts = d.points(pid)
    out = []
    for pt in (pts[0], pts[-1]):
        i = CL.end_icon(pt, d.feet)
        if i is not None:
            out.append(i["box"])
    return out


def _junctions(spec, d: Drawn) -> List[Violation]:
    """F3: two flows crossing at a bend or at a node one of them ends at."""
    out = []
    ids = list(d.paths)
    bends = {pid: d.points(pid)[1:-1] for pid in ids}
    ends = {pid: _end_boxes(d, pid) for pid in ids}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if not CL.two_flows(d.paths[a], d.paths[b]):
                continue
            hit = None
            for s in d.paths[a]:
                for o in d.paths[b]:
                    c = ortho_cross(s, o)
                    if c is None:
                        continue
                    bend = next((v for v in bends[a] + bends[b] if math.dist(v, c) <= JUNCTION_REACH), None)
                    end = next((bx for bx in ends[a] + ends[b] if _pt_box(c, bx) <= JUNCTION_REACH), None)
                    if bend or end:
                        hit = (c, "a bend at " + f"({_f(bend[0])},{_f(bend[1])})" if bend else "a node it ends at")
                        break
                if hit:
                    break
            if hit:
                ea, eb = d.eid(a), d.eid(b)
                c, why = hit
                out.append(Violation("R-flow", (ea, eb), f"F3 {_name(spec, ea)} crosses {_name(spec, eb)} at "
                                     f"({_f(c[0])},{_f(c[1])}) within "
                                     f"{JUNCTION_REACH}px of {why}: the crossing reads as a junction", 1.0, code="F3"))
    return out


def _tips(spec, d: Drawn) -> List[Violation]:
    """F4: each arrowhead ends on the node / group the spec points it at."""
    out = []
    for e in spec.edges:
        for pid in d.edge_paths.get(e.n, ()):
            run = d.paths[pid]
            pts = d.points(pid)
            for k, tip, target, kind in ((0, pts[0], e.a, e.a_kind), (1, pts[-1], e.b, e.b_kind)):
                if not CL._head_at(run, k):
                    continue
                eid = d.eid(pid)
                where = f"({_f(tip[0])},{_f(tip[1])})"
                if kind == "node":
                    foot = d.foot.get(target)
                    hit = CL.end_icon(tip, d.feet)
                    if foot is None:
                        continue
                    if hit is None or d.icon_node.get(id(hit)) != target:
                        got = d.icon_node.get(id(hit)) if hit is not None else None
                        out.append(Violation("R-flow", (eid, f"node:{target}"),
                                             f"F4 {_name(spec, eid)}'s arrowhead at {where} does not end on "
                                             f"{_display(spec, target)} "
                                             f"({'on ' + _display(spec, got) if got else 'on no node'})",
                                             _pt_box(tip, foot),
                                             code="F4"))
                        continue
                    near = [(nid, _pt_box(tip, b)) for nid, b in d.foot.items() if nid != target]
                    near = [(nid, dd) for nid, dd in near if dd <= CL.ICON_CLEAR]
                    if near:
                        nid, dd = min(near, key=lambda t: t[1])
                        out.append(Violation("R-flow", (eid, f"node:{target}", f"node:{nid}"),
                                             f"F4 {_name(spec, eid)}'s arrowhead at {where} into "
                                             f"{_display(spec, target)} is {_f(dd)}px from "
                                             f"{_display(spec, nid)} too (< {CL.ICON_CLEAR}): it points at both",
                                             CL.ICON_CLEAR - dd,
                                             code="F4"))
                else:
                    r = d.group_rect.get(target)
                    if r is None:
                        continue
                    dd = _border_dist(tip, r)
                    if dd > CL.END_REACH:
                        out.append(Violation("R-flow", (eid, f"group:{target}"),
                                             f"F4 {_name(spec, eid)}'s arrowhead at {where} is {_f(dd)}px from "
                                             f"{_display(spec, target)}'s border "
                                             f"(> {CL.END_REACH})", dd - CL.END_REACH, code="F4"))
                        continue
                    other = [(g, _border_dist(tip, b)) for g, b in d.group_rect.items() if g != target]
                    other = [(g, x) for g, x in other if x < CL.BORDER_CLEAR]
                    if other:
                        g, x = min(other, key=lambda t: t[1])
                        out.append(Violation("R-flow", (eid, f"group:{target}", f"group:{g}"),
                                             f"F4 {_name(spec, eid)}'s arrowhead at {where} into "
                                             f"{_display(spec, target)} is {_f(x)}px from "
                                             f"{_display(spec, g)}'s border too (< {CL.BORDER_CLEAR})",
                                             CL.BORDER_CLEAR - x,
                                             code="F4"))
    return out


def own_pieces(d: Drawn, n: int) -> List[dict]:
    """Edge n's segments with those of its flow joined to them (a trunk's other pieces)."""
    mine = d.edge_paths.get(n, [])
    flows = {_flow(d, pid) for pid in mine}
    net = {d.net[pid] for pid in mine}
    return [s for pid, run in d.paths.items() if pid in mine or (d.net[pid] in net and _flow(d, pid) in flows)
            for s in run]


def net_and_other(d: Drawn, n: int) -> Tuple[List[dict], List[dict]]:
    """The segments of edge n's net (check_layout.joined: a trunk and its branches, a bus
    and its drops) and those of every other connector."""
    net = {d.net[pid] for pid in d.edge_paths.get(n, [])}
    own = [s for pid, run in d.paths.items() if d.net[pid] in net for s in run]
    other = [s for pid, run in d.paths.items() if d.net[pid] not in net for s in run]
    return own, other


def _label_box(texts: Sequence[dict]) -> BoxT:
    b = texts[0]["box"]
    for t in texts[1:]:
        b = CL.union(b, t["box"])
    return b


def _attribution(spec, d: Drawn) -> List[Violation]:
    """F5: an edge's labels and badges sit by its own net, nearer it than any other line.
    User decision (2026-11-07, rules-design §6): a label or badge the spec places itself
    (label_at / step_at a point) is exempt, as in L1 (nlb-mtls edge:3)."""
    out = []
    placed = {e.n: (isinstance(e.label_at, M.Place), isinstance(e.step_at, M.Place)) for e in spec.edges}
    for n in sorted(set(d.labels) | set(d.on_line) | set(d.badges)):
        own, other = net_and_other(d, n)
        if not own:
            continue
        fixed_label, fixed_badge = placed.get(n, (False, False))
        items = []
        if d.labels.get(n) and not fixed_label:
            items.append(("label", _label_box(d.labels[n]), d.labels[n][0]["s"]))
        if d.on_line.get(n) and not fixed_label:
            items.append(("label", _label_box(d.on_line[n]), d.on_line[n][0]["s"]))
        if not fixed_badge:
            items += [("badge", box, digit) for box, digit in d.badges.get(n, ())]
        for what, box, s in items:
            d_own = min(_box_seg(box, g) for g in own)
            # the nearest other line with its segment kept, so its owner is the one reported
            d_other, near = min(((_box_seg(box, g), g) for g in other), key=lambda t: t[0], default=(math.inf, None))
            eid = f"edge:{n}"
            if d_own > CL.LABEL_REACH:
                out.append(Violation("R-flow", (eid,), f"F5 {_name(spec, eid)}'s {what} {s!r} is {_f(d_own)}px "
                                     f"from its line "
                                     f"(> {CL.LABEL_REACH})", d_own - CL.LABEL_REACH, code="F5"))
            elif d_other <= d_own + CL.TEXT_GAP:
                o = d.eid(id(near["el"]))
                on = _name(spec, o)
                out.append(Violation("R-flow", (eid, o), f"F5 {_name(spec, eid)}'s {what} {s!r} is "
                                     f"{_f(d_other)}px from "
                                     f"{on}'s line, {_f(d_own)}px from its own line: it reads as {on}'s",
                                     d_own + CL.TEXT_GAP - d_other + 1, code="F5"))
    return out


def _inside_len(p: Pt, q: Pt, b: BoxT) -> float:
    """How much of segment p–q lies inside box b (Liang–Barsky clip)."""
    t0, t1 = 0.0, 1.0
    dx, dy = q[0] - p[0], q[1] - p[1]
    for den, num in ((-dx, p[0] - b[0]), (dx, b[2] - p[0]), (-dy, p[1] - b[1]), (dy, b[3] - p[1])):
        if abs(den) < 1e-12:
            if num < 0:
                return 0.0
            continue
        t = num / den
        if den < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return 0.0
    return (t1 - t0) * math.hypot(dx, dy)


def _display(spec, ref: str) -> str:
    """A node's or group's name as the drawing shows it (its label / title, with which copy
    when another shows the same), else its id (layout_model.item_name)."""
    return M.item_name(spec, ref)


def _name(spec, owner: str) -> str:
    """A draft owner id ("edge:3", "node:rtsp", "group:vpca") as messages name it: the spec
    line and the ends the drawing shows for an edge, the label for a node, the title for a
    group (layout_model.owner_name)."""
    return M.owner_name(spec, owner)


def _node_ref(spec, nid: str) -> str:
    """Where to edit a node, and its name: "nodes[2] db db.2 (Aurora reader 2)"."""
    return M.node_ref(spec, nid)


def _axis_of(seg: dict) -> Optional[str]:
    """The axis a piece's position is on: x for a vertical piece, y for a horizontal one."""
    return "x" if _vert(seg) else "y" if _horiz(seg) else None


def _piece_name(run: List[dict], k: int) -> str:
    a = _axis_of(run[k])
    return f"the {'vertical' if a == 'x' else 'horizontal'} piece at {a}={_f(run[k]['p'][0 if a == 'x' else 1])}"


def _at_icon(d: Drawn, e, run: List[dict], k: int):
    """(field, node id, icon box, end point) when piece k of edge e's drawn run ends on a
    node (its footprint, as F6's attach pieces), not on the trunk it joins; else None."""
    mine = {id(x) for x in run}
    trunk = [x for x in own_pieces(d, e.n) if id(x) not in mine]
    n = len(run)
    for kk, pt, ref, kind, field in ((0, run[0]["p"], e.a, e.a_kind, "from_offset"),
                                     (n - 1, run[-1]["q"], e.b, e.b_kind, "to_offset")):
        icon, ft = d.node_icon.get(ref), d.foot.get(ref)
        if (kk == k and kind == "node" and icon is not None and ft is not None
                and _pt_box(pt, ft) <= CL.END_REACH and not any(CL.on_seg(pt, x) for x in trunk)):
            return field, ref, icon["box"], pt
    return None


def _rel(spec, d: Drawn, e, v: float, axis: str, near: Optional[Pt] = None) -> str:
    """v (a drawn x / y) as an expression on the nearer of edge e's end nodes' icon centre
    (`<node>.cx±n`), so it moves with that node when the spec is solved again (feedback
    rounds and text scale change the coordinates); the plain number without a node end."""
    ends = [x for x, kind in ((e.a, e.a_kind), (e.b, e.b_kind)) if kind == "node" and x in d.node_icon]
    if not ends:
        return _f(round(v))
    k = 0 if axis == "x" else 1
    ref = min(ends, key=lambda x: (math.dist(_centre(d.node_icon[x]["box"]), near) if near is not None
                                   else abs(_centre(d.node_icon[x]["box"])[k] - v)))
    off = round(v - _centre(d.node_icon[ref]["box"])[k])
    return f"{ref}.c{axis}" + (f"{'+' if off > 0 else '-'}{abs(off)}" if off else "")


def _piece_field(spec, d: Drawn, e, run: List[dict], k: int, v: float, other=None) -> Optional[str]:
    """The spec field, with its value, that puts piece k of edge e's drawn run at v on its
    axis: `points` for a pinned line; bend_x / bend_y for a middle piece (and a trunk
    follower's piece that ends on the trunk: the shared bend); from_offset / to_offset for
    an end piece on a node's side while v stays on that side, else None."""
    a = _axis_of(run[k])
    n = len(run)
    alt = f"; or {_f(other)}" if other is not None else ""
    if e.points:
        return f"{M.edge_name(spec, e.n)} points: move {_piece_name(run, k)} to {a}={_f(v)}{alt}"
    if 0 < k < n - 1:
        return f"{M.edge_name(spec, e.n)} bend_{a}: {_f(v)} (moves {_piece_name(run, k)}{alt})"
    end = _at_icon(d, e, run, k)
    if end is None:             # ends on the trunk it joins: the trunk's shared bend
        return (f"{M.edge_name(spec, e.n)} bend_{a}: {_f(v)} (moves {_piece_name(run, k)}"
                f"{', the trunk' + chr(39) + 's shared bend' if e.trunk else ''}{alt})")
    field, ref, box, _ = end
    c = _centre(box)[0 if a == "x" else 1]
    half = (box[2] - box[0] if a == "x" else box[3] - box[1]) / 2
    if abs(v - c) < half:
        return f"{M.edge_name(spec, e.n)} {field}: {_f(v - c)} (moves {_piece_name(run, k)} to {a}={_f(v)})"
    return None


def _over_try(spec, d: Drawn, e, run: List[dict], i: int, nid: str) -> str:
    """A spec change, with its value, that takes piece i of a drawn line off node nid's
    footprint (OVER_CLEAR beyond its nearer side), in the field that places that piece
    (_piece_field). A piece that runs
    across its own end's icon where it attaches cannot leave the icon: the piece before it is
    moved instead, past the footprint on the side the line attaches to (privatelink edge:12,
    a VHV into S3's bottom: its bend_y below S3). An end piece that cannot move far enough on
    its node's side gets the routing fields and the crossed node's move (dx / dy, no dy in a
    flow column)."""
    s = run[i]
    foot = d.foot.get(nid, d.node_icon[nid]["box"])
    n = len(run)
    axis_of, piece = _axis_of, (lambda k: _piece_name(run, k))

    def at_icon(k):
        return _at_icon(d, e, run, k)

    def field_for(k, v, other=None):
        a = axis_of(run[k])
        got = _piece_field(spec, d, e, run, k, v, other)
        if got is not None:
            return got
        field, ref, box, _ = at_icon(k)
        tip = (f"{M.edge_name(spec, e.n)} shape / from_side / to_side ({piece(k)} leaves {_display(spec, ref)} on "
               f"{_display(spec, nid)}'s {'column' if a == 'x' else 'row'})")
        node = spec.nodes.get(nid)
        stacked = {x for ids in spec.flow_stacks().values() for x in ids}
        if node is not None and node.xy is None and not (a == "y" and nid in stacked):
            at = run[k]["p"][0 if a == "x" else 1]
            lo_shift = at - OVER_CLEAR - foot[2 if a == "x" else 3]
            hi_shift = at + OVER_CLEAR - foot[0 if a == "x" else 1]
            shift = lo_shift if abs(lo_shift) <= abs(hi_shift) else hi_shift
            now = node.dx if a == "x" else node.dy
            tip += f", or {_node_ref(spec, nid)}: d{a}: {_f(now + shift)} (moves {_display(spec, nid)} off the piece)"
        return tip

    a = axis_of(s)
    if a is None:
        return f"{M.edge_name(spec, e.n)} points / shape that keep the line off {_display(spec, nid)}"
    end = at_icon(i)
    if end is not None and end[1] == nid and n >= 2:
        # across its own end's icon: bring the line to the side it attaches on first
        j = i - 1 if i == n - 1 else i + 1
        _, _, box, pt = end
        # the side the end point sits beyond (a stem from under the name: bottom), else the nearest
        side = ("bottom" if pt[1] >= box[3] else "top" if pt[1] <= box[1] else "left" if pt[0] <= box[0]
                else "right" if pt[0] >= box[2] else
                min((("left", pt[0] - box[0]), ("right", box[2] - pt[0]), ("top", pt[1] - box[1]),
                     ("bottom", box[3] - pt[1])), key=lambda t: t[1])[0])
        # past the footprint, and far enough from the end for an arrowhead's shaft (MIN_ARROW)
        want = {"left": ("x", min(foot[0] - OVER_CLEAR, pt[0] - CL.MIN_ARROW)),
                "right": ("x", max(foot[2] + OVER_CLEAR, pt[0] + CL.MIN_ARROW)),
                "top": ("y", min(foot[1] - OVER_CLEAR, pt[1] - CL.MIN_ARROW)),
                "bottom": ("y", max(foot[3] + OVER_CLEAR, pt[1] + CL.MIN_ARROW))}[side]
        if axis_of(run[j]) == want[0]:
            return (field_for(j, want[1]) + f", so {piece(i)} reaches {_display(spec, nid)}'s {side} side "
                    f"without crossing it")
    if a == "x":
        lo, hi, at = foot[0] - OVER_CLEAR, foot[2] + OVER_CLEAR, s["p"][0]
    else:
        lo, hi, at = foot[1] - OVER_CLEAR, foot[3] + OVER_CLEAR, s["p"][1]
    to, other = (lo, hi) if abs(at - lo) <= abs(at - hi) else (hi, lo)
    return field_for(i, to, other)


def _over_nodes(spec, d: Drawn) -> List[Violation]:
    """F6: a connector runs over a node's icon body or its name block (label and sub lines,
    node_stacks), with check_layout's LINE OVER ICON / LINE OVER TEXT boxes (icon shrunk by 2,
    text by 1; a piece under a later mask is hidden). Its own end nodes are exempt only for
    the piece that reaches the icon where the line attaches, and only while that piece runs
    at most ATTACH_DEPTH inside the icon; over an own end's name, or across its icon beyond
    that, it is reported. Group titles / CIDR lines (R-border B2), edge labels and badges
    (F5, R-label) are not counted here. One violation per (edge, node); user decision
    2026-11-09 (docs/dev/line-cross/spec.md)."""
    out = []
    for e in spec.edges:
        pids = d.edge_paths.get(e.n)
        if not pids:
            continue
        own = {x for x, kind in ((e.a, e.a_kind), (e.b, e.b_kind)) if kind == "node"}
        hits: Dict[str, Tuple[str, dict, int, List[dict]]] = {}
        for pid in pids:
            run = d.paths[pid]
            pts = d.points(pid)
            # attach pieces: (own node, piece index) where the line ends on that node
            attach = {(x, k) for x in own if x in d.foot
                      for k, pt in ((0, pts[0]), (len(run) - 1, pts[-1]))
                      if _pt_box(pt, d.foot[x]) <= CL.END_REACH}
            for nid, icon in d.node_icon.items():
                if nid in hits:
                    continue
                ib = CL.shrink(icon["box"], 2.0)
                names = d.stacks.get(id(icon["el"]), ())
                for i, s in enumerate(run):
                    p, q = s["p"], s["q"]
                    if CL.seg_hits_box(p, q, ib) and not CL.masked(icon["box"], s["o"], d.masks):
                        if not ((nid, i) in attach and _inside_len(p, q, ib) <= ATTACH_DEPTH + 1e-6):
                            hits[nid] = ("icon", s, i, run)
                            break
                    t = next((t for t in names if CL.seg_hits_box(p, q, CL.shrink(t["box"]))
                              and not CL.masked(t["box"], s["o"], d.masks)), None)
                    if t is not None:
                        hits[nid] = (f"name {t['s']!r}", s, i, run)
                        break
        for nid in sorted(hits):
            what, s, i, run = hits[nid]
            eid, name = f"edge:{e.n}", _display(spec, nid)
            if nid not in own:
                why = (f"runs over {name}'s {what} {CL.fmt(s)}: the flow reads as passing through {name}"
                       + (", and the name is hidden" if what != "icon" else ""))
            elif what == "icon":
                why = (f"runs across its own end {name}'s icon {CL.fmt(s)} beyond where it attaches: "
                       "the line is drawn through its target")
            else:
                why = f"runs over its own end {name}'s {what} {CL.fmt(s)}: the name is hidden"
            out.append(Violation(
                "R-flow", (eid, f"node:{nid}"),
                f"F6 {_name(spec, eid)} {why}; "
                f"try: {_over_try(spec, d, e, run, i, nid)}", 1.0, code="F6",
                at=(tuple(s["p"]), tuple(s["q"]), tuple(d.foot.get(nid, d.node_icon[nid]["box"])))))
    return out


# =======================================================================================
# try values for F3 / F4 / F5 (the summary's unresolved warnings: layout.unfixable_warnings;
# selection never asks for them, so they cost nothing per candidate)

TRY_MARGIN = K.TEXT_GAP     # a suggested spot clears each threshold by this much more
TRY_REACH = 160             # px a piece, label or badge is searched from where it is drawn
TRY_STEP = 2


def _pts_of(run: List[dict]) -> List[Pt]:
    return [run[0]["p"]] + [s["q"] for s in run]


def _rerun(run: List[dict], pts: Sequence[Pt]) -> List[dict]:
    return [dict(s, p=pts[i], q=pts[i + 1]) for i, s in enumerate(run)]


def _shifted(run: List[dict], k: int, v: float) -> Optional[List[dict]]:
    """Edge run with piece k moved to v on its axis (the pieces beside it stretch), or None
    when a piece beside it would turn back or an arrowhead's piece get shorter than MIN_ARROW."""
    a = 0 if _axis_of(run[k]) == "x" else 1
    pts = [list(p) for p in _pts_of(run)]
    pts[k][a] = v
    pts[k + 1][a] = v
    pts = [tuple(p) for p in pts]
    new = _rerun(run, pts)
    for old, s in zip(run, new):
        o = (old["q"][0] - old["p"][0], old["q"][1] - old["p"][1])
        w = (s["q"][0] - s["p"][0], s["q"][1] - s["p"][1])
        if o[0] * w[0] + o[1] * w[1] <= 0 and (abs(o[0]) + abs(o[1])) > 0.5:
            return None
    for j in (0, len(new) - 1):
        if j in (k - 1, k + 1) and CL._head_at(run, 0 if j == 0 else 1) and \
                math.hypot(new[j]["q"][0] - new[j]["p"][0], new[j]["q"][1] - new[j]["p"][1]) < CL.MIN_ARROW:
            return None
    return new


def _junction_hit(a_run: List[dict], b_run: List[dict], feet, reach: float):
    """F3's predicate for one pair of runs: (crossing, why) or None."""
    pa, pb = _pts_of(a_run), _pts_of(b_run)
    bends = pa[1:-1] + pb[1:-1]
    ends = [i["box"] for pt in (pa[0], pa[-1], pb[0], pb[-1]) if (i := CL.end_icon(pt, feet)) is not None]
    for s in a_run:
        for o in b_run:
            c = ortho_cross(s, o)
            if c is None:
                continue
            bend = next((v for v in bends if math.dist(v, c) <= reach), None)
            if bend is not None:
                return c, f"a bend at ({_f(bend[0])},{_f(bend[1])})"
            if any(_pt_box(c, bx) <= reach for bx in ends):
                return c, "a node it ends at"
    return None


def _run_clear(spec, d: Drawn, e, pid: int, new: List[dict], changed: Sequence[int]) -> bool:
    """Is edge e's run `new` (replacing path pid; pieces `changed` moved) clear of what the
    tier-0 R-flow / R-border rules judge: no junction with another flow (F3, TRY_MARGIN wider),
    no piece over a node's icon or any text but its own label (F6 / LINE OVER TEXT), none on
    or in line with another flow (F1 / F2), along a border (B1) or through a header band (B2)?"""
    own = {x for x, kind in ((e.a, e.a_kind), (e.b, e.b_kind)) if kind == "node"}
    mine = f"edge:{e.n}"
    pts = _pts_of(new)
    for k in changed:
        s = new[k]
        p, q = s["p"], s["q"]
        for nid, icon in d.node_icon.items():
            ib = CL.shrink(icon["box"], 2.0)
            if CL.seg_hits_box(p, q, ib):
                attach = nid in own and k in (0, len(new) - 1) and any(
                    _pt_box(pt, d.foot.get(nid, icon["box"])) <= CL.END_REACH for pt in (pts[0], pts[-1]))
                if not (attach and _inside_len(p, q, ib) <= ATTACH_DEPTH + 1e-6):
                    return False
        for t in d.texts:
            if d.owner.get(id(t["el"]), "").startswith(mine + ":"):
                continue
            if CL.seg_hits_box(p, q, CL.shrink(t["box"])):
                return False
    for qid, run in d.paths.items():
        if qid != pid and CL.two_flows(new, run) and \
                _junction_hit(new, run, d.feet, JUNCTION_REACH + TRY_MARGIN):
            return False
    paths = dict(d.paths)
    paths[pid] = new
    if any(pid in (id(s["el"]), id(o["el"])) for s, o, _ in CL.lines_on_lines(paths)):
        return False
    if any(pid in (id(s["el"]), id(o["el"])) for s, o, _ in CL.lines_in_line(paths)):
        return False
    borders = [s for s in d.segs if s["kind"] == "border"]
    if CL.line_hugs(borders + [new[k] for k in changed], d.masks):
        return False
    bands = CL.header_bands(d.rects, d.icons, d.texts, d.owner)
    return not CL.lines_in_headers([new[k] for k in changed], d.masks, bands, d.owner)


def _move_try(spec, d: Drawn, pids: Sequence[int], why: str) -> str:
    """The nearest clear move of one piece of the given drawn lines, as the spec field that
    makes it (_piece_field), or "" when none within TRY_REACH clears every tier-0 test."""
    best = None
    for pid in pids:
        n = d.path_edge.get(pid)
        if n is None or n >= len(spec.edges):
            continue
        e = spec.edges[n]
        run = d.paths[pid]
        # one spec line drawn as several instances (or a trunk) moves them all: not simulated
        if e.trunk or getattr(e, "fork", None) or sum(
                1 for x in spec.edges if x.src == e.src and d.edge_paths.get(x.n)) > 1:
            continue
        for k, s in enumerate(run):
            a = _axis_of(s)
            if a is None or (not e.points and len(run) > 3 and 0 < k < len(run) - 1):
                continue        # several bends: no one spec field places this piece
            if not e.points and len(run) == 1:
                continue        # a straight line: both ends would move
            at = s["p"][0 if a == "x" else 1]
            for step in range(1, TRY_REACH // TRY_STEP + 1):
                if best is not None and step * TRY_STEP >= best[0]:
                    break
                hit = False
                for v in (at - step * TRY_STEP, at + step * TRY_STEP):
                    v = round(v)
                    new = _shifted(run, k, v)
                    if new is None:
                        continue
                    field = _piece_field(spec, d, e, run, k, v)
                    if field is None:
                        continue
                    changed = [j for j in (k - 1, k, k + 1) if 0 <= j < len(run)]
                    if _run_clear(spec, d, e, pid, new, changed):
                        best = (abs(v - at), field)
                        hit = True
                        break
                if hit:
                    break
    if best:
        return f"{best[1]}, the nearest {why}"
    shared = [M.entry_name(spec, spec.edges[d.path_edge[p]].line) for p in pids if d.path_edge.get(p) is not None
              and d.path_edge[p] < len(spec.edges) and (spec.edges[d.path_edge[p]].trunk or sum(
                  1 for x in spec.edges if x.src == spec.edges[d.path_edge[p]].src and d.edge_paths.get(x.n)) > 1)]
    if len(shared) == len(pids):
        return (f"no value: {' and '.join(dict.fromkeys(shared))} draw{'s' if len(set(shared)) == 1 else ''} "
                "several lines (a trunk or a `.*` line) whose bend and offsets one spec value moves together; "
                "give the crossing instance its own spec line to place it")
    return f"no value: no one-piece move within {TRY_REACH}px clears the crossing and every other tier-0 test"


def _f3_try(spec, d: Drawn, v: Violation) -> str:
    ea, eb = v.owners[0], v.owners[1]
    pairs = [(a, b) for a in d.paths for b in d.paths
             if d.eid(a) == ea and d.eid(b) == eb and CL.two_flows(d.paths[a], d.paths[b])
             and _junction_hit(d.paths[a], d.paths[b], d.feet, JUNCTION_REACH)]
    if not pairs:
        return ""
    a, b = pairs[0]
    return _move_try(spec, d, (a, b), f"spot where {M.line_name(spec, d.path_edge[a])} and "
                                      f"{M.line_name(spec, d.path_edge[b])} cross clear of every bend and end "
                                      f"(> {JUNCTION_REACH + TRY_MARGIN}px)")


def _text_free(d: Drawn, box: BoxT, mine: str, gap: float) -> bool:
    """box clears every text but `mine`'s, every icon (ICON_CLEAR), every connector (gap) and
    stays on the canvas."""
    cx, cy, cw, ch = d.canvas
    if cw and not (box[0] >= cx and box[1] >= cy and box[2] <= cx + cw and box[3] <= cy + ch):
        return False
    for t in d.texts:
        if d.owner.get(id(t["el"]), "").startswith(mine) or not t["s"].strip():
            continue
        if _box_box(box, t["box"]) < CL.ICON_CLEAR:
            return False
    for i in d.icons:
        if d.owner.get(id(i["el"]), "").startswith(mine):
            continue
        if _box_box(box, i["box"]) < CL.ICON_CLEAR:
            return False
    return all(_box_seg(box, s) >= gap for s in d.segs if s["kind"] == "connector")


def _f5_try(spec, d: Drawn, v: Violation, rule_side: bool = False) -> str:
    """label_at {x, y, anchor} / step_at [x, y]: the nearest spot above a horizontal piece or
    right of a vertical one (a badge: above / left, as the engine puts them) of the edge's own
    line where F5 holds with TRY_MARGIN to spare and the box clears other text, icons and
    lines."""
    ref = v.owners[0].split(":")
    if len(ref) < 2 or not ref[1].isdigit() or int(ref[1]) >= len(spec.edges):
        return ""
    n = int(ref[1])
    e = spec.edges[n]
    what = "badge" if "'s badge " in v.message and not rule_side else "label"
    drawn_on = (lambda x: d.labels.get(x.n) or d.on_line.get(x.n)) if what == "label" else \
        (lambda x: d.badges.get(x.n))
    if sum(1 for x in spec.edges if x.src == e.src and drawn_on(x)) > 1:
        # a point is one place for every instance of the line: they would overlap
        return (f"no value: {M.entry_name(spec, e.line)} draws its {what} on several instances and one "
                f"{'label_at' if what == 'label' else 'step_at'} point would stack them; give this instance its "
                "own spec line")
    if what == "label":
        texts = sorted(d.labels.get(n) or d.on_line.get(n) or [], key=lambda t: t["box"][1])
        if not texts:
            return ""
        box = _label_box(texts)
    else:
        if not d.badges.get(n):
            return ""
        box = d.badges[n][0][0]
    own, other = net_and_other(d, n)
    w, h = box[2] - box[0], box[3] - box[1]
    cx0, cy0 = _centre(box)
    best = None
    # the rule side first (a label above a horizontal / right of a vertical piece, a badge
    # where the engine puts it); only when no spot there clears, the other side
    for other_side in ((False,) if rule_side else (False, True)):
        for s in d.edge_segs(n):
            horiz, vert = _horiz(s), _vert(s)
            if not (horiz or vert):
                continue
            lo, hi = sorted((s["p"][0], s["q"][0])) if horiz else sorted((s["p"][1], s["q"][1]))
            sign = 1 if other_side else -1
            t = lo
            while t <= hi + 1e-6:
                if what == "label":
                    c = ((t, s["p"][1] + sign * (K.TEXT_GAP + h / 2)) if horiz
                         else (s["p"][0] - sign * (K.TEXT_GAP + 2 + w / 2), t))
                else:
                    c = ((t, s["p"][1] + sign * K.BADGE_DY) if horiz
                         else (s["p"][0] + sign * K.VBADGE_DX, t))
                t += TRY_STEP * 2
                dist = math.hypot(c[0] - cx0, c[1] - cy0)
                if best is not None and dist >= best[0]:
                    continue
                b = (c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2)
                d_own = min(_box_seg(b, g) for g in own)
                d_other = min((_box_seg(b, g) for g in other), default=math.inf)
                if d_own > CL.LABEL_REACH - TRY_MARGIN or d_other <= d_own + CL.TEXT_GAP + TRY_MARGIN:
                    continue
                if not _text_free(d, b, f"edge:{n}:", 2.0):
                    continue
                best = (dist, c, b)
        if best is not None:
            break
    if best is None:
        return (f"no value: no spot {'above / right of' if rule_side else 'beside'} its own line keeps the "
                f"{what} nearer it than the other lines and clear of text and icons")
    _, c, b = best
    dx, dy = c[0] - cx0, c[1] - cy0
    if what == "badge":
        return (f"{M.edge_name(spec, e.n)} step_at: [{_rel(spec, d, e, c[0], 'x', c)}, {_rel(spec, d, e, c[1], 'y', c)}] "
                f"(the badge's centre, at ({_f(round(c[0]))},{_f(round(c[1]))}) now: beside its own line and "
                f"clear of the others)")
    t0 = texts[0]
    anchor = t0["el"].get("text-anchor", "start")
    ax = {"middle": (t0["box"][0] + t0["box"][2]) / 2, "end": t0["box"][2]}.get(anchor, t0["box"][0])
    base = t0["box"][1] + K.GLYPH_ASCENT * t0["fs"]
    x, y = ax + dx, base + dy
    return (f"{M.edge_name(spec, e.n)} label_at: {{x: {_rel(spec, d, e, x, 'x', c)}, y: {_rel(spec, d, e, y, 'y', c)}, "
            f"anchor: {anchor}}} (its first line's baseline, at ({_f(round(x))},{_f(round(y))}) now: beside its "
            f"own line and clear of the others)")


class NodeMove(NamedTuple):
    """One spec change that moves a node: `key` is dx / dy (the new value) or xy (a pair of
    Expr / numbers); `text` is how the hint writes it."""
    nid: str
    key: str
    value: object
    text: str


def _xy_text(spec, c) -> str:
    if isinstance(c, M.Expr):
        base = {"num": "", "col": f"col.{c.ref}", "row": f"row.{c.ref}", "gap": f"gap({c.ref},{c.ref2})",
                "label": f"{c.ref}.label.{c.attr}"}.get(c.kind, f"{c.ref}.{c.attr}")
        if not base:
            return _f(c.offset)
        return base + (f"{'+' if c.offset > 0 else '-'}{_f(abs(c.offset))}" if c.offset else "")
    return _f(c)


def f4_moves(spec, d: Drawn, v: Violation) -> Tuple[List[NodeMove], str]:
    """F4 into a node whose arrowhead lands on (or within ICON_CLEAR of) another node: the
    node moves that would take the two footprints apart at the tip, nearest first — the other
    node's dx / dy (both ways on each axis, ICON_CLEAR + TRY_MARGIN off the tip), and for a
    node pinned with `xy` to the other (xy: [q.cx, q.cy]) that xy moved past the other's
    footprint. Unverified: layout.unfixable_warnings draws each again and keeps the ones that
    clear the F4. With none, (no moves, why)."""
    m = [o for o in v.owners if o.startswith("node:")]
    at = re.search(r"at \((-?[\d.]+),(-?[\d.]+)\)", v.message)
    if at is None:
        return [], ""
    tip = (float(at.group(1)), float(at.group(2)))
    target = m[0][5:] if m else None
    wrong = m[1][5:] if len(m) > 1 else None
    if wrong is None:
        hit = CL.end_icon(tip, d.feet)
        wrong = d.icon_node.get(id(hit)) if hit is not None else None
    if wrong is None or wrong == target or wrong not in d.foot:
        return [], "the arrowhead is on no other node: move the line's end (to_side / to_offset) onto it"
    clear = CL.ICON_CLEAR + TRY_MARGIN
    stacked = {x for ids in spec.flow_stacks().values() for x in ids}
    out: List[Tuple[float, NodeMove]] = []
    foot = d.foot[wrong]
    node = spec.nodes.get(wrong)
    pinned_to = any(isinstance(c, M.Expr) and c.ref == wrong for x in spec.nodes.values() for c in (x.xy or ()))
    if node is not None and node.xy is None and not pinned_to:
        for a in ("x", "y"):
            if a == "y" and wrong in stacked:
                continue        # a flow-column node's y is the stack's
            k = 0 if a == "x" else 1
            now = node.dx if a == "x" else node.dy
            for sh in (tip[k] + clear - foot[k], tip[k] - clear - foot[k + 2]):
                val = round(now + sh)
                out.append((abs(sh), NodeMove(wrong, f"d{a}", val, f"{_node_ref(spec, wrong)}: d{a}: {_f(val)}")))
    # a node pinned with xy on the other one: its own xy moved past the other's footprint
    for pin, other in ((target, wrong), (wrong, target)):
        pn = spec.nodes.get(pin) if pin else None
        if pn is None or pn.xy is None or other not in d.foot or pin not in d.foot:
            continue
        pf, of = d.foot[pin], d.foot[other]
        for k in (0, 1):
            c = pn.xy[k]
            for sh in (of[k + 2] - pf[k] + clear, of[k] - pf[k + 2] - clear):
                sh = round(sh)
                c2 = (M.Expr(c.kind, c.ref, c.attr, c.ref2, c.offset + sh) if isinstance(c, M.Expr)
                      else c + sh)
                xy = tuple(c2 if j == k else pn.xy[j] for j in (0, 1))
                out.append((abs(sh), NodeMove(pin, "xy", xy, f"{_node_ref(spec, pin)}: xy: [{_xy_text(spec, xy[0])}, "
                                                             f"{_xy_text(spec, xy[1])}]")))
    out.sort(key=lambda t: t[0])
    if not out:
        return [], f"{_display(spec, wrong)} is placed by another node's xy: move that node"
    return [mv for _, mv in out], ""


def flow_try(spec, d: Drawn, v: Violation) -> str:
    """A concrete spec change with its value for an F3 / F5 / L1 violation of draft d, `no
    value: <why>` when there is none, or "" (F4: f4_moves, verified by the engine)."""
    try:
        if v.code == "F3" and len(v.owners) == 2:
            return _f3_try(spec, d, v)
        if v.code == "F5":
            return _f5_try(spec, d, v)
        if v.code == "L1":          # the label on its rule side (above / right), F5 kept too
            return _f5_try(spec, d, v, rule_side=True)
    except (KeyError, ValueError, IndexError, AttributeError):
        return ""
    return ""


# =======================================================================================
# R-rt

def _hub_paths(spec, d: Drawn, hub: str):
    """Every drawn line at the hub, oriented away from it: [(edge n, points, far end id, kind)]."""
    hb = d.foot.get(hub)
    out = []
    for e in spec.edges:
        if hub not in (e.a, e.b) or not d.edge_paths.get(e.n):
            continue
        pid = max(d.edge_paths[e.n], key=lambda p: len(d.paths[p]))
        pts = d.points(pid)
        if hb is not None and _pt_box(pts[-1], hb) < _pt_box(pts[0], hb):
            pts = pts[::-1]
        far, kind = (e.b, e.b_kind) if e.a == hub else (e.a, e.a_kind)
        out.append((e.n, pts, far, kind))
    return out


def bracket(spec, d: Drawn, hub: str, assoc: Sequence[int]) -> List[List[Pt]]:
    """The polygons the associated lines draw at the hub: the lines in port-angle order
    around it, each two cyclically next to each other that are both associated close a
    wedge (one path out, the other back, through the hub) together with the hull of their
    far ends (footprints; an end on a group: its tip)."""
    hb = d.foot.get(hub)
    if hb is None:
        return []
    hc = _centre(d.node_icon[hub]["box"]) if hub in d.node_icon else _centre(hb)
    lines = _hub_paths(spec, d, hub)

    def ang(p):
        return math.atan2(p[1] - hc[1], p[0] - hc[0])

    lines.sort(key=lambda t: (round(ang(t[1][0]), 6), round(ang(t[1][-1]), 6)))
    A = set(assoc)
    out, seen = [], set()
    for i in range(len(lines)):
        a, b = lines[i], lines[(i + 1) % len(lines)]
        if a is b or a[0] not in A or b[0] not in A or frozenset((a[0], b[0])) in seen:
            continue
        seen.add(frozenset((a[0], b[0])))
        out.append(a[1] + b[1][::-1])
        ends = []
        for n, pts, far, kind in (a, b):
            fb = d.foot.get(far) if kind == "node" else None
            ends += _corners(fb) if fb else [pts[-1]]
        h = hull(ends)
        if len(h) >= 3:
            out.append(h)
    return out


def _gap_to(d: Drawn, foot: BoxT, oid: str, kind: str) -> Optional[float]:
    if kind == "node":
        b = d.foot.get(oid)
        return None if b is None else _box_box(foot, b)
    r = d.group_rect.get(oid)
    if r is None:
        return None
    if CL.contains(r, foot, 0):
        return min(foot[0] - r[0], r[2] - foot[2], foot[1] - r[1], r[3] - foot[3])
    return _box_box(foot, r)


def rt_rules(spec, d: Drawn) -> List[Violation]:
    out = []
    hubs = {n.assoc.hub for n in spec.nodes.values() if n.assoc is not None and n.assoc.hub}
    for rid, node in spec.nodes.items():
        a = node.assoc
        if a is None or rid not in d.foot:
            continue
        foot = d.foot[rid]
        rc = _centre(d.node_icon[rid]["box"])
        me = f"node:{rid}"
        rn = _display(spec, rid)
        if a.hub is None:
            if a.ends and all(x in spec.groups and spec.groups[x].type in SUBNET_TYPES for x in a.ends):
                out += _rt_subnet(spec, d, rid, foot, rc, a.ends)
            continue
        hub = a.hub
        if hub not in d.foot:
            continue
        lines = _hub_paths(spec, d, hub)
        A = [n for n in a.edges if d.edge_paths.get(n)]
        N = [t for t in lines if t[0] not in set(a.edges)]
        hn = f"node:{hub}"
        hname = _display(spec, hub)
        lim = spec.S + spec.const.sibling_gap
        if len(A) >= 2:
            polys = bracket(spec, d, hub, A)
            # user decision (2026-11-07, rules-design §6): the hub's only table — every line at
            # the hub associated with it — passes right beside the hub, with no bracket (tgw TGW B RT)
            only = not N and _box_box(foot, d.foot[hub]) <= lim
            if not only and not any(inside(rc, p) for p in polys):
                out.append(Violation("R-rt", (me, hn), f"RT1 {rn} at ({_f(rc[0])},{_f(rc[1])}) is outside the bracket "
                                     f"its {len(A)} associated lines at {hname} draw "
                                     f"({', '.join(M.edge_name(spec, n) for n in A)})", 1.0, code="RT1"))
        elif len(A) == 1:
            segs = d.edge_segs(A[0])
            gap = min(_box_seg(foot, s) for s in segs)
            q = min((_pt_seg(rc, s["p"], s["q"]) for s in segs), key=lambda t: t[0])[1]
            mine = set(d.edge_paths.get(A[0], ()))
            crossed = sorted({d.eid(pid) for pid, run in d.paths.items() if pid not in mine for s in run
                              if (c := seg_cross(rc, q, s["p"], s["q"])) is not None and math.dist(c, q) > 1})
            reach = rt2_reach(spec)
            if gap > reach:
                out.append(Violation("R-rt", (me, f"edge:{A[0]}"), f"RT2 {rn} is {_f(gap)}px from its one associated "
                                     f"line {M.edge_name(spec, A[0])} "
                                     f"(> {RT2_REACH_ICONS}S + sibling_gap = {_f(reach)})",
                                     gap - reach, code="RT2"))
            elif crossed:
                out.append(Violation("R-rt", (me, f"edge:{A[0]}") + tuple(crossed),
                                     f"RT2 {rn} reaches its associated line {M.edge_name(spec, A[0])} only across "
                                     f"{', '.join(_name(spec, c) for c in crossed)}", len(crossed), code="RT2"))
        # RT3: nothing of N or of another hub between the table and its hub
        hcen = _centre(d.node_icon[hub]["box"])
        hbox = d.node_icon[hub]["box"]
        other_hub_edges = {e.n for e in spec.edges if (e.a in hubs or e.b in hubs) and hub not in (e.a, e.b)}
        block = {t[0] for t in N} | (other_hub_edges - set(a.edges))
        crossed = set()
        for n in sorted(block):
            for s in d.edge_segs(n):
                c = seg_cross(rc, hcen, s["p"], s["q"])
                if c is not None and _pt_box(c, hbox) > RT_HUB_CLEAR:
                    crossed.add(f"edge:{n}")
        if crossed:
            out.append(Violation("R-rt", (me, hn) + tuple(sorted(crossed)),
                                 f"RT3 the way from {rn} to its hub {hname} crosses "
                                 f"{', '.join(_name(spec, c) for c in sorted(crossed))} "
                                 f"(lines not associated with it)", len(crossed), code="RT3"))
        # RT4: nearer its hub than any other hub or any far end of N
        g_hub = _box_box(foot, d.foot[hub])
        rivals = [(f"node:{h}", _gap_to(d, foot, h, "node")) for h in sorted(hubs - {hub})]
        rivals += [(f"{kind}:{far}", _gap_to(d, foot, far, kind)) for _, _, far, kind in N if far != rid]
        closer = [(o, g) for o, g in rivals if g is not None and g <= g_hub]
        if closer:
            o, g = min(closer, key=lambda t: t[1])
            out.append(Violation("R-rt", (me, hn, o), f"RT4 {rn} is {_f(g)}px from {_name(spec, o)}, not nearer its "
                                 f"hub {hname} "
                                 f"({_f(g_hub)}px)", g_hub - g + 1, code="RT4"))
    return out


def _rt_subnet(spec, d: Drawn, rid: str, foot: BoxT, rc: Pt, ends: Sequence[str]) -> List[Violation]:
    """RT5: a subnet table nearer each of its subnets than any other subnet, inside none."""
    out = []
    me = f"node:{rid}"
    subnets = {g: r for g, r in d.group_rect.items() if g in spec.groups and spec.groups[g].type in SUBNET_TYPES}
    others = {g: r for g, r in subnets.items() if g not in ends}
    for g, r in sorted(others.items()):
        if r[0] <= rc[0] <= r[2] and r[1] <= rc[1] <= r[3]:
            out.append(Violation("R-rt", (me, f"group:{g}"), f"RT5 {_display(spec, rid)} sits inside "
                                 f"{_display(spec, g)}, a subnet it is not "
                                 f"associated with", 1.0, code="RT5"))
            return out
    for s in ends:
        if s not in subnets:
            continue
        ds = _box_box(foot, subnets[s])
        near = [(g, _box_box(foot, r)) for g, r in others.items()]
        near = [(g, x) for g, x in near if x < ds + RT_SUBNET_MARGIN]
        if near:
            g, x = min(near, key=lambda t: t[1])
            out.append(Violation("R-rt", (me, f"group:{s}", f"group:{g}"),
                                 f"RT5 {_display(spec, rid)} is {_f(ds)}px from its subnet {_display(spec, s)} but "
                                 f"{_f(x)}px from {_display(spec, g)} (not "
                                 f"{RT_SUBNET_MARGIN}px nearer its own)", ds + RT_SUBNET_MARGIN - x, code="RT5"))
    return out


# =======================================================================================
# R-twin

def twin_rules(spec, geom) -> List[Violation]:
    import layout                       # late: layout.py imports this module for its rule lines
    out = []
    for cls in layout_solve.twin_classes(spec):
        for axis in ("x", "y"):
            worst = None
            for k in range(len(cls[0][1][axis])):
                vals = [layout.value(m[1][axis][k][1], geom, axis) - layout.value(m[1][axis][k][0], geom, axis)
                        for m in cls]
                spread = max(vals) - min(vals)
                if spread > TWIN_TOL and (worst is None or spread > worst[0]):
                    what = cls[0][1][axis][k][2].split(":", 1)[1]
                    worst = (spread, cls[vals.index(min(vals))][0], cls[vals.index(max(vals))][0], what)
            lo = "L" if axis == "x" else "T"
            for k in range(min(len(m[2]) for m in cls)):
                vals = []
                for gid, _, norder in cls:
                    ng = geom.nodes.get(norder[k])
                    base = layout.value(f"group:{gid}.{lo}", geom, axis)
                    if ng is not None:
                        vals.append(((ng.cx if axis == "x" else ng.cy) - base, gid, norder[k]))
                if len(vals) < 2:
                    continue
                spread = max(v[0] for v in vals) - min(v[0] for v in vals)
                if spread > TWIN_TOL and (worst is None or spread > worst[0]):
                    a, b = min(vals)[1:], max(vals)[1:]
                    worst = (spread, a[0], b[0], f"node {_display(spec, a[1])} / {_display(spec, b[1])}")
            if worst:
                spread, a, b, what = worst
                out.append(Violation("R-twin", (f"group:{a}", f"group:{b}"),
                                     f"TW {_display(spec, a)} and {_display(spec, b)} have one structure but are "
                                     f"drawn {_f(spread)}px unlike on "
                                     f"{axis} ({what})", spread, code="TW"))
    at = {r.id: k for k, r in enumerate(spec.rows)}
    for a, b, rows_a, rows_b in layout_solve.twin_row_orders(spec):
        if set(rows_a) & set(rows_b):    # shared rows: reordering `rows:` moves a's as well
            top = sorted(rows_b, key=at.get)
            moves = ", ".join(f"{r} to {t}" for r, t in zip(rows_b, top) if r != t)
            tip = (f"move what {M.group_ref(spec, b)} has on each row to the row that matches "
                   f"{M.group_ref(spec, a)}'s order: {moves}")
        else:
            tip = (f"in `rows:` put {M.group_ref(spec, b)}'s rows in {M.group_ref(spec, a)}'s order: "
                   f"{', '.join(rows_b)} (like {', '.join(rows_a)})")
        out.append(Violation("R-twin", (f"group:{a}", f"group:{b}"),
                             f"TWR {_display(spec, a)} and {_display(spec, b)} have one structure but their rows "
                             f"are in another order, so they "
                             f"read as two (the engine keeps the spec's row order); try: {tip}", code="TWR"))
    return out


# =======================================================================================
# R-label

def _rule_side(box: BoxT, s: dict) -> bool:
    """Is a label box on the rule side of a straight piece: above a horizontal one (bottom
    at or over its y, overlapping it on x), right of a vertical one (overlapping it on y)?"""
    if _horiz(s):
        lo, hi = sorted((s["p"][0], s["q"][0]))
        return box[3] <= s["p"][1] + STRAIGHT and box[0] < hi and box[2] > lo
    lo, hi = sorted((s["p"][1], s["q"][1]))
    return box[0] >= s["p"][0] - STRAIGHT and box[1] < hi and box[3] > lo


def label_rules(spec, d: Drawn) -> List[Violation]:
    out = []
    for e in spec.edges:
        if e.label_at is not None:
            continue                    # placed where the spec says
        texts, on = d.labels.get(e.n), d.on_line.get(e.n)
        if not texts and not on:
            continue
        own = [s for s in own_pieces(d, e.n) if _horiz(s) or _vert(s)]
        if not own:
            continue
        box = _label_box(texts or on)
        # user decision (2026-11-07, rules-design §6): the own pieces it sits by — within
        # LABEL_REACH (a label at a corner sits by two), else the nearest — and it passes on the
        # rule side of any of them (latest2 / v2-1 edge:8, lanes/j edge:23)
        gaps = [(_box_seg(box, g), g) for g in own]
        by = [g for dd, g in gaps if dd <= CL.LABEL_REACH] or [min(gaps, key=lambda t: t[0])[1]]
        eid = f"edge:{e.n}"
        if on and not texts:
            if not any(CL.seg_hits_box(g["p"], g["q"], CL.expand(box, 0.5)) for g in by):
                out.append(Violation("R-label", (eid,), f"L1 {_name(spec, eid)}'s label {on[0]['s']!r} "
                                     f"over a background "
                                     f"is on none "
                                     f"of the pieces of its line it sits by ({', '.join(CL.fmt(g) for g in by)})",
                                     1.0, code="L1"))
            continue
        if not any(_rule_side(box, g) for g in by):
            out.append(Violation("R-label", (eid,), f"L1 {_name(spec, eid)}'s label {texts[0]['s']!r} is neither above "
                                 f"a horizontal "
                                 f"nor right of a vertical piece of its line it sits by "
                                 f"({', '.join(CL.fmt(g) for g in by)})", 1.0, code="L1"))
    # L2: the badges drawn are the note's steps — each once, or on each instance the spec
    # gives it to (step_each / steps): the edges' resolved steps
    steps = len(spec.note.steps) if spec.note is not None else 0
    got = Counter(digit for bs in d.badges.values() for _, digit in bs)
    want = Counter(str(e.step) for e in spec.edges if e.step is not None)
    unused = [str(k) for k in range(1, steps + 1) if str(k) not in got]
    if got != want or unused:
        missing = sorted(set(want - got) | set(unused), key=lambda s: (len(s), s))
        extra = sorted(got - want, key=lambda s: (len(s), s))
        owners = tuple(sorted({f"edge:{n}" for n, bs in d.badges.items() for _, digit in bs if digit in extra}))
        owners += tuple(sorted({f"edge:{e.n}" for e in spec.edges if e.step is not None and str(e.step) in missing
                                and not any(dg == str(e.step) for _, dg in d.badges.get(e.n, ()))}))
        out.append(Violation("R-label", ("note",) + owners,
                             f"L2 the step badges drawn are not the note's 1..{steps} as the edges give them"
                             + (f"; missing {', '.join(missing)}" if missing else "")
                             + (f"; extra {', '.join(extra)}" if extra else ""),
                             len(missing) + sum((got - want).values()), code="L2"))
    return out


# =======================================================================================
# R-border

def border_rules(spec, d: Drawn) -> List[Violation]:
    out = []
    # B1: check_layout's LINE HUGS BORDER predicate, once per connector and border owner
    seen = set()
    for s, b, dd in CL.line_hugs(d.segs, d.masks):
        a, g = d.eid(id(s["el"])), d.owner.get(id(b["el"]), "?")
        if (a, g) in seen:
            continue
        seen.add((a, g))
        where = "on top of" if dd == 0 else f"{_f(dd)}px from"
        out.append(Violation("R-border", (a, g), f"B1 {_name(spec, a)} runs {where} {_name(spec, g)}'s border "
                             f"({CL.fmt(s)} / {CL.fmt(b)}, "
                             f"< {K.HUG_CLEAR}px): the line reads as the border", K.HUG_CLEAR - dd, code="B1"))
    # B2: the same visible pieces and bands as check_layout's LINE IN HEADER.
    bands = CL.header_bands(d.rects, d.icons, d.texts, d.owner)
    for s, r, band, how in CL.lines_in_headers(d.segs, d.masks, bands, d.owner):
        a, g = d.eid(id(s["el"])), d.owner[id(r[4])]
        out.append(Violation("R-border", (a, g), f"B2 {_name(spec, a)} passes through {_name(spec, g)}'s header band "
                             f"{CL.fmt(s)} {how} "
                             f"(band {_f(band[0])},{_f(band[1])}–{_f(band[2])},{_f(band[3])})", 1.0, code="B2"))
    return out


def containment_rules(spec, d: Drawn) -> List[Violation]:
    """Check the rendered rectangles against in:, independently of solve constraints."""
    out = []
    children = {}
    for gid, g in spec.groups.items():
        if not g.overlay and gid in d.group_rect:
            children.setdefault(g.parent, []).append((f"group:{gid}", d.group_rect[gid], True))
    for nid, n in spec.nodes.items():
        if not n.on and nid in d.foot:
            children.setdefault(n.parent, []).append((f"node:{nid}", d.foot[nid], False))
    for parent, items in children.items():
        if parent in d.group_rect:
            outer = d.group_rect[parent]
            for eid, box, _ in items:
                if not CL.contains(outer, box, 1):
                    out.append(Violation("R-border", (eid, f"group:{parent}"),
                                         f"B3 {_name(spec, eid)} lies outside its declared container "
                                         f"{_display(spec, parent)}",
                                         code="B3"))
        for i, (ae, ab, ag) in enumerate(items):
            for be, bb, bg in items[i + 1:]:
                if not (ag or bg):
                    continue
                if (min(ab[2], bb[2]) - max(ab[0], bb[0]) > 0.5
                        and min(ab[3], bb[3]) - max(ab[1], bb[1]) > 0.5):
                    out.append(Violation("R-border", (ae, be),
                                         f"B4 {_name(spec, ae)} intersects sibling {_name(spec, be)} in "
                                         f"{_display(spec, parent) if parent else 'canvas'}; "
                                         "their declared containers must remain separate",
                                         code="B4"))
    return out


# =======================================================================================
# R-fit

def fit_rules(spec, d: Drawn) -> List[Violation]:
    w, h = d.canvas[2], d.canvas[3]      # collect: (min-x, min-y, w, h)
    if w <= 0 or h <= 0:                 # no usable viewBox: nothing to fit
        return []
    t = K.smallest_text(CL.slide_texts(d.root))
    if t is None:
        return []
    actual, unit, target, _ = K.effective_text(spec.mode, w, h, t[0], spec.title)
    if actual >= target:
        return []
    medium = (f"{'titled' if spec.title else 'untitled'} slide" if spec.mode == "slide"
              else f"{K.DOCUMENT_COLUMN_PX}px column")
    return [Violation("R-fit", ("canvas",), f"FIT smallest text ({_f(t[0])}px, {t[1]!r}) comes out at "
                      f"{actual:.2f}{unit} on a {medium} (< {target}) at {_f(w)} × {_f(h)}",
                      target - actual, TIER_FIT, code="FIT")]


# =======================================================================================
# entry points

_last: list = []                        # (spec, geom, draft, verdict) of the last check()


@scaled_spec
def check(spec, geom, draft: bytes, drawn: Optional[Drawn] = None) -> List[Violation]:
    """Every rule violation of one draft (spec and geom: what it was drawn from). The last
    verdict is kept, so the corpus hook asking again about the draft layout.py just judged
    costs nothing."""
    if _last and _last[0] is spec and _last[1] is geom and _last[2] == draft:
        return list(_last[3])
    d = drawn if drawn is not None else Drawn.parse(draft)
    out = (flow_rules(spec, d) + rt_rules(spec, d) + twin_rules(spec, geom) + label_rules(spec, d)
           + border_rules(spec, d) + containment_rules(spec, d) + fit_rules(spec, d))
    out.sort(key=lambda v: (v.tier, v.rule, v.code, v.owners, v.message))
    _last[:] = [spec, geom, draft, out]
    return list(out)


class Verdict(NamedTuple):
    clipping: int
    tier_0_count: int
    tier_0_cost: float
    checks: int
    text_shortfall: float
    shape_misses: int
    canvas_area: float


def score(viol: Sequence[Violation], probs: Sequence, geom, spec, misses: int,
          enabled_rules=None) -> tuple:
    """Verdict: canvas clipping, tier-0 count/cost, checks, text shortfall, misses, area.

    Only enabled rules count in tier 0 during selection. R-fit always counts, at
    full precision so a larger canvas cannot hide even a small text regression.
    Lost canvas content is critical: reducing other problems cannot buy new clipping.
    """
    hard = [v for v in viol if v.tier == TIER_HARD
            and (enabled_rules is None or v.rule in enabled_rules)]
    fit = sum(v.cost for v in viol if v.rule == "R-fit")
    return Verdict(CL.clipping_count(probs), len(hard), round(sum(v.cost for v in hard), 3),
                   len(probs), fit, misses, round(geom.canvas_w * geom.canvas_h, 1))


def lines(viol: Sequence[Violation]) -> List[str]:
    """The `rule:` lines layout.py prints (report only: the exit status does not count them)."""
    return [f"rule: {v.rule} {v.message}" for v in viol]


def corpus(spec, build, draft: bytes, run) -> List[dict]:
    """tests/run_corpus.py --rule-checker hook: (spec, build, draft, run) → violation dicts.
    The runner loads this file under another module name; the module layout.py imports is
    asked, so its verdict on the same draft is reused."""
    import rules as canon
    return [v.as_dict() for v in canon.check(spec, build.geom, draft)]
