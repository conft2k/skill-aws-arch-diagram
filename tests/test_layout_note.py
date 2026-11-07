#!/usr/bin/env python3
"""layout_note.block against the notes of the reference examples.

    python3 tests/test_layout_note.py

Each example in docs/examples (7 documents, 5 slides) is turned back into a draft in memory
(embed.unembed). From it the test reads the AWS Cloud box, the top-level groups and nodes,
the drawing box (group rects, icons, node label stacks) and the note's own text, builds a
Spec and a Geometry by hand, calls block() and compares:
  - the place auto picks with the place the example uses (12 examples);
  - every note element (rect, badges, hop / description / summary / slide texts) with the
    example's, coordinates within ±2;
  - the pane's wrapped line count per step, its width (300 / 320 / left column) and that
    its Requirements hold on the example;
  - the canvas bottom the note implies (NoteBlock.below() / pane h).
Known deviations of the examples from the rule are listed in KNOWN with the reason.
"""
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_layout as CL  # noqa: E402
import embed  # noqa: E402
import layout_const as K  # noqa: E402
import layout_model as M  # noqa: E402
import layout_note as N  # noqa: E402
from layout_text import font_context, svg_factor, svg_steps  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"
TOL = 2.0
DOC_NAMES = ("nfw", "alb", "gwlb", "tgw", "nlb", "nlb-mtls", "bedrock-dx")
SLIDE_NAMES = ("alb", "gwlb", "nfw", "nlb", "tgw")
EXPECT_PLACE = {("document", n): "panel" for n in ("nfw", "alb", "gwlb", "tgw", "nlb")}
EXPECT_PLACE.update({("document", "nlb-mtls"): "pane", ("document", "bedrock-dx"): "pane"})
EXPECT_PLACE.update({("slide", n): "lines" for n in ("gwlb", "nfw", "tgw")})
EXPECT_PLACE.update({("slide", n): "none" for n in ("alb", "nlb")})   # the slides drop the summary

# Where an example is off the rule on purpose or by hand rounding; (dx, dy) of the example vs the rule.
KNOWN = {
    # description column 165 = 56 + 87.6 + 16 + 5.4: the example estimated "⇄" narrow
    ("document", "gwlb"): {"desc_dx": 5.4},
    # first badge cy = Cloud bottom + 22 (the rule's minimum is + 18): the example fills the 540 canvas
    ("slide", "nfw"): {"dy": 4.0},
}


def num(v):
    return float(v) if v not in (None, "") else 0.0


