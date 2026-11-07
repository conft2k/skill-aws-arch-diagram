#!/usr/bin/env python3
"""Turn a layout spec (<name>.layout.yaml) into a draft SVG that passes check_layout.py.

    python3 scripts/layout.py arch.layout.yaml [-o arch.draft.svg] [--mode slide]
                              [--title | --no-title] [--explain] [--no-check]

The spec names tracks (columns, rows), containers, nodes, edges and the note; the engine
computes every coordinate. Without -o the draft goes next to the spec as <name>.draft.svg.

Pipeline (the contract is layout_model.py's docstring, section 1):
  load → route.plan → solve (no note) → note.block → solve (with the note) → note.block
  (place and width fixed) → route.draw → emit → check_layout in process. A slide that
  comes out under 10pt with diagonal pairs kept apart on y is built once more with every
  such pair on x (solve(diag_x=True)), and the pass with the larger text is kept.
The check applies check_layout --fix's fixed-answer repairs, then answers what is left by
kind and solves again (at most 5 rounds): SHORT ARROW, LINE HUGS BORDER and a label or
badge crowded by a border, icon or another label widen the column / row gap it sits in
(in a flow column, which has no rows, the pitch between its two nodes around the spot);
a connector over a label or icon takes that edge's next routing candidate; LINE LEAVES BOX
and LINE OFF CANVAS (a detour around the outside of the box both ends are in, or past the
canvas edge) grow the room on that side — the box's border (as its pad_top / pad_bottom /
pad_left / pad_right would) or the canvas moves out past the line by its overshoot + 12,
so the next route runs inside (a line still past it after that takes its next routing
candidate); an edge the router could not draw in its planned shape (its "drew X instead
of Y" warning) widens the gaps it spans — a round runs for that even when the check is
clean, since the detour it drew may still pass the check (a shape the spec asked for and
the router refused is not counted: no widening is planned for it). The round with the
fewest problems (a slide that comes out too small counts as one), then the fewest edges
drawn in another shape, is written.

The retained draft's remaining LINE IN HEADER problems get at most five further feedback
rounds: mark those edges' header bands as routing obstacles, then, if no acceptable route
fits, require room from the group's left/top wall to the contained end node. Keep a
candidate only when it reduces header crossings without adding another check code or
rule violation, or taking a previously fitting slide below 10pt.

Output: a summary (canvas, the size the smallest text gets on a 16:9 slide, the note, the icon
refs, warnings), then check_layout's problem lines, each with the spec items behind it and
a spec change to try, and last `Layout OK` or `N problems`, with any remaining rule
violations and delivery guidance appended. Exit status 0 when check_layout and slide fit
pass, 1 when their problems remain or the spec is invalid; rule violations are report-only.
--explain also prints, per track
(and per flow-column node), the chain of constraints that set its position. --no-check skips the check (and the
feedback rounds). The same spec always gives a byte-identical draft.

Needs PyYAML for .yaml specs (`uv run --with pyyaml python3 scripts/layout.py ...` when it
is missing; a .json spec needs nothing). Python 3.9+, standard library otherwise.
"""
import argparse
import copy
import math
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import xml.parsers.expat
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
import layout_text  # noqa: E402
from layout_model import Element, Geometry, NoteBlock, Requirement, Spec  # noqa: E402

MAX_ROUNDS = 5          # feedback rounds after the first solve (DESIGN 4.10)
WIDEN = 16              # px a feedback round adds to a gap
MAX_SKIP = 3            # candidates an edge may skip before its gap is widened instead
# The router's warning for an edge drawn in another shape than plan() reserved space for.
SHAPE_MISS = re.compile(r"drew (\S+) instead of")
# A shape the spec asked for and the router refused (the warning says what to change).
REFUSED = "refusing the requested"
# check_layout's detour problems: the room on that side of the box (or canvas) grows.
DETOURS = ("LINE OFF CANVAS", "LINE LEAVES BOX")
# check_layout's text clashes: one set of owners clashing counts once in a round's score.
TEXT_CLASH = ("TEXT NEAR ICON", "TEXT OVERLAP")
SIDE_VAR = {"left": "L", "right": "R", "top": "T", "bottom": "B"}
SVG_NS = "http://www.w3.org/2000/svg"
# The tags, and the <g> attributes, svg2pptx.collect accepts (DRAWN / its <g> rule).
RAW_TAGS = {"g", "rect", "image", "text", "line", "polyline", "circle", "tspan"}


# =======================================================================================
# One build: spec + feedback → elements

class Build:
    """Everything one pass of the pipeline produced."""

    def __init__(self, spec: Spec, geom: Geometry, nb: NoteBlock, elements: List[Element],
                 warnings: List[str], svg: bytes, avoid_headers=None,
                 feedback_svg: Optional[bytes] = None):
        self.spec, self.geom, self.nb, self.elements = spec, geom, nb, elements
        self.warnings, self.svg = warnings, svg
        self.avoid_headers = set(avoid_headers or ())
        self.feedback_svg = feedback_svg if feedback_svg is not None else svg


def slide_text_pt(spec: Spec, svg: bytes) -> Tuple[float, Optional[Tuple[float, str]], Tuple[float, float]]:
    """(pt, (font-size, text), (w, h)) of the smallest text the draft `svg` puts on a 16:9
    slide (check_layout.slide_texts), at the size svg2pptx gives it on its viewBox
    (layout_const.smallest_pt; inf without text or a usable viewBox)."""
    root = ET.fromstring(svg)
    vb = CL.viewbox(root)[0]
    if vb is None:
        return math.inf, None, (0.0, 0.0)
    pt, t = K.smallest_pt(vb[2], vb[3], spec.title, CL.slide_texts(root))
    return pt, t, (vb[2], vb[3])


