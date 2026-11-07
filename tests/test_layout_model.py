#!/usr/bin/env python3
"""The layout engine's constants and style table against the reference examples.

    python3 tests/test_layout_model.py

Every example in docs/examples (documents and slides) and the docs/example.svg skeleton is
turned back into a draft in memory (embed.unembed) and measured: group border styles,
header geometry, node label stacks, masks, top insets, AZ gaps, step badges and the note.
Also checks the small helpers in layout_model and that mirrored constants still equal
check_layout's. Standard library only (the icon bundle must be present, as for any script).
"""
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_layout as CL  # noqa: E402
import embed  # noqa: E402
import layout_const as K  # noqa: E402
import layout_model as M  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"
DOCS = sorted((ROOT / "docs/examples").glob("*.svg")) + [ROOT / "docs/example.svg"]
SLIDES = sorted((ROOT / "docs/examples/slides").glob("*.svg"))


def num(v):
    return float(v) if v not in (None, "") else 0.0


class Draft:
    """One example as absolute-coordinate lists of rects, images, texts, segments, circles."""

    def __init__(self, path, mode):
        out, _, problems = embed.unembed(path.read_text(encoding="utf-8"))
        assert not problems, problems
        self.name, self.mode = path.stem if path.parent.name != "slides" else "slides/" + path.stem, mode
        self.root = ET.fromstring(out)
        vb = [num(v) for v in self.root.get("viewBox").split()]
        self.w, self.h = vb[2], vb[3]
        self.rects, self.images, self.texts, self.segs, self.circles, self.defs = [], [], [], [], [], []
        self._walk(self.root, 0.0, 0.0)
        self.badges = {(i["x"], i["y"]): i for i in self.images if i["ref"].startswith("group/") or i["w"] < 40}
        self.icons = [i for i in self.images if (i["x"], i["y"]) not in self.badges]
        self.boxes = []          # container rects with their group type
        for r in self.rects:
            if r["stroke"] and r["fill"] == "none":
                b = self.badges.get((r["x"], r["y"]))
                r["type"] = K.group_type_of(r["stroke"], r["dash"], b["ref"] if b else None)
                r["badge"] = b
                self.boxes.append(r)

    def _walk(self, el, ox, oy):
        dx, dy = CL.translate(el)
        ox, oy = ox + dx, oy + dy
        tag = el.tag.replace(NS, "")
        g = el.get
        if tag == "defs":
            self.defs.append(el)
            return
        if tag == "rect":
            x, y = num(g("x")) + ox, num(g("y")) + oy
            self.rects.append({"x": x, "y": y, "w": num(g("width")), "h": num(g("height")),
                               "x1": x + num(g("width")), "y1": y + num(g("height")),
                               "stroke": g("stroke") if g("stroke", "none") != "none" else None,
                               "sw": num(g("stroke-width")), "dash": g("stroke-dasharray"),
                               "fill": g("fill", "")})
        elif tag == "image":
            self.images.append({"x": num(g("x")) + ox, "y": num(g("y")) + oy, "w": num(g("width")),
                                "h": num(g("height")), "ref": g("href", "")[len("bundle:"):]})
        elif tag == "text":
            self.texts.append({"s": "".join(el.itertext()).strip(), "x": num(g("x")) + ox, "y": num(g("y")) + oy,
                               "fs": num(g("font-size")), "fill": (g("fill") or "").upper(),
                               "weight": g("font-weight", ""), "anchor": g("text-anchor", "start")})
        elif tag in ("line", "polyline"):
            if tag == "line":
                pts = [(num(g("x1")), num(g("y1"))), (num(g("x2")), num(g("y2")))]
            else:
                v = [num(p) for p in re.split(r"[ ,]+", g("points").strip())]
                pts = list(zip(v[::2], v[1::2]))
            pts = [(x + ox, y + oy) for x, y in pts]
            self.segs += [(p, q) for p, q in zip(pts, pts[1:])]
        elif tag == "circle":
            self.circles.append({"cx": num(g("cx")) + ox, "cy": num(g("cy")) + oy, "r": num(g("r"))})
        for c in el:
            self._walk(c, ox, oy)

    def parent(self, x0, y0, x1, y1, exclude=None):
        """Smallest container rect holding the box (overlays excluded)."""
        best = None
        for r in self.boxes:
            if r is exclude or r["type"] in K.OVERLAY_TYPES:
                continue
            if r["x"] <= x0 and r["y"] <= y0 and x1 <= r["x1"] and y1 <= r["y1"] and \
                    (r["x"], r["y"], r["x1"], r["y1"]) != (x0, y0, x1, y1):
                if best is None or r["w"] * r["h"] < best["w"] * best["h"]:
                    best = r
        return best

    def title(self, r):
        st = K.style(r["type"])
        for t in self.texts:
            if t["weight"] == "600" and abs(t["y"] - (r["y"] + st.title_dy)) < 1 and \
                    abs(t["x"] - (r["x"] + st.title_dx)) < 1:
                return t
        return None

    def cidr(self, r):
        t0 = self.title(r)
        if not t0:
            return None
        return next((t for t in self.texts if t["fs"] == 12 and abs(t["x"] - t0["x"]) < 0.5
                     and abs(t["y"] - (r["y"] + K.CIDR_DY)) < 0.5 and CL.CIDR_IN.search(t["s"])), None)

    def label_stack(self, i):
        cx = i["x"] + i["w"] / 2
        return sorted((t for t in self.texts if t["anchor"] == "middle" and abs(t["x"] - cx) < 0.5
                       and i["y"] + i["h"] < t["y"] <= i["y"] + i["h"] + K.NODE_LABEL_DY + K.SUB_PITCH * 4),
                      key=lambda t: t["y"])


