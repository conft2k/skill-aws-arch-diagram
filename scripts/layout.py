#!/usr/bin/env python3
"""Turn a layout spec (<name>.layout.yaml) into a draft SVG that passes check_layout.py.

    python3 scripts/layout.py arch.layout.yaml [-o arch.draft.svg] [--mode slide]
                              [--title | --no-title] [--explain] [--no-check]

The spec names tracks (columns, rows), containers, nodes, edges and the note; the engine
computes every coordinate. Without -o the draft goes next to the spec as <name>.draft.svg.

Pipeline (the contract is layout_model.py's docstring, section 1):
  load → route.plan → solve (no note) → note.block → solve (with the note) → note.block
  (place and width fixed) → route.draw → emit → check_layout in process.
The check applies check_layout --fix's fixed-answer repairs, then answers what is left by
kind and solves again (at most 5 rounds): SHORT ARROW, LINE HUGS BORDER and a label or
badge crowded by a border, icon or another label widen the column / row gap it sits in;
a connector over a label or icon takes that edge's next routing candidate; an edge the
router could not draw in its planned shape widens the gaps it spans. The round with the
fewest problems is written.

Output: a summary (canvas, the size 12px text gets on a 16:9 slide, the note, the icon
refs, warnings), then check_layout's problem lines, each with the spec items behind it and
a spec change to try, and last `Layout OK` or `N problems`. Exit status 0 when the draft
is clean, 1 when problems remain or the spec is invalid. --explain also prints, per track,
the chain of constraints that set its position. --no-check skips the check (and the
feedback rounds). The same spec always gives a byte-identical draft.

Needs PyYAML for .yaml specs (`uv run --with pyyaml python3 scripts/layout.py ...` when it
is missing; a .json spec needs nothing). Python 3.9+, standard library otherwise.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_layout as CL  # noqa: E402
import layout_const as K  # noqa: E402
import layout_model as M  # noqa: E402
import layout_note  # noqa: E402
import layout_route  # noqa: E402
import layout_solve  # noqa: E402
import layout_spec  # noqa: E402
from layout_model import Element, Geometry, NoteBlock, Requirement, Spec  # noqa: E402

MAX_ROUNDS = 5          # feedback rounds after the first solve (DESIGN 4.10)
WIDEN = 16              # px a feedback round adds to a gap
MAX_SKIP = 3            # candidates an edge may skip before its gap is widened instead
SVG_NS = "http://www.w3.org/2000/svg"
# The tags, and the <g> attributes, svg2pptx.collect accepts (DRAWN / its <g> rule).
RAW_TAGS = {"g", "rect", "image", "text", "line", "polyline", "circle", "tspan"}


# =======================================================================================
# One build: spec + feedback → elements

class Build:
    """Everything one pass of the pipeline produced."""

    def __init__(self, spec: Spec, geom: Geometry, nb: NoteBlock, elements: List[Element],
                 warnings: List[str], svg: bytes):
        self.spec, self.geom, self.nb, self.elements = spec, geom, nb, elements
        self.warnings, self.svg = warnings, svg


def value(var: str, geom: Geometry, axis: str) -> float:
    """A Requirement variable's value on a solved geometry (layout_model section 4)."""
    if var == "origin":
        return 0.0
    kind, ref = var.split(":", 1)
    if kind == "col" or kind == "row":
        return geom.track(ref)
    if kind == "node":
        n = geom.nodes[ref]
        return n.cx if axis == "x" else n.cy
    gid, side = ref.rsplit(".", 1)
    return geom.groups[gid].rect.get({"L": "x0", "R": "x1", "T": "y0", "B": "y1"}[side])


def build(spec: Spec, extra: Sequence[Requirement], skip: Dict[int, int], place: Optional[str],
          source: str) -> Build:
    reqs = layout_route.plan(spec) + list(extra)
    geom0 = layout_solve.solve(spec, reqs)
    nb0 = layout_note.block(spec, geom0, place=place)
    geom = layout_solve.solve(spec, reqs + nb0.requirements, note_block=nb0)
    nb = layout_note.block(spec, geom, place=nb0.place, width=nb0.w if nb0.place == "pane" else None)
    warns = list(nb0.warnings)
    for r in nb.requirements:          # the contract: nb's requirements hold on geom
        got = value(r.b, geom, r.axis) - value(r.a, geom, r.axis)
        if got < r.d - 0.5:
            warns.append(f"note: requirement {r.why!r} short by {M.fmt_num(r.d - got)}px on the final geometry")
    edges, route_warns = layout_route.draw(spec, geom, skip)
    raws, raw_warns = raw_elements(spec, geom)
    elements = layout_solve.draw(spec, geom) + edges + nb.elements + raws
    warns += [w for w in nb.warnings if w not in warns] + route_warns + raw_warns
    return Build(spec, geom, nb, elements, warns, emit(spec, geom, elements, source))


