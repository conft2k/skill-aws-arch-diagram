"""The note of a layout-engine draft (W4): place, size, elements and pane requirements.

    block(spec, geom, place=None, width=None) -> NoteBlock

The contract (call order, the note's rect per place, the pane Requirements, NoteBlock.below())
is in layout_model.py's docstring, sections 1 and 4; the numbers are layout_const's note
block (QR 169-183, DG "The note — one place per diagram" and "Step legend").

Places (DESIGN 4.7):
  panel  documents: a box below the drawing, one row per step (badge, bold hop, description
         column 16 right of the widest hop), or one summary row, or label rows.
  pane   a box left of the AWS Cloud, steps only, descriptions wrapped under each hop; the
         Cloud starts 24 right of it and what sits left of the Cloud goes below it.
  lines  slides: plain 12px lines below the drawing at the Cloud's left edge, step items
         flowed in a row (20 from a text end to the next badge), ≤ 3 lines.
  none   no note.
Auto rule: a document with steps gets a pane when its drawing is taller than 0.7 × its
width, otherwise a panel; a slide with steps gets a pane when pane + drawing fit the 1108
slide width, otherwise lines; a slide never gets a panel. A pane whose coupling would push
what sits under it down by more than 40 px is widened to 320 first, then given up for the
panel / lines (with a warning).

Text widths that must agree with the examples use text_width (0.55 em Latin): the panel
description column, the slide line flow and the pane wrapping (every example's hand-wrapped
pane lines come out with the same line count only at 0.55 em; 0.6 em breaks two of them).
Pure: reads spec and geom, mutates neither.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_const as K  # noqa: E402
import layout_model as M  # noqa: E402
from layout_model import Box, Element, Geometry, NoteBlock, Requirement, Spec, TextLine  # noqa: E402

OWNER = M.NOTE_EID
Z = K.Z_NOTE
PLACES = ("auto", "panel", "pane", "lines")
PANE_MAX_PUSH = 40        # DESIGN 4.7: a pane pushing what sits under it down by more than this is widened / dropped
SIZE = K.TEXT_NOTE.size   # every note text is 12 px


# =======================================================================================
# Public entry point

def block(spec: Spec, geom: Geometry, place: Optional[str] = None, width: Optional[float] = None) -> NoteBlock:
    """The note for this geom. place / width fix the place and the pane width (W5's second call)."""
    note = spec.note
    if note is None or not (note.steps or note.summary or note.rows):
        return NoteBlock("none")
    warns: List[str] = []
    want = place or note.place or "auto"
    if want not in PLACES and want != "none":
        warns.append(f"{note.src}: unknown place {want!r}, using auto")
        want = "auto"
    if want == "none":
        return NoteBlock("none")
    slide = spec.mode == "slide"
    cloud = _cloud(spec, geom)
    fixed_w = width if width is not None else note.width

    if want == "panel" and slide:
        warns.append(f"{note.src}: a slide never gets a bottom panel (DG \"The note\"); using plain lines")
        want = "lines"
    if want == "lines" and not slide:
        warns.append(f"{note.src}: plain lines are for slides; using the bottom panel")
        want = "panel"
    if want == "pane":
        why = _pane_unfit(spec, cloud)
        if why:
            warns.append(f"{note.src}: {why}; using the {'plain lines' if slide else 'bottom panel'}")
            want = "lines" if slide else "panel"

    if want == "auto":
        want, w, msg = _auto(spec, geom, cloud, fixed_w)
        if msg:
            warns.append(msg)
    else:
        w = None

    if want == "pane":
        nb = _pane(spec, geom, cloud, w if w is not None else pane_width(spec, geom, cloud, fixed_w))
    elif want == "panel":
        nb = _panel(spec, geom)
    else:
        nb = _lines(spec, geom, cloud)
    nb.warnings = warns + nb.warnings
    return nb


# =======================================================================================
# Auto rule

def _auto(spec: Spec, geom: Geometry, cloud: Optional[Box], fixed_w: Optional[float]):
    """(place, pane width or None, warning or None) by DESIGN 4.7."""
    note, slide = spec.note, spec.mode == "slide"
    other = "lines" if slide else "panel"
    if not note.steps or _pane_unfit(spec, cloud):
        return other, None, None
    d = geom.drawing
    w = pane_width(spec, geom, cloud, fixed_w)
    if slide:
        h = pane_height(note.steps, w)
        fit_w = K.PANE_X + w + K.PANE_GAP + d.w + spec.const.canvas_margin
        fit_h = cloud.y0 + h + spec.const.canvas_margin
        if fit_w > K.SLIDE_MAX_W or fit_h > K.SLIDE_MAX_H[bool(spec.title)]:
            return other, None, None
    elif not d.h > K.PANE_RATIO * d.w:
        return other, None, None
    # pane coupling: widen before giving up when it pushes what sits under the pane too far
    tries = [w] + ([K.PANE_W_WIDE] if fixed_w is None and w < K.PANE_W_WIDE else [])
    push = None
    for tw in tries:
        push = pane_push(spec, geom, cloud, tw)
        if push <= PANE_MAX_PUSH:
            return "pane", tw, None
    return other, None, (f"{note.src}: the legend pane would push what sits under it {push:.0f}px down "
                         f"(> {PANE_MAX_PUSH}); using the {'plain lines' if slide else 'bottom panel'}")


def _pane_unfit(spec: Spec, cloud: Optional[Box]) -> Optional[str]:
    if cloud is None:
        return "a legend pane needs an AWS Cloud group to sit beside"
    if not spec.note.steps:
        return "only step rows go in the legend pane"
    return None


def _cloud(spec: Spec, geom: Geometry) -> Optional[Box]:
    cid = spec.cloud_id()
    return geom.groups[cid].rect if cid is not None and cid in geom.groups else None


# =======================================================================================
# Text helpers

def wrap(text: str, width: float, size: float = SIZE) -> List[str]:
    """Greedy word wrap to `width` px (text_width; Hangul words are space separated too).

    A "\\n" in the text forces a break. A single word wider than `width` gets a line of its
    own (the caller warns)."""
    out: List[str] = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            cand = f"{cur} {word}" if cur else word
            if not cur or M.text_width(cand, size) <= width:
                cur = cand
            else:
                out.append(cur)
                cur = word
        out.append(cur)
    return [s for s in out if s] or [""]


def _t(s: str, x: float, y: float, style: K.TextStyle, anchor: str = "start") -> Element:
    return M.el_text(TextLine(s, x, y, style.size, style.fill, style.weight, anchor), z=Z, owner=OWNER)


def _badge(cx: float, cy: float, n: int) -> List[Element]:
    return M.el_badge(cx, cy, n, z=Z, owner=OWNER)


def _rect(box: Box) -> Element:
    return M.el_rect(box, fill=K.NOTE_FILL, stroke=K.NOTE_STROKE, width=K.NOTE_STROKE_W, z=Z, owner=OWNER)


# =======================================================================================
# Bottom panel (documents)

def panel_height(rows: int) -> float:
    return K.PANEL_FIRST + K.PANEL_PITCH * (rows - 1) + K.PANEL_LAST


def _panel_kind(note) -> Tuple[str, List[str]]:
    """The one row kind a panel shows (steps > rows > summary) and warnings for the rest."""
    kinds = [k for k, v in (("steps", note.steps), ("rows", note.rows), ("summary", note.summary)) if v]
    warns = []
    if len(kinds) > 1:
        warns.append(f"{note.src}: a note shows one row kind (DG \"Bottom note panel\"); "
                     f"showing {kinds[0]}, dropping {', '.join(kinds[1:])}")
    return kinds[0], warns


def _panel(spec: Spec, geom: Geometry) -> NoteBlock:
    note = spec.note
    kind, warns = _panel_kind(note)
    n = len(note.steps) if kind == "steps" else len(note.rows) if kind == "rows" else 1
    x0, y0 = K.PANEL_X, geom.drawing.y1 + K.PANEL_GAP
    w, h = geom.canvas_w - 2 * K.PANEL_X, panel_height(n)
    rect = Box.xywh(x0, y0, w, h)
    els = [_rect(rect)]
    right = rect.x1 - (K.PANEL_ROW_X - K.PANEL_X)        # rows keep the 12 px inset on the right too

    def base(i):
        return y0 + K.PANEL_FIRST + K.PANEL_PITCH * i

    if kind == "steps":
        col = K.PANEL_HOP_X + max(M.text_width(hop, SIZE) for hop, _ in note.steps) + K.PANEL_DESC_GAP
        for i, (hop, desc) in enumerate(note.steps):
            b = base(i)
            els += _badge(K.PANEL_BADGE_CX, b - K.BADGE_TEXT_DY, i + 1)
            els.append(_t(hop, K.PANEL_HOP_X, b, K.TEXT_HOP))
            if desc:
                els.append(_t(desc, col, b, K.TEXT_NOTE))
            end = (col + M.text_width(desc, SIZE)) if desc else K.PANEL_HOP_X + M.text_width(hop, SIZE)
            if end > right:
                warns.append(f"{note.src}: step {i + 1} runs {end - right:.0f}px past the bottom panel; "
                             f"shorten it or use place: pane")
    elif kind == "rows":
        col = K.PANEL_ROW_X + max(M.text_width(lab, SIZE) for lab, _ in note.rows) + K.PANEL_DESC_GAP
        for i, (lab, text) in enumerate(note.rows):
            b = base(i)
            els.append(_t(lab, K.PANEL_ROW_X, b, K.TEXT_HOP))
            if text:
                els.append(_t(text, col, b, K.TEXT_NOTE))
            end = col + M.text_width(text, SIZE)
            if end > right:
                warns.append(f"{note.src}: row {i + 1} runs {end - right:.0f}px past the bottom panel; shorten it")
    else:
        els.append(_t(note.summary, K.PANEL_ROW_X, base(0), K.TEXT_NOTE))
        end = K.PANEL_ROW_X + M.text_width(note.summary, SIZE)
        if end > right:
            warns.append(f"{note.src}: the summary runs {end - right:.0f}px past the bottom panel; shorten it")
    return NoteBlock("panel", w=w, h=h, rect=rect, elements=els, warnings=warns)


# =======================================================================================
# Left legend pane

def _left_items(spec: Spec, geom: Geometry, cloud: Box):
    """Top-level nodes and groups entirely left of the AWS Cloud (what goes under the pane)."""
    cid = spec.cloud_id()
    nodes = [nid for nid, n in spec.nodes.items()
             if n.parent is None and n.on is None and nid in geom.nodes
             and geom.nodes[nid].footprint().x1 <= cloud.x0]
    groups = [gid for gid, g in spec.groups.items()
              if g.parent is None and not g.overlay and gid != cid and gid in geom.groups
              and geom.groups[gid].rect.x1 <= cloud.x0]
    return nodes, groups


def _base_width(steps) -> float:
    """300, or 320 when a description would run past four lines at 300 (QR 182)."""
    for _, desc in steps:
        if desc and len(wrap(desc, K.PANE_W - K.PANE_WRAP_INSET)) > K.PANE_WIDE_LINES:
            return K.PANE_W_WIDE
    return K.PANE_W


def pane_width(spec: Spec, geom: Geometry, cloud: Box, fixed: Optional[float] = None) -> float:
    """The pane width: fixed, else max(300 / 320, the left column below it).

    The left column is the room left of the Cloud when something sits there (an on-premises
    group plus a Direct Connect column): the pane takes Cloud.x − 24 − 16 of it, so the Cloud
    doesn't move and no empty column opens beside the pane (ex bedrock-dx 496 − 40 = 456)."""
    if fixed is not None:
        return float(fixed)
    w = _base_width(spec.note.steps)
    nodes, groups = _left_items(spec, geom, cloud)
    if nodes or groups:
        w = max(w, math.floor(cloud.x0 - K.PANE_GAP - K.PANE_X))
    return float(w)


def _pane_layout(steps, w: float, y0: float):
    """[(badge cy, hop baseline, [(line, baseline)])], last baseline, wrap warnings."""
    out, warns = [], []
    room = w - K.PANE_WRAP_INSET
    hop_b = y0 + K.PANE_FIRST_CY + K.BADGE_TEXT_DY
    last = hop_b
    for i, (hop, desc) in enumerate(steps):
        if i:
            hop_b = last + K.PANE_NEXT_HOP
        lines = wrap(desc, room) if desc else []
        if M.text_width(hop, SIZE) > room:
            warns.append(f"step {i + 1} hop is {M.text_width(hop, SIZE) - room:.0f}px wider than the pane text column")
        for s in lines:
            if M.text_width(s, SIZE) > room:
                warns.append(f"step {i + 1}: {s!r} does not fit the pane text column ({room:.0f}px)")
        placed = [(s, hop_b + K.PANE_DESC_DY + K.PANE_DESC_PITCH * k) for k, s in enumerate(lines)]
        last = placed[-1][1] if placed else hop_b
        out.append((hop_b - K.BADGE_TEXT_DY, hop_b, placed))
    return out, last, warns


def pane_height(steps, w: float) -> float:
    _, last, _ = _pane_layout(steps, w, 0.0)
    return last + K.PANE_END


def pane_requirements(spec: Spec, geom: Geometry, cloud: Box, w: float, h: float) -> List[Requirement]:
    """The coupling (layout_model section 4): Cloud right of the pane, what is left of it below."""
    cid = spec.cloud_id()
    cl, ct = f"group:{cid}.L", f"group:{cid}.T"
    reqs = [Requirement("x", "origin", cl, K.PANE_X + w + K.PANE_GAP, "Cloud starts 24 right of the legend pane", OWNER)]
    nodes, groups = _left_items(spec, geom, cloud)
    # Pin the client to the pane's center when it alone sits under a 300/320 pane (a column
    # of top-level nodes, no group); a pane as wide as the left column leaves it where it is.
    wide = w > _base_width(spec.note.steps)
    if nodes and not groups and not wide and len({spec.nodes[n].col for n in nodes}) == 1:
        cx = K.PANE_X + w / 2
        for nid in nodes:
            reqs.append(Requirement("x", "origin", f"node:{nid}", cx, "client centered under the legend pane", OWNER))
            reqs.append(Requirement("x", f"node:{nid}", "origin", -cx, "client centered under the legend pane", OWNER))
    half = spec.S / 2
    for nid in nodes:
        reqs.append(Requirement("y", ct, f"node:{nid}", h + K.PANE_CLIENT_GAP + half,
                                "node under the legend pane: icon ≥ 16 below it", OWNER))
    for gid in groups:
        reqs.append(Requirement("y", ct, f"group:{gid}.T", h + K.PANE_OUTER_GAP,
                                "group under the legend pane: top ≥ 24 below it", OWNER))
    return reqs


def _value(var: str, geom: Geometry, axis: str) -> float:
    if var == "origin":
        return 0.0
    kind, ref = var.split(":", 1)
    if kind == "node":
        n = geom.nodes[ref]
        return n.cx if axis == "x" else n.cy
    gid, edge = ref.rsplit(".", 1)
    return geom.groups[gid].rect.get({"L": "x0", "R": "x1", "T": "y0", "B": "y1"}[edge])


def pane_push(spec: Spec, geom: Geometry, cloud: Box, w: float) -> float:
    """How far (px) the pane's y coupling would push what sits under it, on this geom."""
    h = pane_height(spec.note.steps, w)
    push = 0.0
    for r in pane_requirements(spec, geom, cloud, w, h):
        if r.axis == "y":
            push = max(push, r.d - (_value(r.b, geom, "y") - _value(r.a, geom, "y")))
    return push


def _pane(spec: Spec, geom: Geometry, cloud: Box, w: float) -> NoteBlock:
    note = spec.note
    warns = []
    if note.summary or note.rows:
        warns.append(f"{note.src}: only step rows go in the legend pane; dropping "
                     f"{', '.join(k for k, v in (('summary', note.summary), ('rows', note.rows)) if v)}")
    y0 = cloud.y0
    rows, last, wrap_warns = _pane_layout(note.steps, w, y0)
    warns += [f"{note.src}: {m}" for m in wrap_warns]
    h = last + K.PANE_END - y0
    rect = Box.xywh(K.PANE_X, y0, w, h)
    els = [_rect(rect)]
    for i, ((hop, _), (cy, hop_b, lines)) in enumerate(zip(note.steps, rows)):
        els += _badge(K.PANE_BADGE_CX, cy, i + 1)
        els.append(_t(hop, K.PANE_HOP_X, hop_b, K.TEXT_HOP))
        els += [_t(s, K.PANE_HOP_X, b, K.TEXT_NOTE) for s, b in lines]
    reqs = pane_requirements(spec, geom, cloud, w, h)
    return NoteBlock("pane", w=w, h=h, rect=rect, elements=els, requirements=reqs, warnings=warns)


# =======================================================================================
# Slide plain lines

def _line_items(note) -> Tuple[List[str], List[str]]:
    """(step item texts, text-only lines). A slide item is one plain text: the hop, then the
    description's few words (QR 165-167: no bold hop on slides)."""
    items = [f"{hop} {desc}".strip() if desc else hop for hop, desc in note.steps]
    plain = ([note.summary] if note.summary else []) + [f"{lab} {text}".strip() for lab, text in note.rows]
    return items, plain


def _lines(spec: Spec, geom: Geometry, cloud: Optional[Box]) -> NoteBlock:
    note = spec.note
    warns: List[str] = []
    x0 = cloud.x0 if cloud is not None else geom.drawing.x0
    limit = geom.canvas_w - spec.const.canvas_margin
    bottom = geom.drawing.y1
    items, plain = _line_items(note)
    els: List[Element] = []
    n_lines, last_b, right = 0, None, x0

    if items:
        cy = bottom + K.LINES_FIRST_CY
        cx = x0 + K.LINES_BADGE_DX
        n_lines = 1
        for i, s in enumerate(items):
            tx = cx + (K.LINES_TEXT_DX - K.LINES_BADGE_DX)
            end = tx + M.text_width(s, SIZE)
            if i and end > limit:                       # continue on a second row, same left edge
                cx, cy, n_lines = x0 + K.LINES_BADGE_DX, cy + K.LINES_ROW_PITCH, n_lines + 1
                tx = cx + (K.LINES_TEXT_DX - K.LINES_BADGE_DX)
                end = tx + M.text_width(s, SIZE)
            if end > limit:
                warns.append(f"{note.src}: step {i + 1} runs {end - limit:.0f}px past the canvas; shorten it")
            els += _badge(cx, cy, i + 1)
            els.append(_t(s, tx, cy + K.BADGE_TEXT_DY, K.TEXT_NOTE))
            right = max(right, end)
            cx = end + K.LINES_ITEM_GAP + K.BADGE_R
        last_b = cy + K.BADGE_TEXT_DY
    after_items = bool(items)
    for s in plain:
        # a text-only line: first at bottom + 17; 16 below a text line, 24 below a badge row
        if last_b is None:
            b = bottom + K.LINES_TEXT_ONLY_DY
        else:
            b = last_b + (K.LINES_ROW_PITCH if after_items else K.LINES_TEXT_PITCH)
        after_items = False
        els.append(_t(s, x0, b, K.TEXT_NOTE))
        end = x0 + M.text_width(s, SIZE)
        if end > limit:
            warns.append(f"{note.src}: {s[:24]!r}… runs {end - limit:.0f}px past the canvas; shorten it")
        right = max(right, end)
        last_b, n_lines = b, n_lines + 1
    if n_lines > K.LINES_MAX:
        warns.append(f"{note.src}: {n_lines} note lines on a slide (≤ {K.LINES_MAX}); drop the route line "
                     f"or shorten the items")
    h = last_b + K.LINES_END - bottom
    rect = Box(x0, bottom, right, bottom + h)
    return NoteBlock("lines", w=rect.w, h=h, rect=rect, elements=els, warnings=warns)

