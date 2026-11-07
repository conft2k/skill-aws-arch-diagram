"""Edge routing for the layout engine (W3): shapes, the space routes need, lines, labels, badges.

    plan(spec) -> [Requirement]                  space the routes need (Spec only)
    draw(spec, geom, skip=None) -> ([Element], [str])   lines, labels, badges on a solved Geometry
    shapes(spec) -> {edge n: shape}              the rule-based shape choice plan() and draw() share

The contract (signatures, z layers, ids) is layout_model's docstring; numbers are layout_const.

Shape choice (DESIGN 4.5) is a pure function of the Spec, recomputed by plan() and draw():
  0. `points` → "P"; `shape`; from_side / to_side imply one (both horizontal → H/HVH, …).
  1. row ranges overlap → H; column ranges overlap → V (a colspan node covers its whole
     span, a group its track range, a flow-row node its parent's columns; a flow-column
     node, or a box holding only such nodes, sits between rows at its stack's slot,
     Spec.flow_slot: above the parent's first row (align top), below its last (bottom),
     at its middle (center), so it never shares a grid row; two nodes of one flow column
     are apart by stack order).
     Straight edges mark the node sides they use.
  2. (a colspan is caught by 1: its V / H to a node under one of its tracks draws with a
     jog through a free bend, like a VHV.)
  3. both facing horizontal sides free (columns apart) → HVH, the vertical in a gutter.
  4. the target's facing horizontal side taken and its facing vertical side free → HV.
  5. the source's facing horizontal side taken → VH, except VHV when the VH's vertical
     leg would run through a node in the source's column (tgw: a hub's lower spokes
     through its route table) or the source is a hub (both horizontal sides taken) and
     the line is headless topology ("--", "..": tgw's upper spokes). Rules 3-5 give way to
     VHV for headless lines from one node toward one vertical side that reach both its
     left and its right (a fan of spokes), so the two sides mirror (a hub with one free
     horizontal side would otherwise get a VH on one side and a HVH on the other).
  6. otherwise VHV.
plan() also keeps a vertical leg at a node right of the headers of the boxes it enters
or leaves through their top, a HVH label's run before the bend, and an overlay a line
leaves sideways 16 inside its subnets (layout_model decision n).
Trunks: `trunk: true` instances of one spec line with one far end merge (first instance
draws the whole path and the arrowhead, the others stop at the junction); with one near end
they fork (a shared port, one arrowhead per branch). Labels and the badge of a trunk are
drawn once, on its first instance. Other `*` instances are separate lines, each labelled.

Geometry: icon ends at cx ± (S/2 + 4), top at icon.y − 4, bottom at the last label baseline
+ 8; group ends 4 off the border, at the other end's center when it faces the side, else
the group's row / column center. Several lines on one node side split ±8 (left/right) /
±10 (top/bottom), 12 apart from three on; a straight line keeps the center and the others
move ±12. A bend goes in the free stretch of its gutter (icons, labels, parallel borders
+ trunk clearance avoided), preferring a last segment of arrow_target (48 / 20), else the
middle of the free stretch nearest the target. Every candidate is tested with
check_layout's own seg_hits_box against icons, labels and borders (LINE OVER ICON/TEXT,
LINE NEAR TEXT, LINE HUGS BORDER, SHORT ARROW); edges that share a spec line or a node
side try to share one bend. skip={n: k} takes edge n's k-th clean candidate instead.

Labels and badges (DESIGN 4.6): the line is cut at container borders; the piece is the
longest horizontal one (only vertical pieces → the longest vertical). A line crossing the
AWS Cloud border ranks its piece outside the Cloud above one in the Cloud's bare strip
(Users → IGW), while a piece inside a Region still wins on length (tgw badge 2 at 518). Label baseline y − label_above / y + label_below;
beside a vertical piece x ∓ vlabel_dx (anchor end / start), baseline mid + 4. Badge cy =
y − 14 (vertical: cx = x − 22). A label goes above a horizontal piece and right of a
vertical one, badge or not (beside the badge when it sits on the same piece). Without room
there: on the line itself over a background rect, in the top layer (Z_LABEL_TOP), where no
other connector runs under it if possible; the other side last.
step_at: mid | start | end | gap (the piece inside no container but the ends' common
ones) | stem | branch | [x, y]. On a collision (label ↔ label 4, ↔ border 8, ↔ icon 8,
any line) the text moves 8 px at a time along the piece, then to the other side, then to
the next piece.
"""
from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_layout as CL  # noqa: E402
import layout_const as K  # noqa: E402
import layout_model as M  # noqa: E402
from layout_model import Box, Edge, Element, Geometry, Place, Requirement, Spec, TextLine  # noqa: E402

Pt = Tuple[float, float]

H, V, HVH, VHV, HV, VH, P = "H", "V", "HVH", "VHV", "HV", "VH", "P"
SHAPES = (H, V, HVH, VHV, HV, VH)
ALTERNATIVES = {H: (HVH, VHV), V: (VHV, HVH), HVH: (VHV, HV, VH), VHV: (HVH, VH, HV),
                HV: (VH, HVH, VHV), VH: (HV, VHV, HVH), P: ()}
HORIZ = ("left", "right")
VERT = ("top", "bottom")
MIN_SEG = 12          # shortest headless end segment (ex tgw spoke stubs 226 → 214)
NUDGE = 8             # bend / label / badge step (DESIGN 4.5-4.6)
OVERLAY_EXIT = 16     # overlay side a line leaves through ↔ its member subnet's border
OBST_CLEAR = 4        # a bend keeps this from icons and labels (LINE_CLEAR)
BADGE_CLEAR = 4       # badge circle ↔ icon / text / other badge
HUG_OVERLAP = 20      # check_layout: a parallel run longer than this next to a border is a hug


# =======================================================================================
# Topology (Spec only): shared by plan() and draw()

@dataclass
class _End:
    id: str
    kind: str                                  # node | group
    cext: Optional[Tuple[float, float]]        # column index extent
    rext: Optional[Tuple[float, float]]        # row index extent


@dataclass
class _Topo:
    shape: str
    side_a: Optional[str]
    side_b: Optional[str]
    dx: Optional[int]                          # +1 b right of a, -1 left, 0 overlap, None unknown
    dy: Optional[int]                          # +1 b below a, -1 above
    trunk: Optional[str] = None                # merge | fork (first instance and the others)
    first: Optional[int] = None                # n of the trunk's first instance
    note: str = ""                             # why (for warnings / tests)


def _indices(spec: Spec):
    return {t.id: i for i, t in enumerate(spec.cols)}, {t.id: i for i, t in enumerate(spec.rows)}


def _end(spec: Spec, eid: str, kind: str, ci, ri) -> _End:
    if kind == "group":
        g = spec.groups[eid]
        c = (ci[g.cols[0]], ci[g.cols[1]]) if g.cols else None
        r = (ri[g.rows[0]], ri[g.rows[1]]) if g.rows else None
        a = None if g.rows else spec.float_align(eid)
        if a is not None:                                   # a box holding only flow columns: its slot
            s = spec.flow_slot(g.parent, a)
            r = (s, s) if s is not None else None
        return _End(eid, kind, c, r)
    n = spec.nodes[eid]
    if n.xy is not None:
        # an xy tied to a track sits on it (`xy: [col.a2, row.bot+10]`); numbers: unknown
        c, r = ((idx[x.ref], idx[x.ref]) if isinstance(x, M.Expr) and x.kind == k else None
                for x, k, idx in ((n.xy[0], "col", ci), (n.xy[1], "row", ri)))
        return _End(eid, kind, c, r)
    c = None
    if n.col is not None:
        c1 = ci[n.col]
        c2 = ci[n.col2] if n.col2 else c1
        c = (min(c1, c2), max(c1, c2))
    elif n.parent and spec.groups[n.parent].cols:          # flow-row node: somewhere in its parent
        pc = spec.groups[n.parent].cols
        c = (ci[pc[0]], ci[pc[1]])
    r = None
    if n.row is not None:
        r = (ri[n.row], ri[n.row])
    elif n.col is not None and n.col2 is None:             # flow-column node: its stack's slot between rows
        s = spec.flow_slot(n.parent, spec.track(n.col).align)
        r = (s, s) if s is not None else None
    return _End(eid, kind, c, r)


def _rel(a, b) -> Optional[int]:
    if a is None or b is None:
        return None
    if a[1] < b[0]:
        return 1
    if b[1] < a[0]:
        return -1
    return 0


def _hside(d: Optional[int]) -> Optional[str]:
    return None if d not in (1, -1) else ("right" if d > 0 else "left")


def _vside(d: Optional[int]) -> Optional[str]:
    return None if d not in (1, -1) else ("bottom" if d > 0 else "top")


def _forced(e: Edge, dx, dy) -> Optional[str]:
    if e.points:
        return P
    if e.shape:
        return e.shape
    fs, ts = e.from_side, e.to_side
    if not (fs or ts):
        return None
    fh = (fs in HORIZ) if fs else (ts in HORIZ)
    th = (ts in HORIZ) if ts else fh
    if fh and th:
        return H if dy == 0 else HVH
    if not fh and not th:
        return V if dx == 0 else VHV
    return HV if fh else VH


def _sides(e: Edge, shape: str, dx, dy) -> Tuple[Optional[str], Optional[str]]:
    if shape in (H, HVH):
        sa, sb = _hside(dx), _hside(-dx if dx else None)
    elif shape in (V, VHV):
        sa, sb = _vside(dy), _vside(-dy if dy else None)
    elif shape == HV:
        sa, sb = _hside(dx), _vside(-dy if dy else None)
    elif shape == VH:
        sa, sb = _vside(dy), _hside(-dx if dx else None)
    else:
        sa = sb = None
    return e.from_side or sa, e.to_side or sb