# =======================================================================================
# raw fragments

PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


def raw_elements(spec: Spec, geom: Geometry) -> Tuple[List[Element], List[str]]:
    """raw[i] with its {expr} placeholders replaced, checked against the draft subset."""
    out, problems = [], []
    for i, r in enumerate(spec.raw):
        def sub(m, r=r):
            key = m.group(1)
            e = r.exprs.get(key) or layout_spec.parse_expr(key, spec)
            return M.fmt_num(M.eval_expr(e, geom))
        try:
            svg = PLACEHOLDER.sub(sub, r.svg)
        except (KeyError, ValueError, M.LayoutError) as err:
            raise M.SpecError([f"{r.src or f'raw[{i}]'}: placeholder {err}"])
        bad = raw_problems(svg)
        if bad:
            raise M.SpecError([f"{r.src or f'raw[{i}]'}: {b}" for b in bad])
        z = K.Z_RAW_BELOW if r.layer == "below" else K.Z_RAW_ABOVE
        out.append(M.el_raw(svg, z=z, owner=M.raw_eid(i)))
    return out, problems


def raw_problems(svg: str) -> List[str]:
    """What keeps a raw fragment out of the shared draft subset (svg2pptx.collect's rules)."""
    try:
        root = ET.fromstring(f'<svg xmlns="{SVG_NS}" viewBox="0 0 10 10">{svg}</svg>')
    except ET.ParseError as e:
        return [f"not well-formed SVG ({e})"]
    probs = []
    for el in root.iter():
        tag = el.tag.replace("{%s}" % SVG_NS, "")
        if el is root:
            continue
        if tag not in RAW_TAGS:
            probs.append(f"<{tag}> is not in the draft subset (rect, image, text, line, polyline, circle, g)")
        if el.get("style") or el.get("class"):
            probs.append(f"<{tag}> uses style=/class=; write presentation attributes instead")
        if tag == "g":
            extra = sorted(k for k in el.keys() if k not in ("id", "transform"))
            if extra:
                probs.append(f"<g> carries {', '.join(extra)}; svg2pptx takes only id (and translate)")
            if el.get("transform") and not re.fullmatch(r"\s*translate\([^)]*\)\s*", el.get("transform")):
                probs.append("<g transform> other than translate()")
        if tag == "image":
            href = el.get("href") or el.get("{http://www.w3.org/1999/xlink}href") or ""
            ref = href[len("bundle:"):] if href.startswith("bundle:") else None
            if ref is None:
                probs.append(f"<image href={href[:40]!r}>: use bundle:set/name")
            elif not _bundle_has(ref):
                probs.append(f"<image href='bundle:{ref}'>: not in the icon bundle")
        if tag == "polyline" and (el.get("fill") or "none").lower() != "none":
            probs.append('<polyline> needs fill="none"')
        if tag == "text" and el.get("stroke"):
            probs.append("<text> with a stroke (halo); use a white mask rect")
    return probs


def _bundle_has(ref: str) -> bool:
    import find_icon
    set_, _, name = ref.partition("/")
    return name in find_icon.SETS.get(set_, {})


# =======================================================================================
# emit

def _esc(s: str, attr: bool = False) -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s.replace('"', "&quot;") if attr else s


def el_xml(e: Element) -> str:
    if e.kind == "raw":
        return (e.text or "").strip()
    attrs = " ".join(f'{k}="{M.fmt_num(v) if isinstance(v, (int, float)) else _esc(str(v), True)}"'
                     for k, v in e.attrs.items())
    if e.kind == "text":
        return f"<text {attrs}>{_esc(e.text or '')}</text>"
    return f"<{e.kind} {attrs}/>"


