"""W2: spec + requirements → Geometry (difference constraints, longest path), and the
Elements of every group and node.

    solve(spec, reqs, note_block=None) -> Geometry
    draw(spec, geom) -> list[Element]

The contract (variable names, coordinates, who fills what) is layout_model's docstring;
constants come from layout_const. Outline (DESIGN 4.2-4.3):

  footprints   every node's half width (0.6 em layout widths, rounded up), icon top, last
               baseline and footprint bottom; border nodes use their mask.
  constraints  `b − a ≥ d` per axis, each a layout_model.Requirement with why/owner:
               1 containment (pad, top insets, label_bottom), 2 siblings in one parent
               (separated on the axis their track ranges are disjoint on; rows first for
               diagonal pairs), 3 neighbour pitch, 4 header and CIDR widths, 5 IGW/VGW pinned
               on the VPC border (mask kept MASK_CLEAR from borders), 6 the AZ gap row,
               7 colspan (left side on the first track, right side on the last), 8 flow rows
               (own x variables, pitch, centered in the parent afterwards), 9 overlays (ASG:
               members, header right/below, inside each member subnet), 10 the caller's
               Requirements, 11 canvas margin (and the note's requirements), plus template
               instances kept alike (x: equal edges; y: equal insets, by iteration), badge ↔
               icon clearance, track order / min_gap_before, min_w / min_h.
  solve        Bellman-Ford longest path from "origin" per axis = the minimal solution. A
               positive cycle drops the soft requirements in it and retries; a cycle of hard
               constraints raises SolveError naming each constraint's spec location and why.
  hug          group left / top edges are pulled toward their content (inner groups
               first) as far as every constraint allows; right / bottom edges are already
               tight in the minimal solution.
  explain      for every track, the chain of constraints that set its position.

x is solved (and hugged) before y, because two y rules depend on x: which overlay members
sit under the overlay's header title, and which icons sit under a group badge.
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_const as K  # noqa: E402
from layout_model import (  # noqa: E402
    Box, Element, Geometry, GroupGeom, NodeGeom, Requirement, SolveError, Spec, TextLine,
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
    __slots__ = ("lines", "h", "top", "base", "bot", "mask_w", "mask_h")

    def __init__(self, lines, h, top, base, bot, mask_w, mask_h):
        self.lines = lines          # [(text, size, fill)]
        self.h = h                  # half width (x)
        self.top = top              # icon top offset (−S/2)
        self.base = base            # last baseline offset
        self.bot = bot              # footprint bottom offset (glyph descent or mask bottom)
        self.mask_w = mask_w
        self.mask_h = mask_h


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
        mask_h = S + mc.mask_extra + K.LINE_PITCH * max(0, len(lines) - 1)
        w = mask_w
        bot = max(bot, -S / 2 + mask_h)
    h = _up(w / 2)
    top = -S / 2
    if n.col and n.col2 is None:
        h = max(h, _up(spec.track(n.col).min_w / 2))
    if n.row:
        mw = spec.track(n.row).min_w / 2
        top, bot = min(top, -mw), max(bot, mw)
    return _Foot(lines, h, top, base, bot, mask_w, mask_h)


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
    def __init__(self, spec: Spec):
        self.spec = spec
        self.mc = spec.const
        self.S = spec.S
        self.ci = {t.id: i for i, t in enumerate(spec.cols)}
        self.ri = {t.id: i for i, t in enumerate(spec.rows)}
        self.foot = {nid: _footprint(spec, n) for nid, n in spec.nodes.items()}
        self.flow = {nid for nid, n in spec.nodes.items() if n.xy is None and n.col is None}
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

    # ---- helpers --------------------------------------------------------------------

    def add(self, axis, a: Ref, b: Ref, d: float, why: str, owner: str, soft=False):
        """(b) − (a) ≥ d, with a/b given as (variable, offset)."""
        (va, oa), (vb, ob) = a, b
        dd = d + oa - ob
        if va == vb and dd <= _EPS:
            return
        self.cons[axis].append(Requirement(axis, va, vb, dd, why, owner, soft))

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

    def rng(self, axis, first, last):
        idx = self.ci if axis == "x" else self.ri
        if first is None or first not in idx:
            return None
        return (idx[first], idx[last if last in idx else first])

    def node_rng(self, nid, axis):
        n = self.spec.nodes[nid]
        if n.xy is not None:
            return None
        if axis == "x":
            return None if nid in self.flow else self.rng("x", n.col, n.col2 or n.col)
        return self.rng("y", n.row, n.row)

    def group_rng(self, gid, axis):
        g = self.spec.groups[gid]
        t = g.cols if axis == "x" else g.rows
        return self.rng(axis, t[0], t[1]) if t else None

    def item_group(self, gid):
        g = self.spec.groups[gid]
        return _Item(f"group:{gid}", gid=gid, xr=self.group_rng(gid, "x"), yr=self.group_rng(gid, "y"),
                     gtype=g.type)

    def item_node(self, nid):
        return _Item(f"node:{nid}", nid=nid, border=bool(self.spec.nodes[nid].on),
                     xr=self.node_rng(nid, "x"), yr=self.node_rng(nid, "y"))

    def nref(self, nid, axis, side) -> Ref:
        """A node's center variable; side "lo" (left / as b) or "hi" (right / as a): a
        colspan node uses its first track on the left and its last on the right."""
        n = self.spec.nodes[nid]
        if n.xy is not None or (axis == "x" and nid in self.flow):
            return (f"node:{nid}", 0.0)
        if axis == "x":
            c = n.col2 if (side == "hi" and n.col2) else n.col
            return (f"col:{c}", n.dx)
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
        for nid, n in spec.nodes.items():
            if n.on:
                self._border(axis, nid)
            if n.xy is not None:
                v = (f"node:{nid}", 0.0)
                c = n.xy[0] if axis == "x" else n.xy[1]
                self.add(axis, ("origin", 0), v, c, f"xy {fmt_num(c)}", f"node:{nid}")
                self.add(axis, v, ("origin", 0), -c, f"xy {fmt_num(c)}", f"node:{nid}")
        if axis == "x":
            self._flows()
        else:
            self._az_gaps()
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
            p = self.side_pad(gid, "R") if axis == "x" else self.pad(gid)
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
                self.add(axis, self.hi(it, axis, base=True), gr, mc.label_bottom,
                         f"label_bottom {fmt_num(mc.label_bottom)} {nid} ⊂ {gid}", own)
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
            need = [(_up(hdr) + self.pad(gid), "header height")]
            if g.min_h:
                need.append((g.min_h, "min_h"))
            for w, what in need:
                self.add(axis, gl, gr, w, f"{what} {fmt_num(w)} {gid}", own)
            span = g.span_rows
        if span:
            pre = "col" if axis == "x" else "row"
            p = self.pad_node(gid)
            self.add(axis, gl, (f"{pre}:{span[0]}", 0), p, f"span {gid} ⊃ {span[0]}", own)
            self.add(axis, (f"{pre}:{span[1]}", 0), gr, p, f"span {gid} ⊃ {span[1]}", own)

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
        return mc.sibling_gap, "sibling gap"

    def _sep(self, axis, a: _Item, b: _Item, owner):
        g, what = self._gap(axis, a, b)
        d = g
        why = f"{what} {fmt_num(g)} {a.key} | {b.key}"
        if axis == "x" and a.nid and b.nid:
            # neighbour nodes: center pitch (3), on the conservative colspan sides
            (va, oa), (vb, ob) = self.nref(a.nid, "x", "hi"), self.nref(b.nid, "x", "lo")
            fa, fb = self.foot[a.nid], self.foot[b.nid]
            if self.spec.nodes[a.nid].parent == self.spec.nodes[b.nid].parent or a.border or b.border:
                self.add("x", (va, oa), (vb, ob), self.mc.node_pitch,
                         f"pitch {fmt_num(self.mc.node_pitch)} {a.key} → {b.key}", owner)
            d = g + fa.h + fb.h
            self.add("x", (va, oa), (vb, ob), d, f"{why} (half widths {fmt_num(fa.h)} + {fmt_num(fb.h)})", owner)
            return
        self.add(axis, self.hi(a, axis), self.lo(b, axis), d, why, owner)

    def _siblings(self, axis, parent):
        """Siblings of one parent (2, 3). Border nodes count as siblings both in their VPC's
        parent (except their own VPC) and among the VPC's children."""
        items = [self.item_group(g) for g in self.child_groups[parent]]
        if len(items) + len(self.child_nodes[parent]) > 1:
            for it in items:
                if (it.xr if axis == "x" else it.yr) is None:
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
                if _disjoint(oa, ob):
                    # diagonal: separate on the axis with the wider track gap (ties → rows)
                    here, there = _span_gap(ra, rb), _span_gap(oa, ob)
                    if here < there or (here == there and axis == "x"):
                        continue
                first, second = (a, b) if ra[1] < rb[0] else (b, a)
                self._sep(axis, first, second, owner)

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

    def template_sets(self) -> List[List[str]]:
        sets: Dict[str, List[str]] = {}
        for g in self.tree:
            if g.instance is not None and "." in g.id:
                sets.setdefault(g.id.rsplit(".", 1)[0], []).append(g.id)
        return [v for v in sets.values() if len(v) > 1]

    def _overlay_x(self, g):
        """Overlay (ASG) in x (9): around its members, inside each member's subnet, right of
        the subnet header labels it crosses."""
        mc, st, gid = self.mc, K.style(g.type), g.id
        own = f"group:{gid}"
        gl, gr = (f"group:{gid}.L", 0.0), (f"group:{gid}.R", 0.0)
        pl, pr = self.side_pad(gid, "L", node=True), self.side_pad(gid, "R", node=True)
        for m in g.over:
            it = self.item_node(m)
            self.add("x", gl, self.lo(it, "x"), pl, f"pad {fmt_num(pl)} {gid} ⊃ {m}", own)
            self.add("x", self.hi(it, "x"), gr, pr, f"pad {fmt_num(pr)} {m} ⊂ {gid}", own)
        first = self._overlay_first(g)
        for s in self._overlay_subnets(g):
            sg = self.spec.groups[s]
            ss = K.style(sg.type)
            self.add("x", (f"group:{s}.L", 0), gl, K.OVERLAY_HEADER_GAP, f"overlay inside {s}", own)
            self.add("x", gr, (f"group:{s}.R", 0), K.OVERLAY_HEADER_GAP, f"overlay inside {s}", own)
            if sg.label and (g.header == "right" or s not in first):
                d = ss.title_dx + _up(layout_text_width(sg.label, ss.title_size)) + K.OVERLAY_HEADER_GAP
                self.add("x", (f"group:{s}.L", 0), gl, d, f"overlay right of {s} header {fmt_num(d)}", own)
        if g.label:
            w = st.title_dx + _up(layout_text_width(g.label, st.title_size)) + K.HEADER_TAIL
            self.add("x", gl, gr, w, f"title width {fmt_num(w)} {gid}", own)

    def _overlay_subnets(self, g):
        out = []
        for m in g.over:
            p = self.spec.nodes[m].parent
            if p and p not in out:
                out.append(p)
        return out

    def _overlay_first(self, g, last=False):
        """Member subnets in the overlay's first (or last) member row."""
        rows = [self.ri.get(self.spec.nodes[m].row, 0) for m in g.over]
        want = max(rows) if last else min(rows)
        return [self.spec.nodes[m].parent for m, r in zip(g.over, rows) if r == want and self.spec.nodes[m].parent]

    def y_after_x(self, xv: Dict[str, float], nodes_x: Dict[str, float]):
        """The y rules that depend on solved x: overlay top (9, decision f) and group badge
        ↔ icon clearance (QR 73)."""
        mc, S = self.mc, self.S
        for g in self.overlays:
            st, gid = K.style(g.type), g.id
            own = f"group:{gid}"
            gl, gr = (f"group:{gid}.T", 0.0), (f"group:{gid}.B", 0.0)
            L = xv[f"group:{gid}.L"]
            t0 = L + st.title_dx - K.HEADER_ICON_CLEAR
            t1 = L + st.title_dx + (layout_text_width(g.label, st.title_size) if g.label else 0) + K.HEADER_ICON_CLEAR
            b1 = L + (st.badge_size + K.ICON_CLEAR if st.badge else 0)
            for m in g.over:
                it = self.item_node(m)
                cx = nodes_x[m]
                x0, x1 = cx - S / 2, cx + S / 2
                under = (g.label and x1 > t0 and x0 < t1) or (st.badge and x0 < b1 and x1 > L - K.ICON_CLEAR)
                top = K.top_inset(g.type, mc.name, "icon") if under else K.OVERLAY_HEADER_GAP
                if under and st.badge and x0 < b1:
                    top = max(top, st.badge_size + K.ICON_CLEAR)
                self.add("y", gl, self.lo(it, "y"), top,
                         f"{'header' if under else 'overlay'} inset {fmt_num(top)} {gid} ⊃ {m}", own)
                self.add("y", self.hi(it, "y", base=True), gr, mc.label_bottom,
                         f"label_bottom {fmt_num(mc.label_bottom)} {m} ⊂ {gid}", own)
            for s in self._overlay_first(g):
                if g.header == "below":
                    ss = K.style(self.spec.groups[s].type)
                    d = _up(ss.title_dy + K.GLYPH_DESCENT * ss.title_size) + K.OVERLAY_HEADER_GAP
                else:
                    d = K.OVERLAY_HEADER_GAP
                self.add("y", (f"group:{s}.T", 0), gl, d, f"overlay below {s} top {fmt_num(d)}", own)
            for s in self._overlay_first(g, last=True):
                self.add("y", gr, (f"group:{s}.B", 0), K.OVERLAY_HEADER_GAP, f"overlay inside {s}", own)
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
        if v == "origin" or v.startswith("group:"):
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
    cons = list(cons)
    while True:
        dist, pred, cycle = _bellman_ford(cons)
        if cycle is None:
            return dist, pred, cons
        soft = [c for c in cycle if c.soft]
        if not soft:
            excess = sum(c.d for c in cycle)
            probs = [f"{_loc(m.spec, c.owner)}: contradictory {axis} constraint {c.why!r} "
                     f"({c.a} → {c.b} ≥ {fmt_num(c.d)}) in a cycle that needs {fmt_num(excess)} px more than 0"
                     for c in cycle if c.owner != "canvas" or c.why != "coordinate ≥ 0"]
            raise SolveError(probs or [f"canvas: contradictory {axis} constraints"])
        drop = {id(c) for c in soft}
        for c in soft:
            m.warnings.append(f"{_loc(m.spec, c.owner)}: dropped soft requirement {c.why!r} ({axis}) "
                              f"to resolve contradictory constraints")
        cons = [c for c in cons if id(c) not in drop]


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