class Draft:
    """One example: rects, images, texts, circles in absolute coordinates."""

    def __init__(self, name, mode):
        p = ROOT / "docs/examples" / ("slides" if mode == "slide" else "") / f"{name}-reference-architecture.svg"
        out, _, problems = embed.unembed(p.read_text(encoding="utf-8"))
        assert not problems, problems
        self.name, self.mode = name, mode
        self.root = root = ET.fromstring(out)
        vb = [num(v) for v in root.get("viewBox").split()]
        self.w, self.h = vb[2], vb[3]
        self.rects, self.images, self.texts, self.circles = [], [], [], []
        self._walk(root, 0.0, 0.0)
        self.note_rect = next((r for r in self.rects if r["fill"].upper() == K.NOTE_FILL), None)
        self.boxes = [r for r in self.rects if r["stroke"] and r["fill"] == "none"]
        self.cloud = next(r for r in self.boxes if r["stroke"].upper() == "#232F3E" and r["sw"] == 2
                          and any(i["ref"] == "group/AWS-Cloud-logo_32" and i["x"] == r["x"] and i["y"] == r["y"]
                                  for i in self.images))
        corners = {(r["x"], r["y"]) for r in self.boxes}
        self.icons = [i for i in self.images if i["w"] >= 40 and (i["x"], i["y"]) not in corners]

    def _walk(self, el, ox, oy, owner=""):
        dx, dy = CL.translate(el)
        ox, oy = ox + dx, oy + dy
        tag, g = el.tag.replace(NS, ""), el.get
        owner = g("id", owner)
        if tag == "defs":
            return
        if tag == "rect" and g("x") is not None:
            x, y = num(g("x")) + ox, num(g("y")) + oy
            self.rects.append({"x": x, "y": y, "w": num(g("width")), "h": num(g("height")),
                               "x1": x + num(g("width")), "y1": y + num(g("height")),
                               "stroke": g("stroke") if g("stroke", "none") != "none" else None,
                               "sw": num(g("stroke-width")), "fill": g("fill", "")})
        elif tag == "image":
            self.images.append({"x": num(g("x")) + ox, "y": num(g("y")) + oy, "w": num(g("width")),
                                "h": num(g("height")), "ref": g("href", "")[len("bundle:"):], "owner": owner})
        elif tag == "text":
            self.texts.append({"s": "".join(el.itertext()).strip(), "x": num(g("x")) + ox, "y": num(g("y")) + oy,
                               "fs": num(g("font-size")), "fill": (g("fill") or "").upper(),
                               "weight": g("font-weight", ""), "anchor": g("text-anchor", "start"), "owner": owner})
        elif tag == "circle":
            self.circles.append({"cx": num(g("cx")) + ox, "cy": num(g("cy")) + oy, "r": num(g("r"))})
        for c in el:
            self._walk(c, ox, oy, owner)

    # --- the note as the example draws it -------------------------------------------
    def note_area(self):
        """Box holding the note: its rect, or (slides) everything below the Cloud."""
        if self.note_rect:
            r = self.note_rect
            return M.Box(r["x"], r["y"], r["x1"], r["y1"])
        return M.Box(0, self.cloud["y1"] + 1, self.w, self.h)

    def note_texts(self):
        a = self.note_area()
        return [t for t in self.texts if a.x0 < t["x"] < a.x1 and a.y0 < t["y"] < a.y1 and t["fill"] != K.WHITE]

    def note_circles(self):
        a = self.note_area()
        return sorted((c for c in self.circles if a.x0 < c["cx"] < a.x1 and a.y0 < c["cy"] < a.y1),
                      key=lambda c: (c["cy"], c["cx"]))

    def note_digits(self):
        a = self.note_area()
        return [t for t in self.texts if a.x0 < t["x"] < a.x1 and a.y0 < t["y"] < a.y1 and t["fill"] == K.WHITE]

    def note_spec(self):
        """NoteSpec read back from the example's note text (None when it has no note)."""
        texts = sorted(self.note_texts(), key=lambda t: (t["y"], t["x"]))
        if not texts:
            return None
        if self.mode == "slide":
            return M.NoteSpec(steps=[(t["s"], "") for t in texts])
        hops = [t for t in texts if t["weight"] == "600"]
        if not hops:
            return M.NoteSpec(summary=texts[0]["s"])
        if self.note_rect["y"] == self.cloud["y"]:        # pane: descriptions under each hop
            steps, cur = [], None
            for t in texts:
                if t["weight"] == "600":
                    cur = [t["s"], []]
                    steps.append(cur)
                else:
                    cur[1].append(t["s"])
            return M.NoteSpec(steps=[(h, " ".join(d)) for h, d in steps])
        return M.NoteSpec(steps=[(h["s"], next(t["s"] for t in texts if t["y"] == h["y"] and t is not h))
                                 for h in hops])

    def pane_lines(self):
        """Description line count per step in a pane."""
        texts = sorted(self.note_texts(), key=lambda t: t["y"])
        out = []
        for t in texts:
            if t["weight"] == "600":
                out.append(0)
            else:
                out[-1] += 1
        return out

    # --- the Spec and Geometry the note module sees -------------------------------------
    def label_stack(self, i):
        cx = i["x"] + i["w"] / 2
        return sorted((t for t in self.texts if t["anchor"] == "middle" and abs(t["x"] - cx) < 0.5
                       and (not i["owner"].startswith("node:") or t["owner"] == i["owner"])
                       and i["y"] + i["h"] < t["y"] <= i["y"] + i["h"] + K.NODE_LABEL_DY + K.SUB_PITCH * 4),
                      key=lambda t: t["y"])

    def inside_box(self, x0, y0, x1, y1, exclude=None):
        return any(r is not exclude and r["x"] <= x0 and r["y"] <= y0 and x1 <= r["x1"] and y1 <= r["y1"]
                   for r in self.boxes)

    def build(self):
        S = K.S_DEFAULT
        groups, ggeo = {}, {}
        cid = "cloud"
        groups[cid] = M.Group(cid, "cloud", "AWS Cloud")
        c = self.cloud
        ggeo[cid] = M.GroupGeom(cid, M.Box(c["x"], c["y"], c["x1"], c["y1"]))
        for k, r in enumerate(self.boxes):
            if r is c or self.inside_box(r["x"], r["y"], r["x1"], r["y1"], exclude=r):
                continue
            gid = f"g{k}"
            groups[gid] = M.Group(gid, "generic", None)
            ggeo[gid] = M.GroupGeom(gid, M.Box(r["x"], r["y"], r["x1"], r["y1"]))
        nodes, ngeo = {}, {}
        drawing = [g.rect for g in ggeo.values()]
        for k, i in enumerate(self.icons):
            nid = f"n{k}"
            cx, cy = i["x"] + i["w"] / 2, i["y"] + i["h"] / 2
            lines = [M.TextLine(t["s"], t["x"], t["y"], t["fs"], t["fill"], t["weight"], "middle")
                     for t in self.label_stack(i)]
            top = not self.inside_box(i["x"], i["y"], i["x"] + i["w"], i["y"] + i["h"])
            nodes[nid] = M.Node(nid, "x/y", lines[0].text if lines else "", parent=None if top else cid,
                                col=f"c{round(cx)}")
            ng = M.NodeGeom(nid, cx, cy, M.Box(i["x"], i["y"], i["x"] + i["w"], i["y"] + i["h"]), lines)
            ngeo[nid] = ng
            drawing.append(ng.footprint(conservative=False))
        spec = M.Spec(self.name, mode=self.mode, groups=groups, nodes=nodes, note=self.note_spec())
        geom = M.Geometry(self.mode, S, self.w, self.h, {}, {}, groups=ggeo, nodes=ngeo,
                          drawing=M.union_all(drawing))
        return spec, geom