def _topology(spec: Spec) -> Dict[int, _Topo]:
    ci, ri = _indices(spec)
    cache: Dict[Tuple[str, str], _End] = {}

    def end(eid, kind):
        if (eid, kind) not in cache:
            cache[(eid, kind)] = _end(spec, eid, kind, ci, ri)
        return cache[(eid, kind)]

    stack = {nid: (key, k) for key, ids in spec.flow_stacks().items() for k, nid in enumerate(ids)}
    occ = set()
    out: Dict[int, _Topo] = {}
    for e in spec.edges:
        A, B = end(e.a, e.a_kind), end(e.b, e.b_kind)
        dx, dy = _rel(A.cext, B.cext), _rel(A.rext, B.rext)
        ka = stack.get(e.a) if e.a_kind == "node" else None
        kb = stack.get(e.b) if e.b_kind == "node" else None
        if ka and kb and ka[0] == kb[0]:                # two nodes of one flow column: by stack order
            dy = 1 if kb[1] > ka[1] else -1
        shape = _forced(e, dx, dy)
        note = "override" if shape else ""
        if shape is None:
            if dy == 0:
                shape, note = H, "rows overlap"
            elif dx == 0:
                shape, note = V, "columns overlap"
        out[e.n] = _Topo(shape, None, None, dx, dy, note=note)
        if shape in (H, V):
            sa, sb = _sides(e, shape, dx, dy)
            if e.a_kind == "node" and sa:
                occ.add((e.a, sa))
            if e.b_kind == "node" and sb:
                occ.add((e.b, sb))
    # fans: a node's headless diagonal lines toward one vertical side, by horizontal side
    fan: Dict[Tuple[str, int], set] = {}
    for e in spec.edges:
        t = out[e.n]
        if t.dx in (1, -1) and t.dy in (1, -1) and not (e.head_end or e.head_start) and not e.points:
            if e.a_kind == "node":
                fan.setdefault((e.a, t.dy), set()).add(t.dx)
            if e.b_kind == "node":
                fan.setdefault((e.b, -t.dy), set()).add(-t.dx)
    for e in spec.edges:
        t = out[e.n]
        if t.shape is not None:
            continue
        A, B = end(e.a, e.a_kind), end(e.b, e.b_kind)
        dx, dy = t.dx, t.dy
        if dx in (1, -1) and dy in (1, -1):
            free_a = e.a_kind == "group" or (e.a, _hside(dx)) not in occ
            free_b = e.b_kind == "group" or (e.b, _hside(-dx)) not in occ
            vfree_b = e.b_kind == "group" or (e.b, _vside(-dy)) not in occ
            if free_a and free_b:
                t.shape, t.note = HVH, "rule 3: facing sides free"
            elif not free_b and vfree_b:
                t.shape, t.note = HV, "rule 4: target side taken"
            elif not free_a and free_b:
                hub = e.a_kind == "node" and all((e.a, s) in occ for s in HORIZ)
                if _column_blocked(spec, e, A, B, ri):
                    t.shape, t.note = VHV, "rule 5: VH leg would cross a node"
                elif hub and not (e.head_end or e.head_start):
                    t.shape, t.note = VHV, "rule 5: hub spoke (topology)"
                else:
                    t.shape, t.note = VH, "rule 5: source side taken"
            else:
                t.shape, t.note = VHV, "rule 6"
            if t.shape != VHV and not (e.head_end or e.head_start) and (
                    len(fan.get((e.a, dy), ())) == 2 or len(fan.get((e.b, -dy), ())) == 2):
                # headless spokes leaving one node up (or down) to both sides: every one
                # VHV, out of that node's top (bottom), so the two sides mirror (slide tgw
                # TGW B: VH into DR VPC's side, HVH into Analytics VPC's otherwise)
                t.shape, t.note = VHV, f"rule 5: fan of spokes to both sides (topology; not {t.shape})"
        else:
            t.shape, t.note = VHV, "rule 6 (position unknown)"
    for e in spec.edges:
        t = out[e.n]
        t.side_a, t.side_b = _sides(e, t.shape, t.dx, t.dy)
    # trunks: instances of one spec line marked trunk (or fork: bus, phase 2 → a trunk fork)
    lines: Dict[int, List[Edge]] = {}
    for e in spec.edges:
        if e.trunk or e.fork:
            lines.setdefault(e.line, []).append(e)
    for es in lines.values():
        if len(es) < 2:
            continue
        es = sorted(es, key=lambda e: e.k)
        if len({out[e.n].shape for e in es}) != 1 or out[es[0].n].shape not in (HVH, VHV):
            continue
        if len({(e.b, e.b_kind) for e in es}) == 1:
            kind = "merge"
        elif len({(e.a, e.a_kind) for e in es}) == 1:
            kind = "fork"
        else:
            continue
        for e in es:
            out[e.n].trunk, out[e.n].first = kind, es[0].n
    return out


def _column_blocked(spec: Spec, e: Edge, A: _End, B: _End, ri) -> bool:
    """Would a VH's vertical leg (the source's column, from its row to the target's) run
    through another node? Spec-only, by track indices."""
    if e.a_kind != "node" or A.cext is None or A.rext is None or B.rext is None:
        return False
    lo, hi = sorted((A.rext[0], B.rext[0]))
    for n in spec.nodes.values():
        if n.id in (e.a, e.b) or n.xy is not None or n.col is None or n.row is None:
            continue
        ci, _ = _indices(spec)
        c1 = ci[n.col]
        c2 = ci[n.col2] if n.col2 else c1
        if (c1 + c2) / 2 == (A.cext[0] + A.cext[1]) / 2 and lo <= ri[n.row] <= hi:
            return True
    return False


def shapes(spec: Spec) -> Dict[int, str]:
    """{edge n: shape} by the rules above (also what plan() and draw() use)."""
    return {n: t.shape for n, t in _topology(spec).items()}


# =======================================================================================
# Containment chains (both phases)

def _common_chain(spec: Spec, nids: Sequence[str]) -> List[str]:
    chains = [spec.node_chain(n) for n in nids if n in spec.nodes]
    if not chains:
        return []
    common = set(chains[0]).intersection(*map(set, chains[1:]))
    return [g for g in chains[0] if g in common]


def _chain(spec: Spec, eid: str, kind: str) -> List[str]:
    """Groups containing an endpoint, innermost first (a group endpoint: itself first; an
    overlay: itself, then its members' common containers; a border node: its VPC first)."""
    if kind == "group":
        g = spec.groups[eid]
        if g.overlay:
            return [eid] + _common_chain(spec, g.over)
        return spec.ancestors(eid)
    n = spec.nodes[eid]
    ch = spec.node_chain(eid)
    return ([n.on] + ch) if n.on else ch


def _nonshared(spec: Spec, e: Edge) -> Tuple[List[str], List[str], List[str]]:
    """(a's groups not containing b, b's not containing a, common) innermost first; the
    endpoint groups themselves are left out. A border node counts its VPC only when the
    other end is inside that VPC."""
    ca, cb = _chain(spec, e.a, e.a_kind), _chain(spec, e.b, e.b_kind)
    na = spec.nodes.get(e.a) if e.a_kind == "node" else None
    nb = spec.nodes.get(e.b) if e.b_kind == "node" else None
    if na is not None and na.on and na.on not in cb:
        ca = ca[1:]
    if nb is not None and nb.on and nb.on not in ca:
        cb = cb[1:]
    shared = set(ca) & set(cb)
    sa = [g for g in ca if g not in shared and not (e.a_kind == "group" and g == e.a)]
    sb = [g for g in cb if g not in shared and not (e.b_kind == "group" and g == e.b)]
    return sa, sb, [g for g in ca if g in shared]


# =======================================================================================
# plan(): the space each route needs, as difference constraints

def _lines_count(spec: Spec, nid: str) -> int:
    n = spec.nodes[nid]
    return (1 if n.label else 0) + len(n.sub)


def _off(spec: Spec, eid: str, kind: str, side: str) -> float:
    """Distance from an endpoint's variable to its port on `side` (along the axis)."""
    if kind == "group":
        return K.GROUP_END_GAP
    S = spec.S
    if side == "bottom":
        k = _lines_count(spec, eid)
        return S / 2 + (K.NODE_LABEL_DY + K.SUB_PITCH * (k - 1) + 8 if k else K.END_GAP)
    return S / 2 + K.END_GAP


def _var(eid: str, kind: str, edge: str) -> str:
    return f"group:{eid}.{edge}" if kind == "group" else f"node:{eid}"


def _is_span(spec: Spec, eid: str, kind: str) -> bool:
    return kind == "node" and spec.nodes[eid].col2 is not None


