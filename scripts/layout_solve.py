"""W2: spec + requirements → Geometry (difference constraints, longest path), and the
Elements of every group and node.

    solve(spec, reqs, note_block=None, diag_x=False) -> Geometry
    draw(spec, geom) -> list[Element]

The contract (variable names, coordinates, who fills what) is layout_model's docstring;
constants come from layout_const. Outline (DESIGN 4.2-4.3):

  footprints   every node's half width (0.6 em layout widths, rounded up), icon top, last
               baseline and footprint bottom; border nodes use their mask.
  constraints  `b − a ≥ d` per axis, each a layout_model.Requirement with why/owner:
               1 containment (pad, top insets, label_bottom), 2 siblings in one parent
               (separated on the axis their track ranges are disjoint on; a diagonal pair on
               the wider track gap, ties → rows, unless the solved x keeps it apart or
               y would stack its node between two boxes of one column outside the lines
               they draw past it), 3 neighbour pitch, 4 header and CIDR widths, 5 IGW/VGW pinned
               on the VPC border (mask kept MASK_CLEAR from borders), 6 the AZ gap row,
               7 colspan (reserved from its center for the span a first solve found), 8 flow rows
               (own x variables, pitch, centered in the parent afterwards) and flow columns
               (own y variables, pitch or label stack + stack gap, kept off same-parent
               siblings sharing the column by slot — a flow-row node once solved x shows
               it meets the stack, by Spec.flow_row_above (a row on the parent's edge row
               stays at that edge), twice the column's spacing off it —, then top /
               centered / bottom in the parent's height, with tied xy nodes and
               member-only overlays; no row tracks; a box of stack nodes only likewise),
               9 overlays (ASG:
               members, header right/below, inside the leftmost / rightmost member subnets on x
               and the first / last member row's on y, a short title beside the
               first member row), 10 the caller's Requirements, 11 canvas margin (and the
               note's requirements), plus template
               instances kept alike (x: equal edges; y: equal insets, by iteration), twins
               (containers of one structure anywhere: equal sizes and inner offsets at the
               larger, by iteration on both axes), badge ↔
               icon clearance, track order / min_gap_before, min_w / min_h.
  solve        Bellman-Ford longest path from "origin" per axis = the minimal solution. A
               positive cycle drops the soft requirements in it and retries; a cycle of hard
               ones through an `xy` tie moves that xy center by the cycle's excess (the
               nearest center its boxes, label room and the canvas margin allow; warned),
               and a sibling the moved node lands on is then kept apart from it (solve()
               again); any other cycle raises SolveError naming each constraint's spec
               location and why.
  hug          group left / top edges are pulled toward their content (inner groups
               first) as far as every constraint allows; right / bottom edges are already
               tight in the minimal solution.
  explain      for every track, the chain of constraints that set its position.

x is solved (and hugged) before y, because two y rules depend on x: which overlay members
sit under the overlay's header title, and which icons sit under a group badge.
"""
from __future__ import annotations

import bisect
import math
import re
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_const as K  # noqa: E402
from layout_model import (  # noqa: E402
    Box, Element, Expr, Geometry, GroupGeom, NodeGeom, Requirement, SolveError, Spec, TextLine,
    el_image, el_rect, el_text, fmt_num, layout_text_width, split_eid, union_all,
)

_EPS = 1e-7
_NEG = float("-inf")

Ref = Tuple[str, float]          # (variable, offset): the value is val[var] + offset


def _up(v: float) -> float:
    """Round a text-derived length up to a whole px (keeps drafts on integer coordinates)."""
    return float(math.ceil(v - 1e-9))


# =======================================================================================
# Footprints (DESIGN 4.2)

class _Foot:
    """A node's extent relative to its icon center."""
    __slots__ = ("lines", "h", "top", "base", "bot", "mask_w", "mask_h", "bands")

    def __init__(self, lines, h, top, base, bot, mask_w, mask_h, bands):
        self.lines = lines          # [(text, size, fill)]
        self.h = h                  # half width (x)
        self.top = top              # icon top offset (−S/2)
        self.base = base            # last baseline offset
        self.bot = bot              # footprint bottom offset (glyph descent or mask bottom)
        self.mask_w = mask_w
        self.mask_h = mask_h
        self.bands = bands          # [(y0, y1, half width, text?)]: the icon and each label line (glyph box)


def _footprint(spec: Spec, n) -> _Foot:
    S, mc = spec.S, spec.const
    lines = []
    if n.label:
        lines.append((n.label, K.label_size(S), K.TEXT_NODE.fill))
    lines += [(s, K.TEXT_SUB.size, K.TEXT_SUB.fill) for s in n.sub]
    tw = max([layout_text_width(t, sz) for t, sz, _ in lines] or [0.0])
    base = S / 2 + (K.NODE_LABEL_DY + K.SUB_PITCH * (len(lines) - 1) if lines else 0)
    bot = _up(base + K.GLYPH_DESCENT * lines[-1][1]) if lines else S / 2
    mask_w = mask_h = None
    w = max(S, tw)
    if n.on:
        mask_w = _up(max(S, tw + K.MASK_TEXT_PAD))
        mask_h = S + mc.mask_extra + K.SUB_PITCH * max(0, len(lines) - 1)
        w = mask_w
        bot = max(bot, -S / 2 + mask_h)
    h = _up(w / 2)
    top = -S / 2
    if n.on:
        bands = [(top, bot, h, False)]
    else:
        bands = [(top, S / 2, S / 2, False)]
        for i, (t, sz, _) in enumerate(lines):
            b = S / 2 + K.NODE_LABEL_DY + K.SUB_PITCH * i
            bands.append((b - K.GLYPH_ASCENT * sz, b + K.GLYPH_DESCENT * sz, layout_text_width(t, sz) / 2, True))
    if n.col and n.col2 is None:
        mw = _up(spec.track(n.col).min_w / 2)
        if mw > h:
            h = mw
            bands.append((top, bot, mw, False))
    if n.row:
        mw = spec.track(n.row).min_w / 2
        top, bot = min(top, -mw), max(bot, mw)
    return _Foot(lines, h, top, base, bot, mask_w, mask_h, bands)


# =======================================================================================
# Constraint system

class _Item:
    """A sibling in a parent: a group box or a node (border nodes keep their mask)."""
    __slots__ = ("key", "gid", "nid", "border", "xr", "yr", "gtype")

    def __init__(self, key, gid=None, nid=None, border=False, xr=None, yr=None, gtype=None):
        self.key, self.gid, self.nid, self.border = key, gid, nid, border
        self.xr, self.yr, self.gtype = xr, yr, gtype


def _disjoint(a, b) -> bool:
    return a is not None and b is not None and (a[1] < b[0] or b[1] < a[0])


def _span_gap(a, b) -> int:
    """Track index distance between two disjoint ranges."""
    return b[0] - a[1] if a[1] < b[0] else a[0] - b[1]