def load(mode, names):
    return {n: Draft(n, mode) for n in names}


DOCS = load("document", DOC_NAMES)
SLIDES = load("slide", SLIDE_NAMES)
ALL = [("document", d) for d in DOCS.values()] + [("slide", d) for d in SLIDES.values()]


def elements(nb):
    """(rects, circles, texts) of a NoteBlock as plain dicts."""
    rects = [e.attrs for e in nb.elements if e.kind == "rect"]
    circles = [e.attrs for e in nb.elements if e.kind == "circle"]
    texts = [dict(e.attrs, s=e.text) for e in nb.elements if e.kind == "text"]
    return rects, circles, texts


class AutoPlaceTest(unittest.TestCase):
    def test_auto_matches_examples(self):
        for mode, d in ALL:
            with font_context(svg_factor(d.root), svg_steps(d.root)), self.subTest(example=f"{mode}/{d.name}"):
                spec, geom = d.build()
                nb = N.block(spec, geom)
                self.assertEqual(nb.place, EXPECT_PLACE[(mode, d.name)], nb.warnings)

    def test_ratio_and_slide_fit(self):
        # the drawings behind the decision: panels flat, panes tall; slide panes never fit
        for mode, d in ALL:
            spec, geom = d.build()
            if spec.note is None or not spec.note.steps:
                continue
            dr = geom.drawing
            with self.subTest(example=f"{mode}/{d.name}"):
                if mode == "document":
                    self.assertEqual(dr.h > K.PANE_RATIO * dr.w, EXPECT_PLACE[(mode, d.name)] == "pane")
                else:
                    self.assertGreater(K.PANE_X + K.PANE_W + K.PANE_GAP + dr.w + spec.const.canvas_margin,
                                       K.SLIDE_MAX_W)

    def test_slide_never_panel(self):
        spec, geom = SLIDES["nfw"].build()
        nb = N.block(spec, geom, place="panel")
        self.assertEqual(nb.place, "lines")
        self.assertTrue(any("panel" in w for w in nb.warnings))

    def test_none(self):
        spec, geom = SLIDES["alb"].build()
        self.assertIsNone(spec.note)
        nb = N.block(spec, geom)
        self.assertEqual((nb.place, nb.below(), nb.elements, nb.requirements), ("none", 0.0, [], []))

    def test_forced_places(self):
        spec, geom = DOCS["nlb-mtls"].build()
        self.assertEqual(N.block(spec, geom, place="panel").place, "panel")
        spec, geom = DOCS["nfw"].build()
        self.assertEqual(N.block(spec, geom, place="pane").place, "pane")
        spec, geom = DOCS["alb"].build()          # a summary never goes in the pane
        nb = N.block(spec, geom, place="pane")
        self.assertEqual(nb.place, "panel")
        self.assertTrue(nb.warnings)