def plan(spec: Spec) -> List[Requirement]:
    """The space every route needs (DESIGN 4.3 #10) as Requirements, from the Spec alone:
    a straight line's arrow segment (soft arrow_target, hard arrow_min) and label run, a
    HVH / VHV bend's gutter (trunk_clear soft / HUG_CLEAR hard from the boxes it passes,
    the arrow into the target), an HV / VH's two legs. Fork trunks get none: the router
    puts their trunk beside the targets."""
    m = spec.const
    topo = _topology(spec)
    ci, ri = _indices(spec)
    reqs: List[Requirement] = []
    seen = set()

    def add(axis, a, b, d, why, owner, soft=False):
        key = (axis, a, b, round(d, 2), soft)
        if a != b and key not in seen:
            seen.add(key)
            reqs.append(Requirement(axis, a, b, float(d), why, owner, soft))

    def ext(gid, axis):
        g = spec.groups[gid]
        tr, idx = (g.cols, ci) if axis == "x" else (g.rows, ri)
        return (idx[tr[0]], idx[tr[1]]) if tr else None

    def outer(chain, other, axis, d, near):
        """Outermost group of `chain` wholly before (near: a's, toward d) the other end."""
        out = None
        for g in chain:
            ge = ext(g, axis)
            if ge is None or other is None:
                break
            if near:
                ok = ge[1] < other[0] if d > 0 else ge[0] > other[1]
            else:
                ok = ge[0] > other[1] if d > 0 else ge[1] < other[0]
            if not ok:
                break
            out = g
        return out

    for e in spec.edges:
        t = topo[e.n]
        if t.shape == P:
            continue
        owner = M.edge_eid(e.n)
        A = _end(spec, e.a, e.a_kind, ci, ri)
        B = _end(spec, e.b, e.b_kind, ci, ri)
        na, nb, _ = _nonshared(spec, e)
        follower = t.trunk == "merge" and t.first != e.n
        hs, he = e.head_start, e.head_end and not follower
        shape = t.shape
        if shape == V and (_is_span(spec, e.a, e.a_kind) or _is_span(spec, e.b, e.b_kind)):
            shape = VHV                 # a colspan's V jogs between the two centers
        if shape == H and (_is_span(spec, e.a, e.a_kind) or _is_span(spec, e.b, e.b_kind)) and t.dy != 0:
            shape = HVH

        def seg(head, soft):
            return (m.arrow_target if soft else m.arrow_min) if head else MIN_SEG

        for axis, d in (("x", t.dx), ("y", t.dy)):
            if d not in (1, -1):
                continue
            hor = axis == "x"
            sa, sb = (_hside(d), _hside(-d)) if hor else (_vside(d), _vside(-d))
            ea, eb = (("R", "L") if d > 0 else ("L", "R")) if hor else (("B", "T") if d > 0 else ("T", "B"))
            va, vb = _var(e.a, e.a_kind, ea), _var(e.b, e.b_kind, eb)
            oa, ob = _off(spec, e.a, e.a_kind, sa), _off(spec, e.b, e.b_kind, sb)
            ae, be = (A.cext, B.cext) if hor else (A.rext, B.rext)

            def req(lo_a, hi_b, need, why, soft):
                add(axis, *((lo_a, hi_b) if d > 0 else (hi_b, lo_a)), need, why, owner, soft)

            if (shape == H and hor) or (shape == V and not hor):
                for soft in (False, True):
                    need = oa + ob + max(seg(hs, soft), seg(he, soft))
                    if soft and need == oa + ob + max(seg(hs, False), seg(he, False)):
                        continue
                    req(va, vb, need, f"arrow {need - oa - ob:g} + ends {e.a}→{e.b}", soft)
                if hor:
                    _label_req(spec, e, d, na, nb, ae, be, outer, req, va, vb, oa, ob)
            elif (shape == HVH and hor) or (shape == VHV and not hor):
                ga, gb = outer(na, be, axis, d, True), outer(nb, ae, axis, d, False)
                if t.trunk == "fork" and not ga:
                    # a bare source (IGW on the VPC border): the trunk runs inside the
                    # target's own box, before the branch arrows (ex gwlb)
                    gb = nb[0] if gb else None
                    if gb:
                        for soft in (False, True):
                            clear = m.trunk_clear if soft else K.HUG_CLEAR
                            req(f"group:{gb}.{eb}", vb, clear + ob + seg(he, soft), f"fork trunk inside {gb}", soft)
                        if hor and d > 0:
                            # the trunk enters these boxes through their top / bottom border:
                            # it passes right of their header (layout width + 8)
                            for g in nb:
                                grp = spec.groups[g]
                                if grp.label:
                                    st = K.style(grp.type)
                                    hw = st.title_dx + M.text_width(grp.label, st.title_size) + OBST_CLEAR + 1
                                    req(f"group:{g}.L", vb, hw + ob + seg(he, False), f"fork trunk past {g}'s header", False)
                                    # preferred: the render's wider glyphs + 8, and the arrow at its target length
                                    hw = st.title_dx + M.layout_text_width(grp.label, st.title_size) + K.LABEL_CLEAR
                                    req(f"group:{g}.L", vb, hw + ob + seg(he, True), f"fork trunk past {g}'s header", True)
                    continue
                xa = f"group:{ga}.{ea}" if ga else va
                xb = f"group:{gb}.{eb}" if gb else vb
                extra = MIN_SEG if (not hor and (e.label or e.verb or e.step)) else 0
                hard = None
                for soft in (False, True):
                    clear = m.trunk_clear if soft else K.HUG_CLEAR
                    need = (clear if ga else oa + seg(hs, soft)) + (clear if gb else ob + seg(he, soft)) + extra
                    if soft and need == hard:
                        continue
                    hard = need
                    req(xa, xb, need, f"{'trunk' if t.trunk else 'bend'} gutter {e.a}→{e.b}", soft)
                texts = [s for s in (e.label, e.verb) if s]
                if not hor and texts and not follower and m.name == "document":
                    # a VHV's horizontal piece holds its label with 8 to spare each side
                    # past a split port (ex tgw "VPC attachment" on a spoke); slides put a
                    # label that does not fit beside the vertical piece instead
                    w = max(M.layout_text_width(s, K.TEXT_PROTO.size) for s in texts)
                    ha, hb = (f"node:{e.a}" if e.a_kind == "node" else None), (f"node:{e.b}" if e.b_kind == "node" else None)
                    if ha and hb and t.dx in (1, -1):
                        need = w + 2 * K.LABEL_CLEAR + K.PORT_TOPBOT
                        add("x", *((ha, hb) if t.dx > 0 else (hb, ha)), need, f"label {texts[0]!r} run on the bend", owner, True)
                if hor and texts and not follower:
                    # the label's run: the piece before the bend holds the text + 8 from the
                    # box (or icon) and 4 from the bend, the arrow piece follows (ex nfw
                    # "VPC attachment" 316 − 220); a preference, the router finds another piece
                    w = max(M.layout_text_width(s, K.TEXT_PROTO.size) for s in texts)
                    near = K.LABEL_CLEAR if ga else spec.S / 2 + K.ICON_CLEAR
                    far = m.trunk_clear if gb else ob + seg(he, True)
                    req(xa, xb, near + w + OBST_CLEAR + far, f"label {texts[0]!r} run before the bend", True)
            elif (shape == HV and hor) or (shape == VH and not hor):
                if e.b_kind == "node":         # a's port → b's center line
                    req(va, f"node:{e.b}", oa + seg(hs, False), f"first leg {e.a}→{e.b}", False)
            elif (shape == HV and not hor) or (shape == VH and hor):
                if e.a_kind == "node":         # a's center line → b's port
                    for soft in (False, True):
                        if soft and seg(he, True) == seg(he, False):
                            continue
                        req(f"node:{e.a}", vb, ob + seg(he, soft), f"arrow {seg(he, soft):g} into {e.b}", soft)
        # a vertical leg at a node crosses the top border of the node's boxes the other end
        # is outside of (entering from above, or leaving upward): it passes right of their
        # header (badge, title, CIDR; layout widths + 8), as alb's RDS replication
        # a line leaving an overlay (ASG) box sideways starts 4 off its border: keep the
        # member subnets' parallel border 16 beyond it so the start reads as the ASG's
        # (ex alb SQL 816 → 836, nlb 916 → 932; QR 48's 8 elsewhere)
        for gid, kind, side in ((e.a, e.a_kind, t.side_a), (e.b, e.b_kind, t.side_b)):
            if kind == "group" and spec.groups[gid].overlay and side in ("left", "right"):
                for sub in dict.fromkeys(spec.nodes[m].parent for m in spec.groups[gid].over):
                    if sub is None:
                        continue
                    if side == "right":
                        add("x", f"group:{gid}.R", f"group:{sub}.R", OVERLAY_EXIT, f"line out of {gid} clear of {sub}", owner)
                    else:
                        add("x", f"group:{sub}.L", f"group:{gid}.L", OVERLAY_EXIT, f"line out of {gid} clear of {sub}", owner)
        if shape == HVH and t.dx in (1, -1):
            # the vertical leg drops past the labels of an end it leaves sideways: the
            # stack's widest line, not just the lines beside a neighbour (bedrock-dx PC)
            if e.a_kind == "node" and t.dy == 1:
                _gutter_reqs(spec, e.a, B, t.dx, owner, add)
            if e.b_kind == "node" and t.dy == -1:
                _gutter_reqs(spec, e.b, A, -t.dx, owner, add)
        if t.dy == 1 and shape in (V, VHV, HV) and e.b_kind == "node":
            _header_reqs(spec, e.b, nb, owner, add)
        if t.dy == -1 and shape in (V, VHV, VH) and e.a_kind == "node":
            _header_reqs(spec, e.a, na, owner, add)
    return reqs


def _half(spec: Spec, n) -> float:
    """A node's footprint half width (icon or widest label line at 0.6 em), as the solver's."""
    ws = [M.layout_text_width(n.label, K.label_size(spec.S))] if n.label else []
    ws += [M.layout_text_width(s, K.TEXT_SUB.size) for s in n.sub]
    return float(math.ceil(max([spec.S] + ws) / 2 - 1e-9))


def _gutter_reqs(spec: Spec, nid: str, other: _End, d: int, owner: str, add) -> None:
    """A HVH leaving node `nid` sideways (toward d) and turning down: its vertical runs
    between nid and the first sibling on nid's row toward the other end, past both label
    stacks, so those two keep their whole footprints (widest lines) a sibling gap apart.
    (The solver separates side-by-side nodes by the label lines level with each other
    only.)"""
    n = spec.nodes[nid]
    if n.on or n.xy is not None or n.col is None or n.row is None or other.cext is None:
        return
    ci, _ = _indices(spec)
    lo, hi = ci[n.col], ci[n.col2 or n.col]
    for o in spec.nodes.values():
        if o.id == nid or o.parent != n.parent or o.on or o.xy is not None or o.col is None or o.row != n.row:
            continue
        olo, ohi = ci[o.col], ci[o.col2 or o.col]
        if not (hi < olo <= other.cext[1] if d > 0 else other.cext[0] <= ohi < lo):
            continue
        need = spec.const.sibling_gap + _half(spec, n) + _half(spec, o)
        a, b = (nid, o.id) if d > 0 else (o.id, nid)
        add("x", f"node:{a}", f"node:{b}", need, f"bend gutter past {nid}'s labels | {o.id}", owner)


def _header_reqs(spec: Spec, nid: str, groups: Sequence[str], owner: str, add) -> None:
    if spec.nodes[nid].on or spec.nodes[nid].xy is not None:
        return
    for g in groups:
        grp = spec.groups[g]
        if grp.overlay:
            continue
        st = K.style(grp.type)
        for soft, tw, clear in ((False, M.text_width, OBST_CLEAR + 1), (True, M.layout_text_width, K.LABEL_CLEAR)):
            w = max([tw(grp.label, st.title_size)] if grp.label else [0.0]
                    + ([tw(grp.cidr, K.TEXT_CIDR.size)] if grp.cidr else []))
            if w:
                add("x", f"group:{g}.L", f"node:{nid}", st.title_dx + w + clear,
                    f"vertical line at {nid} passes right of {g}'s header", owner, soft)


def _label_req(spec, e, d, na, nb, ae, be, outer, req, va, vb, oa, ob):
    """A straight line's label needs a run of text + 8 each side between its ends. Which
    piece it lands on (outside the Cloud, inside a Region, ...) is the router's choice on
    the solved geometry, so only the whole line is required; when both ends sit in groups
    of their own, the solver's paddings already size the pieces."""
    texts = [s for s in (e.label, e.verb) if s]
    if not texts:
        return
    w = max(M.layout_text_width(s, K.TEXT_PROTO.size) for s in texts)
    cloud = spec.cloud_id()
    if e.label and cloud and (cloud in na) != (cloud in nb):
        # a protocol label on a line into the AWS Cloud from outside sits outside it, clear
        # of the Cloud and Region borders (DG "Room outside the AWS Cloud", ex alb 110 px)
        wl = M.layout_text_width(e.label, K.TEXT_PROTO.size)
        ea, eb = ("R", "L") if d > 0 else ("L", "R")
        if cloud in nb:
            end_a = spec.S / 2 + K.ICON_CLEAR if e.a_kind == "node" else oa + K.LABEL_CLEAR
            req(va, f"group:{cloud}.{eb}", end_a + wl + K.LABEL_CLEAR, f"label {e.label!r} outside the Cloud", False)
        else:
            end_b = spec.S / 2 + K.ICON_CLEAR if e.b_kind == "node" else ob + K.LABEL_CLEAR
            req(f"group:{cloud}.{ea}", vb, K.LABEL_CLEAR + wl + end_b, f"label {e.label!r} outside the Cloud", False)
    if outer(na, be, "x", d, True) and outer(nb, ae, "x", d, False):
        return
    end_a = spec.S / 2 + K.ICON_CLEAR if e.a_kind == "node" else oa + K.LABEL_CLEAR
    end_b = spec.S / 2 + K.ICON_CLEAR if e.b_kind == "node" else ob + K.LABEL_CLEAR
    req(va, vb, end_a + w + end_b, f"label {texts[0]!r} run", False)
    if e.step is not None and e.step_at in (None, "mid") and e.label_at in (None, "above"):
        # preferred: room for the badge beside the label, both above the line
        need = end_a + 2 * K.BADGE_R + COMBO_GAP + w + end_b
        req(va, vb, need, f"badge {e.step} + label {texts[0]!r} run", True)


# =======================================================================================
# draw(): context