def drawn_text(spec: Spec, svg: bytes):
    """(effective size/unit/target/floor, smallest canvas text, canvas size)."""
    root = ET.fromstring(svg)
    vb = CL.viewbox(root)[0]
    t = K.smallest_text(CL.slide_texts(root))
    if vb is None or t is None:
        return (math.inf, "pt" if spec.mode == "slide" else "px", 0, 0), None, (0, 0)
    return K.effective_text(spec.mode, vb[2], vb[3], t[0], spec.title), t, (vb[2], vb[3])


# check_layout's fixed answers that change a text's size (SMALL TEXT raises it to 12px; CIDR
# IN TITLE uses the scoped CIDR font on its own line): a round showing one is judged on its
# draft after fix_pass, as the written draft will be.
TEXT_SIZE_FIXES = {"SMALL TEXT", "CIDR IN TITLE"}


def value(var: str, geom: Geometry, axis: str) -> float:
    """A Requirement variable's value on a solved geometry (layout_model section 4)."""
    if var == "origin":
        return 0.0
    if var == "drawing":
        return geom.drawing.x1 if axis == "x" else geom.drawing.y1
    kind, ref = var.split(":", 1)
    if kind == "col" or kind == "row":
        return geom.track(ref)
    if kind == "node":
        n = geom.nodes[ref]
        return n.cx if axis == "x" else n.cy
    gid, side = ref.rsplit(".", 1)
    return geom.groups[gid].rect.get({"L": "x0", "R": "x1", "T": "y0", "B": "y1"}[side])


def build(spec: Spec, extra: Sequence[Requirement], skip: Dict[int, int], place: Optional[str],
          source: str, avoid_headers=None) -> Build:
    with layout_text.font_context(spec.font_factor, spec.font_steps):
        return build_at_size(spec, extra, skip, place, source, avoid_headers)


def build_at_size(spec: Spec, extra: Sequence[Requirement], skip: Dict[int, int], place: Optional[str],
                  source: str, avoid_headers=None) -> Build:
    route_kw = {"avoid_headers": avoid_headers} if avoid_headers else {}
    b = _build(spec, extra, skip, place, source, **route_kw)
    if b.geom.diag_y and slide_problem(spec, b.feedback_svg):
        # the solve weighs a diagonal pair's x and y growth px for px, but a 1108 × 540
        # slide has half the room down: with the pairs put on y leaving the text under
        # 10pt, build again with every pair on x and keep the larger text (both passes
        # solve the note too, so its place and size follow the geometry it sits on)
        try:
            alt = _build(spec, extra, skip, place, source, diag_x=True, **route_kw)
        except M.LayoutError:
            return b
        if slide_text_pt(spec, alt.feedback_svg)[0] > slide_text_pt(spec, b.feedback_svg)[0]:
            return alt
    return b


def _build(spec: Spec, extra: Sequence[Requirement], skip: Dict[int, int], place: Optional[str],
           source: str, diag_x: bool = False, avoid_headers=None) -> Build:
    reqs = layout_route.plan(spec) + list(extra)
    geom0 = layout_solve.solve(spec, reqs, diag_x=diag_x)
    nb0 = layout_note.block(spec, geom0, place=place)
    # Notes must not change which drawing/route wins feedback merely by fixing a text
    # overflow. Evaluate the existing note layout, then wrap on the chosen geometry.
    old_nb0 = layout_note.block(spec, geom0, place=nb0.place,
                               width=nb0.w if nb0.place == "pane" else None, wrap_text=False)
    geom = layout_solve.solve(spec, reqs + nb0.requirements, note_block=old_nb0, diag_x=diag_x)
    nb = layout_note.block(spec, geom, place=nb0.place, width=nb0.w if nb0.place == "pane" else None)
    old_nb = layout_note.block(spec, geom, place=nb0.place,
                              width=nb0.w if nb0.place == "pane" else None, wrap_text=False)
    warns = list(nb0.warnings)
    for r in nb.requirements:          # the contract: nb's requirements hold on geom
        got = value(r.b, geom, r.axis) - value(r.a, geom, r.axis)
        if got < r.d - 0.5:
            warns.append(f"note: requirement {r.why!r} short by {M.fmt_num(r.d - got)}px on the final geometry")
    route_kw = {"avoid_headers": avoid_headers} if avoid_headers else {}
    edges, route_warns = layout_route.draw(spec, geom, skip, **route_kw)
    raws, raw_warns = raw_elements(spec, geom)
    drawing = layout_solve.draw(spec, geom) + edges
    feedback_svg = emit(spec, geom, drawing + old_nb.elements + raws, source)
    elements = drawing + nb.elements + raws
    geom.canvas_h = max(geom.canvas_h, math.ceil(geom.drawing.y1 + nb.below()))
    warns += [w for w in nb.warnings if w not in warns] + route_warns + raw_warns
    return Build(spec, geom, nb, elements, warns, emit(spec, geom, elements, source),
                 avoid_headers=avoid_headers, feedback_svg=feedback_svg)


# =======================================================================================
# raw fragments

PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
RAW_ATTRIBUTES = re.compile(rb'\s+([^\s=/>]+)\s*=\s*("[^"]*"|\'[^\']*\')')