def load_all():
    return [Draft(p, "document") for p in DOCS] + [Draft(p, "slide") for p in SLIDES]


DRAFTS = load_all()


class GroupStyleTest(unittest.TestCase):
    def test_every_container_has_a_style(self):
        for d in DRAFTS:
            for r in d.boxes:
                with self.subTest(draft=d.name, rect=(r["x"], r["y"])):
                    self.assertIsNotNone(r["type"], f"{r['stroke']} dash={r['dash']} badge={r['badge']}")

    def test_stroke_width_dash_badge(self):
        seen = set()
        for d in DRAFTS:
            for r in d.boxes:
                st = K.style(r["type"])
                seen.add(r["type"])
                with self.subTest(draft=d.name, type=r["type"], rect=(r["x"], r["y"])):
                    self.assertEqual(r["sw"], st.width)
                    if not st.any_dash:
                        self.assertEqual(r["dash"], st.dash)
                    if st.badge:
                        b = r["badge"]
                        self.assertEqual(b["ref"], st.badge)
                        self.assertEqual((b["w"], b["h"]), (st.badge_size, st.badge_size))
        self.assertTrue({"cloud", "region", "vpc", "az", "public", "private", "sg", "asg",
                         "onprem", "generic"} <= seen, seen)

    def test_header_geometry(self):
        for d in DRAFTS:
            for r in d.boxes:
                st = K.style(r["type"])
                t = d.title(r)
                with self.subTest(draft=d.name, type=r["type"], rect=(r["x"], r["y"])):
                    self.assertIsNotNone(t, "no title at the header slot")
                    self.assertEqual(t["fs"], st.title_size)
                    self.assertEqual(t["fill"], st.title_fill.upper())
                    self.assertEqual(t["weight"], K.TEXT_TITLE_WEIGHT)

    def test_cidr_line(self):
        n = 0
        for d in DRAFTS:
            for t in d.texts:
                if t["fs"] == 12 and CL.BARE_CIDR.match(t["s"]) and t["anchor"] == "start":
                    owner = [r for r in d.boxes if abs(t["y"] - (r["y"] + K.CIDR_DY)) < 0.5
                             and d.title(r) and abs(d.title(r)["x"] - t["x"]) < 0.5]
                    with self.subTest(draft=d.name, cidr=t["s"]):
                        self.assertTrue(owner, "CIDR line not at title x, box.y + 34")
                        self.assertEqual(t["fill"], K.TEXT_CIDR.fill)
                        n += 1
        self.assertGreater(n, 10)