class _Ctx:
    """Static obstacles of a solved Geometry. Node labels use the conservative 0.6 em glyph
    boxes: the checker's 0.55 em runs short of the render on capitals and underscores
    (bedrock-dx CLAUDE_CODE_USE_BEDROCK=1), and a line should miss the real glyphs. Headers
    keep the checker's boxes (plan() reserves their room at 0.6 em already)."""

    def __init__(self, spec: Spec, geom: Geometry):
        self.spec, self.geom = spec, geom
        self.m = K.mode(geom.mode or spec.mode)
        self.S = geom.S or spec.S
        self.node_icons: List[Box] = []
        self.badges: List[Box] = []          # group badge images
        self.texts: List[Box] = []           # node labels, headers
        self.borders: List[Tuple[str, float, float, float, str]] = []   # (h|v, pos, lo, hi, gid)
        self.border_segs: List[Tuple[Pt, Pt]] = []
        for gid, g in geom.groups.items():
            r = g.rect
            self.borders += [("h", r.y0, r.x0, r.x1, gid), ("h", r.y1, r.x0, r.x1, gid),
                             ("v", r.x0, r.y0, r.y1, gid), ("v", r.x1, r.y0, r.y1, gid)]
            self.border_segs += [((r.x0, r.y0), (r.x1, r.y0)), ((r.x1, r.y0), (r.x1, r.y1)),
                                 ((r.x1, r.y1), (r.x0, r.y1)), ((r.x0, r.y1), (r.x0, r.y0))]
            if g.badge:
                self.badges.append(g.badge)
            for t in (g.title, g.cidr):
                if t:
                    self.texts.append(t.box())
        for n in geom.nodes.values():
            self.node_icons.append(n.icon)
            self.texts += [t.box(conservative=True) for t in n.lines]
        self.icons = self.node_icons + self.badges
        # obstacle tuples as _line_problems tests them (icons + 1, texts + LINE_CLEAR)
        self.icon_t = [(b.expand(1).t(), b) for b in self.icons]
        self.text_t = [(b.expand(K.LINE_CLEAR).t(), b) for b in self.texts]
        cloud = spec.cloud_id()
        self.cloud = geom.groups[cloud].rect if cloud in geom.groups else None


@dataclass
class _EG:
    """Endpoint geometry."""
    id: str
    kind: str
    box: Box             # icon or rect
    cx: float
    cy: float
    bottom: float        # bottom port y
    rowc: float          # group: its row center (or rect center)
    colc: float


def _eg(spec: Spec, geom: Geometry, eid: str, kind: str) -> _EG:
    if kind == "group":
        r = geom.groups[eid].rect
        g = spec.groups[eid]
        rowc = geom.rows[g.rows[0]] if g.rows and g.rows[0] == g.rows[1] and g.rows[0] in geom.rows else r.cy
        colc = geom.cols[g.cols[0]] if g.cols and g.cols[0] == g.cols[1] and g.cols[0] in geom.cols else r.cx
        if not r.y0 < rowc < r.y1:
            rowc = r.cy
        if not r.x0 < colc < r.x1:
            colc = r.cx
        return _EG(eid, kind, r, r.cx, r.cy, r.y1 + K.GROUP_END_GAP, rowc, colc)
    n = geom.nodes[eid]
    bottom = (n.last_baseline + 8) if n.lines else n.icon.y1 + K.END_GAP
    return _EG(eid, kind, n.icon, n.cx, n.cy, bottom, n.cy, n.cx)


def _port(g: _EG, side: str, toward: float, off: float = 0.0) -> Pt:
    """Where a line meets an endpoint on `side`; toward = the other end's coordinate along
    the side (a group uses it when it faces the side, else its row / column center)."""
    b = g.box
    if g.kind == "group":
        if side in HORIZ:
            y = toward if b.y0 + 4 < toward < b.y1 - 4 else g.rowc
            return (b.x0 - K.GROUP_END_GAP if side == "left" else b.x1 + K.GROUP_END_GAP, y + off)
        x = toward if b.x0 + 4 < toward < b.x1 - 4 else g.colc
        return (x + off, b.y0 - K.GROUP_END_GAP if side == "top" else b.y1 + K.GROUP_END_GAP)
    if side == "left":
        return (b.x0 - K.END_GAP, g.cy + off)
    if side == "right":
        return (b.x1 + K.END_GAP, g.cy + off)
    if side == "top":
        return (g.cx + off, b.y0 - K.END_GAP)
    return (g.cx + off, g.bottom)


def _simplify(pts: Sequence[Pt]) -> List[Pt]:
    out: List[Pt] = []
    for p in pts:
        p = (float(p[0]), float(p[1]))
        if out and abs(out[-1][0] - p[0]) < 1e-6 and abs(out[-1][1] - p[1]) < 1e-6:
            continue
        if len(out) >= 2:
            (x0, y0), (x1, y1) = out[-2], out[-1]
            if (abs(x0 - x1) < 1e-6 and abs(x1 - p[0]) < 1e-6) or (abs(y0 - y1) < 1e-6 and abs(y1 - p[1]) < 1e-6):
                # collinear: drop the middle point unless the line doubles back
                if (x1 - x0) * (p[0] - x1) >= 0 and (y1 - y0) * (p[1] - y1) >= 0:
                    out[-1] = p
                    continue
        out.append(p)
    return out


def _len(p: Pt, q: Pt) -> float:
    return math.hypot(q[0] - p[0], q[1] - p[1])


# =======================================================================================
# draw(): candidate validation

def _line_problems(ctx: _Ctx, pts: Sequence[Pt], hs: bool, he: bool) -> List[str]:
    """What check_layout would say about these segments (plus a 1 px margin round icons)."""
    probs = []
    segs = list(zip(pts, pts[1:]))
    if not segs:
        return ["no segment"]
    for i, (p, q) in enumerate(segs):
        x0, x1 = (p[0], q[0]) if p[0] <= q[0] else (q[0], p[0])
        y0, y1 = (p[1], q[1]) if p[1] <= q[1] else (q[1], p[1])
        for t, b in ctx.icon_t:
            if t[0] <= x1 and x0 <= t[2] and t[1] <= y1 and y0 <= t[3] and CL.seg_hits_box(p, q, t):
                probs.append(f"LINE OVER ICON ({b.x0:g},{b.y0:g})")
                break
        for t, b in ctx.text_t:
            if t[0] <= x1 and x0 <= t[2] and t[1] <= y1 and y0 <= t[3] and CL.seg_hits_box(p, q, t):
                probs.append(f"LINE OVER TEXT ({b.x0:.0f},{b.y0:.0f})")
                break
        horiz = abs(p[1] - q[1]) < 0.5
        vert = abs(p[0] - q[0]) < 0.5
        for ax, pos, lo, hi, gid in ctx.borders:
            if horiz and ax == "h":
                d, s0, s1 = abs(p[1] - pos), max(min(p[0], q[0]), lo), min(max(p[0], q[0]), hi)
            elif vert and ax == "v":
                d, s0, s1 = abs(p[0] - pos), max(min(p[1], q[1]), lo), min(max(p[1], q[1]), hi)
            else:
                continue
            if d < K.HUG_CLEAR and s1 - s0 > HUG_OVERLAP:
                probs.append(f"LINE HUGS BORDER {gid}")
                break
        if i and not (horiz or vert):
            probs.append("diagonal")
    for i in range(1, len(segs)):            # doubling back on itself
        (p0, p1), (q0, q1) = segs[i - 1], segs[i]
        d1 = (p1[0] - p0[0], p1[1] - p0[1])
        d2 = (q1[0] - q0[0], q1[1] - q0[1])
        if d1[0] * d2[0] + d1[1] * d2[1] < 0:
            probs.append("doubles back")
    if he and _len(*segs[-1]) < K.MIN_ARROW:
        probs.append("SHORT ARROW (end)")
    if hs and _len(*segs[0]) < K.MIN_ARROW:
        probs.append("SHORT ARROW (start)")
    return probs


def _name_prob(ctx: _Ctx, p: str) -> str:
    """A _line_problems entry with the node (or group) it hits named."""
    m = re.match(r"(LINE OVER (?:TEXT|ICON)) \((-?[\d.]+),(-?[\d.]+)\)$", p)
    if not m:
        return p
    x, y = float(m.group(2)), float(m.group(3))
    for nid, n in ctx.geom.nodes.items():
        if m.group(1).endswith("ICON") and abs(n.icon.x0 - x) < 1 and abs(n.icon.y0 - y) < 1:
            return f"{m.group(1)} of {nid}"
        for t in n.lines:
            b = t.box(conservative=True)
            if m.group(1).endswith("TEXT") and abs(b.x0 - x) < 1 and abs(b.y0 - y) < 1:
                return f"{m.group(1)} {t.text!r} of {nid}"
    for gid, g in ctx.geom.groups.items():
        for t in (g.title, g.cidr):
            if t and abs(t.box().x0 - x) < 1 and abs(t.box().y0 - y) < 1:
                return f"{m.group(1)} {t.text!r} ({gid}'s header)"
    return p


def _expr_text(e: M.Expr) -> str:
    base = {"num": "", "col": f"col.{e.ref}", "row": f"row.{e.ref}", "gap": f"gap({e.ref},{e.ref2})",
            "label": f"{e.ref}.label.{e.attr}"}.get(e.kind, f"{e.ref}.{e.attr}")
    if not base:
        return M.fmt_num(e.offset)
    return base + (f"{'+' if e.offset > 0 else '-'}{M.fmt_num(abs(e.offset))}" if e.offset else "")


def _subtract(lo: float, hi: float, blocks) -> List[Tuple[float, float]]:
    free, cur = [], lo
    for s, t in sorted(blocks):
        if t < cur:
            continue
        if s > cur:
            free.append((cur, min(s, hi)))
        cur = max(cur, t)
        if cur >= hi:
            break
    if cur <= hi:
        free.append((cur, hi))
    return [(a, b) for a, b in free if b - a >= 0 and a <= hi and b >= lo]


def _free(ctx: _Ctx, leg_x: bool, lo: float, hi: float, s0: float, s1: float, clear: float):
    """Free stretches for a leg at v ∈ [lo, hi] (x when leg_x: a vertical leg) running
    s0..s1 on the other axis: icons and labels + 4, parallel borders + clear blocked."""
    if lo > hi:
        return []
    s0, s1 = min(s0, s1), max(s0, s1)
    blocks = []
    for b in ctx.icons + ctx.texts:
        a0, a1, o0, o1 = (b.x0, b.x1, b.y0, b.y1) if leg_x else (b.y0, b.y1, b.x0, b.x1)
        if o1 + OBST_CLEAR > s0 and o0 - OBST_CLEAR < s1:
            blocks.append((a0 - OBST_CLEAR, a1 + OBST_CLEAR))
    for ax, pos, l0, l1, _ in ctx.borders:
        if (ax == "v") == leg_x and min(l1, s1) - max(l0, s0) > HUG_OVERLAP:
            blocks.append((pos - clear, pos + clear))
    return _subtract(lo, hi, blocks)


# =======================================================================================
# draw(): one edge's route

@dataclass
class _Route:
    n: int
    shape: str
    pts: List[Pt]            # what is drawn
    hs: bool                 # marker-start drawn
    he: bool                 # marker-end drawn
    probs: List[str] = field(default_factory=list)
    stem: Tuple[int, int] = (0, 0)   # segment index range of the trunk's shared part (stem)
    bend: Optional[float] = None
    quality: int = 3                 # 0 clean + label/badge at their first spot, 1 clean + placed, 2 clean, 3 dirty