def scale_raw_text(svg: str, factor: float, steps=()) -> str:
    """Materialize default/inherited text sizes and scale each original size once.

    Flatten group font inheritance onto text so SVG, the checker and svg2pptx see
    the same size. Byte edits preserve the rest of the fragment, including comments;
    unscaled fragments without inheritance stay byte-identical.
    """
    prefix = f'<svg xmlns="{SVG_NS}">'.encode()
    raw = svg.encode()
    wrapped = prefix + raw + b"</svg>"
    parser = xml.parsers.expat.ParserCreate()
    stack, edits = [(16.0, False)], []   # svg2pptx's default text size

    def start(name, attrs):
        tag = name.rsplit(":", 1)[-1]
        font, inherited = stack[-1]
        declared = attrs.get("font-size")
        valid = declared is None or declared == "inherit"
        if declared is not None and declared != "inherit":
            try:
                value = float(declared)
                valid = math.isfinite(value) and value >= 0
                if valid:
                    font = value
            except ValueError:
                pass
        group_font = tag == "g" and declared is not None and valid
        stack.append((font, inherited or group_font))
        # Plain tspans inherit the parent's scaled size. Formatting on a tspan is
        # already refused by svg2pptx; preserve it for the same diagnostic.
        text_font = tag == "text" and valid and (
            factor != 1 or inherited or declared == "inherit")
        if not group_font and not text_font:
            return
        begin = parser.CurrentByteIndex
        end, quote = begin, None
        while end < len(wrapped):
            char = wrapped[end]
            if quote is not None:
                if char == quote:
                    quote = None
            elif char in (34, 39):
                quote = char
            elif char == 62:
                break
            end += 1
        opening = wrapped[begin:end + 1]
        attr = next((m for m in RAW_ATTRIBUTES.finditer(opening) if m[1] == b"font-size"), None)
        updated = opening
        if group_font and attr:
            updated = opening[:attr.start()] + opening[attr.end():]
        if text_font:
            size = layout_text.font_size(font, factor, steps) if font else 0
            if attr:
                quote_byte = attr[2][:1]
                updated = opening[:attr.start(2)] + quote_byte + str(size).encode() + quote_byte + opening[attr.end(2):]
            else:
                at = len(updated) - (2 if updated.endswith(b"/>") else 1)
                updated = updated[:at] + f' font-size="{size}"'.encode() + updated[at:]
        edits.append((begin - len(prefix), end + 1 - len(prefix), updated))

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda name: stack.pop()
    try:
        parser.Parse(wrapped, True)
    except xml.parsers.expat.ExpatError:
        return svg                    # raw_problems supplies the existing diagnostic
    for begin, end, updated in reversed(edits):
        raw = raw[:begin] + updated + raw[end:]
    return raw.decode()


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
        svg = scale_raw_text(svg, spec.font_factor, spec.font_steps)
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
        if tag != "g" and ((el.get("display") or "").strip().lower() not in ("", "inline", "inherit")
                           or (el.get("visibility") or "").strip().lower() not in ("", "visible", "inherit")):
            probs.append(f"<{tag}> sets display= / visibility= (svg2pptx takes only the defaults); "
                         "leave a hidden element out of the fragment")
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
    scale_attr = (f' data-text-scale="{spec.font_factor:.17g}"' if spec.font_factor != 1 else "")
    if spec.font_steps:
        scale_attr += ' data-text-steps="' + ",".join(f"{s:.17g}" for s in spec.font_steps) + '"'
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="{SVG_NS}" font-family="{_esc(spec.font, True)}"{scale_attr}>',
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


def fixed_build(b: Build, scratch: Path) -> Tuple[bytes, int]:
    """Reuse a build's identical fixed-answer pass during header repair and output."""
    cached = getattr(b, "_fixed_draft", None)
    if cached is None or cached[0] != b.svg:
        cached = (b.svg, fix_pass(b.svg, scratch))
        b._fixed_draft = cached
    return cached[1]


class Problem:
    def __init__(self, iss, owners: List[str], items: List[dict]):
        self.iss, self.owners, self.items = iss, owners, items


def problems_of(data: bytes, hints: bool = False) -> Tuple[List[Problem], "CL.Advisor", List]:
    """Every check_layout problem, with the element ids (<g id>) of what it involves; with
    hints, check_layout's fix line for each (slow: it re-checks candidate moves)."""
    root = ET.fromstring(data)
    adv = CL.Advisor(root, engine=True)
    hint_list = [(iss, adv.hint(iss)) for iss in adv.issues] if hints else []
    parent = {c: p for p in root.iter() for c in p}
    out = []
    for iss in adv.issues:
        owners, items = [], []
        for v in iss.ctx.values():
            if isinstance(v, tuple) and len(v) == 5:     # a container rect (x, y, w, h, element)
                el = v[4]
            elif isinstance(v, dict) and "el" in v:
                items.append(v)
                el = v["el"]
            else:
                continue
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


def between_ports(spec: Spec, geom: Geometry, p: Problem, lo: float, hi: float, i: int) -> bool:
    """Does the gap lo..hi (on axis i) of an in-line LINE ON LINE lie between two ports of
    one node both its lines end on: inside that node's icon along the line (two lines out
    of one side at ±8, turning apart along one line at the ports' height)? No track gap
    opens it: the ports' spacing sets it."""
    nodes = None
    for n, part in (e for e in (edge_of(o) for o in p.owners) if e):
        if part or n >= len(spec.edges):
            continue
        e = spec.edges[n]
        mine = {v for v, kd in ((e.a, e.a_kind), (e.b, e.b_kind)) if kd == "node"}
        nodes = mine if nodes is None else nodes & mine
    for nid in nodes or ():
        b = geom.nodes[nid].icon if nid in geom.nodes else None
        if b is not None and (b.x0, b.y0)[i] - 0.5 <= lo and hi <= (b.x1, b.y1)[i] + 0.5:
            return True
    return False


def where_to_widen(p: Problem, spec: Optional[Spec] = None,
                   geom: Optional[Geometry] = None) -> Optional[Tuple[str, float]]:
    """(axis, coordinate) of the gap a problem asks to widen, or None (also for an in-line
    LINE ON LINE whose gap lies between two ports of one node, given spec and geom:
    between_ports)."""
    k, c = p.iss.kind, p.iss.ctx
    if k == "SHORT ARROW":
        s = c["s"]
        return ("y" if _vertical(s) else "x"), _centre(s)[1 if _vertical(s) else 0]
    if k == "LINE ON LINE":
        s = c["s"]
        if CL.collinear_run(s, c["o"]) <= K.ON_LINE_RUN:
            # two flows on one line with a gap between them (lines_in_line): the gap along
            # the line grows where they part, so the one drawn in a fallback has room for
            # its own shape; not when the gap lies between two ports of one node, whose
            # spacing no track sets (ce-tgw round 0: enib.1 -> tgw and tgw -> seni.2's
            # VHV fallback turning apart under the TGW's bottom ports 12px apart; the
            # fallback's miss feedback widens its gaps: drew another shape)
            ax = "y" if _vertical(s) else "x"
            i = 0 if ax == "x" else 1
            ends = sorted(v for seg in (s, c["o"]) for v in (seg["p"][i], seg["q"][i]))
            if spec is not None and geom is not None and between_ports(spec, geom, p, ends[1], ends[2], i):
                return None
            return ax, (ends[1] + ends[2]) / 2
        # two flows on one run: the gap the run lies in grows, so the router has room for a
        # lane each (layout_route lane_counts / _lanes)
        ax = "x" if _vertical(s) else "y"
        return ax, _centre(s)[0 if ax == "x" else 1]
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


