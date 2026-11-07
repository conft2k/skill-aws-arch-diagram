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
           nodes' icon boxes.
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
           measure, and each node centre from the twin's left / top edge, within TWIN_TOL.
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
  R-fit    the smallest drawn text meets its medium's target (slide pt / document px;
           effective_text, tier 2; cost: the size short).

User decisions (2026-11-07, rules-design §6, after the tgw / nlb-mtls / latest2 cases): the
RT1 only-table pass, the F5 exemption for spec-placed labels and badges and L1's any-nearby-
piece side test above; after rt2.png the RT2 reach of 2S + sibling_gap (was S + sibling_gap);
after hug.png the border hug and the header band crossing as the tier-0 rule R-border.

Violation(rule, owners, message, cost, tier, code): owners are draft element ids (edge:3,
node:rtsp, group:vpca, canvas, note); tier 0 a hard rule, 2 the slide fit. score() orders
candidate drafts by them (not used by the engine yet). corpus() is tests/run_corpus.py's
--rule-checker hook. Thresholds and helpers come from check_layout / layout_const; only the
concepts new here are defined here.
"""
import math
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

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
            out.append(Violation("R-flow", (d.eid(pid),), f"F0 {d.eid(pid)}: diagonal piece {CL.fmt(s)} — "
                                 "connectors run horizontal and vertical only", len(bad), code="F0"))
    # F1 / F2: check_layout's own LINE ON LINE predicates (masked runs aside, as it does)
    on = CL.lines_on_lines(d.paths)
    for s, o, dd in on:
        if _masked(d, s, o):
            continue
        a, b = d.eid(id(s["el"])), d.eid(id(o["el"]))
        out.append(Violation("R-flow", (a, b), f"F1 {a} runs on top of {b} for {_f(dd)}px "
                             f"({CL.fmt(s)} / {CL.fmt(o)}): two flows read as one line", dd, code="F1"))
    seen = {(id(s["el"]), id(o["el"])) for s, o, _ in on}
    for s, o, dd in CL.lines_in_line(d.paths, seen):
        if _masked(d, s, o):
            continue
        a, b = d.eid(id(s["el"])), d.eid(id(o["el"]))
        out.append(Violation("R-flow", (a, b), f"F2 {a} lies on one line with {b}, {_f(dd)}px apart "
                             f"({CL.fmt(s)} / {CL.fmt(o)}): read as one line through the gap", 1.0, code="F2"))
    out += _junctions(d)
    out += _tips(spec, d)
    out += _attribution(spec, d)
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


def _junctions(d: Drawn) -> List[Violation]:
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
                out.append(Violation("R-flow", (ea, eb), f"F3 {ea} crosses {eb} at ({_f(c[0])},{_f(c[1])}) within "
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
                                             f"F4 {eid}'s arrowhead at {where} does not end on {target} "
                                             f"({'on ' + got if got else 'on no node'})", _pt_box(tip, foot),
                                             code="F4"))
                        continue
                    near = [(nid, _pt_box(tip, b)) for nid, b in d.foot.items() if nid != target]
                    near = [(nid, dd) for nid, dd in near if dd <= CL.ICON_CLEAR]
                    if near:
                        nid, dd = min(near, key=lambda t: t[1])
                        out.append(Violation("R-flow", (eid, f"node:{target}", f"node:{nid}"),
                                             f"F4 {eid}'s arrowhead at {where} into {target} is {_f(dd)}px from "
                                             f"{nid} too (< {CL.ICON_CLEAR}): it points at both", CL.ICON_CLEAR - dd,
                                             code="F4"))
                else:
                    r = d.group_rect.get(target)
                    if r is None:
                        continue
                    dd = _border_dist(tip, r)
                    if dd > CL.END_REACH:
                        out.append(Violation("R-flow", (eid, f"group:{target}"),
                                             f"F4 {eid}'s arrowhead at {where} is {_f(dd)}px from {target}'s border "
                                             f"(> {CL.END_REACH})", dd - CL.END_REACH, code="F4"))
                        continue
                    other = [(g, _border_dist(tip, b)) for g, b in d.group_rect.items() if g != target]
                    other = [(g, x) for g, x in other if x < CL.BORDER_CLEAR]
                    if other:
                        g, x = min(other, key=lambda t: t[1])
                        out.append(Violation("R-flow", (eid, f"group:{target}", f"group:{g}"),
                                             f"F4 {eid}'s arrowhead at {where} into {target} is {_f(x)}px from "
                                             f"{g}'s border too (< {CL.BORDER_CLEAR})", CL.BORDER_CLEAR - x,
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
                out.append(Violation("R-flow", (eid,), f"F5 {eid}'s {what} {s!r} is {_f(d_own)}px from its line "
                                     f"(> {CL.LABEL_REACH})", d_own - CL.LABEL_REACH, code="F5"))
            elif d_other <= d_own + CL.TEXT_GAP:
                o = d.eid(id(near["el"]))
                out.append(Violation("R-flow", (eid, o), f"F5 {eid}'s {what} {s!r} is {_f(d_other)}px from {o}'s line, "
                                     f"{_f(d_own)}px from its own line: it reads as {o}'s",
                                     d_own + CL.TEXT_GAP - d_other + 1, code="F5"))
    return out


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
        lim = spec.S + spec.const.sibling_gap
        if len(A) >= 2:
            polys = bracket(spec, d, hub, A)
            # user decision (2026-11-07, rules-design §6): the hub's only table — every line at
            # the hub associated with it — passes right beside the hub, with no bracket (tgw TGW B RT)
            only = not N and _box_box(foot, d.foot[hub]) <= lim
            if not only and not any(inside(rc, p) for p in polys):
                out.append(Violation("R-rt", (me, hn), f"RT1 {rid} at ({_f(rc[0])},{_f(rc[1])}) is outside the bracket "
                                     f"its {len(A)} associated lines at {hub} draw "
                                     f"(edges {', '.join(map(str, A))})", 1.0, code="RT1"))
        elif len(A) == 1:
            segs = d.edge_segs(A[0])
            gap = min(_box_seg(foot, s) for s in segs)
            q = min((_pt_seg(rc, s["p"], s["q"]) for s in segs), key=lambda t: t[0])[1]
            mine = set(d.edge_paths.get(A[0], ()))
            crossed = sorted({d.eid(pid) for pid, run in d.paths.items() if pid not in mine for s in run
                              if (c := seg_cross(rc, q, s["p"], s["q"])) is not None and math.dist(c, q) > 1})
            reach = rt2_reach(spec)
            if gap > reach:
                out.append(Violation("R-rt", (me, f"edge:{A[0]}"), f"RT2 {rid} is {_f(gap)}px from its one associated "
                                     f"line edge:{A[0]} (> {RT2_REACH_ICONS}S + sibling_gap = {_f(reach)})",
                                     gap - reach, code="RT2"))
            elif crossed:
                out.append(Violation("R-rt", (me, f"edge:{A[0]}") + tuple(crossed),
                                     f"RT2 {rid} reaches its associated line edge:{A[0]} only across "
                                     f"{', '.join(crossed)}", len(crossed), code="RT2"))
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
                                 f"RT3 the way from {rid} to its hub {hub} crosses {', '.join(sorted(crossed))} "
                                 f"(lines not associated with it)", len(crossed), code="RT3"))
        # RT4: nearer its hub than any other hub or any far end of N
        g_hub = _box_box(foot, d.foot[hub])
        rivals = [(f"node:{h}", _gap_to(d, foot, h, "node")) for h in sorted(hubs - {hub})]
        rivals += [(f"{kind}:{far}", _gap_to(d, foot, far, kind)) for _, _, far, kind in N if far != rid]
        closer = [(o, g) for o, g in rivals if g is not None and g <= g_hub]
        if closer:
            o, g = min(closer, key=lambda t: t[1])
            out.append(Violation("R-rt", (me, hn, o), f"RT4 {rid} is {_f(g)}px from {o}, not nearer its hub {hub} "
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
            out.append(Violation("R-rt", (me, f"group:{g}"), f"RT5 {rid} sits inside {g}, a subnet it is not "
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
                                 f"RT5 {rid} is {_f(ds)}px from its subnet {s} but {_f(x)}px from {g} (not "
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
                    worst = (spread, a[0], b[0], f"node {a[1]} / {b[1]}")
            if worst:
                spread, a, b, what = worst
                out.append(Violation("R-twin", (f"group:{a}", f"group:{b}"),
                                     f"TW {a} and {b} have one structure but are drawn {_f(spread)}px unlike on "
                                     f"{axis} ({what})", spread, code="TW"))
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
                out.append(Violation("R-label", (eid,), f"L1 {eid}'s label {on[0]['s']!r} over a background is on none "
                                     f"of the pieces of its line it sits by ({', '.join(CL.fmt(g) for g in by)})",
                                     1.0, code="L1"))
            continue
        if not any(_rule_side(box, g) for g in by):
            out.append(Violation("R-label", (eid,), f"L1 {eid}'s label {texts[0]['s']!r} is neither above a horizontal "
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

def border_rules(d: Drawn) -> List[Violation]:
    out = []
    # B1: check_layout's LINE HUGS BORDER predicate, once per connector and border owner
    seen = set()
    for s, b, dd in CL.line_hugs(d.segs, d.masks):
        a, g = d.eid(id(s["el"])), d.owner.get(id(b["el"]), "?")
        if (a, g) in seen:
            continue
        seen.add((a, g))
        where = "on top of" if dd == 0 else f"{_f(dd)}px from"
        out.append(Violation("R-border", (a, g), f"B1 {a} runs {where} {g}'s border ({CL.fmt(s)} / {CL.fmt(b)}, "
                             f"< {K.HUG_CLEAR}px): the line reads as the border", K.HUG_CLEAR - dd, code="B1"))
    # B2: the same visible pieces and bands as check_layout's LINE IN HEADER.
    bands = CL.header_bands(d.rects, d.icons, d.texts, d.owner)
    for s, r, band, how in CL.lines_in_headers(d.segs, d.masks, bands, d.owner):
        a, g = d.eid(id(s["el"])), d.owner[id(r[4])]
        out.append(Violation("R-border", (a, g), f"B2 {a} passes through {g}'s header band {CL.fmt(s)} {how} "
                             f"(band {_f(band[0])},{_f(band[1])}–{_f(band[2])},{_f(band[3])})", 1.0, code="B2"))
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
           + border_rules(d) + fit_rules(spec, d))
    out.sort(key=lambda v: (v.tier, v.rule, v.code, v.owners, v.message))
    _last[:] = [spec, geom, draft, out]
    return list(out)


def score(viol: Sequence[Violation], probs: Sequence, geom, spec, misses: int) -> tuple:
    """A candidate draft's rank, lower is better: (hard violations, their cost, check problems,
    slide points short, shapes drawn other than planned, canvas area)."""
    hard = [v for v in viol if v.tier == TIER_HARD]
    fit = sum(v.cost for v in viol if v.rule == "R-fit")
    return (len(hard), round(sum(v.cost for v in hard), 3), len(probs), round(fit, 3), misses,
            round(geom.canvas_w * geom.canvas_h, 1))


def lines(viol: Sequence[Violation]) -> List[str]:
    """The `rule:` lines layout.py prints (report only: the exit status does not count them)."""
    return [f"rule: {v.rule} {v.message}" for v in viol]


def corpus(spec, build, draft: bytes, run) -> List[dict]:
    """tests/run_corpus.py --rule-checker hook: (spec, build, draft, run) → violation dicts.
    The runner loads this file under another module name; the module layout.py imports is
    asked, so its verdict on the same draft is reused."""
    import rules as canon
    return [v.as_dict() for v in canon.check(spec, build.geom, draft)]
