#!/usr/bin/env python3
"""Compare the structure of two draft SVGs (DESIGN 6, reproduction criterion 3).

    python3 tests/compare_structure.py original.draft.svg generated.draft.svg [--dump] [--only abcdefg]

Pixel positions are not compared. What is compared:
  (a) the multiset of node icon refs
  (b) each node's chain of containing groups, outer → inner (type from border color, dash
      and badge via layout_const.group_type_of, plus title and CIDR line)
  (c) the edge set: connectors that touch at junctions form one net; each end is the
      nearest node (icon + label stack) or group border within 12px; a net becomes
      source → sink pairs (plain ends → arrowed ends), written with the spec operators
      (-> <-> -- ..> <..> ..)
  (d) step badge number → the endpoints of the hop it sits on
  (e) note kind (panel / pane / lines / none), content kind and row count
  (f) left → right order of the nodes in each row (and top → bottom in each column)
  (g) texts: node sub-captions, connector labels (label / verb), note text (whitespace
      ignored, so a different line wrap is not a difference)

Nodes are named by label; repeated labels get #1, #2, ... in (chain, y, x) order, so the
same structure yields the same names in both drafts. Prints the differences and exits 1,
or "Structure OK" and exits 0. --dump prints what was extracted from each draft.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import layout_const as K  # noqa: E402  (import-free; group_type_of)
import layout_text  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}href"
REACH = 12            # an end within this of a node footprint / group border attaches to it
TOUCH = 1.5           # an end this close to another connector is a junction on it
NODE_END = 6          # an end this close to a node is its terminal even where it touches another line
ROW_TOL = 4           # icons whose centers differ by at most this share a row / column
NOTE_FILL = K.NOTE_FILL.lower()
WHITE = {"#fff", "#ffffff", "white"}
SECTIONS = "abcdefg"


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def text_width(s, fs):
    w = 0.0
    for c in s:
        wide = ("ᄀ" <= c <= "ᇿ" or "←" <= c <= "⯿" or "　" <= c <= "鿿" or "가" <= c <= "힣")
        w += fs * (1.0 if wide else 0.55)
    return w


def box_dist(p, b):
    """Distance from point p to box b (0 inside)."""
    dx = max(b[0] - p[0], 0, p[0] - b[2])
    dy = max(b[1] - p[1], 0, p[1] - b[3])
    return (dx * dx + dy * dy) ** 0.5


def border_dist(p, b):
    """Distance from point p to the border of box b."""
    if b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]:
        return min(p[0] - b[0], b[2] - p[0], p[1] - b[1], b[3] - p[1])
    return box_dist(p, b)


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    qx, qy = ax + t * dx, ay + t * dy
    return ((p[0] - qx) ** 2 + (p[1] - qy) ** 2) ** 0.5


def inside(pt, b, eps=0.5):
    return b[0] + eps < pt[0] < b[2] - eps and b[1] + eps < pt[1] < b[3] - eps


def norm_space(s):
    return re.sub(r"\s+", "", s)


# =======================================================================================
# Extraction

class Draft:
    def __init__(self, path):
        self.path = str(path)
        root = ET.parse(path).getroot()
        self.text_scale = float(root.get("data-text-scale", "1"))
        self.font_steps = layout_text.svg_steps(root)
        vb = root.get("viewBox", "0 0 0 0").split()
        self.canvas = (num(vb[2]), num(vb[3]))
        self.texts, self.rects, self.images, self.lines, self.circles = [], [], [], [], []
        self._walk(root, 0.0, 0.0)
        self._groups()
        self._nodes()
        self._note()
        self._badges()
        self._nets()
        self._leftover_texts()

    def font_px(self, size):
        return layout_text.font_size(size, self.text_scale, self.font_steps)

    # -- raw element walk (translate offsets applied, <g id> wrappers transparent) --------
    def _walk(self, el, ox, oy):
        m = re.search(r"translate\(\s*([-\d.]+)[ ,]*([-\d.]*)\s*\)", el.get("transform", ""))
        if m:
            ox, oy = ox + num(m.group(1)), oy + num(m.group(2))
        tag = el.tag.replace(NS, "")
        if tag in ("defs", "marker"):
            return
        if tag == "text":
            s = "".join(el.itertext()).strip()
            if s:
                fs = num(el.get("font-size"), 16)
                x, y = num(el.get("x")) + ox, num(el.get("y")) + oy
                anchor = el.get("text-anchor", "start")
                w = text_width(s, fs)
                x0 = x - w / 2 if anchor == "middle" else x - w if anchor == "end" else x
                self.texts.append({"s": s, "fs": fs, "x": x, "y": y, "anchor": anchor,
                                   "fill": (el.get("fill") or "").lower(),
                                   "weight": el.get("font-weight", ""),
                                   "box": (x0, y - 0.75 * fs, x0 + w, y + 0.25 * fs), "used": None})
        elif tag == "rect":
            x, y = num(el.get("x")) + ox, num(el.get("y")) + oy
            w, h = num(el.get("width")), num(el.get("height"))
            self.rects.append({"box": (x, y, x + w, y + h), "stroke": (el.get("stroke") or "none").lower(),
                               "fill": (el.get("fill") or "#000").lower(),
                               "dash": el.get("stroke-dasharray")})
        elif tag == "image":
            href = el.get("href") or el.get(XLINK) or ""
            x, y = num(el.get("x")) + ox, num(el.get("y")) + oy
            self.images.append({"ref": href[len("bundle:"):] if href.startswith("bundle:") else href[:40],
                                "box": (x, y, x + num(el.get("width")), y + num(el.get("height")))})
        elif tag in ("line", "polyline"):
            if tag == "line":
                pts = [(num(el.get("x1")) + ox, num(el.get("y1")) + oy), (num(el.get("x2")) + ox, num(el.get("y2")) + oy)]
            else:
                v = [num(t) for t in re.split(r"[ ,]+", el.get("points", "").strip()) if t]
                pts = [(v[i] + ox, v[i + 1] + oy) for i in range(0, len(v) - 1, 2)]
            if len(pts) >= 2:
                self.lines.append({"pts": pts, "dash": el.get("stroke-dasharray"),
                                   "start": bool(el.get("marker-start")), "end": bool(el.get("marker-end"))})
        elif tag == "circle":
            cx, cy = num(el.get("cx")) + ox, num(el.get("cy")) + oy
            self.circles.append({"c": (cx, cy), "r": num(el.get("r"))})
        for ch in el:
            self._walk(ch, ox, oy)

    # -- groups --------------------------------------------------------------------------
    def _groups(self):
        self.groups = []
        for r in self.rects:
            if r["stroke"] == "none" or r["fill"] not in ("none", "transparent"):
                continue
            b = r["box"]
            badge = None
            for im in self.images:
                ib = im["box"]
                if abs(ib[0] - b[0]) <= 1 and abs(ib[1] - b[1]) <= 1 and ib[2] - ib[0] <= 32:
                    badge = im["ref"]
                    im["badge"] = True
            gtype = K.group_type_of(r["stroke"], r["dash"], badge)
            title = None
            best = None
            for t in self.texts:
                if t["used"] or t["anchor"] != "start" or t["weight"] not in ("600", "700", "bold") or t["fs"] < self.font_px(14):
                    continue
                dx, dy = t["x"] - b[0], t["y"] - b[1]
                if 0 <= dx <= 50 and 0 < dy <= 30 * self.text_scale and (best is None or dy + dx < best[0]):
                    best = (dy + dx, t)
            cidr = None
            if best:
                title = best[1]
                title["used"] = "group"
                for t in self.texts:
                    if (not t["used"] and t["fs"] <= self.font_px(12) and abs(t["x"] - title["x"]) <= 1
                            and abs(t["y"] - title["y"] - round(16 * self.text_scale)) <= 2):
                        cidr = t
                        t["used"] = "group"
                        break
            g = {"box": b, "type": gtype or "?%s%s%s" % (r["stroke"], "/" + r["dash"] if r["dash"] else "",
                                                         "/" + badge if badge else ""),
                 "title": title["s"] if title else None, "cidr": cidr["s"] if cidr else None}
            self.groups.append(g)
        # parents = smallest strictly containing group; keys after naming
        for g in self.groups:
            b = g["box"]
            g["area"] = (b[2] - b[0]) * (b[3] - b[1])
        for g in self.groups:
            outer = [h for h in self.groups if h is not g and h["area"] > g["area"]
                     and h["box"][0] <= g["box"][0] + 0.5 and h["box"][1] <= g["box"][1] + 0.5
                     and g["box"][2] <= h["box"][2] + 0.5 and g["box"][3] <= h["box"][3] + 0.5]
            g["outer"] = sorted(outer, key=lambda h: -h["area"])
        for g in self.groups:
            desc = g["type"] + (" '%s'" % g["title"] if g["title"] else "") + (" %s" % g["cidr"] if g["cidr"] else "")
            g["desc"] = desc
        self._name(self.groups, lambda g: g["desc"],
                   lambda g: (tuple(h["desc"] for h in g["outer"]), g["box"][1], g["box"][0]))

    @staticmethod
    def _name(items, base, order):
        by = defaultdict(list)
        for it in items:
            by[base(it)].append(it)
        for b, lst in by.items():
            lst.sort(key=order)
            for i, it in enumerate(lst):
                it["name"] = b if len(lst) == 1 else "%s#%d" % (b, i + 1)

    def chain_of(self, pt):
        gs = [g for g in self.groups if inside(pt, g["box"])]
        # an overlay (ASG, target group) spans AZs: it is not nested in the subnet it crosses
        # and its area says nothing about nesting, so it goes innermost
        return [g for g in sorted(gs, key=lambda g: (g["type"] in K.OVERLAY_TYPES, -g["area"]))]

    # -- nodes ---------------------------------------------------------------------------
    def _nodes(self):
        self.nodes = []
        for im in self.images:
            if im.get("badge") or im["ref"].startswith("group/"):
                continue
            b = im["box"]
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            label, subs = None, []
            cands = [t for t in self.texts if not t["used"] and t["fs"] >= self.font_px(13) and t["anchor"] == "middle"
                     and abs(t["x"] - cx) <= 3 and b[3] < t["y"] <= b[3] + 30 * self.text_scale]
            stack = [b]
            if cands:
                label = min(cands, key=lambda t: t["y"])
                label["used"] = "node"
                stack.append(label["box"])
                y = label["y"]
                while True:
                    nxt = [t for t in self.texts if not t["used"] and t["fs"] <= self.font_px(12) and t["anchor"] == "middle"
                           and abs(t["x"] - cx) <= 3 and abs(t["y"] - y - round(16 * self.text_scale)) <= 2]
                    if not nxt:
                        break
                    t = nxt[0]
                    t["used"] = "node"
                    subs.append(t["s"])
                    stack.append(t["box"])
                    y = t["y"]
            foot = (min(s[0] for s in stack), min(s[1] for s in stack), max(s[2] for s in stack), max(s[3] for s in stack))
            chain = self.chain_of((cx, cy))
            self.nodes.append({"ref": im["ref"], "label": label["s"] if label else "(%s)" % im["ref"].split("/")[-1],
                               "subs": subs, "cx": cx, "cy": cy, "box": b, "foot": foot, "chain": chain})
        self._name(self.nodes, lambda n: n["label"],
                   lambda n: (tuple(g["name"] for g in n["chain"]), n["cy"], n["cx"]))

    # -- note ----------------------------------------------------------------------------
    def _note(self):
        self.note_rect = None
        for r in self.rects:
            if r["fill"] == NOTE_FILL:
                self.note_rect = r["box"]
        bottoms = [g["box"][3] for g in self.groups] + [n["foot"][3] for n in self.nodes]
        self.drawing_bottom = max(bottoms) if bottoms else 0.0
        if self.note_rect:
            nb = self.note_rect
            self.note_kind = "panel" if nb[1] >= max([g["box"][3] for g in self.groups] or [0]) - 1 else "pane"
            in_note = lambda p: inside(p, nb, 0)  # noqa: E731
        else:
            self.note_kind = None
            in_note = lambda p: p[1] > self.drawing_bottom  # noqa: E731
        self._in_note = in_note

    # -- badges --------------------------------------------------------------------------
    def _badges(self):
        self.badges, self.note_badges = [], []
        for c in self.circles:
            if c["r"] < 8:
                continue
            digit = None
            for t in self.texts:
                if not t["used"] and abs(t["x"] - c["c"][0]) <= 2 and abs(t["y"] - (c["c"][1] + round(4 * self.text_scale))) <= 2:
                    digit = t
                    break
            if digit is None:
                continue
            digit["used"] = "badge"
            b = {"n": digit["s"], "c": c["c"]}
            if self.note_rect and inside(c["c"], self.note_rect, 0):
                self.note_badges.append(b)
            elif not self.note_rect and c["c"][1] > self.drawing_bottom and self._badge_line(c["c"]) is None:
                self.note_badges.append(b)
            else:
                self.badges.append(b)
        if self.note_rect is None:
            self.note_kind = "lines" if self.note_badges else None

    def _badge_line(self, c, rule_only=True):
        """The connector a badge sits on: by the badge rule (cy = y - 14 on a horizontal
        piece, cx = x - 22 on a vertical one), else (rule_only False) the nearest."""
        best = None
        for i, ln in enumerate(self.lines):
            for a, b in zip(ln["pts"], ln["pts"][1:]):
                if abs(a[1] - b[1]) < 0.5:          # horizontal
                    lo, hi = sorted((a[0], b[0]))
                    if lo - 2 <= c[0] <= hi + 2 and abs(c[1] - (a[1] - (round(10 * self.text_scale) + 4))) <= 3:
                        return i
                elif abs(a[0] - b[0]) < 0.5:        # vertical
                    lo, hi = sorted((a[1], b[1]))
                    if lo - 2 <= c[1] <= hi + 2 and abs(c[0] - (a[0] - (round(10 * self.text_scale) + 12))) <= 3:
                        return i
                d = seg_dist(c, a, b)
                if best is None or d < best[0]:
                    best = (d, i)
        return None if rule_only or best is None else best[1]

    # -- connectors → nets → pairs -------------------------------------------------------
    def _attach(self, p):
        best = None
        for n in self.nodes:
            d = box_dist(p, n["foot"])
            if d <= REACH and (best is None or d < best[0]):
                best = (d, "node", n["name"])
        if best and best[0] <= NODE_END:      # a connector stops END_GAP from its node
            return best
        for g in self.groups:
            d = border_dist(p, g["box"])
            if d <= REACH and (best is None or d < best[0] - 1e-9):
                best = (d, "group", "[%s]" % g["name"])
        return best

    def _nets(self):
        L = self.lines
        ends = []      # per line: [(kind, target, arrow), (kind, target, arrow)]
        parent = list(range(len(L)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i, ln in enumerate(L):
            pair = []
            for k, (p, arrow) in enumerate(((ln["pts"][0], ln["start"]), (ln["pts"][-1], ln["end"]))):
                att = self._attach(p)
                touch = [j for j, o in enumerate(L) if j != i
                         and any(seg_dist(p, a, b) <= TOUCH for a, b in zip(o["pts"], o["pts"][1:]))]
                if att and att[1] == "node" and (att[0] <= NODE_END or not touch):
                    pair.append(("t", att[2], arrow))
                elif touch:
                    pair.append(("j", None, arrow))
                    for j in touch:
                        parent[find(i)] = find(j)
                elif att:
                    pair.append(("t", att[2], arrow))
                else:
                    pair.append(("?", "?(%d,%d)" % p, arrow))
            ends.append(pair)
        self.line_ends = ends
        nets = defaultdict(list)
        for i in range(len(L)):
            nets[find(i)].append(i)
        self.line_net = {i: find(i) for i in range(len(L))}
        self.nets = {}
        for r, members in nets.items():
            terms = [e for i in members for e in ends[i] if e[0] != "j"]
            dashes = {L[i]["dash"] or "" for i in members}
            dashed = "mixed" if len(dashes) > 1 else bool(next(iter(dashes)))
            self.nets[r] = {"lines": members, "terms": terms, "dashed": dashed}
        self.pairs = Counter()
        for net in self.nets.values():
            for p in self._net_pairs(net):
                self.pairs[p] += 1

    @staticmethod
    def _op(a_arrow, b_arrow, dashed):
        d = "~" if dashed == "mixed" else (".." if dashed else "-")
        if a_arrow and b_arrow:
            return "<..>" if d == ".." else "<->" if d == "-" else "<~>"
        if b_arrow:
            return "..>" if d == ".." else "->" if d == "-" else "~>"
        return ".." if d == ".." else "--" if d == "-" else "~~"

    def _net_pairs(self, net):
        terms, dashed = net["terms"], net["dashed"]
        if len(terms) == 2:
            (_, a, aa), (_, b, ba) = terms
            if aa and not ba:
                a, b, aa, ba = b, a, ba, aa
            if aa == ba and b < a:
                a, b = b, a
            return ["%s %s %s" % (a, self._op(aa, ba, dashed), b)]
        if len(terms) < 2:
            return ["%s (dangling net)" % " ".join(t[1] for t in terms) or "(empty net)"]
        src = sorted(t[1] for t in terms if not t[2])
        snk = sorted(t[1] for t in terms if t[2])
        if src and snk:
            return ["%s %s %s" % (s, self._op(False, True, dashed), k) for s in src for k in snk]
        return ["net{%s} %s" % (", ".join(sorted(t[1] for t in terms)), self._op(bool(snk), bool(snk), dashed))]

    def _nearest(self, li, p):
        """The point of connector li nearest p."""
        best = None
        for a, b in zip(self.lines[li]["pts"], self.lines[li]["pts"][1:]):
            L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / L2))
            q = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            d = ((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) ** 0.5
            if best is None or d < best[0] - 1e-9:
                best = (d, q)
        return best[1]

    def _along(self, li, p):
        """Distance along connector li's path to the point of it nearest p."""
        pts, run, best = self.lines[li]["pts"], 0.0, None
        for a, b in zip(pts, pts[1:]):
            L = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            d = seg_dist(p, a, b)
            if best is None or d < best[0] - 1e-9:
                t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / L ** 2))
                best = (d, run + t * L)
            run += L
        return best[1] if best else 0.0

    def hop_of(self, li, c=None):
        """The endpoints of connector li, junction ends replaced by the net's other side. A
        line that runs straight through a fork (or merge) junction other lines start on
        counts, where badge c sits on its shared part, the whole fan: a split trunk drawn
        as stem + branch in one polyline is the same hop as a stem line ending at the
        junction."""
        net = self.nets[self.line_net[li]]
        src = sorted(t[1] for t in net["terms"] if not t[2])
        snk = sorted(t[1] for t in net["terms"] if t[2])
        e = self.line_ends[li]
        if c is not None and e[0][0] != "j" and e[1][0] != "j" and len(net["lines"]) > 1:
            pts = self.lines[li]["pts"]
            joins = [self._along(li, q) for j in net["lines"] if j != li
                     for k, q in enumerate((self.lines[j]["pts"][0], self.lines[j]["pts"][-1]))
                     if self.line_ends[j][k][0] == "j"
                     and any(seg_dist(q, a, b) <= TOUCH for a, b in zip(pts, pts[1:]))]
            if joins:
                at = self._along(li, c)
                fan_b = at <= min(joins) and len(snk) > 1 and not e[0][2]      # badge on the stem of a fork
                fan_a = at >= max(joins) and len(src) > 1 and e[1][2]          # badge past a merge
                if fan_b or fan_a:
                    a = "+".join(src) if fan_a else e[0][1]
                    b = "+".join(snk) if fan_b else e[1][1]
                    return "%s — %s" % (a, b)
        out = []
        for k in (0, 1):
            kind, tgt, arrow = e[k]
            if kind != "j":
                out.append(tgt)
                continue
            other = e[1 - k]
            if other[0] != "j":
                side = snk if not other[2] else src
                if not side:     # topology net: everything but the other end
                    side = sorted(t[1] for t in net["terms"] if t[1] != other[1])
            else:
                side = src if k == 0 else snk
            out.append("+".join(side) if side else "*")
        a, b = out
        if e[0][2] and not e[1][2]:
            a, b = b, a
        return "%s — %s" % (a, b)

    # -- texts left over: connector labels, note text ------------------------------------
    def _leftover_texts(self):
        self.edge_texts = Counter()
        note = []
        for t in self.texts:
            if t["used"]:
                continue
            p = (t["x"], t["y"])
            if self.note_kind and (self._in_note(p) if self.note_rect else t["y"] > self.drawing_bottom):
                note.append(t)
                continue
            kind = "verb" if t["fill"] == K.GRAY.lower() else "label" if t["fill"] == K.INK.lower() else t["fill"]
            self.edge_texts["%s: %s" % (kind, t["s"])] += 1
        note.sort(key=lambda t: (round(t["y"]), t["x"]))
        self.note_texts = note
        self.note_text = norm_space("".join(t["s"] for t in note))
        n = len(self.note_badges)
        if self.note_kind is None:
            self.note_desc = "none"
        elif n:
            self.note_desc = "%s steps %d" % (self.note_kind, n)
        else:
            heads = [t for t in note if t["weight"] in ("600", "700", "bold")]
            if heads:
                self.note_desc = "%s rows %d" % (self.note_kind, len(heads))
            else:
                self.note_desc = "%s summary %d" % (self.note_kind, len({round(t["y"]) for t in note}))

    # -- section data --------------------------------------------------------------------
    def badge_map(self):
        out = defaultdict(list)
        for b in self.badges:
            li = self._badge_line(b["c"], rule_only=True)
            if li is None:
                li = self._badge_line(b["c"], rule_only=False)
            if li is None:
                out[b["n"]].append("(no connector)")
                continue
            hop = self.hop_of(li, b["c"])
            # lines drawn on top of each other from one end (a fork as two full polylines)
            # share the stretch the badge sits on: the hop is the whole fan
            q = self._nearest(li, b["c"])
            a, _, far = hop.partition(" — ")
            fan = {far}
            for j in range(len(self.lines)):
                if j != li and any(seg_dist(q, u, v) <= TOUCH for u, v in zip(self.lines[j]["pts"], self.lines[j]["pts"][1:])):
                    a2, _, far2 = self.hop_of(j, b["c"]).partition(" — ")
                    if a2 == a:
                        fan.update(far2.split("+"))
            if len(fan) > 1:
                fan = {x for f in fan for x in f.split("+")}
                hop = "%s — %s" % (a, "+".join(sorted(fan)))
            out[b["n"]].append(hop)
        return {k: sorted(v) for k, v in out.items()}

    def orders(self):
        """Rows (equal cy) left → right and columns (equal cx) top → bottom, of ≥ 2 nodes."""
        def groups_by(key):
            out = []
            for n in sorted(self.nodes, key=key):
                if out and abs(key(out[-1][-1]) - key(n)) <= ROW_TOL:
                    out[-1].append(n)
                else:
                    out.append([n])
            return [g for g in out if len(g) >= 2]
        rows = [sorted(g, key=lambda n: n["cx"]) for g in groups_by(lambda n: n["cy"])]
        cols = [sorted(g, key=lambda n: n["cy"]) for g in groups_by(lambda n: n["cx"])]
        return rows, cols

    def dump(self):
        print("== %s  (canvas %gx%g)" % (self.path, *self.canvas))
        print("groups:")
        for g in self.groups:
            print("  %-40s in %s" % (g["name"], " / ".join(h["name"] for h in g["outer"]) or "-"))
        print("nodes:")
        for n in self.nodes:
            print("  %-28s %-50s %s%s" % (n["name"], n["ref"], " / ".join(g["name"] for g in n["chain"]) or "-",
                                         "  sub=%s" % n["subs"] if n["subs"] else ""))
        print("connectors:")
        for i, ln in enumerate(self.lines):
            e = self.line_ends[i]
            print("  %2d net%-3d %s%s%s  %s -> %s" % (i, self.line_net[i], "<" if ln["start"] else "-",
                                                 ".." if ln["dash"] else "--", ">" if ln["end"] else "-",
                                                 e[0][1] or "junction", e[1][1] or "junction"))
        print("edges (pairs):")
        for p, c in sorted(self.pairs.items()):
            print("  %s%s" % (p, " ×%d" % c if c > 1 else ""))
        print("badges:", self.badge_map())
        print("note:", self.note_desc)
        print("edge texts:", dict(self.edge_texts))
        print()