def stack_bracket(spec: Spec, geom: Geometry, owners: Sequence[str], v: float) -> Optional[Tuple[str, str, float, str]]:
    """A y spot in a flow column one of `owners` sits in: the neighbouring nodes (a, b) of
    that stack with a ≤ v < b, their distance and the column (flow columns have no rows)."""
    nids = {M.split_eid(o)[1] for o in owners if M.split_eid(o)[0] == "node"}
    for (_, col), ids in spec.flow_stacks().items():
        if not nids & set(ids):
            continue
        for a, c in zip(ids, ids[1:]):
            pa, pc = geom.nodes[a].cy, geom.nodes[c].cy
            if pa <= v < pc:
                return f"node:{a}", f"node:{c}", pc - pa, col
    return None


def edge_of(owner: str) -> Optional[Tuple[int, str]]:
    kind, ref, part = M.split_eid(owner)
    if kind == "edge" and ref.isdigit():
        return int(ref), part
    return None


def feedback(b: Build, probs: List[Problem], extra: Dict[Tuple[str, str, str], Requirement],
             skip: Dict[int, int], avoid_headers=None) -> bool:
    """Answer the problems left with new requirements / skips. False when nothing changes."""
    changed = False
    widened = set()
    roomed = set()          # edges whose detour got room on its side this round

    def widen(axis: str, v: float, why: str, owner: str, owners: Sequence[str] = ()):
        nonlocal changed
        br = (stack_bracket(b.spec, b.geom, owners, v) if axis == "y" else None) or bracket(b.geom, axis, v)
        if br is None:
            return
        a, c, cur = br[:3]
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
        if k == "LINE IN HEADER" and line_edges:
            n = line_edges[0]
            # First constrain routing on the existing geometry. Only a crossing that
            # remains after that asks the solve to open room beside/below the header.
            if avoid_headers is not None and n not in avoid_headers:
                avoid_headers.add(n)
                changed = True
                continue
            r = header_room(b, p, n)
            if r is not None:
                key = (r.axis, r.a, r.b)
                if r.d > (extra[key].d if key in extra else -1e9):
                    extra[key] = r
                    changed = True
                    continue
            if skip.get(n, 0) < MAX_SKIP:
                skip[n] = skip.get(n, 0) + 1
                changed = True
            continue
        if k in DETOURS and line_edges:
            n = line_edges[0]
            r = room(b, p, n)
            if r is not None and (r.d > (extra[(r.axis, r.a, r.b)].d if (r.axis, r.a, r.b) in extra else -1e9)):
                extra[(r.axis, r.a, r.b)] = r
                roomed.add(n)
                changed = True
            elif skip.get(n, 0) < MAX_SKIP:     # the room is there and the route still leaves it
                skip[n] = skip.get(n, 0) + 1
                changed = True
            continue
        if k in ("LINE OVER TEXT", "LINE OVER ICON", "LINE NEAR TEXT", "LOOSE END") and line_edges \
                and p.iss.ctx["s"].get("kind") == "connector":
            n = line_edges[0]
            if skip.get(n, 0) < MAX_SKIP:
                skip[n] = skip.get(n, 0) + 1
                changed = True
                continue
        w = where_to_widen(p, b.spec, b.geom)
        if w:
            widen(w[0], w[1], k.lower(), owner, p.owners)
    # an edge the router drew in another shape than plan() reserved space for: widen the
    # gaps its planned route crosses (DESIGN 4.5 "re-solve")
    for wmsg in b.warnings:
        m = re.match(r"(edges\[\d+\])[^:]*: drew (\S+) instead of (\S+)", wmsg)
        if not m:
            continue
        for e in b.spec.edges:
            if e.src != m.group(1) or not re.search(re.escape(f"{e.a}") + r"\b", wmsg):
                continue
            if e.n in roomed:       # its detour is being given room: that is the answer this round
                continue
            pa, pb = _end_center(b.geom, e.a), _end_center(b.geom, e.b)
            if pa is None or pb is None:
                continue
            ends = [f"node:{i}" for i, k in ((e.a, e.a_kind), (e.b, e.b_kind)) if k == "node"]
            for axis, i in (("x", 0), ("y", 1)):
                if abs(pa[i] - pb[i]) > 1:      # two nodes of one flow column: their pitch
                    widen(axis, (pa[i] + pb[i]) / 2, "drew another shape", M.edge_eid(e.n), ends)
                    # and every other gap between the two ends' tracks: the obstacle that
                    # kept the planned shape out may sit in any of them (ce-tgw: tgw ->
                    # seni.2's HVH needs its bend before Firewall RT, not past it)
                    lo, hi = sorted((pa[i], pb[i]))
                    tr = sorted(v for v in (b.geom.cols if axis == "x" else b.geom.rows).values() if lo - 0.5 <= v <= hi + 0.5)
                    for u, v in zip(tr, tr[1:]):
                        widen(axis, (u + v) / 2, "drew another shape", M.edge_eid(e.n), ends)
    return changed