def emit(spec: Spec, geom: Geometry, elements: Sequence[Element], source: str) -> bytes:
    """The draft: root header, defs, background, then every element by z in <g id> runs."""
    W, H = M.fmt_num(geom.canvas_w), M.fmt_num(geom.canvas_h)
    first: Dict[Tuple[int, str], int] = {}
    for i, e in enumerate(elements):
        first.setdefault((e.z, e.owner), i)
    # ascending z; an owner's elements stay together in the layer, in production order
    order = sorted(range(len(elements)), key=lambda i: (elements[i].z, first[(elements[i].z, elements[i].owner)], i))
    start = any("marker-start" in e.attrs for e in elements)
    name = Path(source).name.replace("--", "- -")
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="{SVG_NS}" font-family="{_esc(spec.font, True)}">',
           f"  <!-- generated by layout.py from {_esc(name)} — edit the spec and re-run; "
           "hand edits are lost on regeneration -->",
           "  <defs>", "    " + K.MARKER_ARROW]
    if start:
        out.append("    " + K.MARKER_ARROW_START)
    out += ["  </defs>", f'  <rect width="{W}" height="{H}" fill="#FFFFFF"/>']
    cur, seen = None, set()
    for i in order:
        e = elements[i]
        gid = M.g_id(e.owner, e.z) if e.owner else None
        if gid != cur:
            if cur is not None:
                out.append("  </g>")
            cur = gid
            if gid is not None:
                if gid in seen:
                    raise M.LayoutError([f"emit: element id {gid!r} used twice"])
                seen.add(gid)
                out.append(f'  <g id="{_esc(gid, True)}">')
        out.append(("    " if cur is not None else "  ") + el_xml(e))
    if cur is not None:
        out.append("  </g>")
    out.append("</svg>")
    return ("\n".join(out) + "\n").encode("utf-8")


# =======================================================================================
# In-process check (check_layout --fix, then what is left)

def fix_pass(data: bytes, scratch: Path) -> Tuple[bytes, int]:
    """check_layout --fix on the bytes (its fixed-answer repairs, re-checked, ≤ 5 passes)."""
    fixed = 0
    for _ in range(5):
        adv = CL.Advisor(ET.fromstring(data))
        if not adv.issues:
            break
        _, accepted = adv.plan()
        real = [(iss, h) for iss, h in accepted if h.note != "cleared by an earlier fix"]
        if not real:
            break
        CL.write_edits(scratch, data, adv.order, [e for _, h in real for e in h.auto])
        data = scratch.read_bytes()
        fixed += len(real)
    return data, fixed


class Problem:
    def __init__(self, iss, owners: List[str], items: List[dict]):
        self.iss, self.owners, self.items = iss, owners, items


def problems_of(data: bytes, hints: bool = False) -> Tuple[List[Problem], "CL.Advisor", List]:
    """Every check_layout problem, with the element ids (<g id>) of what it involves; with
    hints, check_layout's fix line for each (slow: it re-checks candidate moves)."""
    root = ET.fromstring(data)
    adv = CL.Advisor(root)
    hint_list = [(iss, adv.hint(iss)) for iss in adv.issues] if hints else []
    parent = {c: p for p in root.iter() for c in p}
    out = []
    for iss in adv.issues:
        owners, items = [], []
        for v in iss.ctx.values():
            if not (isinstance(v, dict) and "el" in v):
                continue
            items.append(v)
            el = v["el"]
            while el is not None and not (el.tag.endswith("}g") and el.get("id")):
                el = parent.get(el)
            if el is not None and el.get("id") not in owners:
                owners.append(el.get("id"))
        out.append(Problem(iss, owners, items))
    return out, adv, hint_list


def _centre(it: dict) -> Tuple[float, float]:
    if "box" in it:
        b = it["box"]
        return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    (x1, y1), (x2, y2) = it["p"], it["q"]
    return (x1 + x2) / 2, (y1 + y2) / 2


def _vertical(seg: dict) -> bool:
    (x1, y1), (x2, y2) = seg["p"], seg["q"]
    return abs(x2 - x1) < abs(y2 - y1)


def _box(it: dict) -> Tuple[float, float, float, float]:
    if "box" in it:
        return it["box"]
    return CL.seg_box(it)