# =======================================================================================
# solve

def solve(spec: Spec, reqs: Sequence[Requirement], note_block=None) -> Geometry:
    m = _Model(spec)
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

    # ---- x ---------------------------------------------------------------------------
    m.build("x")
    xv, xpred, xcons = _solve_axis(m, "x", m.cons["x"] + mapped["x"])
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

    # ---- y ---------------------------------------------------------------------------
    m.build("y")
    m.y_after_x(xv, nodes_x)
    ycons_in = m.cons["y"] + mapped["y"]
    for _ in range(6):
        ybf, ypred, ycons = _solve_axis(m, "y", ycons_in)
        yv = dict(ybf)
        _hug(m, "y", ycons, yv)          # insets are compared on the hugged boxes
        more = m.even_insets(yv)
        if not more:
            break
        ycons_in = ycons + more

    geom = _geometry(m, xv, yv, note_block)
    geom.explain = _explain(m, "x", xbf, xpred) + _explain(m, "y", ybf, ypred)
    geom.warnings = list(m.warnings)
    return geom


def _node_center(m: _Model, nid: str, axis: str, val) -> float:
    n = m.spec.nodes[nid]
    if n.xy is not None:
        return float(n.xy[0] if axis == "x" else n.xy[1])
    if axis == "x":
        if nid in m.flow:
            return val[f"node:{nid}"]
        if n.col2:
            return (val[f"col:{n.col}"] + val[f"col:{n.col2}"]) / 2 + n.dx
        return val[f"col:{n.col}"] + n.dx
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
    geom.drawing = union_all(boxes) or Box(0, 0, 0, 0)
    d, margin = geom.drawing, mc.canvas_margin
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