def problem_count(probs: List[Problem]) -> int:
    """The problems a round is scored by: check_layout's count, with the text clashes
    (TEXT_CLASH) between one set of owners counted once — two nodes drawn on top of each
    other report a TEXT NEAR ICON and a TEXT OVERLAP for one collision, which must not tie
    that round with one that leaves a line on a border instead."""
    seen, n = set(), 0
    for p in probs:
        if p.iss.kind in TEXT_CLASH and p.owners:
            key = frozenset(p.owners)
            if key in seen:
                continue
            seen.add(key)
        n += 1
    return n


def shape_misses(b: Build) -> int:
    """How many edges the router drew in another shape than planned (each asks a re-solve);
    a shape the spec asked for and the router refused is left out (widening the gaps the
    edge spans is not what it needs: its warning says what is)."""
    return sum(1 for w in b.warnings if SHAPE_MISS.search(w) and REFUSED not in w)


def detour_side(p: Problem, spec: Spec) -> Optional[Tuple[Optional[str], str, float]]:
    """(group id or None for the canvas, side, px past it) of a LINE LEAVES BOX / LINE OFF
    CANVAS problem: the box it leaves (an off-canvas line out of its box too: that box);
    None for a box that is no spec group (a raw rect)."""
    c = p.iss.ctx
    side = c["side"]
    if c.get("r") is None:
        return None, side, c["d"]
    gid = next((M.split_eid(o)[1] for o in p.owners if M.split_eid(o)[0] == "group"
                and M.split_eid(o)[1] in spec.groups), None)
    if gid is None:
        return None
    return gid, side, c["box_d"] if c.get("box_d") is not None else c["d"]


def room(b: Build, p: Problem, n: int) -> Optional[Requirement]:
    """The requirement that moves the border (or canvas edge) a detour leaves past out by
    its overshoot + HUG_CLEAR, measured from edge n's end on that axis: the router keeps
    its detour where it was relative to the ends, so it then runs inside."""
    spec, geom = b.spec, b.geom
    where = detour_side(p, spec)
    if where is None:
        return None
    gid, side, over = where
    e = spec.edges[n]
    axis = "x" if side in ("left", "right") else "y"
    far = side in ("right", "bottom")
    end = next((f"node:{i}" for i, kd in ((e.a, e.a_kind), (e.b, e.b_kind)) if kd == "node"), None)
    if end is None:
        g = next((i for i, kd in ((e.a, e.a_kind), (e.b, e.b_kind)) if kd == "group" and i != gid), None)
        if g is None:
            return None
        end = f"group:{g}.{SIDE_VAR[side]}"
    if gid is not None:
        wall = f"group:{gid}.{SIDE_VAR[side]}"
        need = over + CL.HUG_CLEAR
    elif far:
        # the canvas edge is the drawing's + canvas_margin (more with a note below)
        wall = "drawing"
        edge = geom.canvas_w if axis == "x" else geom.canvas_h
        need = edge + over + CL.HUG_CLEAR - spec.const.canvas_margin - value("drawing", geom, axis)
    else:
        wall = "origin"
        need = over + CL.HUG_CLEAR
    if need <= 0:
        return None
    a, c = (end, wall) if far else (wall, end)
    cur = value(c, geom, axis) - value(a, geom, axis)
    where = f"{gid} {side}" if gid else f"canvas {side}"
    return Requirement(axis, a, c, cur + need, f"feedback: {p.iss.kind.lower()} ({where})", M.edge_eid(n))


def header_room(b: Build, p: Problem, n: int) -> Optional[Requirement]:
    """Keep a header-crossing leg past the band's right/bottom edge.

    As with detour room(), measure from a group wall to the line's contained end.
    Preserve the leg's offset from that end when asking the solve for more room,
    rather than widening an unrelated neighbouring track by a fixed increment.
    """
    spec, geom = b.spec, b.geom
    gid = next((M.split_eid(o)[1] for o in p.owners if M.split_eid(o)[0] == "group"
                and M.split_eid(o)[1] in spec.groups), None)
    if gid is None:
        return None
    e = spec.edges[n]
    ends = [nid for nid, kind in ((e.b, e.b_kind), (e.a, e.a_kind))
            if kind == "node" and gid in spec.node_chain(nid)]
    if not ends or e.points:
        return None
    s, band = p.iss.ctx["s"], p.iss.ctx["band"]
    axis = "x" if _vertical(s) else "y"
    i = 0 if axis == "x" else 1
    nid = min(ends, key=lambda v: abs(value(f"node:{v}", geom, axis) - _centre(s)[i]))
    wall, end = f"group:{gid}.{'L' if axis == 'x' else 'T'}", f"node:{nid}"
    need = band[i + 2] + CL.LINE_CLEAR - min(s["p"][i], s["q"][i])
    cur = value(end, geom, axis) - value(wall, geom, axis)
    return Requirement(axis, wall, end, cur + need, f"feedback: line in header ({gid})", M.edge_eid(n))