class NodeTest(unittest.TestCase):
    def test_label_stack(self):
        for d in DRAFTS:
            for i in d.icons:
                stack = d.label_stack(i)
                with self.subTest(draft=d.name, icon=i["ref"], at=(i["x"], i["y"])):
                    self.assertEqual(i["w"], K.S_DEFAULT)
                    self.assertTrue(stack, "no label under the icon")
                    self.assertEqual(stack[0]["y"], i["y"] + i["h"] + K.NODE_LABEL_DY)
                    self.assertEqual(stack[0]["fs"], K.label_size(i["w"]))
                    self.assertEqual(stack[0]["fill"], K.TEXT_NODE.fill)
                    for prev, t in zip(stack, stack[1:]):
                        self.assertEqual(t["y"] - prev["y"], K.SUB_PITCH)
                        self.assertEqual((t["fs"], t["fill"]), (K.TEXT_SUB.size, K.TEXT_SUB.fill))

    def test_masks(self):
        n = 0
        for d in DRAFTS:
            mc = K.mode(d.mode)
            for r in d.rects:
                if r["stroke"] or r["fill"].upper() != K.WHITE or r["w"] >= d.w:
                    continue
                icon = next(i for i in d.icons if i["y"] == r["y"] and abs(i["x"] + i["w"] / 2 - (r["x"] + r["w"] / 2)) < 0.5)
                label = d.label_stack(icon)[0]
                with self.subTest(draft=d.name, mask=(r["x"], r["y"])):
                    want_w = max(K.S_DEFAULT, M.layout_text_width(label["s"], label["fs"]) + 8)
                    self.assertEqual(r["w"], want_w)
                    self.assertEqual(r["h"], K.S_DEFAULT + mc.mask_extra)
                    # the gateway's icon center is on its VPC's left or right border
                    vpcs = [b for b in d.boxes if b["type"] == "vpc" and b["y"] < r["y"] < b["y1"]]
                    self.assertTrue(any(icon["x"] + 24 in (b["x"], b["x1"]) for b in vpcs))
                    n += 1
        self.assertGreaterEqual(n, 10)


# Insets an example draws tighter than the style table's minimum, on purpose: bedrock-dx's
# Regions sit Cloud + 34 (the slide value; every other document example 40), and the
# docs/example.svg skeleton's AZ 2 EC2 sits subnet + 30 (document examples 32-56).
TIGHTER = {("bedrock-dx-reference-architecture", "region", "cloud"),
           ("example", "service/Amazon-EC2", "private")}


class InsetTest(unittest.TestCase):
    """The style table's top insets are minimums every example keeps (but TIGHTER)."""

    def test_nested_box_top(self):
        for d in DRAFTS:
            for r in d.boxes:
                if r["type"] in K.OVERLAY_TYPES:
                    continue
                p = d.parent(r["x"], r["y"], r["x1"], r["y1"], exclude=r)
                if not p:
                    continue
                want = K.top_inset(p["type"], d.mode, "box", cidr=d.cidr(p) is not None)
                if (d.name, r["type"], p["type"]) in TIGHTER:
                    continue
                with self.subTest(draft=d.name, child=r["type"], parent=p["type"], at=(r["x"], r["y"])):
                    self.assertGreaterEqual(r["y"] - p["y"], want)

    def test_icon_top_and_label_bottom(self):
        for d in DRAFTS:
            mc = K.mode(d.mode)
            for i in d.icons:
                p = d.parent(i["x"], i["y"], i["x"] + i["w"], i["y"] + i["h"])
                if not p:
                    continue
                want = K.top_inset(p["type"], d.mode, "icon", cidr=d.cidr(p) is not None)
                last = d.label_stack(i)[-1]["y"]
                if (d.name, i["ref"], p["type"]) in TIGHTER and i["y"] - p["y"] < want:
                    continue
                with self.subTest(draft=d.name, icon=i["ref"], parent=p["type"], at=(i["x"], i["y"])):
                    self.assertGreaterEqual(i["y"] - p["y"], want)
                    self.assertGreaterEqual(p["y1"] - last, mc.label_bottom)

    def test_overlay_icons_under_the_header(self):
        for d in DRAFTS:
            for r in d.boxes:
                if r["type"] not in K.OVERLAY_TYPES:
                    continue
                t = d.title(r)
                title_x1 = t["x"] + M.text_width(t["s"], t["fs"])
                for i in d.icons:
                    if not (r["x"] <= i["x"] and i["x"] + i["w"] <= r["x1"] and r["y"] <= i["y"] <= r["y1"]):
                        continue
                    with self.subTest(draft=d.name, at=(i["x"], i["y"])):
                        self.assertGreaterEqual(i["y"] - r["y"], K.OVERLAY_HEADER_GAP)
                        if i["x"] < title_x1 and i["y"] < r["y"] + 60:
                            self.assertGreaterEqual(i["y"] - r["y"], K.top_inset("asg", d.mode, "icon"))

    def test_slide_pads(self):
        for d in DRAFTS:
            if d.mode != "slide":
                continue
            for r in d.boxes:
                p = d.parent(r["x"], r["y"], r["x1"], r["y1"], exclude=r)
                if not p or r["type"] in K.OVERLAY_TYPES:
                    continue
                with self.subTest(draft=d.name, child=r["type"], at=(r["x"], r["y"])):
                    self.assertGreaterEqual(min(r["x"] - p["x"], p["x1"] - r["x1"], p["y1"] - r["y1"]), K.SLIDE.pad)

    def test_az_gap(self):
        for d in DRAFTS:
            azs = sorted((r for r in d.boxes if r["type"] == "az"), key=lambda r: (r["x"], r["y"]))
            for a, b in zip(azs, azs[1:]):
                if a["x"] != b["x"]:
                    continue
                # the AZ gap holds a node of the VPC (LB, IGW, firewall); with nothing between
                # them stacked AZ boxes are plain siblings (layout_spec.md "Tracks")
                vpc = min((v for v in d.boxes if v["type"] == "vpc" and v["x"] <= a["x"] and a["x1"] <= v["x1"]
                           and v["y"] <= a["y"] and b["y1"] <= v["y1"]), key=lambda v: v["x1"] - v["x"], default=None)
                lo, hi = (vpc["x"] - 24, vpc["x1"] + 24) if vpc else (a["x"], a["x1"])
                between = any(lo <= i["x"] + i["w"] / 2 <= hi and a["y1"] < i["y"] + i["h"] / 2 < b["y"]
                              for i in d.icons)
                with self.subTest(draft=d.name, gap=(a["y1"], b["y"])):
                    if not between:
                        self.assertGreaterEqual(b["y"] - a["y1"], 8)
                    elif d.mode == "slide":
                        self.assertEqual(b["y"] - a["y1"], K.SLIDE.az_gap)
                    elif "example" not in d.name and "bedrock" not in d.name:
                        self.assertGreaterEqual(b["y"] - a["y1"], K.DOCUMENT.az_gap)