class _Edge:
    """Everything draw() needs about one edge: endpoints, sides, ports, chains."""

    def __init__(self, ctx: _Ctx, e: Edge, t: _Topo):
        self.e, self.t = e, t
        spec, geom = ctx.spec, ctx.geom
        self.A = _eg(spec, geom, e.a, e.a_kind)
        self.B = _eg(spec, geom, e.b, e.b_kind)
        self.na, self.nb, _ = _nonshared(spec, e)
        dx = t.dx if t.dx in (1, -1) else (1 if self.B.cx >= self.A.cx else -1)
        dy = t.dy if t.dy in (1, -1) else (1 if self.B.cy >= self.A.cy else -1)
        self.dx, self.dy = dx, dy
        self.off_a = e.from_offset or 0.0
        self.off_b = e.to_offset or 0.0
        follower = t.trunk is not None and t.first != e.n
        self.hs = e.head_start and not (t.trunk == "fork" and follower)
        self.he = e.head_end and not (t.trunk == "merge" and follower)

    def sides(self, shape: str) -> Tuple[str, str]:
        """The chosen shape uses the topology's sides (hints included); an alternative
        shape takes plain sides by direction."""
        t, e = self.t, self.e
        if shape == t.shape:
            sa, sb = t.side_a, t.side_b
            d = _sides(e, shape, self.dx, self.dy)
            return sa or d[0], sb or d[1]
        return _sides(Edge(e.n, e.a, e.b, e.op), shape, self.dx, self.dy)

    def ends(self, shape: str, oa: float, ob: float) -> Tuple[Pt, Pt]:
        sa, sb = self.sides(shape)
        A, B = self.A, self.B
        pa = _port(A, sa, B.cy if sa in HORIZ else B.cx, oa)
        pb = _port(B, sb, A.cy if sb in HORIZ else A.cx, ob)
        return pa, pb

    def aligned(self) -> bool:
        """A straight H / V whose two ends really share the line (no colspan jog)."""
        if self.t.shape == H:
            return self.A.kind == "group" or self.B.kind == "group" or abs(self.A.cy - self.B.cy) < 0.5
        if self.t.shape == V:
            return self.A.kind == "group" or self.B.kind == "group" or abs(self.A.cx - self.B.cx) < 0.5
        return False


def _path(shape: str, pa: Pt, pb: Pt, bend: Optional[float]) -> List[Pt]:
    if shape.startswith("U"):            # a detour out of one side of both ends
        shape = shape[1:]
    if shape == H:
        if abs(pa[1] - pb[1]) < 0.5:
            return [pa, pb]
        x = bend if bend is not None else (pa[0] + pb[0]) / 2
        return [pa, (x, pa[1]), (x, pb[1]), pb]
    if shape == V:
        if abs(pa[0] - pb[0]) < 0.5:
            return [pa, pb]
        y = bend if bend is not None else (pa[1] + pb[1]) / 2
        return [pa, (pa[0], y), (pb[0], y), pb]
    if shape == HVH:
        return [pa, (bend, pa[1]), (bend, pb[1]), pb]
    if shape == VHV:
        return [pa, (pa[0], bend), (pb[0], bend), pb]
    if shape == HV:
        return [pa, (pb[0], pa[1]), pb]
    if shape == VH:
        return [pa, (pa[0], pb[1]), pb]
    raise ValueError(shape)


def _bends(ctx: _Ctx, x: _Edge, shape: str, pa: Pt, pb: Pt) -> List[float]:
    """Ordered bend coordinates for a HVH (x of the vertical) / VHV (y of the horizontal);
    a V / H with a jog uses the same search. [] for shapes without a free bend."""
    e, m = x.e, ctx.m
    if shape in (HVH, H):
        leg_x, i = True, 0
    elif shape in (VHV, V):
        leg_x, i = False, 1
    else:
        return []
    if shape in (H, V) and abs(pa[1 - i] - pb[1 - i]) < 0.5:
        return []
    hint = e.bend_x if leg_x else e.bend_y
    if hint is not None and hint != "gap":
        try:
            return [M.eval_expr(hint, ctx.geom)]
        except (KeyError, ValueError):
            pass
    if shape in (HVH, VHV):
        sa, sb = x.sides(shape)
        if sa == sb:
            return _out_and_back(ctx, x, leg_x, i, pa, pb, sa)
    a, b = pa[i], pb[i]
    d = 1 if b >= a else -1
    if shape in (H, V):          # a jog: the bend runs along the other axis
        a, b = pa[i], pb[i]
    s0, s1 = pa[1 - i], pb[1 - i]
    min_a = K.MIN_ARROW if x.hs else MIN_SEG
    min_b = K.MIN_ARROW if x.he else MIN_SEG
    lo, hi = (a + min_a, b - min_b) if d > 0 else (b + min_b, a - min_a)
    # the gutter: outside a's groups that lie before b, and b's that lie after that
    ga, gb = a, b
    for gid in x.na:
        r = ctx.geom.groups[gid].rect
        edge = (r.x1 if d > 0 else r.x0) if leg_x else (r.y1 if d > 0 else r.y0)
        if (edge - ga) * d >= 0 and (b - edge) * d > 0:
            ga = edge
        else:
            break
    for gid in x.nb:
        r = ctx.geom.groups[gid].rect
        edge = (r.x0 if d > 0 else r.x1) if leg_x else (r.y0 if d > 0 else r.y1)
        if (edge - ga) * d > 0 and (gb - edge) * d >= 0:
            gb = edge
        else:
            break
    if x.t.trunk == "fork" and ga == a and x.nb:
        r = ctx.geom.groups[x.nb[0]].rect          # bare source: trunk inside the target's box
        edge = (r.x0 if d > 0 else r.x1) if leg_x else (r.y0 if d > 0 else r.y1)
        if (edge - a) * d > 0 and (b - edge) * d > 0:
            ga, gb = edge, b
    glo, ghi = (max(lo, ga), min(hi, gb)) if d > 0 else (max(lo, gb), min(hi, ga))
    want = b - d * m.arrow_target if x.he or (x.t.trunk == "merge") else None
    out: List[float] = []

    def push(v):
        r = round(v * 2) / 2
        v = r if lo - 1e-6 <= r <= hi + 1e-6 else v
        if lo - 1e-6 <= v <= hi + 1e-6 and all(abs(v - u) > 0.25 for u in out):
            out.append(v)

    tiers = []
    for (l, h) in ((glo, ghi), (lo, hi)):
        for clear in (m.trunk_clear, K.HUG_CLEAR):
            tiers.append(_free(ctx, leg_x, l, h, s0, s1, clear))
    for free in tiers:
        free = sorted(free, key=lambda iv: -abs((iv[0] + iv[1]) / 2 - a))   # target side first
        if want is not None:
            for f0, f1 in free:
                if f0 <= want <= f1:
                    push(want)
        for f0, f1 in free:
            c = (f0 + f1) / 2
            push(c)
            for k in (1, 2, 3):
                for s in (d, -d):
                    v = c + s * k * NUDGE
                    if f0 <= v <= f1:
                        push(v)
    if not out and lo <= hi:
        push((lo + hi) / 2)
    return out


def _out_and_back(ctx: _Ctx, x: _Edge, leg_x: bool, i: int, pa: Pt, pb: Pt, side: str) -> List[float]:
    """Bends of a HVH / VHV out of the same side of both ends and back (from_side = to_side,
    e.g. a replication line beside one column): beyond both ports by the end segments,
    clear of icons and labels along the leg, trunk_clear then HUG_CLEAR from parallel
    borders; nearest first, up to 15 nudges out and HUG_CLEAR inside the innermost box
    holding both ends (or the canvas)."""
    m, geom = ctx.m, ctx.geom
    sgn = 1 if side in ("right", "bottom") else -1
    min_a = K.MIN_ARROW if x.hs else MIN_SEG
    min_b = K.MIN_ARROW if x.he else MIN_SEG
    near = (max if sgn > 0 else min)(pa[i] + sgn * min_a, pb[i] + sgn * min_b)
    far = near + sgn * 15 * NUDGE
    common = _nonshared(ctx.spec, x.e)[2]
    if common:
        r = geom.groups[common[0]].rect
        wall = (r.x1 if sgn > 0 else r.x0) if leg_x else (r.y1 if sgn > 0 else r.y0)
    else:
        wall = ((geom.canvas_w if leg_x else geom.canvas_h) if sgn > 0 else 0.0)
    wall -= sgn * K.HUG_CLEAR
    far = min(far, wall) if sgn > 0 else max(far, wall)
    lo, hi = sorted((near, far))
    if (far - near) * sgn < 0:
        return []
    out: List[float] = []
    for clear in (m.trunk_clear, K.HUG_CLEAR):
        free = _free(ctx, leg_x, lo, hi, pa[1 - i], pb[1 - i], clear)
        for f0, f1 in sorted(free, key=lambda iv: abs((iv[0] if sgn > 0 else iv[1]) - near)):
            start = math.ceil(f0 * 2) / 2 if sgn > 0 else math.floor(f1 * 2) / 2
            for k in range(4):
                v = start + sgn * k * NUDGE
                if f0 - 1e-6 <= v <= f1 + 1e-6 and all(abs(v - u) > 0.25 for u in out):
                    out.append(v)
    return out


def _candidates(ctx: _Ctx, x: _Edge, ports: Dict[Tuple[int, str], float]):
    """(shape, pa, pb, bend) in preference order: the chosen shape's bends, then the
    alternative shapes'."""
    t = x.t
    out = []
    for k, shape in enumerate((t.shape,) + ALTERNATIVES.get(t.shape, ())):
        oa = x.off_a if x.e.from_offset is not None else ports.get((x.e.n, "a"), 0.0) if k == 0 else 0.0
        ob = x.off_b if x.e.to_offset is not None else ports.get((x.e.n, "b"), 0.0) if k == 0 else 0.0
        pa, pb = x.ends(shape, oa, ob)
        bends = _bends(ctx, x, shape, pa, pb)
        if shape in (HVH, VHV) and not bends:
            continue
        for b in (bends or [None]):
            out.append((shape, pa, pb, b))
    out += _detours(ctx, x)
    return out


def _detours(ctx: _Ctx, x: _Edge):
    """U-shaped candidates for a line whose straight path is blocked: out of the same side
    of both ends (top/top, bottom/bottom for a horizontal run; left/left, right/right for a
    vertical one) and round the obstacle 24 … 120 px beyond the ports."""
    out = []
    A, B = x.A, x.B
    pairs = (("top", "top", VHV, 1), ("bottom", "bottom", VHV, 1), ("left", "left", HVH, 0), ("right", "right", HVH, 0))
    for sa, sb, shape, i in pairs:
        pa = _port(A, sa, B.cy if sa in HORIZ else B.cx)
        pb = _port(B, sb, A.cy if sb in HORIZ else A.cx)
        sgn = -1 if sa in ("top", "left") else 1
        edge = min(pa[i], pb[i]) if sgn < 0 else max(pa[i], pb[i])
        for k in range(3, 16):
            out.append(("U" + shape, pa, pb, edge + sgn * k * NUDGE))
    return out


def _drawn(x: _Edge, shape: str, pa: Pt, pb: Pt, bend, lead: Optional[_Route]) -> Tuple[List[Pt], Tuple[int, int]]:
    """The polyline actually drawn: a trunk follower stops at (merge) / starts from (fork)
    the junction on the first instance's trunk."""
    full = _path(shape, pa, pb, bend)
    t = x.t
    if t.trunk is None:
        return _simplify(full), (0, 0)
    if t.trunk == "merge":
        if t.first == x.e.n:
            pts = _simplify(full)
            return pts, (len(pts) - 2, len(pts) - 1)
        return _simplify(full[:-1]), (0, 0)
    if t.first == x.e.n:
        return _simplify(full), (0, 1)
    return _simplify(full[1:]), (0, 0)