# =======================================================================================
# Comparison

def counter_diff(a, b):
    out = []
    for k in sorted(set(a) | set(b)):
        if a[k] != b[k]:
            out.append("%s: original %d, generated %d" % (k, a[k], b[k]))
    return out


def compare(A, B, only=SECTIONS):
    diffs = []

    def add(sec, msg):
        if sec in only:
            diffs.append("(%s) %s" % (sec, msg))

    # (a) icon refs
    for d in counter_diff(Counter(n["ref"] for n in A.nodes), Counter(n["ref"] for n in B.nodes)):
        add("a", "icon " + d)
    an = {n["name"]: n for n in A.nodes}
    bn = {n["name"]: n for n in B.nodes}
    for k in sorted(set(an) - set(bn)):
        add("a", "node %r (%s) only in original" % (k, an[k]["ref"]))
    for k in sorted(set(bn) - set(an)):
        add("a", "node %r (%s) only in generated" % (k, bn[k]["ref"]))
    # (b) chains
    for k in sorted(set(an) & set(bn)):
        ca = [g["desc"] for g in an[k]["chain"]]
        cb = [g["desc"] for g in bn[k]["chain"]]
        if ca != cb:
            add("b", "%s: original %s, generated %s" % (k, " / ".join(ca) or "-", " / ".join(cb) or "-"))
        if an[k]["ref"] != bn[k]["ref"]:
            add("b", "%s: icon original %s, generated %s" % (k, an[k]["ref"], bn[k]["ref"]))
    for d in counter_diff(Counter(g["desc"] for g in A.groups), Counter(g["desc"] for g in B.groups)):
        add("b", "group " + d)
    # (c) edges
    for d in counter_diff(A.pairs, B.pairs):
        add("c", "edge " + d)
    # (d) badges
    ba, bb = A.badge_map(), B.badge_map()
    for k in sorted(set(ba) | set(bb), key=lambda s: (len(s), s)):
        if ba.get(k) != bb.get(k):
            add("d", "badge %s: original %s, generated %s" % (k, ba.get(k, "-"), bb.get(k, "-")))
    # (e) note
    reflowed_note = ((A.text_scale > 1 or B.text_scale > 1)
                     and A.note_kind in ("pane", "panel", "lines")
                     and B.note_kind in ("pane", "panel", "lines")
                     and A.note_desc.split()[1:] == B.note_desc.split()[1:])
    if A.note_desc != B.note_desc and not reflowed_note:
        add("e", "note: original %s, generated %s" % (A.note_desc, B.note_desc))
    # (f) orders
    pos_b = {n["name"]: n for n in B.nodes}
    rows, cols = A.orders()
    for seq, axis, word in ((rows, "cx", "row"), (cols, "cy", "column")):
        for grp in seq:
            names = [n["name"] for n in grp if n["name"] in pos_b]
            got = sorted(names, key=lambda m: pos_b[m][axis])
            if names != got:
                add("f", "%s order: original %s, generated %s" % (word, " | ".join(names), " | ".join(got)))
    # (g) texts
    for k in sorted(set(an) & set(bn)):
        if an[k]["subs"] != bn[k]["subs"]:
            add("g", "%s sub: original %s, generated %s" % (k, an[k]["subs"], bn[k]["subs"]))
    for d in counter_diff(A.edge_texts, B.edge_texts):
        add("g", "connector text " + d)
    if A.note_text != B.note_text:
        i = next((i for i, (x, y) in enumerate(zip(A.note_text, B.note_text)) if x != y),
                 min(len(A.note_text), len(B.note_text)))
        add("g", "note text differs at char %d: original …%s…, generated …%s…"
            % (i, A.note_text[max(0, i - 15):i + 25], B.note_text[max(0, i - 15):i + 25]))
    return diffs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("original")
    ap.add_argument("generated")
    ap.add_argument("--dump", action="store_true", help="print what was extracted from each draft")
    ap.add_argument("--only", default=SECTIONS, help="sections to compare (default abcdefg)")
    a = ap.parse_args(argv)
    A, B = Draft(a.original), Draft(a.generated)
    if a.dump:
        A.dump()
        B.dump()
    diffs = compare(A, B, a.only)
    for d in diffs:
        print(d)
    print("Structure OK" if not diffs else "%d differences" % len(diffs))
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