class EdgeTest(unittest.TestCase):
    def _note_area(self, d):
        r = next((r for r in d.rects if r["fill"].upper() == K.NOTE_FILL), None)
        return r

    def test_step_badges_on_their_hop(self):
        good = total = 0
        for d in DRAFTS:
            note = self._note_area(d)
            for c in d.circles:
                if c["r"] != K.BADGE_R:
                    continue
                if note and note["x"] <= c["cx"] <= note["x1"] and note["y"] <= c["cy"] <= note["y1"]:
                    continue
                if d.mode == "slide" and c["cy"] > max(b["y1"] for b in d.boxes if b["type"] == "cloud"):
                    continue    # slide note line
                total += 1
                h = any(abs(p[1] - q[1]) < .1 and min(p[0], q[0]) <= c["cx"] <= max(p[0], q[0])
                        and p[1] - c["cy"] == K.BADGE_DY for p, q in d.segs)
                v = any(abs(p[0] - q[0]) < .1 and min(p[1], q[1]) <= c["cy"] <= max(p[1], q[1])
                        and p[0] - c["cx"] == K.VBADGE_DX for p, q in d.segs)
                good += h or v
        # the exceptions are bedrock-dx's bus drops (badge under the bus) and nfw's badge 1
        self.assertGreaterEqual(good / total, 0.85, f"{good}/{total}")

    def test_connector_labels(self):
        above = below = 0
        for d in DRAFTS:
            mc = K.mode(d.mode)
            for t in d.texts:
                if t["fs"] != 12 or t["anchor"] != "middle" or t["weight"]:
                    continue
                if any(t in d.label_stack(i) for i in d.icons):
                    continue
                for p, q in d.segs:
                    if abs(p[1] - q[1]) < .1 and min(p[0], q[0]) <= t["x"] <= max(p[0], q[0]):
                        if p[1] - t["y"] in (mc.label_above, mc.label_above - 1):
                            above += 1
                        elif t["y"] - p[1] == mc.label_below:
                            below += 1
        self.assertGreater(above, 20)
        self.assertEqual(below, 0)          # labels go above a horizontal line, badge or not