def where_to_widen(p: Problem) -> Optional[Tuple[str, float]]:
    """(axis, coordinate) of the gap a problem asks to widen, or None."""
    k, c = p.iss.kind, p.iss.ctx
    if k == "SHORT ARROW":
        s = c["s"]
        return ("y" if _vertical(s) else "x"), _centre(s)[1 if _vertical(s) else 0]
    if k == "LINE HUGS BORDER":
        s, b = c["s"], c["b"]
        ax = "x" if _vertical(s) else "y"
        i = 0 if ax == "x" else 1
        return ax, (_centre(s)[i] + _centre(b)[i]) / 2
    if k in ("TEXT AT BORDER", "LINE OVER TEXT", "LINE NEAR TEXT", "LINE OVER ICON"):
        s = c["s"]
        t = c.get("t") or c.get("i")
        ax = "x" if _vertical(s) else "y"
        i = 0 if ax == "x" else 1
        return ax, _centre(t)[i]
    pair = [v for v in p.items if "box" in v]
    if len(pair) >= 2:
        a, b = _box(pair[0]), _box(pair[1])
        ox = min(a[2], b[2]) - max(a[0], b[0])      # overlap on x (negative: apart)
        oy = min(a[3], b[3]) - max(a[1], b[1])
        ax = "x" if ox < oy else "y"                # the axis where less movement separates them
        i = 0 if ax == "x" else 1
        return ax, (_centre(pair[0])[i] + _centre(pair[1])[i]) / 2
    return None


def bracket(geom: Geometry, axis: str, v: float) -> Optional[Tuple[str, str, float]]:
    """The neighbouring tracks (a, b) on an axis with a ≤ v < b, and their distance."""
    tr = geom.cols if axis == "x" else geom.rows
    pre = "col" if axis == "x" else "row"
    pos = sorted(((p, t) for t, p in tr.items()), key=lambda it: it[0])
    for (pa, ta), (pb, tb) in zip(pos, pos[1:]):
        if pa <= v < pb and pb - pa > 0.5:
            return f"{pre}:{ta}", f"{pre}:{tb}", pb - pa
    return None


def edge_of(owner: str) -> Optional[Tuple[int, str]]:
    kind, ref, part = M.split_eid(owner)
    if kind == "edge" and ref.isdigit():
        return int(ref), part
    return None


def feedback(b: Build, probs: List[Problem], extra: Dict[Tuple[str, str, str], Requirement],
             skip: Dict[int, int]) -> bool:
    """Answer the problems left with new requirements / skips. False when nothing changes."""
    changed = False
    widened = set()

    def widen(axis: str, v: float, why: str, owner: str):
        nonlocal changed
        br = bracket(b.geom, axis, v)
        if br is None:
            return
        a, c, cur = br
        key = (axis, a, c)
        if key in widened:
            return
        widened.add(key)
        old = extra.get(key)
        d = max(cur, old.d if old else 0.0) + WIDEN
        extra[key] = Requirement(axis, a, c, d, f"feedback: {why}", owner)
        changed = True

    for p in probs:
        k = p.iss.kind
        edges = [e for e in (edge_of(o) for o in p.owners) if e]
        line_edges = [n for n, part in edges if part == ""]
        owner = p.owners[0] if p.owners else "check"
        if k in ("LINE OVER TEXT", "LINE OVER ICON", "LINE NEAR TEXT") and line_edges \
                and p.iss.ctx["s"].get("kind") == "connector":
            n = line_edges[0]
            if skip.get(n, 0) < MAX_SKIP:
                skip[n] = skip.get(n, 0) + 1
                changed = True
                continue
        w = where_to_widen(p)
        if w:
            widen(w[0], w[1], k.lower(), owner)
    # an edge the router drew in another shape than plan() reserved space for: widen the
    # gaps its planned route crosses (DESIGN 4.5 "re-solve")
    for wmsg in b.warnings:
        m = re.match(r"(edges\[\d+\])[^:]*: drew (\S+) instead of (\S+)", wmsg)
        if not m:
            continue
        for e in b.spec.edges:
            if e.src != m.group(1) or not re.search(re.escape(f"{e.a}") + r"\b", wmsg):
                continue
            pa, pb = _end_center(b.geom, e.a), _end_center(b.geom, e.b)
            if pa is None or pb is None:
                continue
            for axis, i in (("x", 0), ("y", 1)):
                if abs(pa[i] - pb[i]) > 1:
                    widen(axis, (pa[i] + pb[i]) / 2, "drew another shape", M.edge_eid(e.n))
    return changed


def _end_center(geom: Geometry, eid: str) -> Optional[Tuple[float, float]]:
    if eid in geom.nodes:
        n = geom.nodes[eid]
        return n.cx, n.cy
    if eid in geom.groups:
        r = geom.groups[eid].rect
        return r.cx, r.cy
    return None


# =======================================================================================
# Reporting

def spec_item(spec: Spec, owner: str) -> str:
    kind, ref, part = M.split_eid(owner)
    if kind == "node" and ref in spec.nodes:
        return f"{spec.nodes[ref].src} {ref}"
    if kind == "group" and ref in spec.groups:
        return f"{spec.groups[ref].src} {ref}"
    if kind == "edge" and ref.isdigit() and int(ref) < len(spec.edges):
        e = spec.edges[int(ref)]
        return f"{e.src} {e.a} {e.op} {e.b}" + (f" ({part})" if part else "")
    if kind == "raw":
        return f"raw[{ref}]"
    return owner