class PanelTest(unittest.TestCase):
    def test_panels(self):
        for name in ("nfw", "alb", "gwlb", "tgw", "nlb"):
            d = DOCS[name]
            known = KNOWN.get(("document", name), {})
            with font_context(svg_factor(d.root), svg_steps(d.root)), self.subTest(example=name):
                spec, geom = d.build()
                self.assertLessEqual(abs(geom.drawing.y1 - d.cloud["y1"]), TOL)
                nb = N.block(spec, geom)
                self.assertEqual(nb.place, "panel")
                r = d.note_rect
                rects, circles, texts = elements(nb)
                self.assertEqual(len(rects), 1)
                for k, v in (("x", r["x"]), ("y", r["y"]), ("width", r["w"]), ("height", r["h"])):
                    self.assertLessEqual(abs(rects[0][k] - v), TOL, k)
                self.assertEqual((rects[0]["fill"], rects[0]["stroke"], rects[0]["stroke-width"]),
                                 (K.NOTE_FILL, K.NOTE_STROKE, K.NOTE_STROKE_W))
                self.assertEqual((rects[0]["x"], rects[0]["width"]), (K.PANEL_X, geom.canvas_w - 2 * K.PANEL_X))
                self.assertLessEqual(abs(geom.drawing.y1 + nb.below() - d.h), TOL)   # canvas ends 16 below
                self._same_circles(circles, d)
                ex = sorted(d.note_texts(), key=lambda t: (t["y"], t["x"]))
                got = [t for t in texts if t["fill"] != K.WHITE]
                got.sort(key=lambda t: (t["y"], t["x"]))
                self.assertEqual([t["s"] for t in got], [t["s"] for t in ex])
                for g, e in zip(got, ex):
                    dx = known.get("desc_dx", 0.0) if e["fill"] == K.GRAY and e["weight"] == "" and \
                        any(t["weight"] == "600" for t in ex) else 0.0
                    self.assertLessEqual(abs(g["x"] + dx - e["x"]), TOL, (g["s"], g["x"], e["x"]))
                    self.assertLessEqual(abs(g["y"] - e["y"]), TOL, g["s"])
                    self.assertEqual(g.get("font-weight", ""), e["weight"], g["s"])
                    self.assertEqual(g["fill"], e["fill"], g["s"])
                self.assertEqual(nb.warnings, [])

    def _same_circles(self, circles, d):
        ex = d.note_circles()
        self.assertEqual(len(circles), len(ex))
        for g, e in zip(circles, ex):
            self.assertLessEqual(abs(g["cx"] - e["cx"]), TOL)
            self.assertLessEqual(abs(g["cy"] - e["cy"]), TOL)
            self.assertEqual(g["r"], e["r"])

    def test_nfw_description_column_exact(self):
        spec, geom = DOCS["nfw"].build()
        _, _, texts = elements(N.block(spec, geom))
        self.assertEqual({t["x"] for t in texts if t["fill"] == K.GRAY}, {56 + 107.4 + 16})

    def test_label_rows_and_overflow_warning(self):
        spec, geom = DOCS["tgw"].build()
        spec.note = M.NoteSpec(rows=[("TGW A RT", "10.0.0.0/8 → VPC"), ("TGW B RT", "x" * 400)])
        nb = N.block(spec, geom)
        _, circles, texts = elements(nb)
        self.assertEqual(circles, [])
        labels = [t for t in texts if t.get("font-weight") == "600"]
        self.assertEqual({t["x"] for t in labels}, {K.PANEL_ROW_X})
        col = K.PANEL_ROW_X + M.text_width("TGW A RT", 12) + K.PANEL_DESC_GAP
        self.assertEqual({t["x"] for t in texts if t["fill"] == K.GRAY}, {col})
        self.assertEqual(nb.h, N.panel_height(2))
        self.assertEqual(len(nb.warnings), 1)

    def test_one_row_kind(self):
        spec, geom = DOCS["nfw"].build()
        spec.note.summary = "extra"
        nb = N.block(spec, geom)
        self.assertEqual(len(nb.elements), 1 + 5 * 4)
        self.assertTrue(any("one row kind" in w for w in nb.warnings))

    def test_long_descriptions_wrap_and_move_following_rows(self):
        spec, geom = DOCS["tgw"].build()
        desc = "한국어 설명과 English words를 단어 경계에서 이어 읽습니다. " * 12
        spec.note = M.NoteSpec(steps=[("VPN → TGW", desc), ("TGW → VPC", "짧은 설명")])
        nb = N.block(spec, geom, place="panel")
        _, _, texts = elements(nb)
        descriptions = [t for t in texts if t["fill"] == K.GRAY]
        wrapped = descriptions[:-1]
        self.assertGreater(len(wrapped), 1)
        self.assertEqual(" ".join(t["s"] for t in wrapped), desc.strip())
        right = nb.rect.x1 - (K.PANEL_ROW_X - K.PANEL_X)
        self.assertTrue(all(t["x"] + M.text_width(t["s"], 12) <= right for t in descriptions))
        self.assertEqual(nb.h, N.panel_height(len(descriptions)))
        self.assertGreater(descriptions[-1]["y"], wrapped[-1]["y"])
        self.assertEqual(nb.warnings, [])

    def test_summary_and_label_rows_wrap(self):
        spec, geom = DOCS["tgw"].build()
        text = "긴 설명 English words " * 40
        for note in (M.NoteSpec(summary=text), M.NoteSpec(rows=[("Route", text)])):
            with self.subTest(note=note):
                spec.note = note
                nb = N.block(spec, geom, place="panel")
                _, _, texts = elements(nb)
                lines = [t for t in texts if t["fill"] == K.GRAY]
                self.assertGreater(len(lines), 1)
                self.assertEqual(" ".join(t["s"] for t in lines), text.strip())
                self.assertEqual(nb.h, N.panel_height(len(lines)))
                self.assertEqual(nb.warnings, [])