class NoteTest(unittest.TestCase):
    def test_panel(self):
        n = 0
        for d in DRAFTS:
            for r in d.rects:
                if r["fill"].upper() != K.NOTE_FILL or r["x"] != K.PANEL_X or r["w"] == K.PANE_W_WIDE \
                        or r["y"] == min(b["y"] for b in d.boxes):
                    continue
                cloud = next(b for b in d.boxes if b["type"] == "cloud")
                rows = sorted({t["y"] for t in d.texts if r["y"] < t["y"] < r["y1"]})
                with self.subTest(draft=d.name):
                    self.assertEqual((r["stroke"], r["sw"]), (K.NOTE_STROKE, K.NOTE_STROKE_W))
                    self.assertEqual(r["w"], d.w - 2 * K.PANEL_X)
                    self.assertEqual(r["y"], cloud["y1"] + K.PANEL_GAP)
                    self.assertEqual(d.h, r["y1"] + K.PANEL_GAP)
                    self.assertEqual(rows[0], r["y"] + K.PANEL_FIRST)
                    self.assertEqual(r["h"], K.PANEL_FIRST + K.PANEL_PITCH * (len(rows) - 1) + K.PANEL_LAST)
                    hops = [t for t in d.texts if r["y"] < t["y"] < r["y1"] and t["weight"] == "600"]
                    if hops:
                        desc_x = {t["x"] for t in d.texts if r["y"] < t["y"] < r["y1"] and t["fill"] == K.GRAY}
                        want = K.PANEL_HOP_X + max(M.text_width(t["s"], 12) for t in hops) + K.PANEL_DESC_GAP
                        self.assertEqual(len(desc_x), 1)
                        # nfw exactly, tgw rounded up (+0.4), gwlb +5.4 (its ⇄ estimated narrow)
                        self.assertTrue(want - 0.5 <= desc_x.pop() <= want + 6)
                        self.assertTrue(all(t["x"] == K.PANEL_HOP_X for t in hops))
                    else:
                        self.assertTrue(all(t["x"] == K.PANEL_ROW_X for t in d.texts if r["y"] < t["y"] < r["y1"]))
                    n += 1
        self.assertGreaterEqual(n, 5)

    def test_pane(self):
        n = 0
        for d in DRAFTS:
            cloud = next(b for b in d.boxes if b["type"] == "cloud")
            for r in d.rects:
                if r["fill"].upper() != K.NOTE_FILL or r["y"] != cloud["y"]:
                    continue
                with self.subTest(draft=d.name):
                    self.assertEqual(r["x"], K.PANE_X)
                    self.assertEqual(cloud["x"], r["x1"] + K.PANE_GAP)
                    hops = sorted((t for t in d.texts if t["weight"] == "600" and t["fs"] == 12
                                   and r["x"] < t["x"] < r["x1"] and t["y"] < r["y1"]), key=lambda t: t["y"])
                    self.assertEqual(hops[0]["y"], r["y"] + K.PANE_FIRST_CY + K.BADGE_TEXT_DY)
                    inside = sorted(t["y"] for t in d.texts if r["x"] < t["x"] < r["x1"] and r["y"] < t["y"] < r["y1"])
                    self.assertEqual(r["y1"], inside[-1] + K.PANE_END)
                    for h in hops:
                        self.assertEqual(h["x"], K.PANE_HOP_X)
                        desc = [y for y in inside if y > h["y"]]
                        self.assertEqual(desc[0], h["y"] + K.PANE_DESC_DY)
                    for h, nxt in zip(hops, hops[1:]):
                        prev = max(y for y in inside if y < nxt["y"])
                        self.assertEqual(nxt["y"], prev + K.PANE_NEXT_HOP)
                    n += 1
        self.assertEqual(n, 2)

    def test_slide_lines(self):
        n = 0
        for d in DRAFTS:
            if d.mode != "slide":
                continue
            cloud = next(b for b in d.boxes if b["type"] == "cloud")
            items = sorted((c for c in d.circles if c["cy"] > cloud["y1"]), key=lambda c: (c["cy"], c["cx"]))
            if not items:
                continue
            with self.subTest(draft=d.name):
                self.assertEqual(items[0]["cx"], cloud["x"] + K.LINES_BADGE_DX)
                self.assertGreaterEqual(items[0]["cy"], cloud["y1"] + K.LINES_FIRST_CY)
                self.assertEqual(d.h, items[-1]["cy"] + K.BADGE_TEXT_DY + K.LINES_END)
                for c, nxt in zip(items, items[1:]):
                    t = next(t for t in d.texts if t["y"] == c["cy"] + K.BADGE_TEXT_DY and t["x"] == c["cx"] + 18)
                    self.assertEqual(t["x"], c["cx"] - K.LINES_BADGE_DX + K.LINES_TEXT_DX)
                    end = t["x"] + M.text_width(t["s"], t["fs"])
                    self.assertLess(abs(nxt["cx"] - K.BADGE_R - (end + K.LINES_ITEM_GAP)), 0.05)
                n += 1
        self.assertEqual(n, 3)