def repair_headers(b: Build, rnd: int, used: Sequence[Requirement], skipped: Dict[int, int],
                   source: str, scratch: Path, max_rounds: int = MAX_ROUNDS):
    """Repair B2 on the retained draft, preserving its other checks, rules and slide fit.

    Earlier rounds can clear transient header crossings by resolving their original
    problems. Start here only if the retained, auto-repaired draft still has B2, so
    inputs whose final draft had no B2 keep their existing output.
    """
    raw_probs = problems_of(b.svg)[0]
    if not any(p.iss.kind in {"LINE IN HEADER", "TITLE OFFSET", "CIDR IN TITLE",
                              "CIDR OFF HEADER", "SMALL TEXT"} for p in raw_probs):
        return rnd, b, list(used), skipped
    initial = fixed_build(b, scratch)[0]
    probs = problems_of(initial)[0]
    headers = [p for p in probs if p.iss.kind == "LINE IN HEADER"]
    if not headers:
        return rnd, b, list(used), skipped
    import rules

    def judge(candidate):
        data = fixed_build(candidate, scratch)[0]
        probs = problems_of(data)[0]
        other = Counter(p.iss.kind for p in probs if p.iss.kind != "LINE IN HEADER")
        viol = Counter((v.rule, v.code) for v in rules.check(candidate.spec, candidate.geom, data) if v.code != "B2")
        return probs, other, viol, bool(slide_problem(candidate.spec, data))

    base_checks = Counter(p.iss.kind for p in probs if p.iss.kind != "LINE IN HEADER")
    base_rules = Counter((v.rule, v.code) for v in rules.check(b.spec, b.geom, initial) if v.code != "B2")
    base_small = bool(slide_problem(b.spec, initial))
    best = (len(headers), rnd, b, list(used), dict(skipped))
    extra = {(r.axis, r.a, r.b): r for r in used}
    skip, avoid = dict(skipped), set()
    place = b.nb.place if b.nb.place != "none" else None
    for step in range(1, max_rounds + 1):
        if not feedback(b, headers, extra, skip, avoid):
            break
        previous, previous_headers = b, headers
        try:
            b = build(b.spec, list(extra.values()), skip, place, source, avoid_headers=avoid)
        except M.LayoutError:
            break
        probs, checks, violations, small = judge(b)
        headers = [p for p in probs if p.iss.kind == "LINE IN HEADER"]
        if not (checks - base_checks or violations - base_rules or (small and not base_small)):
            if len(headers) < best[0]:
                best = (len(headers), rnd + step, b, list(extra.values()), dict(skip))
            if not headers:
                break
        elif not headers:
            # A route that clears B2 by creating another defect is not a repair.
            # Ask for room from the last crossing, then try another candidate.
            b, headers = previous, previous_headers
    return best[1:]


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
    if p.iss.kind in DETOURS and detour_tip(spec, geom, p):
        tips.append(detour_tip(spec, geom, p))
    stacked = {nid: col for (_, col), ids in spec.flow_stacks().items() for nid in ids}
    lines = {spec.edges[e[0]].line for e in (edge_of(o) for o in p.owners)
             if e and e[1] == "" and e[0] < len(spec.edges)}
    n_edges = sum(1 for o in p.owners if (e := edge_of(o)) and e[1] == "")
    one_line = n_edges >= 2 and len(lines) == 1        # the instances of one `.*` line
    for o in p.owners:
        kind, ref, part = M.split_eid(o)
        if kind == "edge" and part in ("label", "badge"):
            tips.append(f"{spec_item(spec, o).split(' ')[0]}: "
                        + ("step_at: start|end|gap|[x, y]" if part == "badge" else "label_at: above|below|left|right"))
        elif kind == "edge":
            # two flows out of (into) one port: an offset gives one a port of its own; one
            # offset is shared by all the instances of a `.*` line, which merge with
            # trunk: true or take one spec line each with its own offset
            offs = ""
            if p.iss.kind == "LINE ON LINE":
                offs = " / from_offset / to_offset" + (
                    " (instances of one line: trunk: true when they merge, else one spec line each with its"
                    " own offset)" if one_line else "")
            tips.append(f"{spec_item(spec, o).split(' ')[0]}: shape / bend_x / bend_y / from_side / to_side{offs}")
            if p.iss.kind == "LOOSE END" and ref.isdigit() and int(ref) < len(spec.edges) \
                    and spec.edges[int(ref)].trunk:
                # a trunk follower that stops short of its lead
                tips.append(f"{spec_item(spec, o).split(' ')[0]}: drop `trunk: true` so each instance has its "
                            "own arrow")
        elif kind == "node" and ref in stacked:
            # a flow-column node takes no dy: the stack sets its y
            tips.append(f"{spec.nodes[ref].src} {ref}: dx (its y: flow / align on column {stacked[ref]})")
        elif kind == "node" and ref in spec.nodes:
            tips.append(f"{spec.nodes[ref].src} {ref}: dx / dy")
        elif kind == "group" and ref in spec.groups and p.iss.kind in ("TEXT AT BORDER", "HEADER CLEARANCE",
                                                                       "LINE HUGS BORDER", "LINE IN HEADER"):
            tips.append(f"{spec.groups[ref].src} {ref}: pad / min_w / min_h")
    w = where_to_widen(p, spec, geom)
    st = stack_bracket(spec, geom, p.owners, w[1]) if w and w[0] == "y" else None
    if st:
        al = spec.track(st[3]).align
        tips.append(f"cols: {{id: {st[3]}, flow: {M.fmt_num(st[2] + WIDEN)}"
                    + (f", align: {al}" if al != "center" else "") + "}")
    elif w:
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


def detour_tip(spec: Spec, geom: Geometry, p: Problem) -> str:
    """The room a detour past a box border (or the canvas edge) needs: that side's pad, at
    the room it has now + the overshoot + 12 — or, on the canvas, a route between the ends."""
    where = detour_side(p, spec)
    if where is None:
        return ""
    gid, side, over = where
    if gid is None:
        return (f"the canvas {side} edge leaves no room for a route round the ends: from_side / to_side / shape "
                f"that keep the line between them, or a node / box beyond them on that side")
    r = geom.groups[gid].rect
    inner = [n.icon if side == "top" else n.footprint() for n in geom.nodes.values()]
    inner += [g.rect for i, g in geom.groups.items() if i != gid]
    inner = [b for b in inner if r.x0 <= b.x0 and b.x1 <= r.x1 and r.y0 <= b.y0 and b.y1 <= r.y1 and b != r]
    k = {"left": 0, "top": 1, "right": 2, "bottom": 3}[side]
    edge = (r.x0, r.y0, r.x1, r.y1)[k]
    have = min((abs(edge - (b.x0, b.y0, b.x1, b.y1)[k]) for b in inner), default=0.0)
    return (f"{spec.groups[gid].src}: pad_{side}: {M.fmt_num(math.ceil(have + over + CL.HUG_CLEAR))} "
            f"(room {side} of what it holds for the line, {M.fmt_num(have)} now)")