def spec_fix(spec: Spec, geom: Geometry, p: Problem) -> str:
    """A spec change to try for a problem the engine could not clear."""
    tips = []
    for o in p.owners:
        kind, ref, part = M.split_eid(o)
        if kind == "edge" and part in ("label", "badge"):
            tips.append(f"{spec_item(spec, o).split(' ')[0]}: "
                        + ("step_at: start|end|gap|[x, y]" if part == "badge" else "label_at: above|below|left|right"))
        elif kind == "edge":
            tips.append(f"{spec_item(spec, o).split(' ')[0]}: shape / bend_x / bend_y / from_side / to_side")
        elif kind == "node" and ref in spec.nodes:
            tips.append(f"{spec.nodes[ref].src} {ref}: dx / dy")
        elif kind == "group" and ref in spec.groups and p.iss.kind in ("TEXT AT BORDER", "HEADER CLEARANCE",
                                                                       "LINE HUGS BORDER"):
            tips.append(f"{spec.groups[ref].src} {ref}: pad / min_w / min_h")
    w = where_to_widen(p)
    if w:
        br = bracket(geom, w[0], w[1])
        if br:
            a, b, cur = br
            tips.append(f"{'cols' if w[0] == 'x' else 'rows'}: {{id: {b.split(':', 1)[1]}, "
                        f"min_gap_before: {M.fmt_num(cur + WIDEN)}}}")
    seen, out = set(), []
    for t in tips:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return "; ".join(out)


def summary(spec: Spec, b: Build, out_path: Path) -> List[str]:
    g, nb = b.geom, b.nb
    W, H = g.canvas_w, g.canvas_h
    lines = [f"draft: {out_path}"]
    pt = K.slide_pt(W, H, spec.title)
    lines.append(f"canvas: {M.fmt_num(W)} × {M.fmt_num(H)} ({spec.mode}); on a 16:9 slide "
                 f"({'titled' if spec.title else 'untitled'}) 12px text → {pt:.1f}pt"
                 + ("" if spec.mode != "slide" else (" (OK ≥ 10)" if pt >= K.SLIDE_MIN_PT else " (< 10pt)")))
    if nb.place == "none":
        lines.append("note: none")
    else:
        n = spec.note
        what = (f"{len(n.steps)} steps" if n.steps else "summary" if n.summary else f"{len(n.rows)} rows")
        lines.append(f"note: {nb.place}, {what}, {M.fmt_num(nb.w)} × {M.fmt_num(nb.h)}"
                     + (f" at ({M.fmt_num(nb.rect.x0)},{M.fmt_num(nb.rect.y0)})" if nb.rect else ""))
    refs = Counter(n.icon for n in spec.nodes.values())
    lines.append(f"icons ({len(spec.nodes)} nodes): " + ", ".join(
        f"{r}" + (f" ×{c}" if c > 1 else "") for r, c in refs.items()))
    for n in spec.nodes.values():
        if n.icon_query and n.template is None or (n.icon_query and n.instance == 1):
            lines.append(f"  alias {n.icon_query!r} → {n.icon} ({n.src})")
    for w in spec.warnings + g.warnings + b.warnings:
        lines.append(f"warning: {w}")
    if spec.mode == "document" and W > K.DOC_WIDE:
        lines.append(f"warning: canvas {M.fmt_num(W)} wide (> {K.DOC_WIDE}): on a ~900 px page 12px text comes out "
                     f"at {12 * 900 / W:.1f}px — fold the longest row: give a branch or a later stage its own row "
                     "(a lane below the main line, its flow still left → right) instead of more columns")
    return lines


def slide_problem(spec: Spec, geom: Geometry) -> Optional[str]:
    if spec.mode != "slide":
        return None
    pt = K.slide_pt(geom.canvas_w, geom.canvas_h, spec.title)
    if pt >= K.SLIDE_MIN_PT:
        return None
    lim_h = K.SLIDE_MAX_H[bool(spec.title)]
    over_w, over_h = geom.canvas_w - K.SLIDE_MAX_W, geom.canvas_h - lim_h
    which = (f"{M.fmt_num(over_w)}px too wide" if over_w >= over_h * K.SLIDE_MAX_W / lim_h
             else f"{M.fmt_num(over_h)}px too tall")
    return (f"SLIDE TOO SMALL 12px text comes out at {pt:.1f}pt (< {K.SLIDE_MIN_PT}) at "
            f"{M.fmt_num(geom.canvas_w)} × {M.fmt_num(geom.canvas_h)}: {which} for "
            f"{K.SLIDE_MAX_W} × {lim_h} — shorten the widest column's labels (see --explain), "
            "move the regional services row into a column, or split the slide")