class ConstTest(unittest.TestCase):
    def test_markers_and_font(self):
        for d in DRAFTS:
            with self.subTest(draft=d.name):
                self.assertEqual(d.root.get("font-family"), K.FONT_FAMILY_DEFAULT)
                for m in (m for defs in d.defs for m in defs.iter(f"{NS}marker")):
                    got = ET.tostring(m, encoding="unicode").replace(' xmlns:ns0="http://www.w3.org/2000/svg"', "")
                    got = re.sub(r"\s*\n\s*", "", got).replace("ns0:", "").replace(" />", "/>")
                    want = K.MARKER_ARROW if m.get("id") == "arrow" else K.MARKER_ARROW_START
                    self.assertEqual(got, want)

    def test_couplings(self):
        """The engine's offsets stay inside the checker's reaches (check_layout imports the
        numbers themselves from layout_const, so only how they relate is tested here)."""
        sizes = (K.MIN_FONT, K.TEXT_SUB.size, K.TEXT_NODE.size, K.label_size())
        # a line out of a node's bottom starts BOTTOM_PORT_GAP under the last baseline: its
        # glyph bottom (GLYPH_DESCENT × size above that) is within END_REACH, so it ends on the node
        for fs in sizes:
            self.assertLessEqual(K.BOTTOM_PORT_GAP - K.GLYPH_DESCENT * fs, K.END_REACH, fs)
            self.assertGreater(K.BOTTOM_PORT_GAP - K.GLYPH_DESCENT * fs, 0, fs)
        self.assertLessEqual(K.END_GAP, K.END_REACH)           # a line 4 short of an icon ends on it
        self.assertLessEqual(K.GROUP_END_GAP, K.END_REACH)     # and 4 short of a border
        for m in K.MODES.values():
            for fs in sizes:
                above = m.label_above - K.GLYPH_DESCENT * fs        # label box bottom ↔ its line
                below = m.label_below - K.GLYPH_ASCENT * fs         # its line ↔ label box top
                with self.subTest(mode=m.name, fs=fs):
                    # near enough to read as that line's label (LABEL_REACH), far enough not to skim it
                    for gap in (above, below, m.vlabel_dx):
                        self.assertLessEqual(gap, K.LABEL_REACH)
                        self.assertGreaterEqual(gap, K.LINE_CLEAR)
            self.assertEqual(m.arrow_min, K.MIN_ARROW)
        self.assertEqual(K.SLIDE.trunk_clear, K.HUG_CLEAR)
        self.assertLess(K.JUNCTION_DOT_R, K.BADGE_R)           # a step badge is never read as a junction dot
        self.assertLess(K.JOIN_REACH, K.END_REACH)
        self.assertLess(K.ON_LINE_GAP, K.IN_LINE_GAP)
        self.assertLess(K.IN_LINE_GAP, K.IN_LINE_CROSS_GAP)
        self.assertGreater(K.IN_LINE_GAP, K.PORT_PITCH)        # two fallbacks one pitch apart read as one line
        # check_layout's own derived header thresholds come from the group styles
        self.assertEqual(CL.CIDR_PITCH, K.SUB_PITCH)
        self.assertEqual(CL.NESTED_TOP_CIDR, K.CIDR_TOP_BOX[0])
        self.assertLess(K.BADGE_SIZE, CL.CLOUD_BADGE_MIN)
        self.assertLessEqual(CL.CLOUD_BADGE_MIN, K.CLOUD_BADGE_SIZE)
        self.assertLess(2 * K.BADGE_R, CL.GROUP_BADGE_MIN)
        self.assertLess(CL.GROUP_BADGE_MIN, K.BADGE_SIZE)
        self.assertTrue(CL.slide_fits(K.SLIDE_MAX_W, K.SLIDE_MAX_H[True], True))
        self.assertTrue(CL.slide_fits(K.SLIDE_MAX_W, K.SLIDE_MAX_H[False], False))
        self.assertFalse(CL.slide_fits(K.SLIDE_MAX_W + 4, K.SLIDE_MAX_H[True], True))
        self.assertFalse(CL.slide_fits(K.SLIDE_MAX_W, K.SLIDE_MAX_H[True] + 4, True))

    def test_slide_fit(self):
        src = (ROOT / "scripts/svg2pptx.py").read_text(encoding="utf-8")
        emu = {k: int(v) for k, v in re.findall(r"^(MARGIN|TITLE_H)\s*=\s*Emu\((\d+)\)", src, re.M)}
        w_emu, h_emu = map(int, re.search(r"SLIDE_W, SLIDE_H = Emu\((\d+)\), Emu\((\d+)\)", src).groups())
        self.assertEqual((w_emu - 2 * emu["MARGIN"]) / 12700, K.SLIDE_AVAIL_W_PT)
        self.assertEqual((h_emu - 2 * emu["MARGIN"] - emu["TITLE_H"]) / 12700, K.SLIDE_AVAIL_H_PT[True])
        self.assertEqual((h_emu - 2 * emu["MARGIN"]) / 12700, K.SLIDE_AVAIL_H_PT[False])
        self.assertEqual(int(re.search(r"^MIN_PT = (\d+)", src, re.M).group(1)), K.SLIDE_MIN_PT)
        self.assertAlmostEqual(K.slide_pt(1108, 540), 10.0, places=1)
        self.assertLess(K.slide_pt(1108, 544), 10.0)        # QR 190: the GWLB slide at 544 is 9.9pt
        self.assertAlmostEqual(K.slide_pt(1108, 600, title=False), 10.0, places=1)

    def test_group_type_lookup(self):
        for st in K.GROUP_STYLES.values():
            self.assertEqual(K.group_type_of(st.stroke.lower(), st.dash, st.badge), st.type)
        self.assertEqual(K.group_type_of("#7D8998", "6,4", None), "generic")
        self.assertIsNone(K.group_type_of("#123456", None, None))
        self.assertEqual(K.top_inset("vpc", "document", "box", cidr=True), 46)
        self.assertEqual(K.top_inset("private", "document", "icon", cidr=True), 50)
        self.assertEqual(K.top_inset("private", "slide", "icon"), 28)
        self.assertEqual(K.top_inset("cloud", "slide", "box"), 34)