class PaneTest(unittest.TestCase):
    WIDTH = {"nlb-mtls": 320, "bedrock-dx": 456}

    def test_panes(self):
        for name in ("nlb-mtls", "bedrock-dx"):
            d = DOCS[name]
            with self.subTest(example=name):
                spec, geom = d.build()
                nb = N.block(spec, geom)
                self.assertEqual(nb.place, "pane")
                self.assertEqual(nb.w, self.WIDTH[name])
                r = d.note_rect
                rects, circles, texts = elements(nb)
                for k, v in (("x", r["x"]), ("y", r["y"]), ("width", r["w"]), ("height", r["h"])):
                    self.assertLessEqual(abs(rects[0][k] - v), TOL, k)
                self.assertEqual(nb.below(), 0.0)
                # wrap: same number of description lines per step as the example
                got_lines = []
                for t in texts:
                    if t.get("font-weight") == "600":
                        got_lines.append(0)
                    elif t["fill"] == K.GRAY:
                        got_lines[-1] += 1
                self.assertEqual(got_lines, d.pane_lines())
                # every element where the example has it
                PanelTest._same_circles(self, circles, d)
                ex = sorted(d.note_texts(), key=lambda t: (t["y"], t["x"]))
                got = sorted((t for t in texts if t["fill"] != K.WHITE), key=lambda t: (t["y"], t["x"]))
                self.assertEqual(len(got), len(ex))
                for g, e in zip(got, ex):
                    self.assertLessEqual(abs(g["x"] - e["x"]), TOL)
                    self.assertLessEqual(abs(g["y"] - e["y"]), TOL, (g["s"], e["s"]))
                    self.assertEqual(g.get("font-weight", ""), e["weight"])
                    if e["weight"] == "600":
                        self.assertEqual(g["s"], e["s"])
                digits = sorted(d.note_digits(), key=lambda t: t["y"])
                self.assertEqual([t["s"] for t in texts if t["fill"] == K.WHITE], [t["s"] for t in digits])
                self.assertEqual(nb.warnings, [])

    def test_requirements_hold_on_example(self):
        for name in ("nlb-mtls", "bedrock-dx"):
            with self.subTest(example=name):
                spec, geom = DOCS[name].build()
                nb = N.block(spec, geom)
                self.assertTrue(nb.requirements)
                for r in nb.requirements:
                    have = N._value(r.b, geom, r.axis) - N._value(r.a, geom, r.axis)
                    self.assertGreaterEqual(have, r.d - TOL, r)
                    self.assertEqual(r.owner, "note")
                self.assertEqual(N.pane_push(spec, geom, geom.groups["cloud"].rect, nb.w), 0.0)

    def test_client_pinned_only_under_a_plain_pane(self):
        spec, geom = DOCS["nlb-mtls"].build()
        pins = [r for r in N.block(spec, geom).requirements
                if r.axis == "x" and (r.a.startswith("node:") or r.b.startswith("node:"))]
        self.assertEqual(len(pins), 2)
        self.assertEqual(pins[0].d, K.PANE_X + 320 / 2)
        cloud_x = [r for r in N.block(spec, geom).requirements if r.b == "group:cloud.L"]
        self.assertEqual([r.d for r in cloud_x], [K.PANE_X + 320 + K.PANE_GAP])
        spec, geom = DOCS["bedrock-dx"].build()
        reqs = N.block(spec, geom).requirements
        self.assertFalse([r for r in reqs if r.axis == "x" and "node:" in r.a + r.b])
        self.assertTrue([r for r in reqs if r.axis == "y" and r.b.startswith("group:")])

    def test_width_rule(self):
        spec, geom = DOCS["nlb-mtls"].build()
        # step 3 runs to five lines at 300, so the pane is 320
        self.assertEqual(len(N.wrap(spec.note.steps[2][1], K.PANE_W - K.PANE_WRAP_INSET)), 5)
        self.assertEqual(N._base_width(spec.note.steps), K.PANE_W_WIDE)
        self.assertEqual(N._base_width(spec.note.steps[:2]), K.PANE_W)
        self.assertEqual(N.block(spec, geom, place="pane", width=400).w, 400)

    def test_second_call_is_stable(self):
        # W5 calls block again on the final geom with place and width fixed: same block
        for name in ("nlb-mtls", "bedrock-dx"):
            spec, geom = DOCS[name].build()
            nb0 = N.block(spec, geom)
            nb = N.block(spec, geom, place=nb0.place, width=nb0.w)
            self.assertEqual((nb.place, nb.w, nb.h, nb.requirements), (nb0.place, nb0.w, nb0.h, nb0.requirements))

    def test_push_falls_back_to_panel(self):
        spec, geom = DOCS["nlb-mtls"].build()
        spec.note.steps = spec.note.steps * 3      # a pane far taller than the client's row
        nb = N.block(spec, geom)
        self.assertEqual(nb.place, "panel")
        self.assertTrue(any("push" in w for w in nb.warnings))