# =======================================================================================
# draw(): pieces, labels, badges

@dataclass
class _Piece:
    p: Pt
    q: Pt
    horiz: bool
    seg: int                 # index of its segment in the path
    depth: int               # containers around its middle
    out_cloud: bool
    strip: bool = False      # inside the AWS Cloud but in no group within it (global strip)

    @property
    def length(self) -> float:
        return _len(self.p, self.q)

    @property
    def mid(self) -> Pt:
        return ((self.p[0] + self.q[0]) / 2, (self.p[1] + self.q[1]) / 2)


def _pieces(ctx: _Ctx, pts: Sequence[Pt]) -> List[_Piece]:
    out = []
    rects = [g.rect for g in ctx.geom.groups.values()]
    for i, (p, q) in enumerate(zip(pts, pts[1:])):
        horiz = abs(p[1] - q[1]) < 0.5
        if horiz:
            y = p[1]
            cuts = [x for r in rects if r.y0 < y < r.y1 for x in (r.x0, r.x1)
                    if min(p[0], q[0]) < x < max(p[0], q[0])]
            ts = sorted({(c - p[0]) / (q[0] - p[0]) for c in cuts})
        else:
            x = p[0]
            cuts = [y for r in rects if r.x0 < x < r.x1 for y in (r.y0, r.y1)
                    if min(p[1], q[1]) < y < max(p[1], q[1])]
            ts = sorted({(c - p[1]) / (q[1] - p[1]) for c in cuts}) if q[1] != p[1] else []
        ts = [0.0] + ts + [1.0]
        for t0, t1 in zip(ts, ts[1:]):
            a = (p[0] + (q[0] - p[0]) * t0, p[1] + (q[1] - p[1]) * t0)
            b = (p[0] + (q[0] - p[0]) * t1, p[1] + (q[1] - p[1]) * t1)
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            depth = sum(1 for r in rects if r.x0 < mx < r.x1 and r.y0 < my < r.y1)
            inside = [r for r in rects if r.x0 < mx < r.x1 and r.y0 < my < r.y1]
            oc = ctx.cloud is not None and ctx.cloud not in inside
            strip = ctx.cloud is not None and bool(inside) and min(inside, key=lambda r: r.w * r.h) is ctx.cloud
            out.append(_Piece(a, b, horiz, i, depth, oc, strip))
    return out


def _piece_order(pieces: List[_Piece], vertical_first: bool = False) -> List[_Piece]:
    """Label / badge preference: the longest horizontal piece, then the longest vertical
    (vertical_first swaps the two). A line that crosses the AWS Cloud border puts its
    piece outside the Cloud before a piece in the Cloud's bare strip (Users → IGW: the
    label stays out of the strip that holds global services); a piece inside a Region
    still wins on length (tgw VPN attachment: badge 2 at 518, not on the 48 px outside)."""
    crosses = any(p.out_cloud for p in pieces) and not all(p.out_cloud for p in pieces)

    def key(p):
        return (0 if (p.horiz != vertical_first) else 1, 1 if (crosses and p.strip) else 0, -p.length)
    return sorted(pieces, key=key)


class _Placer:
    """Collision tests for labels and badges against everything already on the canvas."""

    def __init__(self, ctx: _Ctx, lines: List[Tuple[Pt, Pt]]):
        self.ctx = ctx
        self.lines = lines
        self.texts: List[Box] = list(ctx.texts)
        self.circles: List[Box] = []
        g = ctx.geom
        self.canvas = Box(0, 0, g.canvas_w, g.canvas_h) if g.canvas_w and g.canvas_h else None

    def _common(self, b: Box, icon_clear: float) -> bool:
        if self.canvas and not self.canvas.contains(b):
            return False
        near = b.expand(K.LABEL_CLEAR).t()
        if any(CL.seg_hits_box(p, q, near) for p, q in self.ctx.border_segs):
            return False
        bt = b.expand(1).t()
        if any(CL.seg_hits_box(p, q, bt) for p, q in self.lines):
            return False
        if any(b.expand(icon_clear).overlaps(i) for i in self.ctx.node_icons):
            return False
        if any(b.expand(BADGE_CLEAR).overlaps(i) for i in self.ctx.badges + self.circles):
            return False
        return not any(b.expand(K.TEXT_GAP).overlaps(t) for t in self.texts)

    def text_ok(self, t: TextLine) -> bool:
        return self._common(t.box(), K.ICON_CLEAR)

    def badge_ok(self, cx: float, cy: float, n: int) -> bool:
        c = Box(cx - K.BADGE_R, cy - K.BADGE_R, cx + K.BADGE_R, cy + K.BADGE_R)
        if self.canvas and not self.canvas.contains(c):
            return False
        ct = c.t()
        if any(CL.seg_hits_box(p, q, ct) for p, q in self.lines + self.ctx.border_segs):
            return False
        ce = c.expand(BADGE_CLEAR)
        if any(ce.overlaps(i) for i in self.ctx.icons + self.circles):
            return False
        if any(ce.overlaps(t) for t in self.texts):
            return False
        digit = _digit(cx, cy, n).box()
        return self._common(digit, K.ICON_CLEAR) or False

    def take_text(self, b: Box):
        self.texts.append(b)

    def bg_ok(self, b: Box) -> bool:
        """A label's background on its line: like text_ok but lines may run under it."""
        if self.canvas and not self.canvas.contains(b):
            return False
        near = b.expand(K.LABEL_CLEAR).t()
        if any(CL.seg_hits_box(p, q, near) for p, q in self.ctx.border_segs):
            return False
        if any(b.expand(K.ICON_CLEAR).overlaps(i) for i in self.ctx.node_icons):
            return False
        if any(b.expand(BADGE_CLEAR).overlaps(i) for i in self.ctx.badges + self.circles):
            return False
        return not any(b.expand(K.TEXT_GAP).overlaps(t) for t in self.texts)

    def take_badge(self, cx, cy, n):
        self.circles.append(Box(cx - K.BADGE_R, cy - K.BADGE_R, cx + K.BADGE_R, cy + K.BADGE_R))
        self.texts.append(_digit(cx, cy, n).box())


def _digit(cx, cy, n) -> TextLine:
    st = K.TEXT_BADGE
    return TextLine(str(n), cx, cy + K.BADGE_TEXT_DY, st.size, st.fill, st.weight, "middle")


def _slide(length: float, half: float) -> List[float]:
    """Offsets along a piece: 0, ±8, ±16 … while the center stays within the piece."""
    out = [0.0]
    k = 1
    while k * NUDGE <= length / 2 and k < 40:
        out += [k * NUDGE, -k * NUDGE]
        k += 1
    return out


def _badge_spots(piece: _Piece):
    """Badge centers on a piece in order: along it, above (left) first, then the other side."""
    m = piece.mid
    if piece.horiz:
        lo, hi = sorted((piece.p[0], piece.q[0]))
        for side in (-1, 1):
            for o in _slide(piece.length, K.BADGE_R):
                x = m[0] + o
                if lo - 1e-6 <= x <= hi + 1e-6:
                    yield x, m[1] + side * K.BADGE_DY
    else:
        lo, hi = sorted((piece.p[1], piece.q[1]))
        for side in (-1, 1):
            for o in _slide(piece.length, K.BADGE_R):
                y = m[1] + o
                if lo - 1e-6 <= y <= hi + 1e-6:
                    yield m[0] + side * K.VBADGE_DX, y


def _badge_pieces(ctx: _Ctx, x: _Edge, route: _Route, pieces: List[_Piece]) -> List[_Piece]:
    e = x.e
    order = _piece_order(pieces)
    horiz = [p for p in pieces if p.horiz]
    at = e.step_at if isinstance(e.step_at, str) else "mid"
    first: Optional[_Piece] = None
    if at == "start":
        first = (horiz or pieces)[0]
    elif at == "end":
        first = (horiz or pieces)[-1]
    elif at == "gap":
        cands = sorted(pieces, key=lambda p: (p.depth, 0 if p.horiz else 1, -p.length))
        first = cands[0] if cands else None
    elif at in ("stem", "branch"):
        s0, s1 = route.stem
        trunk = x.t.trunk
        if trunk is None:
            want = [p for p in pieces if p.seg == 0] if at == "stem" else [p for p in pieces if p.seg == len(route.pts) - 2]
        elif at == "stem":
            want = [p for p in pieces if s0 <= p.seg < s1] or [p for p in pieces if p.seg in (s0, s1)]
        else:
            want = [p for p in pieces if not (s0 <= p.seg < s1)]
        want = _piece_order(want)
        first = want[0] if want else None
    if first is not None:
        order = [first] + [p for p in order if p is not first]
    return order


COMBO_GAP = 6     # badge circle ↔ its label beside it, both above the line


def _badge_and_label(ctx: _Ctx, x: _Edge, route: _Route, pieces: List[_Piece], pl: _Placer):
    """A hop's badge and its label side by side above one horizontal piece (badge left,
    label right, the pair centered and slid along the piece), so the label stays above
    the line like every other connector label. Takes them in pl and returns
    ((cx, cy), text lines, first spot?) or None when no spot is clear."""
    e, m = x.e, ctx.m
    texts = [(s, st) for s, st in ((e.label, K.TEXT_PROTO), (e.verb, K.TEXT_VERB)) if s]
    if not texts:
        return None
    w = max(TextLine(s, 0, 0, st.size, st.fill, st.weight, "middle").width() for s, st in texts)
    span = 2 * K.BADGE_R + COMBO_GAP + w
    order = [p for p in _badge_pieces(ctx, x, route, pieces) if p.horiz]
    for i, pc in enumerate(order):
        lo, hi = sorted((pc.p[0], pc.q[0]))
        for j, o in enumerate(_slide(pc.length, 0)):
            x0 = pc.mid[0] + o - span / 2
            cx, tx = x0 + K.BADGE_R, x0 + 2 * K.BADGE_R + COMBO_GAP + w / 2
            if not (lo + K.BADGE_R - 1e-6 <= cx and tx <= hi + 1e-6):
                continue
            cy = pc.mid[1] - K.BADGE_DY
            tls = [TextLine(s, tx, pc.mid[1] - m.label_above - (len(texts) - 1 - k) * K.SUB_PITCH,
                            st.size, st.fill, st.weight, "middle") for k, (s, st) in enumerate(texts)]
            if not pl.badge_ok(cx, cy, e.step):
                continue
            pl.take_badge(cx, cy, e.step)
            if all(pl.text_ok(t) for t in tls) and not _overlap_each(tls):
                for t in tls:
                    pl.take_text(t.box())
                return (cx, cy), tls, i == 0 and j == 0
            pl.circles.pop()
            pl.texts.pop()
    # no room for the pair: the label alone above a horizontal piece, the badge wherever
    # it fits (another piece, the other side)
    for i, pc in enumerate([p for p in _piece_order(pieces) if p.horiz]):
        lo, hi = sorted((pc.p[0], pc.q[0]))
        for o in _slide(pc.length, 0):
            tx = pc.mid[0] + o
            if not lo - 1e-6 <= tx <= hi + 1e-6:
                continue
            tls = [TextLine(s, tx, pc.mid[1] - m.label_above - (len(texts) - 1 - k) * K.SUB_PITCH,
                            st.size, st.fill, st.weight, "middle") for k, (s, st) in enumerate(texts)]
            if not all(pl.text_ok(t) for t in tls) or _overlap_each(tls):
                continue
            for t in tls:
                pl.take_text(t.box())
            for bp in _badge_pieces(ctx, x, route, pieces):
                for cx, cy in _badge_spots(bp):
                    if pl.badge_ok(cx, cy, e.step):
                        pl.take_badge(cx, cy, e.step)
                        return (cx, cy), tls, False
            del pl.texts[-len(tls):]
    return None