# =======================================================================================
# CLI

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("spec", type=Path, help="<name>.layout.yaml (or .json)")
    ap.add_argument("-o", "--out", type=Path, help="draft to write (default <spec dir>/<name>.draft.svg)")
    ap.add_argument("--mode", choices=K.MODES_ORDER, help="override the spec's mode")
    t = ap.add_mutually_exclusive_group()
    t.add_argument("--title", dest="title", action="store_true", default=None,
                   help="slide with a title band (540 high)")
    t.add_argument("--no-title", dest="title", action="store_false", help="slide without one (600 high)")
    ap.add_argument("--explain", action="store_true", help="print which constraints set each track")
    ap.add_argument("--no-check", action="store_true", help="skip the in-process check and its feedback rounds")
    a = ap.parse_args(argv)

    try:
        spec = layout_spec.load(a.spec, mode=a.mode, title=a.title)
    except M.LayoutError as e:
        print("\n".join(e.problems))
        print(f"{len(e.problems)} problem{'s' if len(e.problems) != 1 else ''} in the spec")
        return 1
    out = a.out or a.spec.resolve().parent / f"{spec.name}.draft.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    source = str(a.spec)

    extra: Dict[Tuple[str, str, str], Requirement] = {}
    skip: Dict[int, int] = {}
    best = None                     # (problems, round, build, feedback reqs, skips)
    place = None
    try:
        for rnd in range(MAX_ROUNDS + 1):
            b = build(spec, list(extra.values()), dict(skip), place, source)
            place = b.nb.place if b.nb.place != "none" else None
            if a.no_check:
                best = (0, rnd, b, [], {})
                break
            probs = problems_of(b.svg)[0]
            n = len(probs)
            if best is None or n < best[0]:
                best = (n, rnd, b, list(extra.values()), dict(skip))
            if not probs or rnd == MAX_ROUNDS:
                break
            if not feedback(b, probs, extra, skip):
                break
    except M.LayoutError as e:
        print("\n".join(e.problems))
        print(f"{len(e.problems)} problem{'s' if len(e.problems) != 1 else ''}")
        return 1

    _, rnd, b, used, skipped = best
    data, fixed = (b.svg, 0) if a.no_check else fix_pass(b.svg, out)
    out.write_bytes(data)
    probs, hints = ([], []) if a.no_check else problems_of(data, hints=True)[0::2]
    sp = slide_problem(spec, b.geom)
    n = len(probs) + (1 if sp else 0)
    for line in summary(spec, b, out):
        print(line)
    if rnd:
        print(f"check: {rnd} feedback round{'s' if rnd != 1 else ''} ("
              + ", ".join(f"{r.why[len('feedback: '):]}: {r.a} → {r.b} ≥ {M.fmt_num(r.d)}" for r in used)
              + (f"; next routing candidate for {', '.join(f'edges[{k}]×{v}' for k, v in skipped.items())}"
                 if skipped else "") + ")")
    if fixed:
        print(f"check: {fixed} fixed-answer repair{'s' if fixed != 1 else ''} applied (check_layout --fix)")
    if a.explain:
        print("explain:")
        for line in b.geom.explain:
            print(f"  {line}")
    if a.no_check:
        print("check skipped (--no-check)")
        return 0
    hint_of = {id(iss): h for iss, h in hints}
    for p in probs:
        print(p.iss.msg)
        h = hint_of.get(id(p.iss))
        if h is not None and h.text:
            print(f"  fix: {h.text}")
        if p.owners:
            print(f"  spec: {', '.join(spec_item(spec, o) for o in p.owners)}")
        tip = spec_fix(spec, b.geom, p)
        if tip:
            print(f"  try: {tip}")
    if sp:
        print(sp)
        if not a.explain:              # the evidence: what set each track on the axis that overflows
            pre = "x col" if "too wide" in sp else "y row"
            for line in b.geom.explain:
                if line.startswith(pre):
                    print(f"  {line}")
    if n:
        print(f"{n} problem{'s' if n != 1 else ''}")
        return 1
    print("Layout OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