class _Model:
    def __init__(self, spec: Spec, avoid: Sequence[Tuple[str, str, str, str]] = (), relaxed=()):
        self.spec = spec
        self.relaxed = set(relaxed)       # grid centers promoted to movable pins, per axis
        self.mc = spec.const
        self.S = spec.S
        self.ci = {t.id: i for i, t in enumerate(spec.cols)}
        self.ri = {t.id: i for i, t in enumerate(spec.rows)}
        self.foot = {nid: _footprint(spec, n) for nid, n in spec.nodes.items()}
        self.flow = {nid for nid, n in spec.nodes.items() if n.xy is None and n.col is None}
        self.stacks = spec.flow_stacks()                                     # flow columns
        self.flowc = {nid for ids in self.stacks.values() for nid in ids}
        self.stack_of = {nid: (key, k) for key, ids in self.stacks.items() for k, nid in enumerate(ids)}
        self.floats = {gid: a for gid in spec.groups for a in [spec.float_align(gid)] if a}   # boxes of stacks only
        self.stack_shift: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)   # nid → align moves (explain)
        self.tree = [g for g in spec.groups.values() if not g.overlay]
        self.overlays = [g for g in spec.groups.values() if g.overlay]
        self.child_groups: Dict[Optional[str], List[str]] = defaultdict(list)
        for g in self.tree:
            self.child_groups[g.parent].append(g.id)
        self.child_nodes: Dict[Optional[str], List[str]] = defaultdict(list)
        self.border_of: Dict[str, List[str]] = defaultdict(list)    # vpc id → border node ids
        for nid, n in spec.nodes.items():
            if n.on:
                self.border_of[n.on].append(nid)
            else:
                self.child_nodes[n.parent].append(nid)
        self.cons: Dict[str, List[Requirement]] = {"x": [], "y": []}
        self.ties: Dict[str, List[Tuple[str, str]]] = {"x": [], "y": []}   # equal-edge pairs (hug moves them together)
        self.flow_rows: List[Tuple[Optional[str], List[str]]] = []         # (parent, node ids in order)
        self.aligned: set = set()
        self.warnings: List[str] = []
        # colspan node → the b1 → b2 span its x reservation assumes (held as b2 − b1 ≥ it);
        # empty on the first x solve, which reserves from both end tracks (solve())
        self.span: Dict[str, float] = {}
        self.hold_span = True            # build("x") holds b2 − b1 ≥ span (False: _solve_x measures g(span))
        self.xv: Dict[str, float] = {}           # the solved x (set before build("y"))
        self.nodes_x: Dict[str, float] = {}      # node centers on the solved x
        # diagonal sibling pairs (disjoint on both axes) that the track gaps would separate on
        # y but the solved x does not keep apart: build("y") leaves them out while diag_open
        # is a list (solve() then weighs x against y), else separates them on y; diag_x are
        # the pairs (frozenset of item keys) solve() chose to keep apart on x instead
        self.diag_open: Optional[List[Tuple[_Item, _Item, str]]] = None
        self.diag_x: set = set()
        self.diag_y: set = set()                 # the box pairs build("y") separated on y (keys)
        self.diag_boxes: List[Tuple[_Item, _Item]] = []   # every diagonal node-box pair build("y") met
        self._past: Dict[Tuple[str, str, bool], bool] = {}   # lines_past() cache
        self._twins: Optional[List[list]] = None   # twin_sets() cache
        # (axis, first key, second key, owner): a node whose xy the solve moved and a sibling
        # it landed on, kept apart like grid siblings (solve() finds them: _xy_clashes)
        self.avoid = list(avoid)
        # tracks no grid node sits on: an xy node naming one (`col.c`) takes it as its own
        # track on that axis, so the track gets a node's room instead of folding onto the next
        used = {"x": set(), "y": set()}
        for n in spec.nodes.values():
            if n.xy is None:
                used["x"].update(t for t in (n.col, n.col2) if t)
                used["y"].update(t for t in (n.row,) if t)
        self.bare = {"x": {t.id for t in spec.cols} - used["x"], "y": {t.id for t in spec.rows} - used["y"]}

    # ---- helpers --------------------------------------------------------------------

    def add(self, axis, a: Ref, b: Ref, d: float, why: str, owner: str, soft=False, pin=""):
        """(b) − (a) ≥ d, with a/b given as (variable, offset)."""
        (va, oa), (vb, ob) = a, b
        dd = d + oa - ob
        if va == vb and dd <= _EPS:
            return
        self.cons[axis].append(Requirement(axis, va, vb, dd, why, owner, soft, pin))

    def pad(self, gid):
        g = self.spec.groups[gid]
        return g.pad if g.pad is not None else self.mc.pad

    def pad_node(self, gid):
        g = self.spec.groups[gid]
        return g.pad if g.pad is not None else self.mc.pad_node

    def side_pad(self, gid, side, node=False):
        """x padding on one side ("L" / "R"): pad_left / pad_right, else pad / the mode's."""
        g = self.spec.groups[gid]
        one = g.pad_left if side == "L" else g.pad_right
        if one is not None:
            return one
        return self.pad_node(gid) if node else self.pad(gid)

    def bottom_pad(self, gid):
        """Bottom padding below a child box: pad_bottom, else pad / the mode's."""
        g = self.spec.groups[gid]
        return g.pad_bottom if g.pad_bottom is not None else self.pad(gid)

    def node_bottom(self, gid, it: _Item):
        """(ref, d) keeping a node above gid's bottom border: label_bottom from its last
        baseline, or pad_bottom from its footprint bottom when that is farther."""
        g = self.spec.groups[gid]
        base, lb = self.hi(it, "y", base=True), self.mc.label_bottom
        if g.pad_bottom is None or it.border:
            return base, lb, f"label_bottom {fmt_num(lb)}"
        bot = self.hi(it, "y")
        if bot[1] + g.pad_bottom > base[1] + lb:
            return bot, g.pad_bottom, f"pad_bottom {fmt_num(g.pad_bottom)}"
        return base, lb, f"label_bottom {fmt_num(lb)}"

    def rng(self, axis, first, last):
        idx = self.ci if axis == "x" else self.ri
        if first is None or first not in idx:
            return None
        return (idx[first], idx[last if last in idx else first])

    def node_rng(self, nid, axis):
        n = self.spec.nodes[nid]
        if n.xy is not None:
            # an xy node is no grid sibling, except on a bare track its xy names (col.c)
            c = n.xy[0 if axis == "x" else 1]
            kind = "col" if axis == "x" else "row"
            if isinstance(c, Expr) and c.kind == kind and c.ref in self.bare[axis]:
                i = (self.ci if axis == "x" else self.ri)[c.ref]
                return (i, i)
            return None
        if axis == "x":
            return None if nid in self.flow else self.rng("x", n.col, n.col2 or n.col)
        return None if nid in self.flowc else self.rng("y", n.row, n.row)

    def group_rng(self, gid, axis):
        g = self.spec.groups[gid]
        t = g.cols if axis == "x" else g.rows
        return self.rng(axis, t[0], t[1]) if t else None

    def item_group(self, gid):
        g = self.spec.groups[gid]
        return _Item(f"group:{gid}", gid=gid, xr=self.group_rng(gid, "x"), yr=self.group_rng(gid, "y"),
                     gtype=g.type)

    def item(self, key):
        """The sibling item of an element id (node:… or group:…)."""
        kind, ident, _ = split_eid(key)
        return self.item_group(ident) if kind == "group" else self.item_node(ident)

    def item_node(self, nid):
        return _Item(f"node:{nid}", nid=nid, border=bool(self.spec.nodes[nid].on),
                     xr=self.node_rng(nid, "x"), yr=self.node_rng(nid, "y"))

    def nref(self, nid, axis, side) -> Ref:
        """A node's center variable; side "lo" (left / as b) or "hi" (right / as a): a
        colspan node is its first track + span/2 on the left and its last − span/2 on the
        right (with no span known yet: the end tracks themselves)."""
        n = self.spec.nodes[nid]
        if (axis, nid) in self.relaxed or n.xy is not None or (axis == "x" and nid in self.flow) or (axis == "y" and nid in self.flowc):
            return (f"node:{nid}", 0.0)
        return self.grid_ref(nid, axis, side)

    def grid_ref(self, nid, axis, side):
        """The original grid center, before a conflicting placement is relaxed."""
        n = self.spec.nodes[nid]
        if axis == "x":
            if n.col2:
                # its center is X_b1 + s/2 = X_b2 − s/2 while the span stays s (≥ s holds)
                s = self.span.get(nid, 0.0)
                return (f"col:{n.col2}", n.dx - s / 2) if side == "hi" else (f"col:{n.col}", n.dx + s / 2)
            return (f"col:{n.col}", n.dx)
        return (f"row:{n.row}", n.dy)

    def lo(self, it: _Item, axis) -> Ref:
        if it.gid:
            return (f"group:{it.gid}.{'L' if axis == 'x' else 'T'}", 0.0)
        v, o = self.nref(it.nid, axis, "lo")
        f = self.foot[it.nid]
        return (v, o - f.h) if axis == "x" else (v, o + f.top)

    def hi(self, it: _Item, axis, base=False) -> Ref:
        """Right / bottom extent; base=True gives the last baseline (containment)."""
        if it.gid:
            return (f"group:{it.gid}.{'R' if axis == 'x' else 'B'}", 0.0)
        v, o = self.nref(it.nid, axis, "hi")
        f = self.foot[it.nid]
        if axis == "x":
            return (v, o + f.h)
        return (v, o + (f.base if base and not it.border else f.bot))

    # ---- constraint generation --------------------------------------------------------

    def build(self, axis):
        spec, mc = self.spec, self.mc
        tracks = spec.cols if axis == "x" else spec.rows
        pre = "col" if axis == "x" else "row"
        L, R = ("L", "R") if axis == "x" else ("T", "B")
        # track order and min_gap_before
        for prev, t in zip(tracks, tracks[1:]):
            self.add(axis, (f"{pre}:{prev.id}", 0), (f"{pre}:{t.id}", 0), max(0.0, t.min_gap_before),
                     f"min_gap_before {fmt_num(t.min_gap_before)}" if t.min_gap_before else "track order",
                     f"track:{t.id}")
        for g in self.tree:
            self._group(axis, g, L, R)
        for g in self.overlays:
            if axis == "x":
                self._overlay_x(g)
        for parent in [None] + [g.id for g in self.tree]:
            self._siblings(axis, parent)
            if axis == "y":
                self._float_siblings(parent)
        for ax, k1, k2, owner in self.avoid:
            if ax == axis:
                self._sep(axis, self.item(k1), self.item(k2), owner)
        for nid, n in spec.nodes.items():
            if n.on:
                self._border(axis, nid)
            if n.xy is not None:
                v = (f"node:{nid}", 0.0)
                c = n.xy[0] if axis == "x" else n.xy[1]
                ref, txt = self.xy_ref(c, axis)
                self.add(axis, ref, v, 0, f"xy {txt}", f"node:{nid}", pin="lo")
                self.add(axis, v, ref, 0, f"xy {txt}", f"node:{nid}", pin="hi")
            elif (axis, nid) in self.relaxed:
                v = (f"node:{nid}", 0.0)
                ref = self.grid_ref(nid, axis, "lo")
                why = f"grid {'dx' if axis == 'x' else 'dy'} {fmt_num(n.dx if axis == 'x' else n.dy)}"
                self.add(axis, ref, v, 0, why, f"node:{nid}", pin="lo")
                self.add(axis, v, ref, 0, why, f"node:{nid}", pin="hi")
        if axis == "x":
            for nid, sp in sorted(self.span.items()) if self.hold_span else ():
                n = spec.nodes[nid]
                self.add("x", (f"col:{n.col}", 0), (f"col:{n.col2}", 0), sp,
                         f"colspan {nid} centered (span {fmt_num(sp)})", f"node:{nid}")
            self._flows()
            if mc.badge_clear_x:
                self._badge_clear_x()
        else:
            self._az_gaps()
            self._flow_cols()
        self._templates_equal(axis)
        # canvas margin (11): top-level groups and nodes
        m = mc.canvas_margin
        for gid in self.child_groups[None]:
            self.add(axis, ("origin", 0), self.lo(self.item_group(gid), axis), m, f"canvas margin {fmt_num(m)}",
                     f"group:{gid}")
        for nid in self.child_nodes[None] + [b for v, bs in self.border_of.items()
                                             if spec.groups[v].parent is None for b in bs]:
            self.add(axis, ("origin", 0), self.lo(self.item_node(nid), axis), m, f"canvas margin {fmt_num(m)}",
                     f"node:{nid}")

    def xy_ref(self, c, axis) -> Tuple[Ref, str]:
        """An `xy` component as a (variable, offset) the node's center equals: a number
        from the origin; col / row → the track; <node>.attr → that node's center variable
        ± S/2 for an icon edge; <group>.x0 / x1 / y0 / y1 → its edge (W1 rejects the rest)."""
        if not isinstance(c, Expr):
            return ("origin", float(c)), fmt_num(c)
        txt = (f"{c.kind}." if c.kind in ("col", "row") else "") + c.ref + (f".{c.attr}" if c.attr else "") \
            + (f"{'+' if c.offset > 0 else '-'}{fmt_num(abs(c.offset))}" if c.offset else "")
        if c.kind == "num":
            return ("origin", c.offset), txt
        if c.kind in ("col", "row"):
            return (f"{c.kind}:{c.ref}", c.offset), txt
        if c.kind == "node":
            v, o = self.nref(c.ref, axis, "lo")
            edge = {"x0": -1, "y0": -1, "x1": 1, "y1": 1}.get(c.attr, 0) * self.S / 2
            return (v, o + edge + c.offset), txt
        if c.kind == "group":
            e = {"x0": "L", "x1": "R", "y0": "T", "y1": "B"}[c.attr]
            return (f"group:{c.ref}.{e}", c.offset), txt
        raise SolveError([f"xy expression {txt!r} cannot be tied to the solve"])

    def _group(self, axis, g, L, R):
        """Containment of g's children, header width, min size, span (1, 4)."""
        mc, gid, st = self.mc, g.id, K.style(g.type)
        own = f"group:{gid}"
        gl, gr = (f"group:{gid}.{L}", 0.0), (f"group:{gid}.{R}", 0.0)
        cidr = bool(g.cidr)
        for cid in self.child_groups[gid]:
            if axis == "x":
                p = self.side_pad(gid, "L")
                self.add(axis, gl, (f"group:{cid}.L", 0), p, f"pad {fmt_num(p)} {gid} ⊃ {cid}", own)
            else:
                top = max(K.top_inset(g.type, mc.name, "box", cidr), g.pad_top or 0)
                self.add(axis, gl, (f"group:{cid}.T", 0), top, f"top inset {fmt_num(top)} {gid} ⊃ {cid}", own)
            p = self.side_pad(gid, "R") if axis == "x" else self.bottom_pad(gid)
            self.add(axis, (f"group:{cid}.{R}", 0), gr, p, f"pad {fmt_num(p)} {cid} ⊂ {gid}", own)
        for nid in self.child_nodes[gid]:
            it = self.item_node(nid)
            if axis == "x":
                p = self.side_pad(gid, "L", node=True)
                self.add(axis, gl, self.lo(it, axis), p, f"pad {fmt_num(p)} {gid} ⊃ node {nid}", own)
                p = self.side_pad(gid, "R", node=True)
                self.add(axis, self.hi(it, axis), gr, p, f"pad {fmt_num(p)} node {nid} ⊂ {gid}", own)
            else:
                top = max(K.top_inset(g.type, mc.name, "icon", cidr), g.pad_top or 0)
                self.add(axis, gl, self.lo(it, axis), top, f"icon inset {fmt_num(top)} {gid} ⊃ {nid}", own)
                ref, d, what = self.node_bottom(gid, it)
                self.add(axis, ref, gr, d, f"{what} {nid} ⊂ {gid}", own)
        if axis == "x":
            need = []
            if g.label:
                need.append((st.title_dx + _up(layout_text_width(g.label, st.title_size)) + K.HEADER_TAIL, "title"))
            if g.cidr:
                need.append((st.title_dx + _up(layout_text_width(g.cidr, K.TEXT_CIDR.size)) + K.HEADER_TAIL, "CIDR"))
            if st.badge:
                need.append((st.badge_size + K.HEADER_TAIL, "badge"))
            if g.min_w:
                need.append((g.min_w, "min_w"))
            for w, what in need:
                self.add(axis, gl, gr, w, f"{what} width {fmt_num(w)} {gid}", own)
            span = g.span_cols
        else:
            hdr = max(st.badge_size if st.badge else 0,
                      K.TITLE_DY + K.GLYPH_DESCENT * st.title_size if g.label else 0)
            need = [(_up(hdr) + self.bottom_pad(gid), "header height")]
            if g.min_h:
                need.append((g.min_h, "min_h"))
            for w, what in need:
                self.add(axis, gl, gr, w, f"{what} {fmt_num(w)} {gid}", own)
            span = g.span_rows
        if span:
            # the spanned track centers as if a node sat there with no footprint: pad_node,
            # or pad_left / pad_right / pad_bottom on that side (the top keeps pad_node)
            pre = "col" if axis == "x" else "row"
            p0 = self.side_pad(gid, "L", node=True) if axis == "x" else self.pad_node(gid)
            p1 = self.side_pad(gid, "R", node=True) if axis == "x" else \
                (g.pad_bottom if g.pad_bottom is not None else self.pad_node(gid))
            self.add(axis, gl, (f"{pre}:{span[0]}", 0), p0, f"span {fmt_num(p0)} {gid} ⊃ {span[0]}", own)
            self.add(axis, (f"{pre}:{span[1]}", 0), gr, p1, f"span {fmt_num(p1)} {gid} ⊃ {span[1]}", own)

    def _gap(self, axis, a: _Item, b: _Item):
        """Clearance between two siblings, a before b on this axis."""
        mc = self.mc
        if a.border or b.border:
            if a.gid or b.gid:
                return K.MASK_CLEAR, "mask clear"
            return mc.sibling_gap, "sibling gap"
        if a.gid and b.gid:
            peers = ("region", "vpc", "account")
            if a.gtype in peers and b.gtype in peers:
                return mc.peer_gap, "peer gap"
            return mc.sibling_gap, "sibling gap"
        if axis == "y" and a.nid and b.gid:
            # a node's label stack above a box border: the label ↔ border clearance (QR 71)
            return min(mc.sibling_gap, K.LABEL_CLEAR), "label clear"
        if axis == "y" and a.gid and b.nid:
            return mc.box_node_gap, "box ↔ icon gap"
        if axis == "y" and a.nid and b.nid:
            return mc.stack_gap, "stack gap"
        return mc.sibling_gap, "sibling gap"

    def _sep(self, axis, a: _Item, b: _Item, owner):
        g, what = self._gap(axis, a, b)
        d = g
        why = f"{what} {fmt_num(g)} {a.key} | {b.key}"
        if axis == "x" and a.nid and b.nid:
            # neighbour nodes: center pitch (3), a colspan from its center
            (va, oa), (vb, ob) = self.nref(a.nid, "x", "hi"), self.nref(b.nid, "x", "lo")
            fa, fb = self.foot[a.nid], self.foot[b.nid]
            if self.spec.nodes[a.nid].parent == self.spec.nodes[b.nid].parent or a.border or b.border:
                self.add("x", (va, oa), (vb, ob), self.mc.node_pitch,
                         f"pitch {fmt_num(self.mc.node_pitch)} {a.key} → {b.key}", owner)
            na, nb = self.spec.nodes[a.nid], self.spec.nodes[b.nid]
            if na.row is not None and na.row == nb.row:
                d, ha, hb, what = self._band_sep(fa, fb, nb.dy - na.dy, g)
                why = f"{what} {a.key} | {b.key}"
            else:
                d, ha, hb = g + fa.h + fb.h, fa.h, fb.h
            self.add("x", (va, oa), (vb, ob), d, f"{why} (half widths {fmt_num(ha)} + {fmt_num(hb)})", owner)
            return
        self.add(axis, self.hi(a, axis), self.lo(b, axis), d, why, owner)

    def _band_sep(self, fa: _Foot, fb: _Foot, off: float, g: float):
        """Center distance for two nodes side by side on one row (b right of a, b's icon
        `off` px lower): only the bands (icon, each label line) that overlap vertically
        need room between them — label lines label_gap apart (they overlap when their
        glyph boxes do, like check_layout's TEXT TOO CLOSE), an icon sibling gap g from
        whatever comes within ICON_CLEAR of its height. A long last line below the other
        node's shorter stack sets nothing. Returns (d, half a, half b, why)."""
        best = (0.0, 0.0, 0.0, "")
        for y0, y1, ha, ta in fa.bands:
            for z0, z1, hb, tb in fb.bands:
                text = ta and tb
                if min(y1, z1 + off) - max(y0, z0 + off) <= (0.0 if text else -K.ICON_CLEAR):
                    continue
                gap = self.mc.label_gap if text else g
                d = gap + ha + hb
                if d > best[0]:
                    best = (d, ha, hb, f"{'label gap' if text else 'sibling gap'} {fmt_num(gap)}")
        return (_up(best[0]),) + best[1:]

    def _siblings(self, axis, parent):
        """Siblings of one parent (2, 3). Border nodes count as siblings both in their VPC's
        parent (except their own VPC) and among the VPC's children."""
        items = [self.item_group(g) for g in self.child_groups[parent]]
        if len(items) + len(self.child_nodes[parent]) > 1:
            for it in items:
                if (it.xr if axis == "x" else it.yr) is None and not (axis == "y" and it.gid in self.floats):
                    g = self.spec.groups[it.gid]
                    key = "cols" if axis == "x" else "rows"
                    self.warnings.append(f"{g.src} {g.id}: no node inside and no span on its {key}, so nothing "
                                         f"keeps it apart from its siblings; add span: {{{key}: [a, b]}}")
        items += [self.item_node(n) for n in self.child_nodes[parent]]
        borders = []
        for gid in self.child_groups[parent]:
            borders += [(b, gid) for b in self.border_of.get(gid, [])]
        if parent is not None:
            borders += [(b, None) for b in self.border_of.get(parent, [])]
        all_items = [(it, None) for it in items] + [(self.item_node(b), skip) for b, skip in borders]
        owner = f"group:{parent}" if parent else "canvas"
        for i, (a, sa) in enumerate(all_items):
            for b, sb in all_items[i + 1:]:
                if (sa and b.key == f"group:{sa}") or (sb and a.key == f"group:{sb}"):
                    continue
                ra, rb = (a.yr, b.yr) if axis == "y" else (a.xr, b.xr)
                oa, ob = (a.xr, b.xr) if axis == "y" else (a.yr, b.yr)
                if a.gid and b.gid and ra is not None and ra == rb and not (sa or sb):
                    self._align(axis, a.gid, b.gid)
                if not _disjoint(ra, rb):
                    continue
                first, second = (a, b) if ra[1] < rb[0] else (b, a)
                if _disjoint(oa, ob):
                    # diagonal: separate on the axis with the wider track gap (ties → rows).
                    # A pair with a box in it that this sends to y goes on x instead when the
                    # solved x already keeps it apart, or when solve() puts it there (diag_x:
                    # on y its node would be stacked between two boxes of one column outside
                    # the lines they draw past it, or x takes no more room) — its columns
                    # order it, so a node beside a box needs no rows between them and never
                    # pushes the box's rows (and every box on them) down; it then only keeps
                    # its row order (_diag_order)
                    here, there = _span_gap(ra, rb), _span_gap(oa, ob)
                    box = bool(a.gid or b.gid)
                    if box and axis == "y" and (a.nid or b.nid):
                        self.diag_boxes.append((first, second))   # _stacked_between
                    if box and frozenset((a.key, b.key)) in self.diag_x:
                        if axis == "x":
                            self._sep(axis, first, second, owner)
                        else:
                            self._diag_order(first, second, owner)
                        continue
                    if here < there or (here == there and axis == "x"):
                        continue
                    if box and self._x_apart(first, second):
                        self._diag_order(first, second, owner)
                        continue
                    if box and self.diag_open is not None:
                        self.diag_open.append((first, second, owner))
                        continue
                    if box and axis == "y":
                        self.diag_y.add(frozenset((a.key, b.key)))
                self._sep(axis, first, second, owner)

    def _diag_order(self, first: _Item, second: _Item, owner):
        """A diagonal pair kept apart on x: the one on the later rows goes beside the other,
        never above it (its top level with the other's or below)."""
        self.add("y", self.lo(first, "y"), self.lo(second, "y"), 0,
                 f"diagonal order {first.key} | {second.key} (apart on x)", owner)

    def _x_extent(self, it: _Item) -> Tuple[float, float]:
        """An item's left / right on the solved x (a node: its footprint, a mask)."""
        if it.gid:
            return self.xv[f"group:{it.gid}.L"], self.xv[f"group:{it.gid}.R"]
        c, h = self.nodes_x[it.nid], self.foot[it.nid].h
        return c - h, c + h

    def x_short(self, a: _Item, b: _Item) -> float:
        """How much more x the solved x needs to keep a diagonal pair its x gap apart
        (≤ 0: it does)."""
        if b.xr[1] < a.xr[0]:
            a, b = b, a
        (_, a1), (b0, _) = self._x_extent(a), self._x_extent(b)
        g, _ = self._gap("x", a, b)
        return g - (b0 - a1)

    def _inside(self, eid: str, gid: str) -> bool:
        """An edge end (node or group id) is gid or drawn in it (a border node on it too)."""
        spec = self.spec
        if eid in spec.groups:
            return gid in spec.ancestors(eid)
        n = spec.nodes[eid]
        return gid in spec.ancestors(n.parent) or (n.on is not None and gid in spec.ancestors(n.on))

    def lines_past(self, gid: str, nid: str, left: bool) -> bool:
        """Box gid, on columns left of node nid's (left) or right of them, draws a line (an
        edge from it or from anything in it) to something on the node's far side on the
        solved x (its center past the node's; a box holding the node or gid does not
        count): stacked on y in gid's column, the node would sit outside the lines gid draws
        past it (y only, after x)."""
        key = (gid, nid, left)
        if key not in self._past:
            c, xv = self.nodes_x[nid], self.xv
            past = False
            for e in self.spec.edges:
                for near, far in ((e.a, e.b), (e.b, e.a)):
                    if far == nid or not self._inside(near, gid) or self._inside(far, gid):
                        continue
                    if far in self.spec.groups:
                        if self._inside(nid, far) or self._inside(gid, far):
                            continue
                        x = (xv[f"group:{far}.L"] + xv[f"group:{far}.R"]) / 2
                    else:
                        x = self.nodes_x[far]
                    past = past or (x > c + _EPS if left else x < c - _EPS)
            self._past[key] = past
        return self._past[key]

    def _x_apart(self, a: _Item, b: _Item) -> bool:
        """The solved x keeps a and b at least their x gap apart (y only, after x)."""
        return bool(self.xv) and self.x_short(a, b) <= _EPS

    def _float_units(self, parent):
        """The y blocks of parent's children that have no row of their own: each flow
        column's stack (its first node's top → its last node's bottom) and each box holding
        only stacks, as (x range, top item, bottom item, slot among the rows)."""
        out = []
        for (p, col), ids in self.stacks.items():
            if p == parent:
                out.append(((self.ci[col], self.ci[col]), self.item_node(ids[0]), self.item_node(ids[-1]),
                            self.spec.flow_slot(p, self.spec.track(col).align)))
        for gid in self.child_groups[parent]:
            if gid in self.floats:
                it = self.item_group(gid)
                out.append((it.xr, it, it, self.spec.flow_slot(parent, self.floats[gid])))
        return out

    def _float_siblings(self, parent):
        """Siblings that share a flow column's x with a stack (a node pinned on one of its
        grid rows, a box over its column, another stack box) are kept off it on y: above the
        stack when the middle of their rows lies above the stack's slot (Spec.flow_slot),
        else below; two stack blocks by slot, then spec order."""
        units = self._float_units(parent)
        if not units:
            return
        others = [self.item_group(g) for g in self.child_groups[parent] if g not in self.floats]
        others += [self.item_node(n) for n in self.child_nodes[parent] if n not in self.flowc]
        for gid in self.child_groups[parent]:
            others += [self.item_node(b) for b in self.border_of.get(gid, [])]
        if parent is not None:
            others += [self.item_node(b) for b in self.border_of.get(parent, [])]
        owner = f"group:{parent}" if parent else "canvas"
        for xr, top, bot, slot in units:
            for o in others:
                if o.xr is None or o.yr is None or _disjoint(xr, o.xr):
                    continue                     # x keeps them apart (or nothing places it)
                if slot is not None and (o.yr[0] + o.yr[1]) / 2 < slot:
                    self._sep("y", o, top, owner)
                else:
                    self._sep("y", bot, o, owner)
        for i, (xa, ta, ba, sa) in enumerate(units):
            for xb, tb, bb, sb in units[i + 1:]:
                if _disjoint(xa, xb):
                    continue
                if (sb if sb is not None else 0) < (sa if sa is not None else 0):
                    self._sep("y", bb, ta, owner)
                else:
                    self._sep("y", ba, tb, owner)

    def _align(self, axis, a, b):
        """Sibling boxes over the same tracks share both edges on this axis (subnets of one
        AZ row: one top and bottom; spoke VPCs in one column: one left and right)."""
        key = (axis,) + tuple(sorted((a, b)))
        if key in self.aligned:
            return
        self.aligned.add(key)
        for e in (("L", "R") if axis == "x" else ("T", "B")):
            va, vb = (f"group:{a}.{e}", 0), (f"group:{b}.{e}", 0)
            self.add(axis, va, vb, 0, f"aligned with {a} (same tracks)", f"group:{b}")
            self.add(axis, vb, va, 0, f"aligned with {a} (same tracks)", f"group:{b}")
            self.ties[axis].append((va[0], vb[0]))
        # children of aligned boxes over the same tracks align too (the AZ rows and subnets
        # of two side-by-side VPCs; the subnets of two stacked spoke VPCs)
        for ca in self.child_groups[a]:
            ra = self.group_rng(ca, axis)
            for cb in self.child_groups[b]:
                if ra is not None and ra == self.group_rng(cb, axis):
                    self._align(axis, ca, cb)

    def _border(self, axis, nid):
        """IGW / VGW pinned on its VPC's left or right border (5)."""
        n, spec = self.spec.nodes[nid], self.spec
        v = spec.groups[n.on]
        own = f"node:{nid}"
        it = self.item_node(nid)
        if axis == "x":
            side = n.side or "left"
            if side not in ("left", "right"):
                self.warnings.append(f"{n.src} {nid}: side {side!r} is phase 2; drawn on the left border")
                side = "left"
            edge = (f"group:{v.id}.{'L' if side == 'left' else 'R'}", 0.0)
            c = self.nref(nid, "x", "lo")
            self.add("x", edge, c, 0, f"on the {side} border of {v.id}", own)
            self.add("x", c, edge, 0, f"on the {side} border of {v.id}", own)
            if v.parent:
                self.add("x", (f"group:{v.parent}.L", 0), self.lo(it, "x"), K.MASK_CLEAR,
                         f"mask clear {K.MASK_CLEAR} {v.parent} ⊃ {nid}", own)
                self.add("x", self.hi(it, "x"), (f"group:{v.parent}.R", 0), K.MASK_CLEAR,
                         f"mask clear {K.MASK_CLEAR} {nid} ⊂ {v.parent}", own)
        else:
            top = K.top_inset(v.type, self.mc.name, "icon", bool(v.cidr))
            self.add("y", (f"group:{v.id}.T", 0), self.lo(it, "y"), top, f"icon inset {fmt_num(top)} {v.id} ⊃ {nid}", own)
            self.add("y", self.hi(it, "y"), (f"group:{v.id}.B", 0), K.MASK_CLEAR,
                     f"mask clear {K.MASK_CLEAR} {nid} ⊂ {v.id}", own)

    def _flows(self):
        """Flow rows (8): own x variables, pitch apart, in spec order."""
        rows = defaultdict(list)
        for nid in self.flow:
            n = self.spec.nodes[nid]
            rows[(n.parent, n.row)].append(nid)
        for key in sorted(rows, key=lambda k: (str(k[0]), str(k[1]))):
            ids = sorted(rows[key], key=lambda i: (self.spec.nodes[i].flow_index or 0,
                                                   list(self.spec.nodes).index(i)))
            tr = self.spec.track(key[1]) if key[1] else None
            pitch = tr.flow if tr is not None and tr.flow else self.mc.flow_pitch
            for a, b in zip(ids, ids[1:]):
                d = max(pitch, self.foot[a].h + self.foot[b].h + self.mc.sibling_gap)
                self.add("x", (f"node:{a}", 0), (f"node:{b}", 0), d,
                         f"flow pitch {fmt_num(pitch)} {a} → {b}", f"node:{b}")
            self.flow_rows.append((key[0], ids))

    def _flow_cols(self):
        """Flow columns (8): own y variables, top → bottom in spec order, each next icon at
        least the column's pitch below, and below the previous label stack + stack gap."""
        for (parent, col), ids in sorted(self.stacks.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
            pitch = self.spec.track(col).flow or self.mc.flow_pitch
            for a, b in zip(ids, ids[1:]):
                d = max(pitch, self.foot[a].bot - self.foot[b].top + self.mc.stack_gap)
                self.add("y", (f"node:{a}", 0), (f"node:{b}", 0), d,
                         f"flow pitch {fmt_num(pitch)} {a} ↓ {b}" + (" (label stack)" if d > pitch else ""),
                         f"node:{b}")

    def align_stacks(self, cons: List[Requirement], yv: Dict[str, float]):
        """Move each flow column, and each box holding only stacks, down from its minimal
        (top) position: centered in its parent's height (a stack from its first node's icon
        top to its last node's footprint bottom; at the top level, the height of the rest of
        the drawing), or to the bottom, as far as every constraint allows. Innermost first.
        What is tied to the block moves with it (an `xy` node on a stack node's y, an overlay
        over stack members only); anything else it would push limits the move."""
        units = []
        for (parent, col), ids in self.stacks.items():
            mem = {f"node:{i}" for i in ids}
            ext = (f"node:{ids[0]}", self.foot[ids[0]].top, f"node:{ids[-1]}", self.foot[ids[-1]].bot)
            units.append((parent, self.spec.track(col).align, mem, ext, None))
        for gid, align in self.floats.items():
            mem = {f"group:{g}.{e}" for g in self.spec.groups if gid in self.spec.ancestors(g) for e in "TB"}
            mem |= {self.nref(n, "y", "lo")[0] for n in self.spec.nodes if gid in self.spec.node_chain(n)}
            ext = (f"group:{gid}.T", 0.0, f"group:{gid}.B", 0.0)
            units.append((self.spec.groups[gid].parent, align, mem, ext, gid))
        depth = {None: -1, **{g: self.spec.groups[g].depth for g in self.spec.groups}}
        for parent, align, mem, (tv, to, bv, bo), gid in sorted(units, key=lambda u: -depth[u[0]]):
            if align == "top":
                continue
            mem = self._followers(cons, mem)
            slack = _shift_slack(cons, yv, mem)
            top, bot = yv[tv] + to, yv[bv] + bo
            if parent is None:
                rest = self._top_extent(yv, mem, gid)
                if rest is None:
                    continue
                pt, pb = rest
            else:
                pt, pb = yv[f"group:{parent}.T"], yv[f"group:{parent}.B"]
            want = (pt + pb) / 2 - (top + bot) / 2 if align == "center" else (slack if parent else pb - bot)
            lim = min(want, slack)
            shift = math.floor(lim + 1e-9) if lim != float("inf") else 0
            if shift > 0:
                for v in mem:
                    yv[v] += shift
                where = parent or "the drawing"
                for v in mem:
                    if v.startswith("node:") and v[5:] in self.flowc:
                        self.stack_shift[v[5:]].append((align, where, shift))

    def _followers(self, cons: List[Requirement], mem: set) -> set:
        """mem plus what a move of it carries along: `xy` nodes a constraint ties to it and
        overlays whose members all move."""
        mem = set(mem)
        while True:
            add = {c.b for c in cons if c.a in mem and c.b not in mem and c.b.startswith("node:")
                   and self.spec.nodes[c.b[5:]].xy is not None}
            for g in self.overlays:
                vs = {f"group:{g.id}.T", f"group:{g.id}.B"}
                if not vs <= mem and all(self.nref(m, "y", "lo")[0] in mem for m in g.over):
                    add |= vs
            add -= mem
            if not add:
                return mem
            mem |= add

    def _top_extent(self, yv, mem, gid) -> Optional[Tuple[float, float]]:
        """The y extent of the top-level boxes and nodes outside mem (a top-level stack
        aligns in it); None when there are none."""
        ext = [(yv[f"group:{g}.T"], yv[f"group:{g}.B"]) for g in self.child_groups[None]
               if g != gid and f"group:{g}.T" not in mem]
        for nid in self.child_nodes[None] + [b for v, bs in self.border_of.items()
                                             if self.spec.groups[v].parent is None for b in bs]:
            v, o = self.nref(nid, "y", "lo")
            if v not in mem and v in yv:
                f = self.foot[nid]
                ext.append((yv[v] + o + f.top, yv[v] + o + f.bot))
        if not ext:
            return None
        return min(e[0] for e in ext), max(e[1] for e in ext)

    def _badge_clear_x(self):
        """Slides: the nodes on a badged box's first row sit right of its badge (icon left ≥
        badge right + ICON_CLEAR) instead of pushing the row down under it (y_after_x)."""
        S = self.S
        for g in self.tree:              # not overlays: an ASG's title already sets its header
            st = K.style(g.type)
            if not st.badge or not g.rows:
                continue
            if g.type not in ("public", "private"):
                continue                 # subnets: nodes sit right under the header (ex slide nfw)
            members = self.child_nodes[g.id]
            first = self.spec.track(g.rows[0])
            d = st.badge_size + K.ICON_CLEAR + S / 2
            for nid in members:
                n = self.spec.nodes[nid]
                if n.xy is not None or n.row != first.id or nid in self.flow:
                    continue
                v, o = self.nref(nid, "x", "lo")
                self.add("x", (f"group:{g.id}.L", 0), (v, o), d,
                         f"badge clear x {fmt_num(d)} {g.id} ⊃ {nid}", f"group:{g.id}")

    def _az_gaps(self):
        """The row between two AZ boxes (6): ≥ az_gap, its tracks centered at least half,
        only when a node of the AZs' parent (or one on its border) sits on a row between
        them; otherwise the boxes keep the sibling gap."""
        gap = self.mc.az_gap
        for parent, kids in self.child_groups.items():
            azs = [self.item_group(g) for g in kids if self.spec.groups[g].type == "az"]
            azs = sorted((a for a in azs if a.yr), key=lambda a: a.yr)
            for a, b in zip(azs, azs[1:]):
                if not a.yr[1] < b.yr[0] or not self._between_az(parent, a.yr[1], b.yr[0]):
                    continue
                own = f"group:{b.gid}"
                self.add("y", (f"group:{a.gid}.B", 0), (f"group:{b.gid}.T", 0), gap,
                         f"az gap {fmt_num(gap)} {a.gid} | {b.gid}", own)
                if not self.mc.az_gap_center:
                    continue
                for t in self.spec.rows[a.yr[1] + 1:b.yr[0]]:
                    self.add("y", (f"group:{a.gid}.B", 0), (f"row:{t.id}", 0), gap / 2,
                             f"az gap half {fmt_num(gap / 2)} {a.gid} → row {t.id}", own)
                    self.add("y", (f"row:{t.id}", 0), (f"group:{b.gid}.T", 0), gap / 2,
                             f"az gap half {fmt_num(gap / 2)} row {t.id} → {b.gid}", own)

    def _between_az(self, parent, lo, hi) -> bool:
        """A node of parent's subtree outside its AZ boxes, or on the border of parent or a
        group inside it, whose row lies strictly between track indexes lo and hi."""
        for nid, n in self.spec.nodes.items():
            r = self.node_rng(nid, "y")
            if r is None or not (lo < r[0] and r[1] < hi):
                continue
            chain = self.spec.ancestors(n.on) if n.on else self.spec.node_chain(nid)
            if parent is None or parent in chain:
                return True
        return False

    def _templates_equal(self, axis):
        """Instances of one template group with identical track ranges on this axis get
        equal edges (the other axis is evened out by iteration, see _even)."""
        for ids in self.template_sets():
            rs = [self.group_rng(g, axis) for g in ids]
            if any(r != rs[0] for r in rs):
                continue
            for a, b in zip(ids, ids[1:]):
                for e in (("L", "R") if axis == "x" else ("T", "B")):
                    va, vb = (f"group:{a}.{e}", 0), (f"group:{b}.{e}", 0)
                    self.add(axis, va, vb, 0, f"template instances alike {a} = {b}", f"group:{b}")
                    self.add(axis, vb, va, 0, f"template instances alike {a} = {b}", f"group:{b}")
                    self.ties[axis].append((va[0], vb[0]))

    # ---- twins: containers of one structure drawn alike ----------------------------

    def _subtree(self, gid) -> List[str]:
        out = [gid]
        for c in self.child_groups[gid]:
            out += self._subtree(c)
        return out

    def _tracks_used(self, gid) -> Tuple[List[int], List[int]]:
        """The row and column indexes gid's subtree covers (its boxes' ranges, its nodes')."""
        rows, cols = set(), set()
        for g in self._subtree(gid):
            for axis, out in (("y", rows), ("x", cols)):
                r = self.group_rng(g, axis)
                if r:
                    out.update(r)
                for nid in self.child_nodes[g] + self.border_of.get(g, []):
                    r = self.node_rng(nid, axis)
                    if r:
                        out.update(r)
        return sorted(rows), sorted(cols)

    def _shape(self, gid, rank, root=False):
        """(signature, its subtree's box ids, its nodes' ids, both in canonical order): the
        group type tree with each box's type, title (not a named root's own: two App VPCs
        are twins), CIDR line or not and track ranks, and per box its nodes' icons, caption
        line counts and track ranks. Children come in signature order (spec order breaks
        ties), so twins' boxes and nodes correspond by index."""
        g = self.spec.groups[gid]
        ry, rx = rank

        def rel(r, rk):
            return None if r is None else (rk[r[0]], rk[r[1]])

        kids = sorted(((self._shape(c, rank), k) for k, c in enumerate(self.child_groups[gid])),
                      key=lambda it: (repr(it[0][0]), it[1]))
        nodes = []
        for k, nid in enumerate(self.child_nodes[gid] + self.border_of.get(gid, [])):
            n = self.spec.nodes[nid]
            nodes.append(((n.icon, 1 + len(n.sub), rel(self.node_rng(nid, "y"), ry), rel(self.node_rng(nid, "x"), rx),
                           bool(n.on), n.side if n.on else None), k, nid))
        nodes.sort(key=lambda it: (repr(it[0]), it[1]))
        label = None if root and g.type in TWIN_NAMED else g.label
        sig = (g.type, label, bool(g.cidr), rel(self.group_rng(gid, "y"), ry), rel(self.group_rng(gid, "x"), rx),
               tuple(sh[0] for sh, _ in kids), tuple(t for t, _, _ in nodes))
        order = [gid] + [d for (_, ds, _), _ in kids for d in ds]
        norder = [nid for _, _, nid in nodes] + [n for (_, _, ns), _ in kids for n in ns]
        return sig, order, norder

    def _overlay_shape(self, norder, used):
        """The overlays reaching into gid's subtree (norder: its nodes in signature order;
        used: the (rows, cols) indexes it covers) as part of its signature, and per overlay
        the edges inside it on each axis. Per overlay with a member in the subtree: its type,
        title, header placement (given, and beside its first row or not), per axis the rank
        of each end track among `used` (between two used tracks: the gap's rank − 0.5;
        outside the subtree: None — that edge is not the box's), and its members in the
        subtree by index in norder, each with whether it sits on the overlay's first and
        last member row and whether its subnet is a leftmost and a rightmost one
        (_overlay_sides) (which decide where the header goes and which subnets it insets).
        Members outside the subtree count only through those flags, so a box an overlay
        reaches into from outside (an ASG across a VPC's AZs) twins with the box holding the
        same part of an equal overlay. Sorted; the edges come in the same order."""
        idx = {nid: k for k, nid in enumerate(norder)}
        out = []
        for o in self.overlays:
            if not any(m in idx for m in o.over):
                continue
            rows = [self._member_row(m) for m in o.over]
            first, last = min(rows), max(rows)
            sides = self._overlay_sides(o)
            mem = tuple(sorted((idx[m], r == first, r == last, sides.get(self.spec.nodes[m].parent, (True, True)))
                               for m, r in zip(o.over, rows) if m in idx))
            rr, edges = [], []
            for axis, ts, lo, hi in (("y", used[0], "T", "B"), ("x", used[1], "L", "R")):
                r = self.group_rng(o.id, axis)
                ends, es = [], []
                for t, e in (() if r is None or not ts else ((r[0], lo), (r[1], hi))):
                    if not ts[0] <= t <= ts[-1]:
                        ends.append(None)
                        continue
                    k = bisect.bisect_left(ts, t)
                    ends.append(k if ts[k] == t else k - 0.5)
                    es.append(e)
                rr.append(tuple(ends))
                edges.append(es)
            out.append(((o.type, o.label, self._overlay_header(o), self._overlay_beside(o), tuple(rr), mem),
                        (o.id, edges[1], edges[0])))
        out.sort(key=lambda it: repr(it[0]))
        return tuple(sh for sh, _ in out), [e for _, e in out]

    def twin_sets(self) -> List[list]:
        """Containers of one structure anywhere in the drawing (twins), per class of two or
        more: (box id, (its row ids, its col ids) in rank order, its subtree's boxes in
        corresponding order, the overlays reaching into it with their edges inside it, see
        _overlay_shape). Instances of one template keep their own rule (alike in a
        document, each hugging its content on a slide): an instance only twins with boxes
        of its own instance number."""
        if self._twins is not None:
            return self._twins
        classes: Dict[tuple, list] = defaultdict(list)
        for g in self.tree:
            rows, cols = self._tracks_used(g.id)
            if not rows and not cols:
                continue
            rank = ({r: k for k, r in enumerate(rows)}, {c: k for k, c in enumerate(cols)})
            sig, order, norder = self._shape(g.id, rank, root=True)
            over, oedges = self._overlay_shape(norder, (rows, cols))
            key = (repr((sig, over)), g.instance if g.template else None)
            classes[key].append((g.id, ([self.spec.rows[i].id for i in rows], [self.spec.cols[i].id for i in cols]),
                                 order, oedges))
        self._twins = [v for v in classes.values() if len(v) > 1]
        return self._twins

    def _twin_measures(self, axis, member) -> List[Tuple[str, str, str]]:
        """A twin's measures on this axis in corresponding order, each (a, b, what): b − a
        is measured, what names it. From its left / top edge: its far edge, each box of
        its subtree's two edges, each covered track, each overlay's right / bottom edge
        inside it; an overlay's left / top edge inside it to its far edge (an overlay hugs
        its members from outside, so the larger value is the wider overlay)."""
        gid, (rows, cols), order, oedges = member
        lo, hi = ("L", "R") if axis == "x" else ("T", "B")
        base, far = f"group:{gid}.{lo}", f"group:{gid}.{hi}"
        out = [far]
        for d in order[1:]:
            out += [f"group:{d}.{lo}", f"group:{d}.{hi}"]
        out += [f"{'col' if axis == 'x' else 'row'}:{t}" for t in (cols if axis == "x" else rows)]
        ms = [(base, v, v) for v in out]
        for oid, xe, ye in oedges:
            for e in (xe if axis == "x" else ye):
                v = f"group:{oid}.{e}"
                ms.append((v, far, v) if e == lo else (base, v, v))
        return ms

    def twins_even(self, axis, val: Dict[str, float], have: Dict[tuple, Requirement]) -> bool:
        """Twins on this axis: every measure (size, each inner box's edges, each track, from
        the twin's own left / top edge; an overlay's edges, see _twin_measures) at the
        largest its class has, as soft lower bounds in `have` ((a, b) → requirement, raised
        in place) — offsets, never positions, so twins on other tracks stay where they are.
        True when one was added or raised. Twins whose tracks other twins share can push
        each other on without end: the caller keeps the round with the least twins_spread
        and stops when a round does not lower it (twins_unlike then warns)."""
        changed = False
        for cls in self.twin_sets():
            ms = [self._twin_measures(axis, mem) for mem in cls]
            for k in range(len(ms[0])):
                vals = [val[m[k][1]] - val[m[k][0]] for m in ms]
                top = max(vals)
                like = cls[vals.index(top)][0]
                for m, got, mem in zip(ms, vals, cls):
                    a, b, what = m[k]
                    key = (a, b)
                    if got >= top - 0.25 or (key in have and have[key].d >= top - _EPS):
                        continue
                    have[key] = Requirement(axis, a, b, top, f"{TWIN_WHY} {mem[0]} like {like} "
                                            f"({fmt_num(top)} to {what.split(':', 1)[1]})", f"group:{mem[0]}", True)
                    changed = True
        return changed

    def twins_spread(self, axis, val: Dict[str, float]) -> float:
        """How unlike the twins still are on this axis: Σ (largest − smallest) per measure."""
        out = 0.0
        for cls in self.twin_sets():
            ms = [self._twin_measures(axis, mem) for mem in cls]
            for k in range(len(ms[0])):
                vals = [val[m[k][1]] - val[m[k][0]] for m in ms]
                out += max(vals) - min(vals)
        return out

    def twins_unlike(self, axis, val: Dict[str, float]) -> List[str]:
        """Warnings for twins still drawn unlike (their spacing dropped in a contradiction,
        or not settled): one per class and axis."""
        out = []
        for cls in self.twin_sets():
            ms = [self._twin_measures(axis, mem) for mem in cls]
            for k in range(len(ms[0])):
                vals = [val[m[k][1]] - val[m[k][0]] for m in ms]
                if max(vals) - min(vals) > 0.5:
                    a, b = cls[vals.index(min(vals))][0], cls[vals.index(max(vals))][0]
                    out.append(f"{self.spec.groups[a].src} {a}: same structure as {b} but drawn "
                               f"{fmt_num(max(vals) - min(vals))} px unlike it on {axis} "
                               f"({ms[vals.index(min(vals))][k][2].split(':', 1)[1]}); other constraints keep "
                               f"them apart")
                    break
        return out

    def template_sets(self) -> List[List[str]]:
        sets: Dict[str, List[str]] = {}
        for g in self.tree:
            if g.instance is not None and "." in g.id:
                sets.setdefault(g.id.rsplit(".", 1)[0], []).append(g.id)
        return [v for v in sets.values() if len(v) > 1]

    def _overlay_x(self, g):
        """Overlay (ASG) in x (9): around its members; its left edge inside (and right of the
        header label of) each leftmost member subnet, its right edge inside each rightmost one
        (_overlay_sides: subnets stacked on rows are all both, so the overlay sits inside each;
        side by side, an ASG across AZ columns, it spans the ones between)."""
        mc, st, gid = self.mc, K.style(g.type), g.id
        own = f"group:{gid}"
        gl, gr = (f"group:{gid}.L", 0.0), (f"group:{gid}.R", 0.0)
        pl, pr = self.side_pad(gid, "L", node=True), self.side_pad(gid, "R", node=True)
        for m in g.over:
            it = self.item_node(m)
            self.add("x", gl, self.lo(it, "x"), pl, f"pad {fmt_num(pl)} {gid} ⊃ {m}", own)
            self.add("x", self.hi(it, "x"), gr, pr, f"pad {fmt_num(pr)} {m} ⊂ {gid}", own)
        if self._overlay_beside(g):
            # a short title: the first member row sits right of the badge + title (ex gwlb)
            d = (st.title_dx + _up(layout_text_width(g.label, st.title_size)) + K.HEADER_ICON_CLEAR if g.label
                 else st.badge_size + K.ICON_CLEAR) + self.S / 2
            for m in self._overlay_first(g, nodes=True):
                self.add("x", gl, self.nref(m, "x", "lo"), d, f"beside {gid} title {fmt_num(d)} ⊃ {m}", own)
        # over stack members: no subnet holds it, so keep it off the parent's other children
        # left and right of the column (a long title would reach over the VPC beside it)
        for (parent, col), ids in self.stacks.items():
            if not set(ids) & set(g.over):
                continue
            c = self.ci[col]
            sibs = [self.item_group(x) for x in self.child_groups[parent]]
            sibs += [self.item_node(n) for n in self.child_nodes[parent] if n not in ids]
            for o in sibs:
                if o.xr is not None and o.xr[1] < c:
                    self.add("x", self.hi(o, "x"), gl, mc.sibling_gap, f"overlay {gid} right of {o.key}", own)
                elif o.xr is not None and o.xr[0] > c:
                    self.add("x", gr, self.lo(o, "x"), mc.sibling_gap, f"overlay {gid} left of {o.key}", own)
        first, header = self._overlay_first(g), self._overlay_header(g)
        for s, (left, right) in self._overlay_sides(g).items():
            sg = self.spec.groups[s]
            ss = K.style(sg.type)
            if left:
                self.add("x", (f"group:{s}.L", 0), gl, K.OVERLAY_HEADER_GAP, f"overlay inside {s}", own)
            if right:
                self.add("x", gr, (f"group:{s}.R", 0), K.OVERLAY_HEADER_GAP, f"overlay inside {s}", own)
            if sg.label and (header == "right" or s not in first) and (left or s not in first):
                # an edge that runs down through the subnet's header row clears its title: the
                # left edge of a leftmost one, else (a lower-row rightmost one) the right edge
                d = ss.title_dx + _up(layout_text_width(sg.label, ss.title_size)) + K.OVERLAY_HEADER_GAP
                if left:
                    self.add("x", (f"group:{s}.L", 0), gl, d, f"overlay right of {s} header {fmt_num(d)}", own)
                elif right:
                    self.add("x", (f"group:{s}.L", 0), gr, d, f"overlay ends right of {s} header {fmt_num(d)}", own)
        w = (st.title_dx + _up(layout_text_width(g.label, st.title_size)) + K.HEADER_TAIL if g.label
             else st.badge_size + K.ICON_CLEAR if st.badge else 0)
        if g.label:
            self.add("x", gl, gr, w, f"title width {fmt_num(w)} {gid}", own)
        if w:
            # the header row lies in the first-row leftmost subnet: one the overlay leaves on
            # the right (AZ columns) ends past the title, its border off the text
            sides = self._overlay_sides(g)
            for s in first:
                if s in sides and sides[s] == (True, False):
                    self.add("x", gl, (f"group:{s}.R", 0), w, f"{gid} title {fmt_num(w)} inside {s}", own)

    def _overlay_subnets(self, g):
        out = []
        for m in g.over:
            p = self.spec.nodes[m].parent
            if p and p not in out:
                out.append(p)
        return out

    def _overlay_sides(self, g) -> Dict[str, Tuple[bool, bool]]:
        """Per member subnet (spec order): (leftmost, rightmost) — no other member subnet
        sits beside it on its left (right): wholly left (right) of it on the columns, with
        the two boxes just below their lowest common ancestor (AZ a and AZ b, or the two
        subnets of one AZ) sharing a row, so the solve keeps them apart on x. Judged by those
        ancestors, not the subnets' own rows: under an ASG across AZ columns a lower subnet of
        AZ a (Worker, row 2) with none beside it in AZ b is still left of AZ b's subnets, as
        AZ a is left of AZ b (an L-shaped ASG). Subnets stacked on rows (on one column, or
        AZs on a diagonal) are each both, and the overlay sits inside every one; side by side
        (AZ columns) its left edge stays in the left ones, its right edge in the right ones,
        and it spans the ones between. A subnet with no column range counts as both; a box
        with no row range shares every row; one subnet inside another is not beside it."""
        subs = self._overlay_subnets(g)
        groups = self.spec.groups

        def chain(s):
            out = []
            while s is not None:
                out.append(s)
                s = groups[s].parent
            return out

        def below_lca(a, b):
            """a's and b's ancestors (or selves) just below their lowest common ancestor;
            None when one holds the other."""
            ca, cb = chain(a), chain(b)
            ia = next((k for k, x in enumerate(ca) if x in cb), len(ca))
            ib = cb.index(ca[ia]) if ia < len(ca) else len(cb)
            if ia == 0 or ib == 0:
                return None
            return ca[ia - 1], cb[ib - 1]

        def share_row(a, b):
            return a is None or b is None or (a[0] <= b[1] and b[0] <= a[1])

        out = {}
        for s in subs:
            rx = self.group_rng(s, "x")
            if rx is None:
                out[s] = (True, True)
                continue
            beside = []
            for u in subs:
                tx, pair = self.group_rng(u, "x"), below_lca(s, u) if u != s else None
                if tx is not None and pair is not None \
                        and share_row(self.group_rng(pair[0], "y"), self.group_rng(pair[1], "y")):
                    beside.append(tx)
            out[s] = (not any(t[1] < rx[0] for t in beside), not any(t[0] > rx[1] for t in beside))
        return out

    def _overlay_header(self, g) -> str:
        """The header placement the overlay is drawn with: its `header` (default right),
        except `below` when a first-row member subnet that is not leftmost has a header (a
        badge, title or CIDR line) — the top edge, level with the subnet titles under
        `right`, would cross it (an ASG across AZ columns)."""
        if g.header == "below":
            return "below"
        return "below" if self._overlay_crossed(g) else "right"

    def _overlay_crossed(self, g) -> List[str]:
        """First-row member subnets that are not leftmost and have a header (badge, title or
        CIDR line) the overlay's top edge would cross level with the subnet titles."""
        sides = self._overlay_sides(g)
        out = []
        for s in self._overlay_first(g):
            sg = self.spec.groups[s]
            if s in sides and not sides[s][0] and (sg.label or sg.cidr or K.style(sg.type).badge) and s not in out:
                out.append(s)
        return out

    def overlay_header_warnings(self) -> List[str]:
        """An overlay given `header: right` that _overlay_header draws `below`."""
        out = []
        for g in self.overlays:
            if g.header == "right":
                crossed = self._overlay_crossed(g)
                if crossed:
                    out.append(f"{g.src}: header: right drawn as below — level with the subnet titles its "
                               f"top would cross the header of {', '.join(crossed)} (not leftmost); "
                               f"drop `header:` or give `header: below`")
        return out

    def _overlay_first(self, g, last=False, nodes=False):
        """Member subnets (or, nodes=True, the members) in the overlay's first (or last) member
        row. A flow-column member sits at its stack's slot (Spec.flow_slot); of a stack only
        the first node of a top-aligned column is a first-row member (the others, and a
        centered or bottom stack, sit below their subnet's top)."""
        rows = [self._member_row(m) for m in g.over]
        want = max(rows) if last else min(rows)
        if nodes:
            return [m for m, r in zip(g.over, rows) if r == want and self._stack_top(m)]
        return [self.spec.nodes[m].parent for m, r in zip(g.over, rows) if r == want and self.spec.nodes[m].parent]

    def _member_row(self, m) -> float:
        """An overlay member's row index; a flow-column node its stack's slot (the first node
        of a top-aligned stack: its parent's first row, beside the nodes on it)."""
        n = self.spec.nodes[m]
        if m not in self.stack_of:
            return self.ri.get(n.row, 0)
        (parent, col), k = self.stack_of[m]
        align = self.spec.track(col).align
        rows = self.spec.groups[parent].rows if parent else None
        if k == 0 and align == "top" and rows:
            return self.ri[rows[0]]
        slot = self.spec.flow_slot(parent, align)
        return 0 if slot is None else slot

    def _stack_top(self, m) -> bool:
        """Not a flow-column node, or the first node of a top-aligned stack."""
        if m not in self.stack_of:
            return True
        (_, col), k = self.stack_of[m]
        return k == 0 and self.spec.track(col).align == "top"

    def _overlay_beside(self, g) -> bool:
        """An overlay title no wider than an icon (or a badge alone) goes left of the first
        member row, when the header inset under it would push that row below its subnet's
        own icon inset; a longer title stays above the members (ex alb, nlb) — y_after_x
        then finds them clear of the header. Only when every first-row member is in a
        subnet and on its first row: a member lower in its box (something of the box above
        it) or outside any box has no subnet header to sit beside, so the title goes above."""
        st, mc = K.style(g.type), self.mc
        if g.label:
            if layout_text_width(g.label, st.title_size) > self.S:
                return False
        elif not st.badge:
            return False
        under = K.top_inset(g.type, mc.name, "icon")
        if st.badge:
            under = max(under, st.badge_size + K.ICON_CLEAR)
        first = self._overlay_first(g, nodes=True)
        for m in first:
            p = self.spec.nodes[m].parent
            if p is None:
                return False
            r, pr = self.node_rng(m, "y"), self.group_rng(p, "y")
            if r is not None and pr is not None and r[0] > pr[0]:
                return False
        return any(self._overlay_below(g, p) + under > self._icon_inset(p)
                   for p in (self.spec.nodes[m].parent for m in first))

    def _overlay_below(self, g, s) -> float:
        """Subnet s's top → the overlay's top: 8, or 8 below s's title (header: below, see
        _overlay_header)."""
        if self._overlay_header(g) == "below":
            ss = K.style(self.spec.groups[s].type)
            return _up(ss.title_dy + K.GLYPH_DESCENT * ss.title_size) + K.OVERLAY_HEADER_GAP
        return K.OVERLAY_HEADER_GAP

    def _icon_inset(self, gid) -> float:
        sg = self.spec.groups[gid]
        return max(K.top_inset(sg.type, self.mc.name, "icon", bool(sg.cidr)), sg.pad_top or 0)

    def _float_flow_rows(self, xv: Dict[str, float], nodes_x: Dict[str, float]):
        """A flow row and a stack block of one parent (8): a flow-row node has no column, so
        _float_siblings cannot tell from the tracks whether it shares the stack's x. Once x
        is solved, each flow-row node whose footprint comes within sibling_gap of the block's
        x extent (its nodes' footprints; a box of stacks: its edges) is kept off it on y, on
        the side Spec.flow_row_above gives: a row on the parent's first row above a
        top-aligned block, one on its last row below a bottom-aligned block (the block stops
        at the row and the row keeps the parent's edge), else as a node pinned on that row
        (above when its row lies before the block's slot). Against a stack's end node the
        footprint gap is twice the column's own spacing there (its pitch, or label stack +
        stack gap, less the two footprints), at least that spacing + sibling_gap, so the row
        node never sits where the column's next node would and cannot be read as one."""
        g = self.mc.sibling_gap
        for parent, ids in self.flow_rows:
            units = self._float_units(parent)
            if not units:
                continue
            owner = f"group:{parent}" if parent else "canvas"
            for xr, top, bot, slot in units:
                if top.gid:
                    x0, x1 = xv[f"group:{top.gid}.L"], xv[f"group:{top.gid}.R"]
                    align, pitch = self.floats[top.gid], None
                else:
                    col = self.spec.nodes[top.nid].col
                    mem = self.stacks[(parent, col)]
                    x0 = min(nodes_x[i] - self.foot[i].h for i in mem)
                    x1 = max(nodes_x[i] + self.foot[i].h for i in mem)
                    align = self.spec.track(col).align
                    pitch = self.spec.track(col).flow or self.mc.flow_pitch
                for nid in ids:
                    o = self.item_node(nid)
                    h = self.foot[nid].h
                    if o.yr is None or nodes_x[nid] + h + g <= x0 or nodes_x[nid] - h - g >= x1:
                        continue
                    above = self.spec.flow_row_above(parent, align, o.yr[0])
                    a, b = (o, top) if above else (bot, o)
                    self._sep("y", a, b, owner)
                    if pitch is not None:
                        fa, fb = self.foot[a.nid], self.foot[b.nid]
                        sp = max(pitch, fa.bot - fb.top + self.mc.stack_gap) - (fa.bot - fb.top)
                        d = sp + max(g, sp)
                        self.add("y", self.hi(a, "y"), self.lo(b, "y"), d,
                                 f"off the column {fmt_num(d)} (2 × its spacing {fmt_num(sp)}, ≥ spacing + "
                                 f"sibling gap {fmt_num(g)}) {a.key} | {b.key}", owner)

    def y_after_x(self, xv: Dict[str, float], nodes_x: Dict[str, float]):
        """The y rules that depend on solved x: a flow row kept off a stack it meets on x
        (8), overlay top (9, decision f) and group badge ↔ icon clearance (QR 73)."""
        mc, S = self.mc, self.S
        self._float_flow_rows(xv, nodes_x)
        for g in self.overlays:
            st, gid = K.style(g.type), g.id
            own = f"group:{gid}"
            gl, gr = (f"group:{gid}.T", 0.0), (f"group:{gid}.B", 0.0)
            L = xv[f"group:{gid}.L"]
            t0 = L + st.title_dx - K.HEADER_ICON_CLEAR
            t1 = L + st.title_dx + (layout_text_width(g.label, st.title_size) if g.label else 0) + K.HEADER_ICON_CLEAR
            b1 = L + (st.badge_size + K.ICON_CLEAR if st.badge else 0)
            beside = set(self._overlay_first(g, nodes=True)) if self._overlay_beside(g) else set()
            for m in g.over:
                it = self.item_node(m)
                cx = nodes_x[m]
                x0, x1 = cx - S / 2, cx + S / 2
                under = (g.label and x1 > t0 and x0 < t1) or (st.badge and x0 < b1 and x1 > L - K.ICON_CLEAR)
                top = K.top_inset(g.type, mc.name, "icon") if under else K.OVERLAY_HEADER_GAP
                if under and st.badge and x0 < b1:
                    top = max(top, st.badge_size + K.ICON_CLEAR)
                what = "header" if under else "overlay"
                if m in beside and not under:
                    # beside its title: the subnet's own icon inset, less the overlay's top
                    # inset in the subnet, so the top hugs to 8 under the subnet top when the
                    # row sits at that inset and follows the row when it sits lower
                    p = self.spec.nodes[m].parent
                    top, what = max(top, self._icon_inset(p) - self._overlay_below(g, p)), "beside"
                self.add("y", gl, self.lo(it, "y"), top, f"{what} inset {fmt_num(top)} {gid} ⊃ {m}", own)
                ref, d, what = self.node_bottom(gid, it)
                self.add("y", ref, gr, d, f"{what} {m} ⊂ {gid}", own)
            for s in self._overlay_first(g):
                d = self._overlay_below(g, s)
                self.add("y", (f"group:{s}.T", 0), gl, d, f"overlay below {s} top {fmt_num(d)}", own)
            for s in self._overlay_first(g, last=True):
                self.add("y", gr, (f"group:{s}.B", 0), K.OVERLAY_HEADER_GAP, f"overlay inside {s}", own)
            # over part of a stack: clear of its nodes just above and below the members
            for key, ids in self.stacks.items():
                ks = [k for k, i in enumerate(ids) if i in g.over]
                if not ks:
                    continue
                if ks[0] > 0:
                    it = self.item_node(ids[ks[0] - 1])
                    self.add("y", self.hi(it, "y"), gl, K.LABEL_CLEAR, f"overlay {gid} below {it.nid}", own)
                if ks[-1] < len(ids) - 1:
                    it = self.item_node(ids[ks[-1] + 1])
                    self.add("y", gr, self.lo(it, "y"), mc.box_node_gap, f"overlay {gid} above {it.nid}", own)
            hdr = _up(max(st.badge_size, K.TITLE_DY + K.GLYPH_DESCENT * st.title_size))
            self.add("y", gl, gr, hdr + mc.pad, f"header height {gid}", own)
        # badge ↔ icon of the group's own nodes
        for g in self.tree:
            st = K.style(g.type)
            if not st.badge:
                continue
            L = xv[f"group:{g.id}.L"]
            b1 = L + st.badge_size + K.ICON_CLEAR
            for nid in self.child_nodes[g.id]:
                cx = nodes_x[nid]
                if cx - S / 2 < b1 and cx + S / 2 > L - K.ICON_CLEAR:
                    d = st.badge_size + K.ICON_CLEAR
                    self.add("y", (f"group:{g.id}.T", 0), self.lo(self.item_node(nid), "y"), d,
                             f"badge clear {fmt_num(d)} {g.id} ⊃ {nid}", f"group:{g.id}")

    def even_insets(self, yv: Dict[str, float]) -> List[Requirement]:
        """Template instances on different rows: equal top / bottom insets (DESIGN 2.2) — in
        documents; on slides each instance hugs its own content (an ASG header deepens only
        AZ 1's top, its bottom only AZ 2's)."""
        out = []
        if not self.mc.even_instances:
            return out
        for ids in self.template_sets():
            refs = []
            for g in ids:
                rows = self.spec.groups[g].rows
                if not rows:
                    break
                refs.append((g, f"row:{rows[0]}"))
            else:
                if len({r for _, r in refs}) < 2:
                    continue
                top = max(yv[r] - yv[f"group:{g}.T"] for g, r in refs)
                bot = max(yv[f"group:{g}.B"] - yv[r] for g, r in refs)
                for g, r in refs:
                    if yv[r] - yv[f"group:{g}.T"] < top - _EPS:
                        out.append(Requirement("y", f"group:{g}.T", r, top,
                                               f"template inset {fmt_num(top)} like the other instances", f"group:{g}"))
                    if yv[f"group:{g}.B"] - yv[r] < bot - _EPS:
                        out.append(Requirement("y", r, f"group:{g}.B", bot,
                                               f"template inset {fmt_num(bot)} like the other instances", f"group:{g}"))
        return out


# =======================================================================================
# Requirements from the other modules

def _map_req(m: _Model, r: Requirement) -> Requirement:
    def one(v, side):
        if v.startswith("node:"):
            nid = v[5:]
            if nid not in m.spec.nodes:
                raise KeyError(v)
            return m.nref(nid, r.axis, side)
        if v in ("origin", "drawing") or v.startswith("group:"):
            if v.startswith("group:"):
                gid, _, e = v[6:].rpartition(".")
                if gid not in m.spec.groups or e not in (("L", "R") if r.axis == "x" else ("T", "B")):
                    raise KeyError(v)
            return (v, 0.0)
        pre = "col:" if r.axis == "x" else "row:"
        if v.startswith(pre) and v[4:] in (m.ci if r.axis == "x" else m.ri):
            return (v, 0.0)
        raise KeyError(v)

    (va, oa), (vb, ob) = one(r.a, "hi"), one(r.b, "lo")
    return Requirement(r.axis, va, vb, r.d + oa - ob, r.why, r.owner, r.soft)


# =======================================================================================
# Longest path

def _bellman_ford(cons: Sequence[Requirement]):
    vs = ["origin"]
    seen = {"origin"}
    for c in cons:
        for v in (c.a, c.b):
            if v not in seen:
                seen.add(v)
                vs.append(v)
    full = [Requirement(cons[0].axis if cons else "x", "origin", v, 0.0, "coordinate ≥ 0", "canvas")
            for v in vs[1:]] + list(cons)
    dist = {v: _NEG for v in vs}
    dist["origin"] = 0.0
    pred: Dict[str, Requirement] = {}
    last = None
    for _ in range(len(vs)):
        last = None
        for c in full:
            da = dist[c.a]
            if da == _NEG:
                continue
            nd = da + c.d
            if nd > dist[c.b] + _EPS:
                dist[c.b] = nd
                pred[c.b] = c
                last = c.b
        if last is None:
            return dist, pred, None
    v = last
    for _ in range(len(vs)):
        v = pred[v].a
    cycle, u = [], v
    while True:
        c = pred[u]
        cycle.append(c)
        u = c.a
        if u == v or len(cycle) > len(vs):
            break
    return dist, pred, cycle[::-1]


def _loc(spec: Spec, owner: str) -> str:
    kind, ident, _ = split_eid(owner)
    if kind == "node" and ident in spec.nodes:
        return f"{spec.nodes[ident].src} {ident}".strip()
    if kind == "group" and ident in spec.groups:
        return f"{spec.groups[ident].src} {ident}".strip()
    if kind == "edge" and ident.isdigit() and int(ident) < len(spec.edges):
        return spec.edges[int(ident)].src or owner
    if kind == "track":
        for name, ts in (("cols", spec.cols), ("rows", spec.rows)):
            for t in ts:
                if t.id == ident:
                    return f"{name}[{t.index}] {ident}"
    if kind == "note":
        return spec.note.src if spec.note else "note"
    return owner


def _solve_axis(m: _Model, axis: str, cons: List[Requirement]):
    """Longest path over cons. A positive cycle drops its soft requirements (a twin's
    spacing first) and retries; a cycle of hard ones that holds an `xy` pin moves that pin
    (_move_pin) and retries; any other raises SolveError naming each constraint. Returns
    (dist, pred, the constraints solved: pins at their moved offsets, each with the whys
    that moved it — _pin_warnings reads them off the final solve's)."""
    cons = list(cons)
    rounds, limit = 0, PIN_ROUNDS * (1 + sum(1 for c in cons if c.pin == "lo"))
    while True:
        dist, pred, cycle = _bellman_ford(cons)
        if cycle is None:
            return dist, pred, cons
        soft = [c for c in cycle if c.soft]
        if not soft:
            pins = [c for c in cycle if c.pin]
            if pins and rounds < limit:
                rounds += 1
                cons = _move_pin(m, cons, cycle, pins)
                continue
            excess = sum(c.d for c in cycle)
            probs = [f"{_loc(m.spec, c.owner)}: contradictory {axis} constraint {c.why!r} "
                     f"({c.a} → {c.b} ≥ {fmt_num(c.d)}) in a cycle that needs {fmt_num(excess)} px more than 0"
                     for c in cycle if c.owner != "canvas" or c.why != "coordinate ≥ 0"]
            raise SolveError(probs or [f"canvas: contradictory {axis} constraints"])
        # a twin's spacing goes first and alone; the caller's soft requirements stay while
        # dropping those breaks the cycle
        soft = [c for c in soft if c.why.startswith(TWIN_WHY)] or soft
        drop = {id(c) for c in soft}
        for c in soft:
            m.warnings.append(f"{_loc(m.spec, c.owner)}: dropped soft requirement {c.why!r} ({axis}) "
                              f"to resolve contradictory constraints")
        cons = [c for c in cons if id(c) not in drop]


def _move_pin(m: _Model, cons: List[Requirement], cycle, pins) -> List[Requirement]:
    """An `xy` center the rest of the drawing cannot meet (a positive cycle through one half
    of its tie: inside its boxes' pad or below its label room, past the canvas margin, …):
    move its offset by the cycle's excess, rounded up to a whole px, the way the cycle
    needs — the nearest center that cycle allows. The "lo" half (center − ref ≥ offset)
    in the cycle asks a smaller coordinate (left / up), the "hi" half a larger one. Of
    several pins in one cycle the first node in spec order moves. Both halves of the tie
    move, so it stays an equality; both record the cycle's other whys (moved_by)."""
    order = {f"node:{nid}": i for i, nid in enumerate(m.spec.nodes)}
    c = min(pins, key=lambda r: (order.get(r.owner, len(order)), r.pin))
    excess = _up(sum(r.d for r in cycle))
    delta = -excess if c.pin == "lo" else excess
    var = c.b if c.pin == "lo" else c.a
    whys = tuple(dict.fromkeys(r.why for r in cycle if not r.pin and r.why != "coordinate ≥ 0"))
    out = []
    for r in cons:
        if r.pin and r.owner == c.owner and (r.b if r.pin == "lo" else r.a) == var:
            r = replace(r, d=r.d + delta if r.pin == "lo" else r.d - delta, moved=r.moved + delta,
                        moved_by=tuple(dict.fromkeys(r.moved_by + whys)))
        out.append(r)
    return out


def _pin_moves(cons: Sequence[Requirement]) -> Dict[Tuple[str, str], float]:
    """The xy pins a solve moved and by how much (to tell whether two solves moved the
    same pins the same way)."""
    return {(r.owner, r.pin): r.moved for r in cons if r.pin and r.moved}


def _xy_text(src: str, c, shift: float, spec: Spec) -> str:
    """An xy component as the spec would write it after a shift: a number moved, or the
    expression with its ±n replaced by the moved offset (`sn.y1-40` up 14 → `sn.y1-54`,
    `cloud.x0+0` right 40 → `cloud.x0+40`). A trailing `-n` that is part of a track's name
    (`col.a-1` with a track a-1, as the loader reads it) stays: the offset goes after it."""
    if not isinstance(c, Expr):
        return fmt_num(c + shift)
    off = c.offset + shift
    base = src.strip()
    m = re.match(r"^(.*?)\s*[+-]\s*\d+(?:\.\d+)?$", base)
    whole = re.match(r"^(?:col|row)\.([A-Za-z0-9_-]+)$", base)
    if m and not (whole and any(t.id == whole.group(1) for t in spec.cols + spec.rows)):
        base = m.group(1)
    return base + (f"{'+' if off > 0 else '-'}{fmt_num(abs(off))}" if off else "")


def _pin_warnings(m: _Model, axis: str, cons: Sequence[Requirement], val: Dict[str, float]) -> List[str]:
    """What _move_pin did, read off the final solve: per spec node (its template instances
    together) from where to where, why, and what to write instead. With instances moved
    unalike, the farthest move is the one to write (it holds for every instance). A node
    that then landed on a sibling (m.avoid) says that writing the value alone leaves that
    sibling on it."""
    i = 0 if axis == "x" else 1
    whys: Dict[str, Tuple[str, ...]] = {}
    for r in cons:
        if r.pin and r.moved_by:
            nid = r.owner[5:]
            whys[nid] = tuple(dict.fromkeys(whys.get(nid, ()) + r.moved_by))
    groups: Dict[str, list] = {}
    out = []
    for nid, n in m.spec.nodes.items():
        if n.xy is None:
            if (axis, nid) in m.relaxed:
                sh = _xy_shift(m, nid, axis, val)
                if abs(sh) > 0.5:
                    key = "dx" if axis == "x" else "dy"
                    old = n.dx if axis == "x" else n.dy
                    way = ("right" if sh > 0 else "left") if axis == "x" else ("down" if sh > 0 else "up")
                    why = "; ".join(whys.get(nid, ())) or "declared container separation"
                    out.append(f"{_loc(m.spec, f'node:{nid}')}: grid {key} {fmt_num(old)} moved "
                               f"{fmt_num(abs(sh))} px {way} to {fmt_num(old + sh)} to keep {why}; "
                               f"write {key}: {fmt_num(old + sh)} to place it without this warning")
            continue
        sh = _xy_shift(m, nid, axis, val)
        if abs(sh) > 0.5:
            groups.setdefault(n.src, []).append((nid, _up(sh) if sh > 0 else -_up(-sh)))
    for src_loc, moves in groups.items():
        n = m.spec.nodes[moves[0][0]]
        c = n.xy[i]
        src = n.xy_src[i] if n.xy_src else m.xy_ref(c, axis)[1]
        far = max(moves, key=lambda t: abs(t[1]))[1]
        way = ("right" if far > 0 else "left") if axis == "x" else ("down" if far > 0 else "up")
        new = _xy_text(src, c, far, m.spec)
        ids = ", ".join(nid for nid, _ in moves)
        if len({sh for _, sh in moves}) == 1:
            what = f"moved {fmt_num(abs(far))} px {way} to {new}"
        else:
            what = f"moved {way}: " + ", ".join(f"{nid} {fmt_num(abs(sh))} px to {_xy_text(src, c, sh, m.spec)}"
                                                 for nid, sh in moves) + ","
        why = "; ".join(dict.fromkeys(w for nid, _ in moves for w in whys.get(nid, ()))) or "the constraints it meets"
        keys = {f"node:{nid}" for nid, _ in moves}
        others = list(dict.fromkeys(split_eid(k)[1] for a in m.avoid if a[3] in keys
                                    for k in (a[1], a[2]) if k not in keys))
        tail = (f"; writing {new} in xy[{i}] places it there, but then nothing keeps {', '.join(others)} off it: "
                f"move {'them' if len(others) > 1 else 'that'} too" if others else
                f"; write {new} in xy[{i}] (or make room there) to place it without this warning")
        out.append(f"{src_loc} {ids}: xy {axis} {src} {what} to keep {why}{tail}")
    return out


def _hug(m: _Model, axis: str, cons: List[Requirement], val: Dict[str, float]):
    """Pull every group's left (top) edge toward its content, inner groups first, as far as
    every constraint allows. Edges tied equal (aligned siblings, template instances) move
    together."""
    parent: Dict[str, str] = {}

    def find(v):
        while parent.get(v, v) != v:
            v = parent[v]
        return v

    for a, b in m.ties[axis]:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    e = "L" if axis == "x" else "T"
    order = [f"group:{g.id}.{e}" for g in reversed(list(m.spec.groups.values()))]
    sets: Dict[str, List[str]] = {}
    for v in order:
        sets.setdefault(find(v), []).append(v)
    done = set()
    for v in order:
        root = find(v)
        if root in done or v not in val:
            continue
        done.add(root)
        mem = set(sets[root])
        slack = _shift_slack(cons, val, mem)
        if slack != float("inf") and slack > _EPS:
            for u in mem:
                val[u] += slack


def _shift_slack(cons, val, members: set) -> float:
    s = float("inf")
    for c in cons:
        if c.a in members and c.b not in members:
            s = min(s, val[c.b] - val[c.a] - c.d)
    return s


def _explain(m: _Model, axis: str, val, pred) -> List[str]:
    pre = "col" if axis == "x" else "row"
    tracks = m.spec.cols if axis == "x" else m.spec.rows
    out = []
    for t in tracks:
        v = f"{pre}:{t.id}"
        chain, u, seen = [], v, set()
        while u in pred and u not in seen:
            seen.add(u)
            c = pred[u]
            if c.why == "coordinate ≥ 0":
                u = c.a
                break
            chain.append(c)
            u = c.a
            if u == "origin" or u.startswith(pre + ":"):
                break
        parts = " + ".join(f"{fmt_num(c.d)} ({c.why}, {c.owner})" for c in reversed(chain)) or "0"
        out.append(f"{axis} {pre} {t.id} = {fmt_num(val.get(v, 0))}: {u} {fmt_num(val.get(u, 0))} + {parts}")
    return out


def _explain_stacks(m: _Model, val, pred, final) -> List[str]:
    """Flow columns: per node, the chain that set its y (back to the node above it, a row
    or the origin), and the align shift."""
    out = []
    for (parent, col), ids in m.stacks.items():
        for k, nid in enumerate(ids):
            v = f"node:{nid}"
            stop = {"origin", f"node:{ids[k - 1]}"} if k else {"origin"}
            chain, u, seen = [], v, set()
            while u in pred and u not in seen:
                seen.add(u)
                c = pred[u]
                if c.why == "coordinate ≥ 0":
                    u = c.a
                    break
                chain.append(c)
                u = c.a
                if u in stop or u.startswith("row:"):
                    break
            parts = " + ".join(f"{fmt_num(c.d)} ({c.why}, {c.owner})" for c in reversed(chain)) or "0"
            tail = "".join(f"; then {'centered in' if a == 'center' else 'at the bottom of'} {w} +{fmt_num(sh)}"
                           for a, w, sh in m.stack_shift.get(nid, ()))
            out.append(f"y flow {col} {nid} = {fmt_num(final.get(v, 0))}: {u} {fmt_num(val.get(u, 0))} + {parts}{tail}")
    return out


# =======================================================================================
# solve

SPAN_TOL = 0.01         # px: a colspan's span has settled when its solve gives it back this close
SPAN_ROUNDS = 12        # x solves spent looking for the spans (then the closest, with a warning)
PIN_ROUNDS = 64         # xy pins moved per axis solve before a cycle still left is reported as a contradiction
AVOID_ROUNDS = 6        # solves spent keeping moved xy nodes off the siblings they land on
TWIN_ROUNDS = 6         # solves per axis spent evening out twins (their measures at the class's largest)
TWIN_WHY = "twins alike"
TWIN_NAMED = ("vpc", "account", "region", "onprem", "cloud")   # a twin root's own title may differ


def _solve_x(m: _Model, extra: Sequence[Requirement]):
    """The x solve. A colspan node's center (X_b1 + X_b2) / 2 is no single variable, so its
    footprint and requirements are reserved from X_b1 + s/2 (as b) and X_b2 − s/2 (as a)
    for an assumed span s (s = 0: from both end tracks). g(s), the span a solve with that
    reservation gives b2 − b1, grows with s at a slope below 1 (only half the reservation
    moves), so the span wanted is the fixed point g(s) = s: found per colspan by secant
    steps on h(s) = g(s) − s, by regula falsi (Illinois) once a step overshoots (h < 0, as
    when the reservation stops pulling b1 left), to SPAN_TOL, at most SPAN_ROUNDS solves.
    The answer is solved once more with b2 − b1 ≥ s held, so the reservation is exact or
    conservative whatever s was (DESIGN 4.3 #7). Every round rebuilds the x model whole
    (constraints, ties, flow rows, warnings), so _hug and flow-row centering see the
    answer's own."""
    spec = m.spec
    spans = [nid for nid, n in spec.nodes.items() if n.col2 and n.xy is None]
    w0 = len(m.warnings)

    def run(span, hold):
        m.span, m.hold_span = dict(span), hold
        m.cons["x"], m.ties["x"], m.flow_rows = [], [], []
        m.aligned = {k for k in m.aligned if k[0] != "x"}
        del m.warnings[w0:]
        m.build("x")
        mapped = [_map_req(m, r) for r in extra if r.axis == "x"]
        out = _solve_axis(m, "x", m.cons["x"] + mapped)
        got = {nid: out[0][f"col:{spec.nodes[nid].col2}"] - out[0][f"col:{spec.nodes[nid].col}"] for nid in spans}
        return out, got

    out, g = run({}, True)
    if not spans:
        return out
    s = {i: 0.0 for i in spans}
    lo: Dict[str, Tuple[float, float]] = {}        # last s with h > 0 (span too small), its h
    hi: Dict[str, Tuple[float, float]] = {}        # last s with h < 0 (overshot), its h
    prev: Dict[str, Tuple[float, float]] = {}      # the step before (secant)
    side: Dict[str, int] = {}                      # Illinois: which end stayed twice
    for _ in range(SPAN_ROUNDS):
        h = {i: g[i] - s[i] for i in spans}
        if all(abs(h[i]) <= SPAN_TOL for i in spans):
            break
        nxt = {}
        for i in spans:
            if abs(h[i]) <= SPAN_TOL:
                nxt[i] = s[i]
                continue
            if h[i] > 0:
                if i in lo:
                    prev[i] = lo[i]
                lo[i] = (s[i], h[i])
                if side.get(i) == 1 and i in hi:
                    hi[i] = (hi[i][0], hi[i][1] / 2)
                side[i] = 1
            else:
                hi[i] = (s[i], h[i])
                if side.get(i) == -1:
                    lo[i] = (lo[i][0], lo[i][1] / 2)
                side[i] = -1
            if i in hi:                            # bracketed: regula falsi
                (a, ha), (b, hb) = lo[i], hi[i]
                nxt[i] = a + ha * (b - a) / (ha - hb)
            elif i in prev and lo[i][0] != prev[i][0]:  # secant through the last two under-steps
                (a, ha), (b, hb) = prev[i], lo[i]
                slope = (hb - ha) / (b - a)        # h' = g' − 1, in [−1, 0) while g' ∈ [0, 1)
                nxt[i] = b - hb / slope if slope < -1e-9 else b + hb
            else:
                nxt[i] = s[i] + h[i]               # plain step: s ← g(s)
        s = nxt
        out, g = run(s, False)                     # measure g(s): the span not held
    unsettled = [f"{spec.nodes[i].src} {i}: its colspan span did not settle in {SPAN_ROUNDS} solves "
                 f"(assumed {fmt_num(s[i])}, solved {fmt_num(g[i])}); its room is reserved from the center "
                 f"of a span ≥ {fmt_num(s[i])}" for i in spans if abs(g[i] - s[i]) > SPAN_TOL]
    out, _ = run(s, True)
    m.warnings += unsettled
    return out


def solve(spec: Spec, reqs: Sequence[Requirement], note_block=None, diag_x: bool = False) -> Geometry:
    """diag_x: keep every diagonal pair build("y") leaves open apart on x, without weighing
    x against y (layout.build's retry for a slide the weighing leaves too small).

    An `xy` node the solve had to move (_move_pin), or one whose xy follows it, may land on
    a sibling it was never kept apart from (xy nodes are no grid siblings): such pairs are
    kept apart like grid siblings and the drawing solved again, until none is left
    (_xy_clashes, at most AVOID_ROUNDS rounds). A round's pairs that make the solve
    contradictory are tried in the other order, then on the other axis in either order
    (_avoid_variants), the first that solves kept; none: the pairs stay apart undone, with
    a warning."""
    avoid: List[Tuple[str, str, str, str]] = []
    res = _solve_once(spec, reqs, note_block, diag_x, avoid)
    res, avoid = _repair_xy(spec, reqs, note_block, diag_x, avoid, res)
    return _separate_containers(spec, reqs, note_block, diag_x, avoid, res)[1]


def _repair_xy(spec, reqs, note_block, diag_x, avoid, res, relaxed=()):
    """Repeat collision avoidance after any solve that may have moved a center."""
    stuck: List[tuple] = []
    why = "keeping them apart contradicts the drawing in every order and axis"
    for _ in range(AVOID_ROUNDS):
        clashes = _xy_clashes(*res)
        if not clashes:
            break
        for cand in _avoid_variants(clashes):
            try:
                res2 = _solve_once(spec, reqs, note_block, diag_x, avoid + cand, relaxed)
            except SolveError:
                continue
            avoid, res = avoid + cand, res2
            break
        else:
            stuck = clashes
            break
    else:
        stuck = _xy_clashes(*res)
        why = f"still there after {AVOID_ROUNDS} rounds"
    geom = res[1]
    geom.warnings += [_avoid_warning(spec, a) for a in avoid if a[3].startswith("node:")]
    geom.warnings += [f"{_loc(spec, c[0])}: its moved xy lands on {split_eid(c[1])[1]}, {why}; "
                      f"give it an xy clear of {split_eid(c[1])[1]}" for c in stuck]
    return res, avoid


def _container_clashes(m: _Model, geom: Geometry):
    """Intersecting sibling boxes / node footprints, excluding overlays and on: masks."""
    for parent in [None] + [g.id for g in m.tree]:
        items = [m.item_group(g) for g in m.child_groups[parent]]
        items += [m.item_node(n) for n in m.child_nodes[parent]]
        for i, a in enumerate(items):
            ab = geom.groups[a.gid].rect if a.gid else geom.nodes[a.nid].footprint()
            for b in items[i + 1:]:
                if not (a.gid or b.gid):
                    continue
                bb = geom.groups[b.gid].rect if b.gid else geom.nodes[b.nid].footprint()
                if (min(ab.x1, bb.x1) - max(ab.x0, bb.x0) > 0.5
                        and min(ab.y1, bb.y1) - max(ab.y0, bb.y0) > 0.5):
                    yield parent, a, b, ab, bb


def _separate_containers(spec, reqs, note_block, diag_x, avoid, res):
    """Add the missing disjunction only for actual intersections, preserving clean drafts.

    Try each axis and order. If shared tracks conflict, promote the sibling's grid
    centers to movable pins: containment stays hard, placement moves minimally and warns.
    """
    if next(_container_clashes(res[0], res[1]), None) is None:
        return res
    m = res[0]
    # Each retained hard separation removes one pair permanently. Bound by the
    # number of eligible sibling pairs, rather than the xy repair's six rounds.
    limit = sum(len(gs) * (len(gs) - 1) // 2 + len(gs) * len(m.child_nodes[parent])
                for parent, gs in m.child_groups.items())
    warnings = list(res[1].warnings)
    relaxed = set(m.relaxed)
    for _ in range(limit):
        clash = next(_container_clashes(res[0], res[1]), None)
        if clash is None:
            res[1].warnings = list(dict.fromkeys(warnings + res[1].warnings))
            return res
        parent, a, b, ab, bb = clash
        owner = f"group:{parent}" if parent else "canvas"
        candidates = []
        failures = []
        for axis in ("x", "y"):
            ac = (ab.x0 + ab.x1) if axis == "x" else (ab.y0 + ab.y1)
            bc = (bb.x0 + bb.x1) if axis == "x" else (bb.y0 + bb.y1)
            first, second = (a, b) if ac <= bc else (b, a)
            for lo, hi in ((first, second), (second, first)):
                pair = (axis, lo.key, hi.key, owner)
                try:
                    trial = _solve_once(spec, reqs, note_block, diag_x, avoid + [pair], relaxed)
                except SolveError as e:
                    failures.extend(e.problems[:2])
                    continue
                # Account siblings read side by side whenever x is feasible.
                vertical = int(axis == "y" and a.gtype == b.gtype == "account")
                candidates.append((vertical, trial[1].canvas_w * trial[1].canvas_h, pair, trial, relaxed))
        if not candidates:
            # A grid track is a preferred position, like xy, rather than a reason to
            # draw an incorrect hierarchy. Relax only one conflicting sibling branch.
            for axis in ("x", "y"):
                ac = ab.x0 + ab.x1 if axis == "x" else ab.y0 + ab.y1
                bc = bb.x0 + bb.x1 if axis == "x" else bb.y0 + bb.y1
                first, second = (a, b) if ac <= bc else (b, a)
                for lo, hi in ((first, second), (second, first)):
                    pair = (axis, lo.key, hi.key, owner)
                    for moving in (hi, lo):
                        ids = [nid for nid, n in spec.nodes.items()
                               if (nid == moving.nid or (moving.gid and m._inside(nid, moving.gid)))
                               and n.xy is None
                               and not (axis == "x" and nid in m.flow)
                               and not (axis == "y" and nid in m.flowc)]
                        flex = relaxed | {(axis, nid) for nid in ids}
                        if flex == relaxed:
                            continue
                        try:
                            trial = _solve_once(spec, reqs, note_block, diag_x, avoid + [pair], flex)
                        except SolveError:
                            continue
                        shift = sum(abs(_xy_shift(trial[0], nid, axis, trial[2 if axis == "x" else 3]))
                                    for nid in ids)
                        vertical = int(axis == "y" and a.gtype == b.gtype == "account")
                        candidates.append((vertical, shift, pair, trial, flex))
        if not candidates:
            def tracks(it):
                obj = spec.groups[it.gid] if it.gid else spec.nodes[it.nid]
                cols = obj.cols if it.gid else (obj.col, obj.col2 or obj.col)
                rows = obj.rows if it.gid else (obj.row, obj.row)
                return f"{_loc(spec, it.key)} (cols={cols}, rows={rows})"
            raise SolveError([
                f"{tracks(a)} intersects sibling {tracks(b)} in {parent or 'canvas'}: "
                "declared containment cannot be drawn on these tracks; separation in either "
                "axis/order contradicts containment or placement constraints. Use separate "
                "columns/rows (or adjust xy/dx/dy/span) for the sibling containers",
                *list(dict.fromkeys(failures))[:4],
            ])
        _, _, pair, res, relaxed = min(candidates, key=lambda c: (c[0], c[1], c[2]))
        avoid = avoid + [pair]
        res, avoid = _repair_xy(spec, reqs, note_block, diag_x, avoid, res, relaxed)
        m = res[0]
        warnings += res[1].warnings
    if next(_container_clashes(res[0], res[1]), None) is not None:
        raise SolveError([f"declared containment still has intersecting siblings after {limit} "
                          "separation rounds; use separate columns/rows for the sibling containers"])
    res[1].warnings = list(dict.fromkeys(warnings + res[1].warnings))
    return res


def _avoid_variants(clashes) -> List[List[Tuple[str, str, str, str]]]:
    """A round's clashes as avoid pairs, in the order solve() tries them: each pair on its
    axis in its order; every order flipped; every pair on the other axis in that axis's
    order; that flipped."""
    def pairs(other, flip):
        out = []
        for node, key, axis, first, first_other in clashes:
            ax, f = (("y" if axis == "x" else "x"), first_other) if other else (axis, first)
            f = f != flip
            out.append((ax, node, key, node) if f else (ax, key, node, node))
        return out
    return [pairs(False, False), pairs(False, True), pairs(True, False), pairs(True, True)]


def _solve_once(spec: Spec, reqs: Sequence[Requirement], note_block, diag_x: bool, avoid, relaxed=()):
    m = _Model(spec, avoid, relaxed)
    extra = list(reqs) + (list(note_block.requirements) if note_block is not None else [])
    mapped = {"x": [], "y": []}
    probs = []
    for r in extra:
        if r.axis not in mapped:
            probs.append(f"{_loc(spec, r.owner)}: requirement {r.why!r} has axis {r.axis!r}")
            continue
        try:
            mapped[r.axis].append(_map_req(m, r))
        except KeyError as e:
            probs.append(f"{_loc(spec, r.owner)}: requirement {r.why!r} names unknown variable {e.args[0]!r} "
                         f"on the {r.axis} axis")
    if probs:
        raise SolveError(probs)

    # ---- x, then the diagonal pairs ---------------------------------------------------
    xbf, xpred, xcons, xv, nodes_x = _x_twins(m, extra)
    m.xv, m.nodes_x, m.diag_open = xv, nodes_x, []
    m.build("y")
    m.y_after_x(xv, nodes_x)
    open_keys = {frozenset((first.key, second.key)) for first, second, _ in m.diag_open}
    pick = open_keys if diag_x else _diagonals(m, m.cons["y"] + mapped["y"], extra)
    if pick:
        # a pair x keeps apart for less than y would: solve again with it on x (the rows
        # it no longer pushes stay where the rest puts them); m2's build("y") puts every
        # other pair its x does not keep apart on y (m2.diag_y), the new ones included
        m2 = _Model(spec, avoid, relaxed)
        m2.diag_x = pick
        m = m2
        xbf, xpred, xcons, xv, nodes_x = _x_twins(m, extra)
        m.xv, m.nodes_x = xv, nodes_x
        m.build("y")
        m.y_after_x(xv, nodes_x)
    else:
        for first, second, owner in m.diag_open:
            m._sep("y", first, second, owner)
        m.diag_y |= open_keys
        m.diag_open = None

    # ---- y ---------------------------------------------------------------------------
    ycons_in = m.cons["y"] + mapped["y"]
    twins: Dict[tuple, Requirement] = {}
    w0 = len(m.warnings)
    best = None
    for _ in range(max(6, TWIN_ROUNDS)):
        del m.warnings[w0:]
        ybf, ypred, ycons = _solve_axis(m, "y", ycons_in + list(twins.values()))
        yv = dict(ybf)
        _hug(m, "y", ycons, yv)          # insets are compared on the hugged boxes
        spread = m.twins_spread("y", yv)
        more = m.even_insets(yv)
        if best is not None and spread > best[0] + 0.5 and not more:
            break                        # twins pushing each other on: keep the best round
        if best is None or spread <= best[0] + 0.5:
            best = (spread, ybf, ypred, ycons, yv, m.warnings[w0:])
        grew = m.twins_even("y", yv, twins)
        if not more and not grew:
            break
        ycons_in = [c for c in ycons if not c.why.startswith(TWIN_WHY)] + more
    _, ybf, ypred, ycons, yv, w = best
    m.warnings[w0:] = w
    m.align_stacks(ycons, yv)
    m.warnings += m.twins_unlike("x", xv) + m.twins_unlike("y", yv) + m.overlay_header_warnings()
    m.warnings += _pin_warnings(m, "x", xcons, xv) + _pin_warnings(m, "y", ycons, yv)

    geom = _geometry(m, xv, yv, note_block)
    geom.explain = _explain(m, "x", xbf, xpred) + _explain(m, "y", ybf, ypred) + _explain_stacks(m, ybf, ypred, yv)
    geom.warnings = list(m.warnings)
    geom.diag_y = len(m.diag_y)
    return m, geom, xv, yv


def _xy_shift(m: _Model, nid: str, axis: str, val: Dict[str, float]) -> float:
    """How far the solve moved an xy node's center on one axis from what its xy asks."""
    n = m.spec.nodes[nid]
    if n.xy is None:
        if (axis, nid) not in m.relaxed:
            return 0.0
        v, o = m.grid_ref(nid, axis, "lo")
    else:
        (v, o), _ = m.xy_ref(n.xy[0 if axis == "x" else 1], axis)
    return val[f"node:{nid}"] - (val.get(v, 0.0) + o)


def _xy_clashes(m: _Model, geom: Geometry, xv, yv) -> List[Tuple[str, str, str, bool, bool]]:
    """The siblings a moved xy node (or one whose xy follows a moved one, any number of
    steps away) lands on: its footprint and theirs (a box's rect, a node's footprint)
    closer than the gap the grid keeps between them on both axes. Returns (node key,
    sibling key, axis, node first, node first on the other axis) per pair: the axis is the
    one the node moved along (the larger move); the order is the one their centers have
    on it — a box counted with its border nodes (an IGW on the VPC's right border sits
    right of it), and a border node with its box, so the node takes one side of both — a
    tie putting the node on the side it came from (moved right: it stays left)."""
    out = []
    have = {(a[1], a[2]) for a in m.avoid} | {(a[2], a[1]) for a in m.avoid}
    spec = m.spec
    sh = {nid: {ax: _xy_shift(m, nid, ax, xv if ax == "x" else yv) for ax in ("x", "y")}
          for nid, n in spec.nodes.items() if n.xy is not None or any((ax, nid) in m.relaxed for ax in ("x", "y"))}
    # how far each xy center moved: its own pin's move plus, through each reference to
    # another xy node (`t: [q.cx, …]`), what that one moved on the referenced axis
    eff = {nid: dict(v) for nid, v in sh.items()}
    for _ in range(len(eff) + 1):
        grew = False
        for nid, n in spec.nodes.items():
            if nid not in eff or n.xy is None:
                continue
            for i, c in enumerate(n.xy):
                ax = "x" if i == 0 else "y"
                if isinstance(c, Expr) and c.kind == "node" and c.ref in eff:
                    want = sh[nid][ax] + eff[c.ref]["x" if "x" in c.attr else "y"]
                    if abs(want - eff[nid][ax]) > _EPS:
                        eff[nid][ax] = want
                        grew = True
        if not grew:
            break
    moved: Dict[str, Tuple[str, float]] = {}       # node → (axis, shift)
    for nid, e in eff.items():
        if max(abs(v) for v in e.values()) > 0.5:
            axis = "x" if abs(e["x"]) > abs(e["y"]) else "y"
            moved[nid] = (axis, e[axis])

    def unit(gid) -> Box:
        boxes = [geom.groups[gid].rect] + [geom.nodes[b].footprint() for b in m.border_of.get(gid, [])]
        return union_all(boxes)

    for nid in [k for k in spec.nodes if k in moved]:
        n = spec.nodes[nid]
        axis, shift = moved[nid]
        me = m.item_node(nid)
        mine = geom.nodes[nid].footprint()
        parent = n.parent
        # its siblings as _siblings sees them (a border node: also its VPC's children and
        # other border nodes, not the VPC itself)
        sibs = [f"group:{g}" for g in m.child_groups[parent] if g != n.on]
        sibs += [f"node:{o}" for o in m.child_nodes[parent] if o != nid]
        sibs += [f"node:{b}" for g in m.child_groups[parent] for b in m.border_of.get(g, []) if b != nid]
        if parent is not None:
            sibs += [f"node:{b}" for b in m.border_of.get(parent, []) if b != nid]
        if n.on:
            sibs += [f"group:{g}" for g in m.child_groups[n.on]] + [f"node:{o}" for o in m.child_nodes[n.on]]
        sibs = list(dict.fromkeys(sibs))
        for key in sibs:
            if (me.key, key) in have:
                continue
            kind, ident, _ = split_eid(key)
            box = geom.groups[ident].rect if kind == "group" else geom.nodes[ident].footprint()
            it = m.item(key)
            near = []
            for ax in ("x", "y"):
                a0, a1, b0, b1 = (mine.x0, mine.x1, box.x0, box.x1) if ax == "x" else (mine.y0, mine.y1, box.y0, box.y1)
                g = min(m._gap(ax, me, it)[0], m._gap(ax, it, me)[0])
                near.append(b0 - a1 < g - _EPS and a0 - b1 < g - _EPS)
            if not all(near):
                continue
            # the box it orders against: a box with its border nodes, a border node of a
            # sibling box with that box (not the node's own VPC)
            if kind == "group":
                obox = unit(ident)
            elif spec.nodes[ident].on and spec.nodes[ident].on != n.on and f"group:{spec.nodes[ident].on}" in sibs:
                obox = unit(spec.nodes[ident].on)
            else:
                obox = box

            def node_first(ax, sv):
                c0 = (mine.x0 + mine.x1) / 2 if ax == "x" else (mine.y0 + mine.y1) / 2
                c1 = (obox.x0 + obox.x1) / 2 if ax == "x" else (obox.y0 + obox.y1) / 2
                return c0 < c1 - _EPS or (abs(c0 - c1) <= _EPS and sv >= 0)

            other = "y" if axis == "x" else "x"
            out.append((me.key, key, axis, node_first(axis, shift), node_first(other, eff[nid][other])))
            have |= {(me.key, key), (key, me.key)}
    return out


def _avoid_warning(spec: Spec, a: Tuple[str, str, str, str]) -> str:
    axis, k1, k2, owner = a
    other = k2 if k1 == owner else k1
    kind, ident, _ = split_eid(other)
    way = {("x", True): "right of", ("x", False): "left of", ("y", True): "below", ("y", False): "above"}[
        (axis, k1 == owner)]
    what = f"box {ident}" if kind == "group" else f"node {ident}"
    return (f"{_loc(spec, owner)}: its moved xy landed on {what}, so {what} goes {way} it; give the node an xy "
            f"clear of {ident} to place them yourself")


def _x_twins(m: _Model, extra: Sequence[Requirement]):
    """_x_stage, again with the twins' x measures raised to their class's largest until
    they hold (at most TWIN_ROUNDS solves; the round leaving them least unlike wins)."""
    twins: Dict[tuple, Requirement] = {}
    w0 = len(m.warnings)
    best = None
    for _ in range(TWIN_ROUNDS):
        del m.warnings[w0:]
        out = _x_stage(m, list(extra) + list(twins.values()))
        spread = m.twins_spread("x", out[3])
        if best is not None and spread > best[0] + 0.5:
            break                        # twins pushing each other on: keep the best round
        best = (spread, out, list(twins.values()), m.warnings[w0:])
        if not m.twins_even("x", out[3], twins):
            break
    if best[1] is not out:
        # the model's x state (flow rows, ties, spans) is the last solve's: solve the best again
        del m.warnings[w0:]
        out = _x_stage(m, list(extra) + best[2])
    return out


def _x_stage(m: _Model, extra: Sequence[Requirement]):
    """Solve x, hug it, center the flow rows: (bellman-ford x, its pred, its constraints,
    the final x, node centers)."""
    spec = m.spec
    xv, xpred, xcons = _solve_x(m, extra)
    xbf, xv = xv, dict(xv)
    _hug(m, "x", xcons, xv)
    for parent, ids in m.flow_rows:
        if parent is None:
            continue
        mem = {f"node:{i}" for i in ids}
        want = (xv[f"group:{parent}.L"] + xv[f"group:{parent}.R"]) / 2 - (xv[f"node:{ids[0]}"] + xv[f"node:{ids[-1]}"]) / 2
        shift = math.floor(min(want, _shift_slack(xcons, xv, mem)) + 1e-9)
        if shift > 0:
            for v in mem:
                xv[v] += shift
    nodes_x = {nid: _node_center(m, nid, "x", xv) for nid in spec.nodes}
    return xbf, xpred, xcons, xv, nodes_x


def _extent(val: Dict[str, float]) -> float:
    return max(val.values(), default=0.0)


def _stacked_between(m: _Model) -> List[Tuple[_Item, _Item, str]]:
    """The open pairs of a node with the diagonal sibling boxes on one side of its columns
    (all left or all right of them) that draw lines past it (_Model.lines_past), when one
    such box lies above its rows and one below: apart on y the node would sit stacked in
    their column, in the gap between them, outside the bracket their lines draw — a Spoke
    RT between VPC A and VPC B, on the far side of their lines to the TGW, instead of
    beside them. Whether its center, footprint or label falls inside the boxes' x range
    does not matter, nor whether one box is already beside it. They go on x unweighed
    (which can widen the drawing). A node with such a box on one side only (a route table
    above a lone VPC), or one the boxes' lines end at (an IGW or GWLB on its VPC's AZ gap
    row: the AZs draw no line past it), is weighed like any pair."""
    def split(first, second):
        node, box = (first, second) if first.nid else (second, first)
        return node, box, box.xr[1] < node.xr[0]        # side: the box's columns left of the node's

    sides: Dict[Tuple[str, bool], set] = defaultdict(set)
    for first, second in m.diag_boxes:
        node, box, side = split(first, second)
        if m.lines_past(box.gid, node.nid, side):
            sides[(node.key, side)].add("above" if first is box else "below")
    out = []
    for p in m.diag_open:
        if not (p[0].nid or p[1].nid):
            continue
        node, box, side = split(p[0], p[1])
        if len(sides[(node.key, side)]) == 2 and m.lines_past(box.gid, node.nid, side):
            out.append(p)
    return out


def _diagonals(m: _Model, ycons: List[Requirement], extra: Sequence[Requirement]) -> set:
    """The diagonal sibling pairs build("y") left open (m.diag_open: the track gaps say y,
    the solved x does not keep them apart): a pair goes on x when y would push the drawing
    a sibling gap or more and x grows it no more than that + a sibling gap — its columns
    already order it, so it needs no rows between them, and a node beside a box stops
    pushing the box's rows (and every box sharing them) down; a pair y keeps apart for
    less (an IGW on the AZ gap row) stays on y. A pair's x cost is how much farther right
    the x solve reaches with it kept apart on x; its y cost how much farther down the y
    solve reaches with it kept apart on y, with the pairs already put on y held: put every
    pair that stays on y there, weigh again until none moves; the rest go on x (two nodes
    pushing one box both move; one that x cannot move keeps the other on y, where it then
    costs nothing). The pairs of a node y would stack between two boxes of one column,
    outside the lines they draw past it (_stacked_between), go on x without weighing.
    Returns the x pairs' keys."""
    if not m.diag_open:
        return set()
    stacked = _stacked_between(m)
    open_ = [p for p in m.diag_open if p not in stacked]
    w0 = len(m.warnings)
    base = _solve_axis(m, "x", m.cons["x"] + [_map_req(m, r) for r in extra if r.axis == "x"])
    x0, pins0 = _extent(base[0]), _pin_moves(base[2])
    xcost = {}
    for first, second, _ in open_:
        mp = _Model(m.spec, m.avoid)
        mp.diag_x = {frozenset((first.key, second.key))}
        try:
            out = _solve_x(mp, extra)
            # a pair x can keep apart only by moving an xy center further than the solve
            # without it does costs what a contradiction does: it stays on y
            xcost[(first.key, second.key)] = (_extent(out[0]) - x0 if _pin_moves(out[2]) == pins0
                                              else float("inf"))
        except SolveError:
            xcost[(first.key, second.key)] = float("inf")

    def ysolve(pairs) -> float:
        n0 = len(m.cons["y"])
        for first, second, owner in pairs:
            m._sep("y", first, second, owner)
        held = m.cons["y"][n0:]
        del m.cons["y"][n0:]
        return _extent(_solve_axis(m, "y", list(ycons) + held)[0])

    on_y: List[Tuple[_Item, _Item, str]] = []
    g = m.mc.sibling_gap
    while open_:
        y0 = ysolve(on_y)
        moved = []
        for p in open_:
            dy = ysolve(on_y + [p]) - y0
            if dy < g - _EPS or xcost[(p[0].key, p[1].key)] > dy + g + _EPS:
                moved.append(p)
        if not moved:
            break
        on_y += moved
        open_ = [p for p in open_ if p not in moved]
    del m.warnings[w0:]              # the solves proper report their own
    return {frozenset((first.key, second.key)) for first, second, _ in open_ + stacked}


def _node_center(m: _Model, nid: str, axis: str, val) -> float:
    n = m.spec.nodes[nid]
    if n.xy is not None or (axis, nid) in m.relaxed:
        return val[f"node:{nid}"]
    if axis == "x":
        if nid in m.flow:
            return val[f"node:{nid}"]
        if n.col2:
            return (val[f"col:{n.col}"] + val[f"col:{n.col2}"]) / 2 + n.dx
        return val[f"col:{n.col}"] + n.dx
    if nid in m.flowc:
        return val[f"node:{nid}"]
    return val[f"row:{n.row}"] + n.dy


def _r(v: float) -> float:
    v = round(v, 2)
    return 0.0 if v == 0 else v


def _geometry(m: _Model, xv, yv, note_block) -> Geometry:
    spec, S, mc = m.spec, m.S, m.mc
    geom = Geometry(mode=spec.mode, S=S, canvas_w=0, canvas_h=0,
                    cols={t.id: _r(xv.get(f"col:{t.id}", 0.0)) for t in spec.cols},
                    rows={t.id: _r(yv.get(f"row:{t.id}", 0.0)) for t in spec.rows})
    for gid, g in spec.groups.items():
        st = K.style(g.type)
        rect = Box(_r(xv[f"group:{gid}.L"]), _r(yv[f"group:{gid}.T"]), _r(xv[f"group:{gid}.R"]), _r(yv[f"group:{gid}.B"]))
        gg = GroupGeom(gid, rect)
        if st.badge:
            gg.badge = Box.xywh(rect.x0, rect.y0, st.badge_size, st.badge_size)
        if g.label:
            gg.title = TextLine(g.label, rect.x0 + st.title_dx, rect.y0 + st.title_dy, st.title_size, st.title_fill,
                                K.TEXT_TITLE_WEIGHT)
        if g.cidr:
            gg.cidr = TextLine(g.cidr, rect.x0 + st.title_dx, rect.y0 + K.CIDR_DY, K.TEXT_CIDR.size, K.TEXT_CIDR.fill,
                               K.TEXT_CIDR.weight)
        geom.groups[gid] = gg
    for nid, n in spec.nodes.items():
        f = m.foot[nid]
        cx, cy = _r(_node_center(m, nid, "x", xv)), _r(_node_center(m, nid, "y", yv))
        icon = Box(cx - S / 2, cy - S / 2, cx + S / 2, cy + S / 2)
        lines = [TextLine(t, cx, icon.y1 + K.NODE_LABEL_DY + K.SUB_PITCH * i, sz, fill, "", "middle")
                 for i, (t, sz, fill) in enumerate(f.lines)]
        ng = NodeGeom(nid, cx, cy, icon, lines)
        if n.on:
            ng.mask = Box.xywh(cx - f.mask_w / 2, icon.y0, f.mask_w, f.mask_h)
            ng.side = n.side or "left"
        geom.nodes[nid] = ng
    for t in spec.cols:
        fs = [geom.nodes[nid].footprint() for nid, n in spec.nodes.items()
              if n.col == t.id and n.col2 is None and n.xy is None]
        c = geom.cols[t.id]
        geom.col_extent[t.id] = (min([b.x0 for b in fs] + [c]), max([b.x1 for b in fs] + [c]))
    for t in spec.rows:
        fs = [geom.nodes[nid].footprint() for nid, n in spec.nodes.items() if n.row == t.id and n.xy is None]
        c = geom.rows[t.id]
        geom.row_extent[t.id] = (min([b.y0 for b in fs] + [c]), max([b.y1 for b in fs] + [c]))
    boxes = [g.rect for g in geom.groups.values()] + [n.footprint() for n in geom.nodes.values()]
    d = union_all(boxes) or Box(0, 0, 0, 0)
    # "drawing": a route the caller kept inside the canvas past everything drawn (an
    # out-and-back right of / below the outermost items) extends the drawing to it
    geom.drawing = d = Box(d.x0, d.y0, max(d.x1, xv.get("drawing", d.x1)), max(d.y1, yv.get("drawing", d.y1)))
    margin = mc.canvas_margin
    w = d.x1
    h = d.y1 + margin
    if note_block is not None:
        h = max(h, d.y1 + note_block.below())
        if note_block.place == "pane":
            w = max(w, K.PANE_X + note_block.w)
            cid = spec.cloud_id()
            if cid:
                h = max(h, geom.groups[cid].rect.y0 + note_block.h + margin)
    geom.canvas_w = _r(_up(w + margin))
    geom.canvas_h = _r(_up(h))
    return geom


# =======================================================================================
# draw

def draw(spec: Spec, geom: Geometry) -> List[Element]:
    """Groups (z Z_GROUP: rect, badge, title, CIDR) then nodes (z Z_NODE: mask, icon, lines)."""
    out: List[Element] = []
    for gid, gg in geom.groups.items():
        g = spec.groups[gid]
        st = K.style(g.type)
        own = f"group:{gid}"
        out.append(el_rect(gg.rect, stroke=st.stroke, width=st.width, dash=g.dash if g.dash is not None else st.dash,
                           z=K.Z_GROUP, owner=own))
        if gg.badge:
            out.append(el_image(st.badge, gg.badge, z=K.Z_GROUP, owner=own))
        for t in (gg.title, gg.cidr):
            if t:
                out.append(el_text(t, z=K.Z_GROUP, owner=own))
    for nid, ng in geom.nodes.items():
        own = f"node:{nid}"
        if ng.mask:
            out.append(el_rect(ng.mask, fill=K.WHITE, z=K.Z_NODE, owner=own))
        out.append(el_image(spec.nodes[nid].icon, ng.icon, z=K.Z_NODE, owner=own))
        for t in ng.lines:
            out.append(el_text(t, z=K.Z_NODE, owner=own))
    return out


# =======================================================================================
# twins, for the rule checker (scripts/rules.py R-twin)

def twin_classes(spec: Spec) -> List[List[Tuple[str, Dict[str, List[Tuple[str, str, str]]], List[str]]]]:
    """The twins solve() draws alike (_Model.twin_sets), per class of two or more: per twin
    (its box id, per axis its measures (a, b, what) — b − a measured, in corresponding
    order, see _Model._twin_measures — and its subtree's node ids in corresponding order).
    Read only: the rule checker evaluates the measures on the final Geometry."""
    m = _Model(spec)
    out = []
    for cls in m.twin_sets():
        row = []
        for mem in cls:
            gid = mem[0]
            rows, cols = m._tracks_used(gid)
            rank = ({r: k for k, r in enumerate(rows)}, {c: k for k, c in enumerate(cols)})
            norder = m._shape(gid, rank, root=True)[2]
            row.append((gid, {axis: m._twin_measures(axis, mem) for axis in ("x", "y")}, norder))
        out.append(row)
    return out