def summary(spec: Spec, b: Build, out_path: Path, svg: Optional[bytes] = None) -> List[str]:
    """The summary lines; the slide text size from `svg`, the draft as written (b.svg if None)."""
    g, nb = b.geom, b.nb
    W, H = g.canvas_w, g.canvas_h
    lines = [f"draft: {out_path}"]
    data = b.svg if svg is None else svg
    (actual, unit, target, floor), t, _ = drawn_text(spec, data)
    if spec.mode == "slide":
        lines.append(f"canvas: {M.fmt_num(W)} × {M.fmt_num(H)} ({spec.mode}); on a 16:9 slide "
                 f"({'titled' if spec.title else 'untitled'}) "
                 + ("no text" if t is None else f"the smallest text ({M.fmt_num(t[0])}px) → {actual:.1f}pt"
                    + (f" (OK ≥ {target})" if actual >= target else f" (< {target}pt)")))
    else:
        lines.append(f"canvas: {M.fmt_num(W)} × {M.fmt_num(H)} ({spec.mode}); "
                     + ("no text" if t is None else
                        f"smallest text {M.fmt_num(t[0])}px → {actual:.1f}px in a "
                        f"{K.DOCUMENT_COLUMN_PX}px column (target {target})"))
    if t is not None and actual < target:
        lines.append(f"warning: smallest text {actual:.1f}{unit} below target {target}{unit}"
                     + (f" and floor {floor}{unit}; split the diagram or write a mode: slide spec"
                        if actual < floor else ""))
    if spec.font_factor != 1:
        lines.append(f"text scale: {spec.font_factor:.3g}× (uniform fonts, re-laid out)")
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
    return lines


def slide_problem(spec: Spec, svg: bytes) -> Optional[str]:
    """SLIDE TOO SMALL when the smallest text the draft `svg` draws comes out under 10pt."""
    if spec.mode != "slide":
        return None
    (pt, _, target, _), t, (W, H) = drawn_text(spec, svg)
    if t is None or pt >= K.SLIDE_MIN_PT:
        return None
    px = t[0]
    lim_w, lim_h = K.slide_max(spec.title, px)
    over_w, over_h = W - lim_w, H - lim_h
    which = (f"{M.fmt_num(over_w)}px too wide" if over_w >= over_h * lim_w / lim_h
             else f"{M.fmt_num(over_h)}px too tall")
    return (f"SLIDE TOO SMALL smallest text ({M.fmt_num(px)}px, {t[1]!r}) comes out at {pt:.1f}pt "
            f"(< {K.SLIDE_MIN_PT}) at {M.fmt_num(W)} × {M.fmt_num(H)}: {which} for "
            f"{lim_w} × {lim_h} — shorten the widest column's labels (see --explain), "
            "move the regional services row into a column, or split the slide")


def rule_lines(spec: Spec, geom: Geometry, data: bytes) -> List[str]:
    """The user rules' verdict on the written draft (scripts/rules.py), one `rule:` line per
    violation — report only: neither the draft nor the exit status depends on it."""
    try:
        import rules
        with layout_text.font_context(spec.font_factor, spec.font_steps):
            return rules.lines(rules.check(spec, geom, data))
    except Exception as e:  # noqa: BLE001 — a checker bug must not cost the draft
        return [f"rule: checker error {e!r}"]


def result_line(n: int, verdict: Sequence[str], document_on_slide: bool = False) -> str:
    """Keep the check's status, but make unresolved report-only rules visible at the end.

    Use the verdict already printed, so the final line describes that same written draft
    and a checker failure cannot silently become an unqualified success.
    """
    status = f"{n} problem{'s' if n != 1 else ''}" if n else "Layout OK"
    counts: Counter = Counter()
    checker_error = False
    for line in verdict:
        match = re.match(r"rule: (R-\S+) ([A-Z][A-Z0-9]*)\b", line)
        if match:
            counts[(match[1], match[2])] += 1
        else:
            checker_error = True
    if counts:
        total = sum(counts.values())
        details = ", ".join(f"{rule} {code} ×{count}" for (rule, code), count in sorted(counts.items()))
        fit_only = all(rule == "R-fit" for rule, _ in counts)
        guidance = ("text-size issue only: adjust text_scale, shorten labels, rearrange tracks, "
                    "or split the diagram before delivering" if fit_only else
                    "fix them with the spec hints before delivering")
        if document_on_slide and any(rule == "R-fit" for rule, _ in counts):
            guidance += "; write a slide spec (see docs/examples/specs/slides/)"
        status += (f" — {total} rule violation{'s' if total != 1 else ''} "
                   f"{'remain' if total != 1 else 'remains'} "
                   f"({details}): {guidance}")
    if checker_error:
        status += " — rule checker error: resolve it before delivering"
    return status


# =======================================================================================
# CLI

def render_checked(spec: Spec, source: str, scratch: Path, no_check: bool = False,
                   max_rounds: int = MAX_ROUNDS):
    """One font size, with the existing routing feedback and fixed-answer repairs."""
    with layout_text.font_context(spec.font_factor, spec.font_steps):
        extra: Dict[Tuple[str, str, str], Requirement] = {}
        skip: Dict[int, int] = {}
        best, place = None, None
        for rnd in range(max_rounds + 1):
            try:
                b = build(spec, list(extra.values()), dict(skip), place, source)
            except M.LayoutError:
                if best is None:
                    raise
                break
            place = b.nb.place if b.nb.place != "none" else None
            if no_check:
                best = ((0, 0, 0), rnd, b, [], {})
                break
            probs = [p for p in problems_of(b.feedback_svg)[0] if p.iss.kind != "LINE IN HEADER"]
            wide = int(spec.mode == "document" and b.geom.canvas_w > K.DOC_WIDE)
            judged = b.feedback_svg
            if spec.mode == "slide" and any(p.iss.kind in TEXT_SIZE_FIXES for p in probs):
                judged = fix_pass(b.feedback_svg, scratch)[0]
            score = (problem_count(probs) + (1 if slide_problem(spec, judged) else 0), wide, shape_misses(b))
            if best is None or score < best[0]:
                best = (score, rnd, b, list(extra.values()), dict(skip))
            if score == (0, 0, 0) or rnd == max_rounds or not feedback(b, probs, extra, skip):
                break
        _, rnd, b, used, skipped = best
        if not no_check:
            rnd, b, used, skipped = repair_headers(b, rnd, used, skipped, source, scratch, max_rounds)
        data, fixed = (b.svg, 0) if no_check else fixed_build(b, scratch)
        probs = [] if no_check else problems_of(data)[0]
        return b, data, fixed, probs, rnd, used, skipped