class WrapTest(unittest.TestCase):
    def test_wrap(self):
        self.assertEqual(N.wrap("aa bb cc", M.text_width("aa bb", 12)), ["aa bb", "cc"])
        self.assertEqual(N.wrap("가나 다라", M.text_width("가나", 12)), ["가나", "다라"])
        self.assertEqual(N.wrap("one\ntwo", 1000), ["one", "two"])
        self.assertEqual(N.wrap("toolongword x", 10), ["toolongword", "x"])

    def test_pane_line_counts(self):
        for name in ("nlb-mtls", "bedrock-dx"):
            d = DOCS[name]
            spec, _ = d.build()
            w = PaneTest.WIDTH[name]
            got = [len(N.wrap(desc, w - K.PANE_WRAP_INSET)) for _, desc in spec.note.steps]
            self.assertEqual(got, d.pane_lines(), name)


class SlideLinesTest(unittest.TestCase):
    def test_badges_fit_without_reducing_slide_text_size(self):
        for name in ("gwlb", "nfw", "tgw"):
            spec, geom = SLIDES[name].build()
            with self.subTest(example=name):
                nb = N.block(spec, geom)
                _, circles, texts = elements(nb)
                end = geom.drawing.y1 + nb.below()
                self.assertTrue(all(c["cy"] + c["r"] <= end for c in circles))
                self.assertTrue(all(c["cy"] - c["r"] >= geom.drawing.y1 + K.LINES_END for c in circles))
                # Preserve the original text-based height by redistributing spare space.
                self.assertEqual(end, geom.drawing.y1 + K.LINES_FIRST_CY + K.BADGE_TEXT_DY + K.LINES_END)
                for c in circles:
                    digit = next(t for t in texts if t["fill"] == K.WHITE and t["x"] == c["cx"])
                    self.assertEqual(digit["y"], c["cy"] + K.BADGE_TEXT_DY)

    def test_radius_and_stroke_can_require_a_taller_block(self):
        spec, geom = SLIDES["tgw"].build()
        spec.note = M.NoteSpec(steps=[("Hop", "")])
        factory = N._badge
        for radius, stroke in ((8, 0), (10, 0), (12, 0), (14, 0), (10, 4)):
            with self.subTest(radius=radius, stroke=stroke):
                def badge(cx, cy, n):
                    els = factory(cx, cy, n)
                    els[0].attrs["r"] = radius
                    if stroke:
                        els[0].attrs.update(stroke=K.BADGE_FILL, **{"stroke-width": stroke})
                    return els

                with mock.patch.object(N, "_badge", side_effect=badge):
                    nb = N.block(spec, geom)
                circle = next(e.attrs for e in nb.elements if e.kind == "circle")
                ink_r = radius + stroke / 2
                self.assertGreaterEqual(circle["cy"] - ink_r, geom.drawing.y1 + K.LINES_END)
                self.assertLessEqual(circle["cy"] + ink_r, geom.drawing.y1 + nb.below())
                if radius == 14 or stroke:
                    self.assertGreater(nb.h, K.LINES_FIRST_CY + K.BADGE_TEXT_DY + K.LINES_END)

    def test_word_wrapped_notes_fit_complete_badge_ink(self):
        spec, geom = SLIDES["tgw"].build()
        spec.note = M.NoteSpec(steps=[("Hop", "한국어 English words " * 40), ("Last", "")])
        factory = N._badge
        for radius, stroke in ((8, 0), (10, 0), (12, 0), (14, 0), (10, 4)):
            with self.subTest(radius=radius, stroke=stroke):
                def badge(cx, cy, n):
                    els = factory(cx, cy, n)
                    els[0].attrs["r"] = radius
                    if stroke:
                        els[0].attrs.update(stroke=K.BADGE_FILL, **{"stroke-width": stroke})
                    return els

                with mock.patch.object(N, "_badge", side_effect=badge):
                    nb = N.block(spec, geom)
                circles = [e.attrs for e in nb.elements if e.kind == "circle"]
                self.assertEqual(len(circles), 2)
                for circle in circles:
                    ink_r = radius + stroke / 2
                    self.assertGreaterEqual(circle["cy"] - ink_r, geom.drawing.y1 + K.LINES_END)
                    self.assertLessEqual(circle["cy"] + ink_r, geom.drawing.y1 + nb.h)

    def test_wrapped_badge_rows_fit_and_keep_their_pitch(self):
        spec, geom = SLIDES["tgw"].build()
        # Each item fits a line; exercise badge-row flow rather than word wrapping.
        spec.note = M.NoteSpec(steps=[("Hop " * 25, "")] * 3)
        nb = N.block(spec, geom)
        circles = [e.attrs for e in nb.elements if e.kind == "circle"]
        cys = sorted({c["cy"] for c in circles})
        self.assertGreater(len(cys), 1)
        self.assertTrue(all(b - a == K.LINES_ROW_PITCH for a, b in zip(cys, cys[1:])))
        self.assertLessEqual(max(c["cy"] + c["r"] for c in circles), geom.drawing.y1 + nb.h)

    def test_lines(self):
        for name in ("gwlb", "nfw", "tgw"):
            d = SLIDES[name]
            dy = KNOWN.get(("slide", name), {}).get("dy", 0.0)
            with self.subTest(example=name):
                spec, geom = d.build()
                self.assertLessEqual(abs(geom.drawing.y1 - d.cloud["y1"]), TOL)
                nb = N.block(spec, geom)
                self.assertEqual(nb.place, "lines")
                rects, circles, texts = elements(nb)
                self.assertEqual(rects, [])
                ex_c = d.note_circles()
                self.assertEqual(len(circles), len(ex_c))
                for g, e in zip(circles, ex_c):
                    self.assertLessEqual(abs(g["cx"] - e["cx"]), TOL)
                    self.assertLessEqual(abs(g["cy"] + dy - e["cy"]), TOL)
                ex = sorted(d.note_texts(), key=lambda t: (t["y"], t["x"]))
                got = sorted((t for t in texts if t["fill"] != K.WHITE), key=lambda t: (t["y"], t["x"]))
                self.assertEqual([t["s"] for t in got], [t["s"] for t in ex])
                for g, e in zip(got, ex):
                    self.assertLessEqual(abs(g["x"] - e["x"]), TOL, g["s"])
                    self.assertLessEqual(abs(g["y"] + dy - e["y"]), TOL, g["s"])
                    self.assertEqual((g["fill"], g.get("font-weight", "")), (K.GRAY, ""))
                self.assertLessEqual(abs(geom.drawing.y1 + nb.below() + dy - d.h), TOL)   # canvas ends 4 below
                self.assertEqual(nb.requirements, [])
                self.assertEqual(nb.warnings, [])

    def test_second_row_and_max_lines(self):
        spec, geom = SLIDES["tgw"].build()
        long = "긴 항목 " * 12
        spec.note = M.NoteSpec(steps=[(long, "")] * 4, summary="요약")
        nb = N.block(spec, geom)
        _, circles, texts = elements(nb)
        cys = sorted({c["cy"] for c in circles})
        self.assertEqual(cys, [geom.drawing.y1 + 18 + 24 * k for k in range(len(cys))])
        self.assertTrue(len(cys) >= 2)
        self.assertTrue(all(c["cx"] == geom.groups["cloud"].rect.x0 + 10 for c in circles
                            if c is min((c2 for c2 in circles if c2["cy"] == c["cy"]), key=lambda q: q["cx"])))
        summary = next(t for t in texts if t["s"] == "요약")
        self.assertEqual((summary["x"], summary["y"]), (geom.groups["cloud"].rect.x0, cys[-1] + 4 + 24))
        self.assertTrue(any("note lines" in w for w in nb.warnings))

    def test_text_only_line(self):
        spec, geom = SLIDES["nlb"].build()
        spec.note = M.NoteSpec(summary="Internet-facing NLB · TLS 종료")
        nb = N.block(spec, geom)
        self.assertEqual(nb.place, "lines")
        t = nb.elements[0].attrs
        self.assertEqual((t["x"], t["y"]), (geom.groups["cloud"].rect.x0, geom.drawing.y1 + 17))
        self.assertEqual(nb.h, 17 + 4)

    def test_long_steps_wrap_without_losing_words_or_badges(self):
        spec, geom = SLIDES["gwlb"].build()
        text = "한글 설명과 English words를 모두 읽을 수 있습니다. " * 16
        spec.note = M.NoteSpec(steps=[("IGW → GWLBe", text), ("GWLB → EC2", text)])
        nb = N.block(spec, geom)
        _, circles, texts = elements(nb)
        lines = [t for t in texts if t["fill"] == K.GRAY]
        self.assertEqual(len(circles), 2)
        expected = " ".join(N._line_items(spec.note)[0]).split()
        self.assertEqual(" ".join(t["s"] for t in lines).split(), expected)
        limit = geom.canvas_w - spec.const.canvas_margin
        self.assertTrue(all(t["x"] + M.text_width(t["s"], 12) <= limit for t in lines))
        self.assertGreater(nb.h, K.LINES_FIRST_CY + K.BADGE_TEXT_DY + K.LINES_END)
        self.assertFalse(any("past" in w or "does not fit" in w for w in nb.warnings))

    def test_long_plain_notes_wrap(self):
        spec, geom = SLIDES["nlb"].build()
        text = "한국어와 English words " * 40
        spec.note = M.NoteSpec(summary=text, rows=[("경로", text)])
        nb = N.block(spec, geom)
        _, circles, texts = elements(nb)
        self.assertEqual(circles, [])
        self.assertEqual(" ".join(t["s"] for t in texts).split(),
                         (text + " 경로 " + text).split())
        self.assertTrue(all(t["x"] + M.text_width(t["s"], 12)
                            <= geom.canvas_w - spec.const.canvas_margin for t in texts))
        self.assertEqual(nb.rect.y1, texts[-1]["y"] + K.LINES_END)

    def test_only_unbreakable_words_keep_overflow_warnings(self):
        spec, geom = SLIDES["gwlb"].build()
        spec.note = M.NoteSpec(steps=[("IGW", "x" * 400 + " 다음 단어")])
        nb = N.block(spec, geom)
        self.assertEqual(len([w for w in nb.warnings if "does not fit" in w]), 1)
        _, _, texts = elements(nb)
        lines = [t["s"] for t in texts if t["fill"] == K.GRAY]
        self.assertIn("x" * 400, lines)
        self.assertIn("다음 단어", lines)


if __name__ == "__main__":
    unittest.main(verbosity=1)