class ModelTest(unittest.TestCase):
    def test_text_width(self):
        self.assertAlmostEqual(M.text_width("IGW", 14), 3 * 0.55 * 14)
        self.assertAlmostEqual(M.layout_text_width("IGW", 14), 3 * 0.6 * 14)
        self.assertEqual(M.layout_text_width("방화벽", 12), 36)
        self.assertAlmostEqual(M.layout_text_width("A → B", 12), 4 * 0.6 * 12 + 12)
        for s in ("TGW ENI → 방화벽", "Region ap-northeast-2", "동기식 복제"):
            self.assertGreaterEqual(M.layout_text_width(s, 12), M.text_width(s, 12))

    def test_fmt_num(self):
        for v, s in ((222, "222"), (222.0, "222"), (179.4, "179.4"), (179.400001, "179.4"), (-8, "-8"),
                     (0.004, "0"), (-0.001, "0"), (1514.256, "1514.26"), (12.5, "12.5")):
            self.assertEqual(M.fmt_num(v), s)

    def test_boxes_and_text(self):
        b = M.Box.xywh(10, 20, 48, 48)
        self.assertEqual((b.cx, b.cy, b.x1, b.y1), (34, 44, 58, 68))
        self.assertTrue(CL.seg_hits_box((0, 44), (100, 44), b.t()))
        t = M.TextLine("NAT gateway", 34, 86, 14, K.INK, anchor="middle")
        tb = t.box()
        self.assertAlmostEqual(tb.cx, 34)
        self.assertEqual((tb.y0, tb.y1), (86 - 10.5, 86 + 3.5))
        self.assertGreater(t.box(conservative=True).w, tb.w)
        ng = M.NodeGeom("nat", 34, 44, b, [t, M.TextLine("0.0.0.0/0 → IGW", 34, 102, 12, K.GRAY, anchor="middle")])
        self.assertEqual(ng.last_baseline, 102)
        self.assertTrue(ng.footprint().contains(b))

    def test_ids(self):
        self.assertEqual(M.split_eid("edge:3:label"), ("edge", "3", "label"))
        self.assertEqual(M.split_eid("node:nat.1"), ("node", "nat.1", ""))
        self.assertEqual(M.g_id("edge:3", K.Z_EDGE), "edge:3")
        self.assertEqual(M.g_id("edge:3", K.Z_EDGE_LABEL), "edge:3:label")
        self.assertEqual(M.g_id("edge:3", K.Z_BADGE), "edge:3:badge")
        self.assertEqual(M.g_id("node:igw", K.Z_NODE), "node:igw")
        self.assertEqual(M.g_id("raw:0", K.Z_RAW_ABOVE), "raw:0")

    def test_factories(self):
        r = M.el_rect(M.Box.xywh(16, 16, 100, 50), stroke="#00A4A6", width=2, dash="3,3", owner="group:r")
        self.assertEqual(list(r.attrs), ["x", "y", "width", "height", "fill", "stroke", "stroke-width",
                                         "stroke-dasharray"])
        p = M.el_path([(0, 0), (10, 0), (10, 10)], dash=K.DASH_DASHED, end=True, owner="edge:0")
        self.assertEqual((p.kind, p.attrs["points"], p.attrs["marker-end"]), ("polyline", "0,0 10,0 10,10", "url(#arrow)"))
        ln = M.el_path([(0, 0), (10, 0)], start=True, end=True)
        self.assertEqual((ln.kind, ln.attrs["marker-start"]), ("line", "url(#arrowStart)"))
        c, t = M.el_badge(645, 208, 3, owner="edge:2")
        self.assertEqual((c.attrs["r"], c.attrs["fill"], t.attrs["y"], t.text, t.attrs["font-weight"]),
                         (10, "#232F3E", 212, "3", "700"))
        self.assertEqual(c.z, K.Z_BADGE)

    def test_gap_and_expr(self):
        g = M.Geometry("document", 48, 400, 200, cols={"a": 50, "b": 350}, rows={"r": 100})
        g.nodes["n1"] = M.NodeGeom("n1", 50, 100, M.Box(26, 76, 74, 124))
        g.nodes["n2"] = M.NodeGeom("n2", 350, 100, M.Box(326, 76, 374, 124))
        g.groups["box"] = M.GroupGeom("box", M.Box(100, 20, 300, 180))
        # free corridors 74–100, 100–300, 300–326: the widest is the box interior
        self.assertEqual(g.gap("a", "b"), 200)
        self.assertEqual(M.eval_expr(M.Expr("group", "box", "x1", offset=-20), g), 280)
        self.assertEqual(M.eval_expr(M.Expr("node", "n1", "cx", offset=4), g), 54)
        self.assertEqual(M.eval_expr(M.Expr("col", "b"), g), 350)
        self.assertEqual(M.eval_expr(M.Expr("gap", "a", ref2="b", offset=8), g), 208)
        self.assertEqual(M.eval_expr(M.Expr("num", offset=7), g), 7)

    def test_note_below(self):
        self.assertEqual(M.NoteBlock("panel", w=1340, h=140).below(), 172)
        self.assertEqual(M.NoteBlock("lines", h=34).below(), 34)
        self.assertEqual(M.NoteBlock("pane", w=320, h=268).below(), 0)

    def test_edge_ops(self):
        e = M.Edge(0, "a", "b", "<..>")
        self.assertEqual((e.dashed, e.head_end, e.head_start), (True, True, True))
        e = M.Edge(1, "a", "b", "--")
        self.assertEqual((e.dashed, e.head_end, e.head_start), (False, False, False))

    def test_spec_helpers(self):
        sp = M.Spec("x")
        sp.groups["cloud"] = M.Group("cloud", "cloud", "AWS Cloud")
        sp.groups["r"] = M.Group("r", "region", "Region", parent="cloud", depth=1)
        sp.nodes["n"] = M.Node("n", "service/Amazon-EC2", "EC2", parent="r")
        self.assertEqual(sp.cloud_id(), "cloud")
        self.assertEqual(sp.node_chain("n"), ["r", "cloud"])
        self.assertEqual(sp.kind("r"), "group")
        self.assertIs(sp.const, K.DOCUMENT)
        with self.assertRaises(M.SpecError) as cm:
            raise M.SpecError(["nodes[0] n: bad"])
        self.assertEqual(cm.exception.problems, ["nodes[0] n: bad"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