def other_rule_counts(spec: Spec, b: Build, data: bytes):
    """Scaling may improve fit but must not introduce more violations of other rules."""
    import rules
    with layout_text.font_context(spec.font_factor, spec.font_steps):
        return Counter(v.rule for v in rules.check(spec, b.geom, data) if v.rule != "R-fit")


def trunk_badge_branches(spec: Spec, data: bytes):
    """Keep a step badge on the same side of a trunk's merge/fork junctions.

    A badge moving from one branch onto the shared stem changes which hop it names,
    even when the larger circle and digit still pass the geometric checks.
    """
    if not any(e.trunk and e.step is not None for e in spec.edges):
        return {}
    import rules
    out = {}
    with layout_text.font_context(spec.font_factor, spec.font_steps):
        d = rules.Drawn.parse(data)
        for e in spec.edges:
            if not e.trunk or e.step is None:
                continue
            for box, digit in d.badges.get(e.n, ()):
                center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
                paths = d.edge_paths.get(e.n, ())
                if not paths:
                    continue
                pid = min(paths, key=lambda p: min(rules._pt_seg(center, s["p"], s["q"])[0]
                                                  for s in d.paths[p]))
                points = d.points(pid)

                def along(point):
                    total, candidates = 0.0, []
                    for a, b in zip(points, points[1:]):
                        distance, projection = rules._pt_seg(point, a, b)
                        candidates.append((distance, total + math.dist(a, projection)))
                        total += math.dist(a, b)
                    return min(candidates, key=lambda c: c[0])

                joins = set()
                for other in d.paths:
                    if other == pid or d.net[other] != d.net[pid]:
                        continue
                    for point in (d.points(other)[0], d.points(other)[-1]):
                        distance, position = along(point)
                        if distance <= K.JOIN_REACH:
                            joins.add(round(position, 2))
                position = along(center)[1]
                out[(e.n, digit)] = sum(join < position for join in joins)
    return out


def render_readable(spec: Spec, source: str, scratch: Path, no_check: bool = False):
    """Render, then try at most two uniform font enlargements; keep a safe improvement."""
    result = render_checked(spec, source, scratch, no_check)
    if spec.text_scale != "auto":
        return result
    for _ in range(2):
        b, data, _, probs, *_ = result
        (actual, _, target, _), t, _ = drawn_text(b.spec, data)
        if t is None or actual >= target:
            break
        trial = copy.deepcopy(b.spec)
        step = min(1.8, target / actual)
        trial.font_factor *= step
        trial.font_steps += (step,)
        try:
            # The initial render gets the full feedback budget. Font retries have a
            # smaller budget: unresolved collisions safely keep that initial result.
            candidate = render_checked(trial, source, scratch, no_check, min(2, MAX_ROUNDS))
        except M.LayoutError:
            break
        cb, cd, _, cp, *_ = candidate
        new_actual = drawn_text(trial, cd)[0][0]
        if new_actual < actual or len(cp) > len(probs):
            break
        if trunk_badge_branches(b.spec, data) != trunk_badge_branches(trial, cd):
            break
        if not no_check:
            try:
                before, after = other_rule_counts(b.spec, b, data), other_rule_counts(trial, cb, cd)
            except Exception:  # report-only checker failure must not cost the previous draft
                break
            if any(count > before[rule] for rule, count in after.items()):
                break
        result = candidate
    return result


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
        # The expanded spec retains the override, so read only the original mode to
        # distinguish a document converted with --mode slide from a slide-authored spec.
        document_on_slide = (a.mode == "slide" and
                             layout_spec._read(a.spec)[0].get("mode", "document") == "document")
    except M.LayoutError as e:
        print("\n".join(e.problems))
        print(f"{len(e.problems)} problem{'s' if len(e.problems) != 1 else ''} in the spec")
        return 1
    out = a.out or a.spec.resolve().parent / f"{spec.name}.draft.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    source = str(a.spec)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            b, data, fixed, _, rnd, used, skipped = render_readable(
                spec, source, Path(tmp) / "round.svg", a.no_check)
    except M.LayoutError as e:
        print("\n".join(e.problems))
        print(f"{len(e.problems)} problem{'s' if len(e.problems) != 1 else ''}")
        return 1
    spec = b.spec
    out.write_bytes(data)
    probs, hints = ([], []) if a.no_check else problems_of(data, hints=True)[0::2]
    sp = slide_problem(spec, data)
    n = len(probs) + (1 if sp else 0)
    for line in summary(spec, b, out, data):
        print(line)
    if rnd:
        print(f"check: {rnd} feedback round{'s' if rnd != 1 else ''} ("
              + ", ".join(f"{r.why[len('feedback: '):]}: {r.a} → {r.b} ≥ {M.fmt_num(r.d)}" for r in used)
              + (f"; next routing candidate for {', '.join(f'edges[{k}]×{v}' for k, v in skipped.items())}"
                 if skipped else "")
              + (f"; avoid header bands for {', '.join(f'edges[{k}]' for k in sorted(b.avoid_headers))}"
                 if b.avoid_headers else "") + ")")
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
            pre = ("x col",) if "too wide" in sp else ("y row", "y flow")
            for line in b.geom.explain:
                if line.startswith(pre):
                    print(f"  {line}")
    verdict = rule_lines(spec, b.geom, data)
    for line in verdict:
        print(line)
    print(result_line(n, verdict, document_on_slide))
    if n:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