def _place(ctx: _Ctx, x: _Edge, route: _Route, pl: _Placer, draw_texts: bool
           ) -> Tuple[List[Element], List[str], bool]:
    """Badge then labels of one edge. Returns (elements, warnings, perfect): perfect when
    each went to its first spot (no nudge, no other side, no other piece)."""
    e = x.e
    perfect = True
    owner = M.edge_eid(e.n)
    els: List[Element] = []
    warns: List[str] = []
    pieces = _pieces(ctx, route.pts)
    badge_piece: Optional[_Piece] = None
    if e.step is not None:
        spot = None
        if isinstance(e.step_at, Place):
            try:
                spot = (M.eval_expr(e.step_at.x, ctx.geom), M.eval_expr(e.step_at.y, ctx.geom))
            except (KeyError, ValueError) as err:
                warns.append(f"{_where(e)}: step_at {err}")
        if spot is None and draw_texts and e.label_at in (None, "above"):
            combo = _badge_and_label(ctx, x, route, pieces, pl)
            if combo is not None:
                (cx, cy), tls, first = combo
                els += M.el_badge(cx, cy, e.step, z=K.Z_BADGE, owner=owner)
                for t in tls:
                    els.append(M.el_text(t, z=K.Z_EDGE_LABEL, owner=owner))
                return els, warns, perfect and first
        if spot is None:
            order = _badge_pieces(ctx, x, route, pieces)
            for i, pc in enumerate(order):
                for j, (cx, cy) in enumerate(_badge_spots(pc)):
                    if pl.badge_ok(cx, cy, e.step):
                        spot, badge_piece = (cx, cy), pc
                        perfect = perfect and i == 0 and j == 0
                        break
                if spot:
                    break
            if spot is None and order:
                pc = order[0]
                cx, cy = pc.mid if not pc.horiz else (pc.mid[0], pc.mid[1] - K.BADGE_DY)
                if not pc.horiz:
                    cx -= K.VBADGE_DX
                spot, badge_piece, perfect = (cx, cy), pc, False
                warns.append(f"{_where(e)}: no clear spot for badge {e.step}; placed at ({cx:g},{cy:g})")
        if spot:
            pl.take_badge(spot[0], spot[1], e.step)
            els += M.el_badge(spot[0], spot[1], e.step, z=K.Z_BADGE, owner=owner)
    if not draw_texts:
        return els, warns, perfect
    texts = [(s, st) for s, st in ((e.label, K.TEXT_PROTO), (e.verb, K.TEXT_VERB)) if s]
    if not texts:
        return els, warns, perfect
    if isinstance(e.label_at, Place):
        try:
            x0, y0 = M.eval_expr(e.label_at.x, ctx.geom), M.eval_expr(e.label_at.y, ctx.geom)
            for k, (s, st) in enumerate(texts):
                tl = TextLine(s, x0, y0 + k * K.SUB_PITCH, st.size, st.fill, st.weight, e.label_at.anchor)
                pl.take_text(tl.box())
                els.append(M.el_text(tl, z=K.Z_EDGE_LABEL, owner=owner))
            return els, warns, perfect
        except (KeyError, ValueError) as err:
            warns.append(f"{_where(e)}: label_at {err}")
    want = e.label_at if isinstance(e.label_at, str) else None
    order = _piece_order(pieces, vertical_first=want in ("left", "right"))
    if badge_piece is not None and want is None:
        # the badge's piece first: its label sits above the line beside the badge
        order = [p for p in order if p is badge_piece] + [p for p in order if p is not badge_piece] \
            if order and order[0] is badge_piece else order
    placed = None
    rule_side = want in (None, "above", "right")     # the preferred side (asked for or by default)
    for i, pc in enumerate(order):
        for j, tls in enumerate(_label_spots(ctx, pc, texts, want, pc is badge_piece, other=not rule_side)):
            if all(pl.text_ok(t) for t in tls) and not _overlap_each(tls):
                placed = tls
                perfect = perfect and i == 0 and j == 0
                break
        if placed:
            break
    if placed is None and rule_side and order:
        # second best: on the line itself, over a background rect, on top of everything
        on_line = _on_line(ctx, order, texts, route, pl)
        if on_line is not None:
            for t in on_line:
                b = t.box(conservative=True).expand(K.LABEL_BG_PAD)
                pl.take_text(b)
                els.append(M.el_rect(b, fill=K.LABEL_BG, z=K.Z_LABEL_TOP, owner=owner))
                els.append(M.el_text(t, z=K.Z_LABEL_TOP, owner=owner))
            warns.append(f"{_where(e)}: label {texts[0][0]!r} sits on its line over a background — no room "
                         f"above / right of it; widen that side (min_gap_before, pad, min_w) to lift it off")
            return els, warns, False
    if placed is None and rule_side:
        # last: the other side
        for pc in order:
            for tls in _label_spots(ctx, pc, texts, want, pc is badge_piece):
                if all(pl.text_ok(t) for t in tls) and not _overlap_each(tls):
                    placed = tls
                    break
            if placed:
                break
        perfect = False
    if placed is None and order:
        perfect = False
        placed = next(iter(_label_spots(ctx, order[0], texts, want, order[0] is badge_piece)), None)
        if placed:
            warns.append(f"{_where(e)}: no clear spot for label {texts[0][0]!r}")
    elif placed:
        side = _label_side(placed, pieces)
        rule = want or ("right" if side in ("left", "right") else "above")
        if side and side != rule:
            warns.append(f"{_where(e)}: label {texts[0][0]!r} went {side} of its line — no room {rule} of it "
                         f"(labels go above a horizontal line and right of a vertical one); widen that side "
                         f"(min_gap_before, pad, min_w)")
    for t in placed or []:
        pl.take_text(t.box())
        els.append(M.el_text(t, z=K.Z_EDGE_LABEL, owner=owner))
    return els, warns, perfect


def _on_line(ctx: _Ctx, order: List[_Piece], texts, route: _Route, pl: _Placer) -> Optional[List[TextLine]]:
    """Label lines centered on a piece of the route (crossing it), clear of icons, badges,
    labels and borders; first where no other connector runs under the background, then
    anywhere."""
    own = set()
    for p, q in zip(route.pts, route.pts[1:]):
        own.add((tuple(p), tuple(q)))
        own.add((tuple(q), tuple(p)))
    others = [(p, q) for p, q in pl.lines if (tuple(p), tuple(q)) not in own]
    n = len(texts)
    for strict in (True, False):
        for pc in order:
            lo, hi = sorted((pc.p[0], pc.q[0])) if pc.horiz else sorted((pc.p[1], pc.q[1]))
            for o in _slide(pc.length, 0):
                c = (pc.mid[0] if pc.horiz else pc.mid[1]) + o
                if not lo - 1e-6 <= c <= hi + 1e-6:
                    continue
                x, yc = (c, pc.mid[1]) if pc.horiz else (pc.mid[0], c)
                tls = [TextLine(s, x, yc + 3 + (k - (n - 1) / 2) * K.SUB_PITCH, st.size, st.fill, st.weight, "middle")
                       for k, (s, st) in enumerate(texts)]
                bgs = [t.box(conservative=True).expand(K.LABEL_BG_PAD) for t in tls]
                if _overlap_each(tls) or not all(pl.bg_ok(b) for b in bgs):
                    continue
                if strict and any(CL.seg_hits_box(p, q, b.t()) for p, q in others for b in bgs):
                    continue
                return tls
    return None


def _label_side(tls: List[TextLine], pieces: List[_Piece]) -> Optional[str]:
    """Which side of its piece a placed label went: above / below / left / right."""
    t = tls[0]
    if t.anchor in ("start", "end"):
        return "right" if t.anchor == "start" else "left"
    top, bottom = tls[0].box().y0, tls[-1].box().y1
    best = None
    for pc in pieces:
        lo, hi = sorted((pc.p[0], pc.q[0]))
        if pc.horiz and lo - 1e-6 <= t.x <= hi + 1e-6:
            y = pc.p[1]
            d, side = (y - bottom, "above") if bottom <= y + 1e-6 else (top - y, "below")
            if d >= -1e-6 and (best is None or d < best[0]):
                best = (d, side)
    return best[1] if best else None


def _overlap_each(tls: List[TextLine]) -> bool:
    bs = [t.box() for t in tls]
    return any(a.expand(K.TEXT_GAP).overlaps(b) for i, a in enumerate(bs) for b in bs[i + 1:])


def _label_spots(ctx: _Ctx, pc: _Piece, texts, want, has_badge: bool, other: bool = True):
    """Candidate label line sets on a piece: centered and slid 8 px at a time, the wanted
    side first, then the other side."""
    m = ctx.m
    mid = pc.mid
    if pc.horiz:
        sides = ["below", "above"] if want == "below" else ["above", "below"]
        if want in (None, "above") and not other:
            sides = ["above"]
        lo, hi = sorted((pc.p[0], pc.q[0]))
        for side in sides:
            for o in _slide(pc.length, 0):
                x = mid[0] + o
                if not lo - 1e-6 <= x <= hi + 1e-6:
                    continue
                out = []
                for k, (s, st) in enumerate(texts):
                    if side == "above":
                        y = mid[1] - m.label_above - (len(texts) - 1 - k) * K.SUB_PITCH
                    else:
                        y = mid[1] + m.label_below + k * K.SUB_PITCH
                    out.append(TextLine(s, x, y, st.size, st.fill, st.weight, "middle"))
                yield out
    else:
        sides = ["left", "right"] if want == "left" else ["right", "left"]
        if want in (None, "right") and not other:
            sides = ["right"]
        lo, hi = sorted((pc.p[1], pc.q[1]))
        n = len(texts)
        for side in sides:
            for o in _slide(pc.length, 0):
                yc = mid[1] + o
                if not lo - 1e-6 <= yc <= hi + 1e-6:
                    continue
                x = mid[0] - m.vlabel_dx if side == "left" else mid[0] + m.vlabel_dx
                anchor = "end" if side == "left" else "start"
                out = []
                for k, (s, st) in enumerate(texts):
                    y = yc + 4 + (k - (n - 1) / 2) * K.SUB_PITCH
                    out.append(TextLine(s, x, y, st.size, st.fill, st.weight, anchor))
                yield out


def _where(e: Edge) -> str:
    return f"{e.src or f'edges[{e.line}]'} {e.a} {e.op} {e.b}"


# =======================================================================================
# draw(): ports and bend groups

def _assign_ports(ctx: _Ctx, xs: Dict[int, _Edge]) -> Dict[Tuple[int, str], float]:
    """Split several lines on one node side (DESIGN 4.5 ports)."""
    sides: Dict[Tuple[str, str], List[Tuple[float, int, str, bool, List[Tuple[int, str]]]]] = {}
    seen_trunk = set()
    for n, x in xs.items():
        t, e = x.t, x.e
        if t.shape == P:
            continue
        straight = x.aligned()
        for end, eid, kind, side, other in (("a", e.a, e.a_kind, t.side_a, x.B), ("b", e.b, e.b_kind, t.side_b, x.A)):
            if kind != "node" or side is None:
                continue
            if (end == "a" and e.from_offset is not None) or (end == "b" and e.to_offset is not None):
                continue
            shared = (t.trunk == "fork" and end == "a") or (t.trunk == "merge" and end == "b")
            key = (eid, side)
            if shared:
                tk = (t.first, end)
                if tk in seen_trunk:
                    for item in sides.get(key, []):
                        if item[4][0] == (t.first, end):
                            item[4].append((n, end))
                    continue
                seen_trunk.add(tk)
            coord = other.cy if side in HORIZ else other.cx
            sides.setdefault(key, []).append((coord, n, end, straight, [(n, end)]))
    out: Dict[Tuple[int, str], float] = {}
    for (eid, side), items in sides.items():
        if len(items) < 2:
            continue
        g = ctx.geom.nodes[eid]
        center = g.cy if side in HORIZ else g.cx
        items.sort(key=lambda it: (it[0], it[1]))
        offs: List[float] = []
        if any(it[3] for it in items):
            below = [it for it in items if not it[3] and it[0] < center]
            above = [it for it in items if not it[3] and it[0] >= center]
            res = {}
            for k, it in enumerate(reversed(below)):
                res[id(it)] = -K.PORT_PITCH * (k + 1)
            for k, it in enumerate(above):
                res[id(it)] = K.PORT_PITCH * (k + 1)
            offs = [0.0 if it[3] else res[id(it)] for it in items]
        elif len(items) == 2:
            d = K.PORT_SIDE if side in HORIZ else K.PORT_TOPBOT
            offs = [-d, d]
        else:
            offs = [(i - (len(items) - 1) / 2) * K.PORT_PITCH for i in range(len(items))]
        for it, o in zip(items, offs):
            for key in it[4]:
                out[key] = o
    return out


def _bend_groups(xs: Dict[int, _Edge]) -> List[List[int]]:
    """Edges that should share a bend: one spec line, or one node side with one shape."""
    parent = {n: n for n in xs}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    keys: Dict[tuple, int] = {}
    for n, x in xs.items():
        t, e = x.t, x.e
        if not (t.shape in (HVH, VHV) or (t.shape in (H, V) and not x.aligned())) \
                or e.bend_x is not None or e.bend_y is not None:
            continue
        for key in (("line", e.line, t.shape, x.dx, x.dy),
                    ("end", e.a, t.side_a, t.shape), ("end", e.b, t.side_b, t.shape)):
            if key[0] == "end" and key[2] is None:
                continue
            if key in keys:
                parent[find(n)] = find(keys[key])
            else:
                keys[key] = n
    groups: Dict[int, List[int]] = {}
    for n in xs:
        groups.setdefault(find(n), []).append(n)
    return [sorted(g) for g in sorted(groups.values(), key=min)]


# =======================================================================================
# draw()

def draw(spec: Spec, geom: Geometry, skip: Optional[Dict[int, int]] = None) -> Tuple[List[Element], List[str]]:
    skip = dict(skip or {})
    ctx = _Ctx(spec, geom)
    topo = _topology(spec)
    warns: List[str] = []
    xs: Dict[int, _Edge] = {}
    for e in spec.edges:
        try:
            xs[e.n] = _Edge(ctx, e, topo[e.n])
        except KeyError as err:
            warns.append(f"{_where(e)}: endpoint {err} not in the geometry; edge skipped")
    for e in spec.edges:
        if e.fork and e.n in xs:
            warns.append(f"{_where(e)}: fork: {e.fork} is phase 2; drawn as a trunk fork")
            break
    ports = _assign_ports(ctx, xs)
    routes: Dict[int, _Route] = {}
    done_lines: List[Tuple[Pt, Pt]] = []

    def build(x: _Edge, cand) -> _Route:
        shape, pa, pb, bend = cand
        pts, stem = _drawn(x, shape, pa, pb, bend, None)
        hs, he = x.hs and len(pts) >= 2, x.he and len(pts) >= 2
        r = _Route(x.e.n, shape, pts, hs, he, _line_problems(ctx, pts, hs, he), stem, bend)
        if r.probs:
            r.quality = 3
        elif x.e.step is None and not (x.e.label or x.e.verb):
            r.quality = 0
        else:
            pl = _Placer(ctx, done_lines + list(zip(pts, pts[1:])))
            _, w, perfect = _place(ctx, x, r, pl, x.t.trunk is None or x.t.first == x.e.n)
            r.quality = 2 if w else 0 if perfect else 1
        return r

    def points_route(x: _Edge) -> _Route:
        try:
            pts = [(M.eval_expr(a, geom), M.eval_expr(b, geom)) for a, b in x.e.points]
        except (KeyError, ValueError) as err:
            warns.append(f"{_where(x.e)}: points {err}")
            pts = list(x.ends(H, 0, 0))
        pts = _simplify(pts)
        return _Route(x.e.n, P, pts, x.hs, x.he, _line_problems(ctx, pts, x.hs, x.he))

    def individual(x: _Edge, k: int = 0) -> _Route:
        t = x.t
        lead = routes.get(t.first) if t.trunk and t.first != x.e.n else None
        if lead is not None and lead.shape == t.shape:      # a trunk follower takes the lead's bend
            pa, pb = x.ends(t.shape, ports.get((x.e.n, "a"), 0.0), ports.get((x.e.n, "b"), 0.0))
            return build(x, (t.shape, pa, pb, lead.bend))
        # a clean line in the chosen shape beats any other shape (that would change the
        # gutters plan() reserved); within a shape, the better label / badge spot wins
        ranked = [((r.quality == 3, r.shape != t.shape, r.quality), i, r)
                  for i, r in enumerate(build(x, c) for c in _candidates(ctx, x, ports))]
        if not ranked:
            pa, pb = x.ends(H, 0, 0)
            return _Route(x.e.n, H, [pa, pb], x.hs, x.he, ["no candidate"])
        ranked.sort(key=lambda it: (it[0], it[1]))
        clean = [r for q, _, r in ranked if not q[0]]
        return clean[min(k, len(clean) - 1)] if clean else ranked[0][2]

    def shared(todo: List[_Edge]) -> Optional[Dict[int, _Route]]:
        """One bend for every member: the best value by the worst member's quality."""
        per = {x.e.n: [c for c in _candidates(ctx, x, ports) if c[0] == x.t.shape] for x in todo}
        values: List[float] = []
        for x in todo:
            for c in per[x.e.n]:
                if c[3] is not None and all(abs(c[3] - v) > 0.25 for v in values):
                    values.append(c[3])
        best, best_q = None, 3
        for v in values:
            rs = {}
            for x in todo:
                if not per[x.e.n]:
                    break
                c = per[x.e.n][0]
                rs[x.e.n] = build(x, (c[0], c[1], c[2], v))
            else:
                q = max(r.quality for r in rs.values())
                if q < best_q:
                    best, best_q = rs, q
                    if q == 0:
                        break
        return best

    for group in _bend_groups(xs):
        members = [xs[n] for n in group]
        todo = [x for x in members if x.e.n not in skip and x.t.shape != P]
        if len(todo) >= 2:
            chosen = shared(todo)
            for n, r in (chosen or {}).items():
                routes[n] = r
                done_lines.extend(zip(r.pts, r.pts[1:]))
        for x in members:
            if x.e.n in routes:
                continue
            r = points_route(x) if x.t.shape == P else individual(x, skip.get(x.e.n, 0))
            routes[x.e.n] = r
            done_lines.extend(zip(r.pts, r.pts[1:]))
    def refused(x: _Edge, r: _Route) -> str:
        """Why the spec's own shape (`shape`, or the one from_side / to_side imply) was not
        drawn, and the change that would let it."""
        e, want = x.e, x.t.shape
        asked = f"shape: {want}" if e.shape else f"from_side / to_side → {want}"
        leg = "bend_x" if want in (HVH, H) else "bend_y" if want in (VHV, V) else None
        hint = getattr(e, leg) if leg else None
        hint = hint if isinstance(hint, M.Expr) else None
        mine = [build(x, c) for c in _candidates(ctx, x, ports) if c[0] == want]
        if not mine:
            why = f"no {want} fits between the two ends (no free stretch for its bend)"
        else:
            probs = list(dict.fromkeys(mine[0].probs))[:3]
            why = "; ".join(_name_prob(ctx, p) for p in probs) or "a cleaner candidate won"
            if hint is not None:
                why = f"{leg} {_expr_text(hint)} = {M.fmt_num(mine[0].bend)}: {why}"
        if hint is not None:
            x2 = _Edge(ctx, replace(e, **{leg: None}), x.t)
            clean = [c for c in _candidates(ctx, x2, ports) if c[0] == want and c[3] is not None
                     and not build(x2, c).probs]
            fix = (f"{leg}: {M.fmt_num(clean[0][3])} (or drop {leg}: the router finds that bend)" if clean else
                   f"no {leg} draws a clean {want} here: widen the gap between the ends (min_gap_before / pad), "
                   f"or drop shape / {leg}")
        else:
            fix = (f"widen the gap between the ends (min_gap_before / pad) so a {want} has a clean bend, "
                   f"or drop the hint and let the rule pick")
        return f"{_where(e)}: drew {r.shape} instead of {want}, refusing the requested {asked} — {why}; try {fix}"

    # trunks whose followers could not share the first instance's bend: report
    for n, r in sorted(routes.items()):
        x = xs[n]
        if r.probs and x.t.shape != P:      # `points` is the spec's own route: check_layout judges it
            warns.append(f"{_where(x.e)}: {', '.join(sorted(set(r.probs)))} (best of the candidates)")
        if r.shape != x.t.shape and x.t.shape != P:
            if x.t.note == "override":
                warns.append(refused(x, r))
            else:
                warns.append(f"{_where(x.e)}: drew {r.shape} instead of {x.t.shape} (re-solve may be needed)")
    # elements: lines (Edge.n order), then labels, then badges
    els: List[Element] = []
    all_lines = [s for r in routes.values() for s in zip(r.pts, r.pts[1:])]
    for n in sorted(routes):
        r, x = routes[n], xs[n]
        els.append(M.el_path(r.pts, dash=K.DASH_DASHED if x.e.dashed else None, start=r.hs, end=r.he,
                             z=K.Z_EDGE, owner=M.edge_eid(n)))
    pl = _Placer(ctx, all_lines)
    labels: List[Element] = []
    badges: List[Element] = []
    on_line: List[Element] = []
    for n in sorted(routes):
        r, x = routes[n], xs[n]
        texts_here = x.t.trunk is None or x.t.first == n
        e_els, w, _ = _place(ctx, x, r, pl, texts_here)
        warns += w
        labels += [el for el in e_els if el.z == K.Z_EDGE_LABEL]
        badges += [el for el in e_els if el.z == K.Z_BADGE]
        on_line += [el for el in e_els if el.z == K.Z_LABEL_TOP]
    return els + labels + badges + on_line, warns
