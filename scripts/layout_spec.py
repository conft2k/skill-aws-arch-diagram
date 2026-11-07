"""W1 of the layout engine: load a spec (`<name>.layout.yaml` / .json / dict) into a Spec.

    spec = load("arch.layout.yaml", mode=None, title=None)   # → layout_model.Spec
    expr = parse_expr("igw.cx-20")                          # → layout_model.Expr

load() reads the file (PyYAML for .yaml/.yml, json for .json), checks the schema (unknown
keys, types, references, id characters, unique track names), applies defaults, expands
`per` templates (descendant groups and nodes copied as `<id>.<n>`, `{n}` in labels, `{1: …,
2: …}` per-instance values, `only: [n, …]` to keep an item in some instances), parses edge strings (-> <-> -- ..> <..> .., comma targets),
pairs `*` patterns, resolves step / step_each / steps, resolves icons (full `set/name`
refs checked against the bundle; aliases through find_icon.search, a unique best score
≥ 95 only), resolves route-table associations (`for` / `via` → Node.assoc, layout_model
decision t), parses expressions, rejects from_side = to_side lines whose ends share the row / column
their leg would need (layout_route.same_side_problems), and lints (DESIGN 4.1). Every problem found is collected
and raised as one SpecError; non-fatal lint goes to Spec.warnings. The contract is in
layout_model.py's docstring.

Raw fragments: RawSpec.exprs maps each placeholder's inner text ("br.cx+4" for "{br.cx+4}")
to its Expr, so W5 substitutes with re.sub(r"\\{([^{}]+)\\}", …) and looks the text up.
"""
from __future__ import annotations

import copy
import dataclasses
import difflib
import functools
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_layout  # noqa: E402  (services_in_label, OUTSIDE_CLOUD)
import find_icon  # noqa: E402  (search, SETS: the icon bundle assets/icons.json)
import layout_const as K  # noqa: E402
import layout_route  # noqa: E402  (same_side_problems, plan: split_overlays)
import layout_solve  # noqa: E402  (solve: split_overlays)
from layout_model import (Assoc, Edge, Expr, Group, LayoutError, Node, NoteSpec, Place, RawSpec, Spec,  # noqa: E402
                          SpecError, Track, fmt_num)

ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
ATTRS = ("x0", "x1", "cx", "y0", "y1", "cy")
OPS = ("<..>", "<->", "..>", "->", "--", "..")       # longest first
EDGE_RE = re.compile(r"^\s*(\S+)\s+(<\.\.>|<->|\.\.>|->|--|\.\.)\s+(\S.*?)\s*$")
SHAPES = ("H", "V", "HVH", "VHV", "HV", "VH")
SIDES = ("left", "right", "top", "bottom")
HSIDES, VSIDES = ("left", "right"), ("top", "bottom")
SHAPE_SIDES = {"H": (HSIDES, HSIDES), "HVH": (HSIDES, HSIDES), "V": (VSIDES, VSIDES), "VHV": (VSIDES, VSIDES),
               "HV": (HSIDES, VSIDES), "VH": (VSIDES, HSIDES)}   # from_side / to_side each shape takes
STEP_AT = ("mid", "start", "end", "gap", "stem", "branch")
LABEL_AT = ("above", "below", "left", "right")
ANCHORS = ("start", "middle", "end")
NOTE_PLACES = ("auto", "panel", "pane", "lines")
ICON_MIN_SCORE = 95
# Load balancers and the firewall sit in the row between AZs, not inside an AZ template (DESIGN 2.3).
LB_ICONS = ("service/Elastic-Load-Balancing", "service/AWS-Network-Firewall")
LB_PREFIX = "resource/Elastic-Load-Balancing_"
# Route tables (VPC subnet and TGW tables alike): the package's only route table icon. A node
# with one of these icons should say what it is associated with (`for:`, layout_model decision t).
RT_ICONS = ("resource/Amazon-Route-53_Route-Table",)
# `for:` ends that are all subnet boxes make a subnet association (no hub), whatever lines reach them;
# `via: none` forces no hub. A Transit Gateway is the likeliest hub when several nodes reach the ends.
SUBNET_TYPES = ("public", "private")
VIA_NONE = "none"
TGW_ICONS = ("service/AWS-Transit-Gateway",)

TOP_KEYS = ("name", "mode", "title", "S", "font", "cols", "rows", "groups", "nodes", "edges", "note", "raw")
TRACK_KEYS = ("id", "min_gap_before", "min_w", "flow", "align")
FLOW_ALIGN = ("top", "center", "bottom")   # a flow column in its parent's height
GROUP_KEYS = ("id", "type", "label", "cidr", "in", "per", "only", "over", "span", "pad", "pad_top", "pad_left",
              "pad_right", "pad_bottom", "min_w", "min_h",
              "dash", "header")
NODE_KEYS = ("id", "icon", "label", "sub", "in", "only", "at", "col", "row", "on", "dx", "dy", "xy", "for", "via")
EDGE_KEYS = ("e", "label", "verb", "step", "step_at", "steps", "step_each", "label_at", "trunk", "fork", "shape",
             "bend_x", "bend_y", "from_side", "to_side", "from_offset", "to_offset", "points")
NOTE_KEYS = ("place", "width", "steps", "summary", "rows")
RAW_KEYS = ("layer", "svg")
PLACE_KEYS = ("x", "y", "anchor")
SPAN_KEYS = ("cols", "rows")
# Fields a template item may give per instance ({1: …, 2: …}).
NO_PER_INSTANCE = ("id", "type", "in", "per", "only", "over", "span", "header", "on")

_OFFSET = r"\s*(?:(?P<sign>[+-])\s*(?P<num>\d+(?:\.\d+)?))?\s*$"
NUM_RE = re.compile(r"^\s*[+-]?\d+(?:\.\d+)?\s*$")
GAP_RE = re.compile(r"^\s*gap\(\s*(?P<a>[A-Za-z0-9_-]+)\s*,\s*(?P<b>[A-Za-z0-9_-]+)\s*\)" + _OFFSET)
TRACK_RE = re.compile(r"^\s*(?P<axis>col|row)\.(?P<ref>[A-Za-z0-9_-]+?)" + _OFFSET)
TRACK_WHOLE_RE = re.compile(r"^\s*(?:col|row)\.(?P<ref>[A-Za-z0-9_-]+)\s*$")
REF_RE = re.compile(r"^\s*(?P<ref>[A-Za-z0-9_.-]+?)\.(?P<label>label\.)?(?P<attr>x0|x1|cx|y0|y1|cy)" + _OFFSET)
PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


# =======================================================================================
# Expressions

def parse_expr(s: Union[str, int, float], spec: Optional[Spec] = None) -> Expr:
    """Parse one expression (layout_model docstring section 6).

    Without `spec`, `<id>.<attr>` comes back as kind "node" (the grammar alone cannot tell
    a node from a group); with `spec` the id is resolved (node → "node", group → "group")
    and every reference is checked. Raises SpecError(["expression '…': …"]) when invalid."""
    if isinstance(s, bool):
        raise SpecError([f"expression {s!r}: expected a number or an expression string"])
    if isinstance(s, (int, float)):
        if not _finite(s):
            raise SpecError([f"expression {s!r}: expected a finite number"])
        return Expr("num", offset=float(s))
    if not isinstance(s, str):
        raise SpecError([f"expression {s!r}: expected a number or an expression string"])
    if NUM_RE.match(s):
        if not _finite(float(s)):         # a digit string too long for a float reads as inf
            raise SpecError([f"expression {s!r}: the number is too large to be a coordinate"])
        return Expr("num", offset=float(s))

    def off(m) -> float:
        if not m.group("sign"):
            return 0.0
        return float(m.group("num")) * (-1 if m.group("sign") == "-" else 1)

    m = GAP_RE.match(s)
    if m:
        e = Expr("gap", ref=m.group("a"), ref2=m.group("b"), offset=off(m))
    else:
        m = REF_RE.match(s)
        t = TRACK_RE.match(s)
        if t and not m:
            e = Expr(t.group("axis"), ref=t.group("ref"), offset=off(t))
            w = TRACK_WHOLE_RE.match(s)       # "col.a-1": a track named a-1 wins over track a − 1
            if spec is not None and w and w.group("ref") != e.ref and \
                    any(x.id == w.group("ref") for x in spec.cols + spec.rows):
                e = Expr(e.kind, ref=w.group("ref"))
        elif m:
            e = Expr("label" if m.group("label") else "node", ref=m.group("ref"), attr=m.group("attr"),
                     offset=off(m))
        else:
            raise SpecError([f"expression {s!r}: expected <number>, <id>.(x0|x1|cx|y0|y1|cy)[±n], "
                             f"<node>.label.<attr>[±n], col.<track>[±n], row.<track>[±n] or gap(<a>,<b>)[±n]"])
    if not _finite(e.offset):
        raise SpecError([f"expression {s!r}: the offset is too large to be a coordinate"])
    if spec is not None:
        e = _resolve_expr(e, s, spec)
    return e


def _resolve_expr(e: Expr, s: str, spec: Spec) -> Expr:
    tracks = {t.id: t for t in spec.cols + spec.rows}
    if e.kind in ("col", "row"):
        t = tracks.get(e.ref)
        if t is None or t.axis != e.kind:
            raise SpecError([f"expression {s!r}: no {e.kind} track {e.ref!r}"])
        return e
    if e.kind == "gap":
        for r in (e.ref, e.ref2):
            if r not in tracks:
                raise SpecError([f"expression {s!r}: no track {r!r}"])
        if tracks[e.ref].axis != tracks[e.ref2].axis:
            raise SpecError([f"expression {s!r}: gap() needs two tracks of one axis "
                             f"({e.ref} is a {tracks[e.ref].axis}, {e.ref2} a {tracks[e.ref2].axis})"])
        return e
    if e.kind == "label":
        if e.ref not in spec.nodes:
            raise SpecError([f"expression {s!r}: .label needs a node id, {e.ref!r} is not one"])
        return e
    if e.ref in spec.nodes:
        return e
    if e.ref in spec.groups:
        return Expr("group", ref=e.ref, attr=e.attr, offset=e.offset)
    raise SpecError([f"expression {s!r}: no node or group {e.ref!r}"])


# =======================================================================================
# Reading

def _yaml_loader():
    try:
        import yaml
    except ImportError:
        return None

    class Loader(yaml.SafeLoader):
        """SafeLoader with YAML 1.2 booleans: `on:` / `yes` / `off` stay strings."""

    Loader.yaml_implicit_resolvers = {k: [r for r in v if r[0] != "tag:yaml.org,2002:bool"]
                                      for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
    Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
                                 list("tTfF"))
    return yaml, Loader


def _read(path_or_dict) -> Tuple[Any, str, str]:
    """(parsed data, Spec.source, default name)."""
    if isinstance(path_or_dict, dict):
        return path_or_dict, "<dict>", ""
    p = Path(path_or_dict)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise SpecError([f"{p}: cannot read the spec ({e.strerror or e})"])
    stem = p.name
    for suf in (".yaml", ".yml", ".json"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
    if stem.endswith(".layout"):
        stem = stem[: -len(".layout")]
    if p.suffix.lower() == ".json":
        try:
            return json.loads(text), str(p), stem
        except json.JSONDecodeError as e:
            raise SpecError([f"{p}: line {e.lineno}: invalid JSON ({e.msg})"])
    y = _yaml_loader()
    if y is None:
        raise SpecError([f"{p}: PyYAML is not installed; run with "
                         f"`uv run --with pyyaml python3 scripts/layout.py {p}` (or pass a .json spec)"])
    yaml, Loader = y
    try:
        return yaml.load(text, Loader=Loader), str(p), stem
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"line {mark.line + 1}: " if mark is not None else ""
        msg = getattr(e, "problem", None) or str(e).splitlines()[0]
        raise SpecError([f"{p}: {where}invalid YAML ({msg})"])


@functools.lru_cache(maxsize=None)
def default_font() -> str:
    """Decision g: the examples' fixed string unless Noto Sans CJK KR is not installed."""
    try:
        out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return K.FONT_FAMILY_DEFAULT
    fams = {f.strip() for line in out.splitlines() for f in line.split(",")}
    first = next((c for c in K.FONT_CANDIDATES if c in fams), None)
    if first is None or first == K.FONT_CANDIDATES[0]:
        return K.FONT_FAMILY_DEFAULT
    order = [first] + [c for c in K.FONT_CANDIDATES if c != first]
    return ", ".join(f"'{c}'" for c in order) + ", Arial, sans-serif"


# =======================================================================================
# Helpers

class _PerInst(dict):
    """A converted per-instance value: {n: value} for n = 1..k."""


def _is_inst_map(v) -> bool:
    return (isinstance(v, dict) and bool(v)
            and all((isinstance(k, int) and not isinstance(k, bool)) or (isinstance(k, str) and k.isdigit())
                    for k in v))


def _pick(v, n: Optional[int]):
    return v[n] if isinstance(v, _PerInst) else v


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finite(v) -> bool:
    """A number a float can hold: not NaN, not ±inf (YAML .nan / .inf / -.inf), not an int too big."""
    try:
        return math.isfinite(v)
    except OverflowError:
        return False


def _num(v) -> bool:
    """A finite number (int or float, not bool): every size, gap, coordinate, offset and width."""
    return _is_number(v) and _finite(v)


def _nf(v) -> str:
    """The hint added to a rejected number's message when it (or an item of a list) is not finite."""
    items = v if isinstance(v, (list, tuple)) else [v]
    return " (not a finite number)" if any(_is_number(x) and not _finite(x) for x in items) else ""


def _text(v) -> Optional[str]:
    """A text field: str, or a number written bare in YAML (label: 443)."""
    if isinstance(v, str):
        return v
    if _is_number(v):
        return str(v)
    return None


def _close(word: str, options: Sequence[str]) -> str:
    m = difflib.get_close_matches(str(word), list(options), n=1)
    return f" (did you mean {m[0]!r}?)" if m else ""


def _inst_id(base: str, n: Optional[int]) -> str:
    return base if n is None else f"{base}.{n}"


# =======================================================================================
# Overlays over nested containers (_Loader.split_overlays)

def _holds(sp: Spec, p: Optional[str], q: Optional[str]) -> bool:
    """Group p strictly holds group q (None, the top level, holds every group)."""
    return p != q and (p is None or p in sp.ancestors(q))


def _nest_parts(sp: Spec, over: Sequence[str]) -> List[List[str]]:
    """An overlay's members by containment level: those in the innermost containers (none
    holding another member's container), then the next ones out, and so on. One part when
    no member's container holds another's (subnets side by side or stacked, one subnet)."""
    par = {m: sp.nodes[m].parent for m in over}
    left, parts = list(over), []
    while left:
        ps = {par[m] for m in left}
        inner = {p for p in ps if not any(_holds(sp, p, q) for q in ps)}
        parts.append([m for m in left if par[m] in inner])
        left = [m for m in left if par[m] not in inner]
    return parts


def _box_range(sp: Spec, idx: Dict[str, int], over: Sequence[str], span_cols, span_rows):
    """An overlay box's (cols, rows): its members' cells and its span (as _Loader.ranges)."""
    def merge(cur, ids):
        ids = [i for i in ids if i is not None]
        if not ids:
            return cur
        lo, hi = min(ids, key=idx.get), max(ids, key=idx.get)
        return (lo, hi) if cur is None else (min(cur[0], lo, key=idx.get), max(cur[1], hi, key=idx.get))

    cols = rows = None
    for m in over:
        n = sp.nodes[m]
        cols, rows = merge(cols, [n.col, n.col2]), merge(rows, [n.row])
    return merge(cols, list(span_cols or ())), merge(rows, list(span_rows or ()))


def _box_holds(sp: Spec, idx: Dict[str, int], over: Sequence[str], span_cols, span_rows) -> List[str]:
    """The nodes not in `over` on a track cell its box covers (as _Loader.overlay_strays)."""
    cols, rows = _box_range(sp, idx, over, span_cols, span_rows)
    if not cols or not rows:
        return []
    (c0, c1), (r0, r1) = [(idx[a], idx[b]) for a, b in (cols, rows)]
    return [n.id for n in sp.nodes.values()
            if n.id not in over and n.xy is None and n.col is not None and n.row is not None
            and idx[n.col] <= c1 and c0 <= idx[n.col2 or n.col] and r0 <= idx[n.row] <= r1]


def _overlay_parts(sp: Spec, idx: Dict[str, int], g: Group, nest: List[List[str]]) -> List[List[str]]:
    """The boxes of a split overlay: its containment levels (_nest_parts), a level whose box
    would hold a node that is not in it (a member of another level between its members)
    split by container, and a container's members whose box still would, one box each.
    Ordered by the first member listed in `over:`."""
    out: List[List[str]] = []
    for part in nest:
        by_parent: Dict[Optional[str], List[str]] = {}
        for m in part:
            by_parent.setdefault(sp.nodes[m].parent, []).append(m)
        for subs in ([part], list(by_parent.values())):
            if not any(_box_holds(sp, idx, s, g.span_cols, g.span_rows) for s in subs):
                out += subs
                break
        else:
            for s in by_parent.values():
                out += [s] if not _box_holds(sp, idx, s, g.span_cols, g.span_rows) else [[m] for m in s]
    return sorted(out, key=lambda part: g.over.index(part[0]))


def _split_warning(sp: Spec, g: Group, ids: Sequence[str], parts) -> str:
    """Which two members cannot share a box (the border between them), the boxes drawn and
    how to get one box."""
    over = g.over
    par = {m: sp.nodes[m].parent for m in over}
    a, b = next((a, b) for a in over for b in over if _holds(sp, par[b], par[a]) or _holds(sp, par[a], par[b]))
    inner, outer = (a, b) if _holds(sp, par[b], par[a]) else (b, a)
    chain = sp.ancestors(par[inner])
    border = chain[chain.index(par[outer]) - 1] if par[outer] is not None else chain[-1]
    side = {inner: f"in {border}", outer: f"outside {border}"}
    titled = f" titled {g.label!r}" if g.label else ""
    boxes = "; ".join(f"{bid} around {', '.join(part)}" for bid, part in zip(ids, parts))
    return (f"{g.src}: members {a} ({side[a]}) and {b} ({side[b]}) cannot share one box without crossing a group "
            f"border; drew {len(parts)} boxes{titled} ({boxes}); for one box, list in `over:` only members on "
            f"one side of {border}'s border, or move {outer} into {par[inner]}")


def _end_chain(sp: Spec, eid: str) -> List[str]:
    """The groups an edge end sits in, innermost first: a node's containers, a group and its
    ancestors, an overlay (box) its members' common containers."""
    if eid in sp.nodes:
        return sp.node_chain(eid)
    g = sp.groups[eid]
    if not g.overlay:
        return sp.ancestors(eid)
    chains = [sp.node_chain(m) for m in g.over]
    return [c for c in chains[0] if all(c in ch for ch in chains[1:])]


def _end_boxes(sp: Spec, e: Edge, boxes: Dict[str, List[str]], loc: str) -> Optional[str]:
    """Point an edge at a split overlay to one of its boxes (both ends together when both
    are split overlays): the pair of ends sharing the innermost container, then the one
    fewer group borders apart — `acm ..> og` ends on the box around CloudWatch beside ACM,
    `alb -> og` on the one in the VPC. A tie takes the pair whose members sort first (so
    the order of `over:` does not choose) and returns a warning."""
    A, B = boxes.get(e.a, [e.a]), boxes.get(e.b, [e.b])

    def key(pair):
        ca, cb = (_end_chain(sp, x) for x in pair)
        shared = sum(1 for c in ca if c in cb)
        return -shared, len(ca) + len(cb) - 2 * shared

    def members(x):
        return tuple(sorted(sp.groups[x].over)) if x in sp.groups and sp.groups[x].overlay else (x,)

    pairs = [(x, y) for x in A for y in B]
    best = min(pairs, key=lambda p: (key(p), members(p[0]), members(p[1])))
    tied = [p for p in pairs if key(p) == key(best)]
    orig = (e.a, e.b)
    e.a, e.b = best
    if len(tied) == 1:
        return None
    split = "; ".join(f"{x!r} is drawn as {len(boxes[x])} boxes ({', '.join(boxes[x])})" for x in orig if x in boxes)
    return (f"{loc}: {split}, and the ends {' and '.join(f'{x} – {y}' for x, y in tied)} are as near; drew "
            f"{best[0]} – {best[1]} (point the edge at a member node to pick another box)")


def _solves(sp: Spec) -> bool:
    """The build's first solve (the route plan, no note) has no contradiction."""
    s = copy.deepcopy(sp)
    try:
        layout_solve.solve(s, layout_route.plan(s))
    except LayoutError:
        return False
    return True


class _Conv(Exception):
    """A field conversion failed; the message is the problem text after 'key: '."""


# =======================================================================================
# The loader

class _Loader:
    def __init__(self, data, source: str, stem: str, mode: Optional[str], title: Optional[bool]):
        self.data = data
        self.source = source
        self.stem = stem
        self.mode_arg = mode
        self.title_arg = title
        self.problems: List[str] = []
        self.warnings: List[str] = []
        self.spec = Spec(name="", source=source)
        self.pending: List[Tuple[str, str, Any, Expr]] = []   # expressions to resolve once ids exist
        self.edge_lines: List[dict] = []
        self.edge_failed = False         # some edge line was dropped: don't report its step as missing
        self.split_needed: List[str] = []  # overlays whose one box would hold non-members (overlay_strays)

    # ---- problem helpers
    def err(self, loc: str, msg: str) -> None:
        self.problems.append(f"{loc}: {msg}")

    def warn(self, loc: str, msg: str) -> None:
        self.warnings.append(f"{loc}: {msg}")

    def keys(self, loc: str, d: dict, known: Sequence[str]) -> None:
        for k in d:
            if k not in known:
                self.err(loc, f"unknown key {k!r}{_close(k, known)} (known: {', '.join(known)})")

    # ---- entry
    def run(self) -> Spec:
        d = self.data
        if not isinstance(d, dict):
            raise SpecError([f"spec: expected a mapping of top-level keys, got {type(d).__name__}"])
        self.keys("spec", d, TOP_KEYS)
        self.top(d)
        self.tracks(d)
        self.group_structure(d.get("groups"))
        self.node_structure(d.get("nodes"))
        self.check_ids()
        self.templates()
        self.group_fields()
        self.node_fields()
        self.expand_groups()
        self.expand_nodes()
        self.overlays()
        self.ranges()
        self.overlay_strays()
        self.border_sides()
        self.edges(d.get("edges"))
        self.associations()
        self.note(d.get("note"))
        self.raw(d.get("raw"))
        self.exprs()
        self.same_sides()
        self.lint()
        if self.problems:
            raise SpecError(self.problems)
        self.split_overlays()
        self.spec.warnings = self.warnings
        return self.spec

    # ---- top level
    def top(self, d: dict) -> None:
        sp = self.spec
        name = d.get("name", self.stem or None)
        if name is None:
            self.err("spec", "name: required (the output stem, <name>.draft.svg)")
        elif not isinstance(name, str) or not name.strip() or "/" in name:
            self.err("spec", f"name: expected a file stem string, got {name!r}")
        else:
            sp.name = name
        mode = self.mode_arg if self.mode_arg is not None else d.get("mode", "document")
        if mode not in K.MODES:
            self.err("spec", f"mode: expected document or slide, got {mode!r}")
        else:
            sp.mode = mode
        title = self.title_arg if self.title_arg is not None else d.get("title", True)
        if not isinstance(title, bool):
            self.err("spec", f"title: expected true or false, got {title!r}")
        else:
            sp.title = title
        S = d.get("S", K.S_DEFAULT)
        if not _num(S) or S <= 0:
            self.err("spec", f"S: expected a positive number (icon size, default {K.S_DEFAULT}), got {S!r}{_nf(S)}")
        else:
            sp.S = float(S) if not float(S).is_integer() else int(S)
        if "font" in d:
            if not isinstance(d["font"], str) or not d["font"].strip():
                self.err("spec", f"font: expected a font-family string, got {d['font']!r}")
            else:
                sp.font = d["font"]
        else:
            sp.font = default_font()

    # ---- tracks
    def tracks(self, d: dict) -> None:
        self.track_by: Dict[str, Track] = {}
        for axis, key in (("col", "cols"), ("row", "rows")):
            items = d.get(key)
            if items is None:
                self.err("spec", f"{key}: required (a list of track names)")
                continue
            if not isinstance(items, list):
                self.err("spec", f"{key}: expected a list of track names or {{id, …}} items")
                continue
            out = getattr(self.spec, key)
            for i, it in enumerate(items):
                loc = f"{key}[{i}]"
                if isinstance(it, str):
                    it = {"id": it}
                if not isinstance(it, dict):
                    self.err(loc, f"expected a track name or {{id, min_gap_before, min_w, flow, align}}, got {it!r}")
                    continue
                self.keys(loc, it, TRACK_KEYS)
                tid = it.get("id")
                if not isinstance(tid, str) or not ID_RE.match(tid):
                    self.err(loc, f"id: expected a name of [A-Za-z0-9_-], got {tid!r}")
                    continue
                loc = f"{loc} {tid}"
                t = Track(tid, axis, len(out))
                for k in ("min_gap_before", "min_w"):
                    if k in it:
                        if not _num(it[k]) or it[k] < 0:
                            self.err(loc, f"{k}: expected a number ≥ 0 (px), got {it[k]!r}{_nf(it[k])}")
                        else:
                            setattr(t, k, float(it[k]))
                if "flow" in it:
                    fl = it["flow"]
                    if fl is True:
                        t.flow = float(K.mode(self.spec.mode).flow_pitch)
                    elif _num(fl) and fl > 0:
                        t.flow = float(fl)
                    elif fl not in (False, None):
                        self.err(loc, f"flow: expected a pitch in px (e.g. 160) or true, got {fl!r}{_nf(fl)}")
                if "align" in it:
                    al = it["align"]
                    if axis == "row":
                        self.err(loc, "align: only a flow column takes align (top | center | bottom); "
                                      "a flow row is centered in its parent")
                    elif t.flow is None:
                        self.err(loc, f"align: {tid!r} is not a flow column; give `flow: <pitch>` too")
                    elif al not in FLOW_ALIGN:
                        self.err(loc, f"align: expected one of {' | '.join(FLOW_ALIGN)}, got {al!r}")
                    else:
                        t.align = al
                if tid in self.track_by:
                    other = self.track_by[tid]
                    self.err(loc, f"duplicate track {tid!r} (already a {other.axis} track); "
                                  "track names are unique across cols and rows")
                    continue
                self.track_by[tid] = t
                out.append(t)

    def track(self, loc: str, key: str, tid, axis: str) -> Optional[Track]:
        if not isinstance(tid, str):
            self.err(loc, f"{key}: expected a {axis} track name, got {tid!r}")
            return None
        t = self.track_by.get(tid)
        if t is None:
            names = [x.id for x in (self.spec.cols if axis == "col" else self.spec.rows)]
            self.err(loc, f"{key}: unknown {axis} track {tid!r}{_close(tid, names)}")
            return None
        if t.axis != axis:
            self.err(loc, f"{key}: {tid!r} is a {t.axis} track, expected a {axis} track")
            return None
        return t

    # ---- groups / nodes: structure pass
    def group_structure(self, items) -> None:
        self.graw: Dict[str, dict] = {}       # base id → {"i", "loc", "d", ...}
        self.gorder: List[str] = []
        if items is None:
            items = []
        if not isinstance(items, list):
            self.err("spec", "groups: expected a list")
            items = []
        for i, d in enumerate(items):
            loc = f"groups[{i}]"
            if not isinstance(d, dict):
                self.err(loc, f"expected a mapping {{id, type, …}}, got {d!r}")
                continue
            gid = d.get("id")
            if not isinstance(gid, str) or not ID_RE.match(gid):
                self.err(loc, f"id: expected an id of [A-Za-z0-9_-] (\".\" is for template instances), got {gid!r}")
                continue
            loc = f"{loc} {gid}"
            self.keys(loc, d, GROUP_KEYS)
            r = {"i": i, "loc": loc, "d": d, "ok": True}
            t = d.get("type")
            if t not in K.GROUP_STYLES:
                self.err(loc, f"type: expected one of {', '.join(K.GROUP_STYLES)}, got {t!r}{_close(t, K.GROUP_STYLES)}")
                r["ok"] = False
            if gid in self.graw:
                self.err(loc, f"duplicate group id {gid!r} (first at {self.graw[gid]['loc']})")
                continue
            self.graw[gid] = r
            self.gorder.append(gid)

    def node_structure(self, items) -> None:
        self.nraw: Dict[str, dict] = {}
        self.norder: List[str] = []
        if items is None:
            items = []
        if not isinstance(items, list):
            self.err("spec", "nodes: expected a list")
            items = []
        for i, d in enumerate(items):
            loc = f"nodes[{i}]"
            if not isinstance(d, dict):
                self.err(loc, f"expected a mapping {{id, icon, label, …}}, got {d!r}")
                continue
            nid = d.get("id")
            if not isinstance(nid, str) or not ID_RE.match(nid):
                self.err(loc, f"id: expected an id of [A-Za-z0-9_-] (\".\" is for template instances), got {nid!r}")
                continue
            loc = f"{loc} {nid}"
            self.keys(loc, d, NODE_KEYS)
            if nid in self.nraw:
                self.err(loc, f"duplicate node id {nid!r} (first at {self.nraw[nid]['loc']})")
                continue
            self.nraw[nid] = {"i": i, "loc": loc, "d": d, "ok": True}
            self.norder.append(nid)

    def check_ids(self) -> None:
        for nid in list(self.norder):
            if nid in self.graw:
                self.err(self.nraw[nid]["loc"], f"id {nid!r} is also a group ({self.graw[nid]['loc']}); "
                                                "node and group ids share one namespace")

    # ---- containment and templates
    def templates(self) -> None:
        """Parents, overlays, cycles, `per` and each item's template root."""
        for gid in self.gorder:
            r = self.graw[gid]
            d, loc = r["d"], r["loc"]
            r["over"] = "over" in d and d["over"] is not None
            par = d.get("in")
            r["parent"] = None
            if par is not None:
                if r["over"]:
                    self.err(loc, "in: an overlay group (over:) is outside the containment tree; drop `in`")
                elif not isinstance(par, str) or par not in self.graw:
                    self.err(loc, f"in: unknown group {par!r}{_close(par, self.gorder)}")
                elif par == gid:
                    self.err(loc, "in: a group cannot contain itself")
                else:
                    r["parent"] = par
        for gid in self.gorder:          # overlays cannot be parents
            r = self.graw[gid]
            p = r["parent"]
            if p is not None and self.graw[p]["over"]:
                self.err(r["loc"], f"in: {p!r} is an overlay group (over:); it cannot contain groups")
                r["parent"] = None
        reported = set()
        for gid in self.gorder:          # cycles (each reported once, at its first group)
            seen, cur = [], gid
            while cur is not None and cur not in seen:
                seen.append(cur)
                cur = self.graw[cur]["parent"]
            if cur is not None and cur == gid and gid not in reported:
                reported.update(seen)
                self.err(self.graw[gid]["loc"], f"in: containment cycle {' → '.join(seen + [gid])}")
        for gid in self.gorder:          # break cycles so later passes terminate
            seen, cur = set(), gid
            while cur is not None:
                if cur in seen:
                    self.graw[cur]["parent"] = None
                    break
                seen.add(cur)
                cur = self.graw[cur]["parent"]
        # per
        for gid in self.gorder:
            r = self.graw[gid]
            d, loc = r["d"], r["loc"]
            r["per"] = None
            if d.get("per") is None:
                continue
            per = d["per"]
            if r["over"]:
                self.err(loc, "per: an overlay group cannot be a template")
                continue
            if not isinstance(per, list) or not per:
                self.err(loc, f"per: expected a list of row tracks (one instance each), got {per!r}")
                continue
            rows, ok = [], True
            for k, tid in enumerate(per):
                t = self.track(loc, f"per[{k}]", tid, "row")
                if t is None:
                    ok = False
                elif t.flow is not None:
                    self.err(loc, f"per[{k}]: {tid!r} is a flow row; a template instance needs a grid row")
                    ok = False
                elif tid in rows:
                    self.err(loc, f"per[{k}]: row {tid!r} repeated")
                    ok = False
                else:
                    rows.append(tid)
            if ok:
                r["per"] = rows
        # template root of every group: the nearest ancestor-or-self with per
        for gid in self.gorder:
            r, chain, cur = self.graw[gid], [], gid
            while cur is not None:
                chain.append(cur)
                cur = self.graw[cur]["parent"]
            roots = [c for c in chain if self.graw[c]["per"] is not None]
            r["tmpl"] = roots[0] if roots else None
            if len(roots) > 1:
                self.err(r["loc"], f"per: nested templates ({' in '.join(roots)}) are phase 2")
        self.nodes_parents()

    def nodes_parents(self) -> None:
        for nid in self.norder:
            r = self.nraw[nid]
            d, loc = r["d"], r["loc"]
            r["parent"] = r["on"] = None
            par, on = d.get("in"), d.get("on")
            if par is not None and on is not None:
                self.err(loc, "in / on: give one (`on: <vpc>` puts the node on that VPC's border)")
            if par is not None:
                if not isinstance(par, str) or par not in self.graw:
                    self.err(loc, f"in: unknown group {par!r}{_close(par, self.gorder)}")
                elif self.graw[par]["over"]:
                    self.err(loc, f"in: {par!r} is an overlay group; list the node in its `over:` instead")
                else:
                    r["parent"] = par
            if on is not None:
                if not isinstance(on, str) or on not in self.graw:
                    self.err(loc, f"on: unknown group {on!r}{_close(on, self.gorder)}")
                elif self.graw[on]["d"].get("type") != "vpc":
                    self.err(loc, f"on: {on!r} is a {self.graw[on]['d'].get('type')} group; "
                                  "`on` puts a gateway on a VPC border, so it must name a vpc group")
                else:
                    r["on"] = on
                    r["parent"] = self.graw[on]["parent"]
            g = r["on"] or r["parent"]
            r["tmpl"] = self.graw[g]["tmpl"] if g is not None else None
            if r["on"] is not None and r["tmpl"] is not None:
                self.err(loc, f"on: {on!r} is inside the per template {r['tmpl']!r}; border nodes in templates "
                              "are not supported")
                r["tmpl"] = None

    def count(self, tmpl: Optional[str]) -> int:
        return len(self.graw[tmpl]["per"]) if tmpl else 0

    # ---- field conversion (handles per-instance maps)
    def field(self, r: dict, key: str, conv, default=None):
        """Convert d[key] with conv(v) (raises _Conv); per-instance maps → _PerInst."""
        d, loc = r["d"], r["loc"]
        if key not in d:
            return default
        v = d[key]
        if _is_inst_map(v) and key not in NO_PER_INSTANCE:
            k = self.count(r["tmpl"])
            if not k:
                self.err(loc, f"{key}: per-instance values ({{1: …, 2: …}}) are only for items inside a per template")
                return default
            vals = {int(n): x for n, x in v.items()}
            extra = sorted(n for n in vals if not 1 <= n <= k)
            keep = r.get("only")
            missing = [n for n in range(1, k + 1) if n not in vals and (keep is None or n in keep)]
            if extra:
                self.err(loc, f"{key}: instance {extra[0]} does not exist (the template has {k} instances)")
            if missing:
                self.err(loc, f"{key}: no value for instance {missing[0]} (give 1..{k})")
            if extra or missing:
                return default
            out = _PerInst()
            for n in range(1, k + 1):
                if n not in vals:
                    continue
                try:
                    out[n] = conv(vals[n])
                except _Conv as e:
                    self.err(loc, f"{key}[{n}]: {e}")
                    return default
            return out
        try:
            return conv(v)
        except _Conv as e:
            self.err(loc, f"{key}: {e}")
            return default

    @staticmethod
    def c_text(v):
        t = _text(v)
        if t is None:
            raise _Conv(f"expected a string, got {v!r}")
        return t

    @staticmethod
    def c_label(v):
        if v is None or v == "":
            return None
        t = _text(v)
        if t is None:
            raise _Conv(f"expected a string (or null for no title), got {v!r}")
        return t

    @staticmethod
    def c_lines(v):
        if isinstance(v, list):
            out = []
            for x in v:
                t = _text(x)
                if t is None:
                    raise _Conv(f"expected a string or a list of strings, got {v!r}")
                out.append(t)
            return out
        t = _text(v)
        if t is None:
            raise _Conv(f"expected a string or a list of strings, got {v!r}")
        return [t]

    @staticmethod
    def c_num(v):
        if not _num(v):
            raise _Conv(f"expected a number (px), got {v!r}{_nf(v)}")
        return float(v)

    @staticmethod
    def c_pos(v):
        if not _num(v) or v < 0:
            raise _Conv(f"expected a number ≥ 0 (px), got {v!r}{_nf(v)}")
        return float(v)

    @staticmethod
    def c_ids(v):
        vals = [v] if isinstance(v, str) else v
        if not isinstance(vals, list) or not vals or not all(isinstance(x, str) and x for x in vals):
            raise _Conv(f"expected a list of the node / group ids the table is associated with "
                        f"(<id>.* for a template's instances), got {v!r}")
        return list(vals)

    @staticmethod
    def c_id(v):
        if not isinstance(v, str) or not v:
            raise _Conv(f"expected the hub node's id, or {VIA_NONE} for no hub, got {v!r}")
        return v

    @staticmethod
    def c_dash(v):
        t = _text(v)
        if t is None or not re.match(r"^\s*\d+(\.\d+)?([ ,]+\d+(\.\d+)?)*\s*$", t):
            raise _Conv(f"expected a stroke-dasharray such as \"6,4\", got {v!r}")
        return t.strip()

    def subst(self, r: dict, key: str, s: Optional[str], n: Optional[int]) -> Optional[str]:
        if s is None:
            return None
        if n is not None:
            return s.replace("{n}", str(n))
        if "{n}" in s:
            self.err(r["loc"], f"{key}: {{n}} is the instance number; only items inside a per template have one")
        return s

    def only(self, r: dict, root: bool = False) -> None:
        """`only: [n, …]` (or one n): the template instances an item inside a per template is
        drawn in; the others leave it (and, for a group, everything inside it) out."""
        d, loc = r["d"], r["loc"]
        r["only"] = None
        if "only" not in d:
            return
        v = d["only"]
        k = self.count(r["tmpl"])
        if not k:
            self.err(loc, "only: is for items inside a per template (it picks the instances to draw)")
            return
        if root:
            self.err(loc, "only: the template group itself is drawn once per `per` row; shorten `per` instead")
            return
        vals = v if isinstance(v, list) else [v]
        if not vals or not all(isinstance(n, int) and not isinstance(n, bool) for n in vals):
            self.err(loc, f"only: expected instance numbers 1..{k} (e.g. only: [1]), got {v!r}")
            return
        bad = [n for n in vals if not 1 <= n <= k]
        if bad:
            self.err(loc, f"only: instance {bad[0]} does not exist (the template has {k} instances)")
            return
        if len(set(vals)) != len(vals):
            self.err(loc, f"only: instance repeated in {v!r}")
            return
        r["only"] = set(vals)
        if len(vals) == k:
            self.warn(loc, f"only: lists every instance (1..{k}); drop it")

    def group_fields(self) -> None:
        for gid in self.gorder:
            r = self.graw[gid]
            d, loc = r["d"], r["loc"]
            self.only(r, root=r["tmpl"] == gid)
            st = K.GROUP_STYLES.get(d.get("type"))
            r["label"] = self.field(r, "label", self.c_label) if "label" in d else (st.label if st else None)
            r["label_default"] = "label" not in d
            r["cidr"] = self.field(r, "cidr", self.c_label)
            for k in ("pad", "pad_top", "pad_left", "pad_right", "pad_bottom", "min_w", "min_h"):
                r[k] = self.field(r, k, self.c_pos)
            r["dash"] = st.dash if st else None
            if "dash" in d:
                if st is not None and not st.any_dash:
                    self.err(loc, f"dash: only generic (and cloudwan) groups take a dash; {st.type} is always "
                                  f"{st.dash or 'solid'}")
                else:
                    dv = d["dash"]
                    r["dash"] = None if dv in (None, "none", "") else self.field(r, "dash", self.c_dash)
            r["header"] = None
            if "header" in d:
                if not r["over"]:
                    self.err(loc, "header: only overlay groups (over:) have a header placement")
                elif d["header"] not in ("right", "below"):
                    self.err(loc, f"header: expected right or below, got {d['header']!r}")
                else:
                    r["header"] = d["header"]
            r["span_cols"] = r["span_rows"] = None
            if "span" in d:
                sp = d["span"]
                if not isinstance(sp, dict):
                    self.err(loc, f"span: expected {{cols: [a, b], rows: [r1, r2]}}, got {sp!r}")
                else:
                    self.keys(f"{loc} span", sp, SPAN_KEYS)
                    for key, axis in (("cols", "col"), ("rows", "row")):
                        if key not in sp:
                            continue
                        v = sp[key]
                        if not (isinstance(v, list) and len(v) == 2):
                            self.err(loc, f"span.{key}: expected [first, last] {axis} tracks, got {v!r}")
                            continue
                        a = self.track(loc, f"span.{key}[0]", v[0], axis)
                        b = self.track(loc, f"span.{key}[1]", v[1], axis)
                        if a and b:
                            if a.index > b.index:
                                self.err(loc, f"span.{key}: {a.id!r} comes after {b.id!r}")
                            else:
                                r[f"span_{key}"] = (a.id, b.id)

    def node_fields(self) -> None:
        for nid in self.norder:
            r = self.nraw[nid]
            d, loc = r["d"], r["loc"]
            self.only(r)
            if "icon" not in d:
                self.err(loc, "icon: required (a full `set/name` ref, e.g. service/Amazon-EC2)")
            r["icon"] = self.field(r, "icon", self.c_text)
            if "label" not in d:
                self.err(loc, "label: required (the 14px node label)")
            r["label"] = self.field(r, "label", self.c_text, "")
            r["sub"] = self.field(r, "sub", self.c_lines, [])
            r["dx"] = self.field(r, "dx", self.c_num, 0.0)
            r["dy"] = self.field(r, "dy", self.c_num, 0.0)
            r["xy"] = None
            if "xy" in d:
                v = d["xy"]
                if not (isinstance(v, list) and len(v) == 2
                        and all(_num(x) or (isinstance(x, str) and not isinstance(x, bool)) for x in v)):
                    self.err(loc, f"xy: expected [cx, cy], each a number or an expression "
                                  f"(col.<track>, row.<track>, <id>.<attr>, ±n), got {v!r}{_nf(v)}")
                else:
                    # numbers stay absolute; an expression is parsed now and tied to the
                    # solve (layout_solve) once exprs() has checked its reference
                    r["xy"] = tuple(float(x) if _num(x) else self.expr(loc, f"xy[{i}]", x)
                                    for i, x in enumerate(v))
                    r["xy_src"] = tuple(fmt_num(float(x)) if _num(x) else x.strip() for x in v)
            r["for"] = self.field(r, "for", self.c_ids)
            r["via"] = self.field(r, "via", self.c_id)
            if "via" in d and "for" not in d:
                self.err(loc, "via: names the hub whose lines to the `for:` ids are the associated attachments; "
                              "give for: too")
            self.position(r)
            if r["icon"] is not None:
                r["icon_res"] = self.resolve_icon(r)

    def position(self, r: dict) -> None:
        d, loc = r["d"], r["loc"]
        r["col"] = r["col2"] = r["row"] = None
        colspec = rowspec = None
        if "at" in d:
            if "col" in d or "row" in d:
                self.err(loc, "at / col / row: give `at: [col, row]` or `col:` / `row:`, not both")
            at = d["at"]
            if not (isinstance(at, list) and len(at) == 2):
                self.err(loc, f"at: expected [col, row] (col may be a span b1..b2), got {at!r}")
                return
            colspec, rowspec = at
            rowkey = "at[1]"
        else:
            colspec, rowspec, rowkey = d.get("col"), d.get("row"), "row"
        colkey = "at[0]" if "at" in d else "col"
        if colspec is not None:
            if isinstance(colspec, str) and ".." in colspec:
                a, _, b = colspec.partition("..")
                ta = self.track(loc, colkey, a.strip(), "col")
                tb = self.track(loc, colkey, b.strip(), "col")
                if ta and tb:
                    if ta.index >= tb.index:
                        self.err(loc, f"{colkey}: span {colspec!r} must go left to right across two tracks")
                    else:
                        r["col"], r["col2"] = ta.id, tb.id
            else:
                t = self.track(loc, colkey, colspec, "col")
                if t:
                    r["col"] = t.id
        if rowspec is not None:
            t = self.track(loc, rowkey, rowspec, "row")
            if t:
                r["row"] = t.id
        if r["tmpl"] is not None:
            if rowspec is not None:
                self.err(loc, f"{rowkey}: inside the per template {r['tmpl']!r} give `col:` only "
                              "(the row is the instance's)")
                r["row"] = None
            if colspec is None and r["xy"] is None:
                self.err(loc, "col: required (a node in a per template needs its column)")
            return
        if r["xy"] is not None:
            return
        flow = r["row"] is not None and self.track_by[r["row"]].flow is not None
        if flow:        # `row:` only → placed in list order; with a col it keeps that grid column
            return
        fcol = r["col"] is not None and self.track_by[r["col"]].flow is not None
        if rowspec is None and fcol and r["col2"] is None:
            # `col:` only on a flow column → stacked top → bottom in list order
            if r["on"] is not None:
                self.err(loc, f"on: a border node needs a grid row; {r['col']!r} is a flow column "
                              "(give `at: [col, row]`)")
            if "dy" in d:
                self.err(loc, f"dy: a node on the flow column {r['col']!r} takes its y from the stack; "
                              "drop dy (the column's `flow:` pitch spaces the nodes)")
            return
        if rowspec is None and colspec is None:
            self.err(loc, "at: required (`at: [col, row]`, `row:` for a flow row, `col:` for a flow "
                          "column, or `xy:`)")
        elif rowspec is None and r["col2"] is not None:
            self.err(loc, f"{rowkey}: required (a span {colspec!r} needs a row: `at: [{colspec}, <row>]`)")
        elif rowspec is None:
            self.err(loc, f"{rowkey}: required (only nodes in a per template or on a flow column take no row"
                          + (f"; {r['col']!r} is a grid column: give it `flow: <pitch>` to stack its nodes"
                             if r["col"] is not None and not fcol else "") + ")")
        elif colspec is None:
            self.err(loc, "col: required (only flow-row nodes have no column)")

    # ---- icons
    def resolve_icon(self, r: dict):
        icon = r["icon"]
        if isinstance(icon, _PerInst):
            out = _PerInst()
            for n, v in icon.items():
                out[n] = self.one_icon(r["loc"], v)
            return out
        return self.one_icon(r["loc"], icon)

    def one_icon(self, loc: str, q: str) -> Optional[Tuple[str, Optional[str]]]:
        """(ref, alias or None)."""
        if "/" in q:
            setname, _, name = q.partition("/")
            if setname in find_icon.SETS and name in find_icon.SETS[setname]:
                return q, None
            hits = find_icon.search(name.replace("-", " ").replace("_", " ") or q, k=3)
            hint = f"; closest: {', '.join(ref for _, ref in hits)}" if hits else ""
            self.err(loc, f"icon: {q!r} is not in the icon bundle (assets/icons.json){hint}")
            return None
        hits = find_icon.search(q, k=5)
        top = [h for h in hits if h[0] >= ICON_MIN_SCORE]
        if top and (len(top) == 1 or top[0][0] > top[1][0]):
            return top[0][1], q
        cands = ", ".join(f"{ref} ({s})" for s, ref in hits[:3])
        why = "is ambiguous" if top else f"has no match scoring ≥ {ICON_MIN_SCORE}"
        self.err(loc, f"icon: alias {q!r} {why}; write the full ref"
                      + (f" — candidates: {cands}" if cands else " — find_icon.py lists the icons"))
        return None

    # ---- expansion
    def expand_groups(self) -> None:
        sp = self.spec
        self.children: Dict[str, List[str]] = {g: [] for g in self.gorder}
        for gid in self.gorder:
            p = self.graw[gid]["parent"]
            if p is not None:
                self.children[p].append(gid)
        self.inst: Dict[str, List[Tuple[int, str]]] = {}   # templated base id → [(n, id)]
        self.dropped: Dict[str, str] = {}                  # instance id left out by `only` → its src
        self.restricted: set = set()                       # base ids with `only` (directly or by a parent)

        def emit(base: str, n: Optional[int], parent: Optional[str], depth: int) -> None:
            r = self.graw[base]
            if r["per"] is not None and n is None:
                for k in range(1, len(r["per"]) + 1):
                    emit(base, k, parent, depth)
                return
            gid = _inst_id(base, n)
            if n is not None and ((r.get("only") is not None and n not in r["only"])
                                  or (parent is not None and parent in self.dropped)):
                self.dropped[gid] = r["loc"]
                self.restricted.add(base)
                for c in self.children[base]:
                    emit(c, n, gid, depth + 1)
                return
            if parent is not None and parent in self.dropped:
                return
            if n is not None:
                self.inst.setdefault(base, []).append((n, gid))
            label = _pick(r["label"], n)
            if r["label_default"] and label and "{n}" in label and n is None:
                label = label.replace(" {n}", "").replace("{n}", "")
                self.warn(r["loc"], f"an {r['d'].get('type')} outside a per template has no number; "
                                    f"titled {label!r} (give `label:` to name it)")
            else:
                label = self.subst(r, "label", label, n)
            g = Group(id=gid, type=r["d"].get("type") if r["ok"] else "generic", label=label,
                      cidr=self.subst(r, "cidr", _pick(r["cidr"], n), n), parent=parent,
                      header=r["header"], span_cols=r["span_cols"], span_rows=r["span_rows"],
                      pad=_pick(r["pad"], n), pad_top=_pick(r["pad_top"], n), pad_left=_pick(r["pad_left"], n),
                      pad_right=_pick(r["pad_right"], n), pad_bottom=_pick(r["pad_bottom"], n),
                      min_w=_pick(r["min_w"], n), min_h=_pick(r["min_h"], n),
                      dash=_pick(r["dash"], n), template=r["tmpl"], instance=n, depth=depth, src=r["loc"])
            sp.groups[gid] = g
            if r.get("only") is not None:
                self.restricted.add(base)
            if parent is not None:
                sp.groups[parent].children.append(gid)
            for c in self.children[base]:
                emit(c, n, gid, depth + 1)

        for gid in self.gorder:
            if self.graw[gid]["parent"] is None and not self.graw[gid]["over"]:
                emit(gid, None, None, 0)
        for gid in self.gorder:
            if self.graw[gid]["over"]:
                emit(gid, None, None, 0)

    def expand_nodes(self) -> None:
        sp = self.spec
        for nid in self.norder:
            r = self.nraw[nid]
            k = self.count(r["tmpl"])
            for n in (range(1, k + 1) if k else [None]):
                iid = _inst_id(nid, n)
                pid = None
                if r["parent"] is not None:
                    pid = _inst_id(r["parent"], n if self.graw[r["parent"]]["tmpl"] else None)
                if n is not None and ((r.get("only") is not None and n not in r["only"]) or pid in self.dropped):
                    self.dropped[iid] = r["loc"]
                    self.restricted.add(nid)
                    continue
                if r.get("only") is not None:
                    self.restricted.add(nid)
                if n is not None:
                    self.inst.setdefault(nid, []).append((n, iid))
                res = _pick(r.get("icon_res"), n)
                parent = None
                if r["parent"] is not None:
                    pt = self.graw[r["parent"]]["tmpl"]
                    parent = _inst_id(r["parent"], n if pt else None)
                row = r["row"]
                if n is not None:
                    row = self.graw[r["tmpl"]]["per"][n - 1]
                sub = [self.subst(r, "sub", s, n) for s in (_pick(r["sub"], n) or [])]
                node = Node(id=iid, icon=res[0] if res else "", label=self.subst(r, "label", _pick(r["label"], n), n)
                            or "", sub=sub, parent=parent, col=r["col"], col2=r["col2"], row=row, on=r["on"],
                            dx=_pick(r["dx"], n), dy=_pick(r["dy"], n), xy=r["xy"], xy_src=r.get("xy_src"),
                            icon_query=res[1] if res else None, template=r["tmpl"], instance=n, src=r["loc"])
                if r["xy"] is not None:        # the absolute center overrides the grid position
                    node.col = node.col2 = node.row = None
                sp.nodes[iid] = node
                if parent is not None and parent in sp.groups and r["on"] is None:
                    sp.groups[parent].nodes.append(iid)        # `in` nodes only, not border nodes
        # flow-row (flow-column) order among the track's nodes in the same parent
        seen: Dict[Tuple[str, Optional[str]], int] = {}
        for node in sp.nodes.values():
            if node.xy is not None:
                continue
            if node.row is not None and node.col is None and self.track_by[node.row].flow is not None:
                key = (node.row, node.parent)
            elif node.col is not None and node.row is None and node.col2 is None and node.on is None \
                    and self.track_by[node.col].flow is not None:
                key = (node.col, node.parent)
            else:
                continue
            node.flow_index = seen.get(key, 0)
            seen[key] = node.flow_index + 1

    def pattern(self, loc: str, key: str, pat, want=("node", "group")) -> Optional[List[Tuple[Optional[int], str]]]:
        """An endpoint / member pattern → [(instance n or None, expanded id)]."""
        sp = self.spec
        if not isinstance(pat, str) or not pat:
            self.err(loc, f"{key}: expected an id, got {pat!r}")
            return None
        if pat.endswith(".*"):
            base = pat[:-2]
            if base in self.inst:
                out = [(n, i) for n, i in self.inst[base]]
                kinds = {sp.kind(i) for _, i in out}
                if not kinds <= set(want):
                    self.err(loc, f"{key}: {pat!r} names groups; expected {' or '.join(want)} ids")
                    return None
                return out
            if base in self.nraw or base in self.graw:
                self.err(loc, f"{key}: {pat!r}: {base!r} is not inside a per template, so it has no instances; "
                              f"write {base!r}")
            else:
                self.err(loc, f"{key}: unknown id {base!r} in {pat!r}{_close(base, list(sp.nodes) + list(sp.groups))}")
            return None
        if pat in sp.nodes or pat in sp.groups:
            kind = sp.kind(pat)
            if kind not in want:
                self.err(loc, f"{key}: {pat!r} is a {kind}; expected a {' or '.join(want)} id")
                return None
            obj = sp.nodes.get(pat) or sp.groups.get(pat)
            return [(obj.instance, pat)]
        if pat in self.dropped:
            base = pat.rsplit(".", 1)[0]
            have = ", ".join(i for _, i in self.inst.get(base, [])) or "none"
            self.err(loc, f"{key}: {pat!r} is left out by `only:` ({self.dropped[pat]}); drawn instances: {have}")
            return None
        if pat in self.inst:
            ids = [i for _, i in self.inst[pat]]
            self.err(loc, f"{key}: {pat!r} is a per template ({', '.join(ids)}); write {pat}.* or one instance "
                          f"such as {ids[0]}")
            return None
        if pat in self.nraw or pat in self.graw:
            return None          # declared but broken: already reported
        self.err(loc, f"{key}: unknown id {pat!r}{_close(pat, list(sp.nodes) + list(sp.groups))}")
        return None

    def overlays(self) -> None:
        sp = self.spec
        for gid in self.gorder:
            r = self.graw[gid]
            if not r["over"]:
                continue
            g, loc, over = sp.groups[gid], r["loc"], r["d"]["over"]
            if not isinstance(over, list) or not over:
                self.err(loc, f"over: expected a list of member nodes (ec2a.* for every instance), got {over!r}")
                continue
            members: List[str] = []
            for k, pat in enumerate(over):
                res = self.pattern(loc, f"over[{k}]", pat, want=("node",))
                for _, i in res or []:
                    if i not in members:
                        members.append(i)
            g.over = members
            if not members:
                self.err(loc, "over: no member nodes")

    # ---- overlays over nested containers
    def split_overlays(self) -> None:
        """An overlay is one box around its members (an ASG over subnets stacked on rows sits
        inside each, across AZ columns it spans the AZ borders between). When a member's
        container holds another member's (CloudWatch in the Region, an EC2 in a subnet of the
        Region's VPC) and that one box would hold a node that is not a member (overlay_strays:
        split_needed) or cannot be solved (the probe: the first solve the build makes, without
        the note), the overlay is drawn as several boxes with its title and style instead
        (_overlay_parts). Only the overlays the solve needs split are split (added one by one
        in spec order until it solves, then each dropped again that it solves without); when
        splitting does not make it solve, those overlays stay one box and the build reports
        the contradiction as before. A spec that solves as it is, with no overlay holding a
        non-member, keeps every overlay one box."""
        sp = self.spec
        cands = {gid: parts for gid, g in sp.groups.items() if g.overlay
                 for parts in [_nest_parts(sp, g.over)] if len(parts) > 1}
        must = list(self.split_needed)
        if not cands or _solves(self.split_spec(must, cands)[0] if must else sp):
            if must:
                self.spec, warns = self.split_spec(must, cands)
                self.warnings += warns
            return
        chosen: List[str] = list(must)
        for gid in cands:
            if gid in chosen:
                continue
            chosen.append(gid)
            if _solves(self.split_spec(chosen, cands)[0]):
                break
        else:
            chosen = must
        for gid in list(chosen):
            rest = [x for x in chosen if x != gid]
            if gid not in must and _solves(self.split_spec(rest, cands)[0] if rest else sp):
                chosen = rest
        if not chosen:
            return
        self.spec, warns = self.split_spec(chosen, cands)
        self.warnings += warns

    def split_spec(self, gids: Sequence[str], cands: Dict[str, List[List[str]]]) -> Tuple[Spec, List[str]]:
        """A copy of the spec with each overlay of gids drawn as boxes (_overlay_parts): the
        box with the first member listed keeps the id, the others are <id>.2, <id>.3, each
        right after it; edges to the overlay end on one of its boxes (_end_boxes). Returns
        the copy and its warnings."""
        sp, warns = copy.deepcopy(self.spec), []
        idx = {t.id: t.index for t in sp.cols + sp.rows}
        boxes: Dict[str, List[str]] = {}
        new: Dict[str, Group] = {}
        for gid in gids:
            g = sp.groups[gid]
            parts = _overlay_parts(sp, idx, g, cands[gid])
            ids = [gid] + [f"{gid}.{k}" for k in range(2, len(parts) + 1)]
            boxes[gid] = ids
            warns.append(_split_warning(sp, g, ids, parts))
            for bid, part in zip(ids, parts):
                b = g if bid == gid else dataclasses.replace(g, id=bid, children=[], nodes=[])
                b.over = part
                b.cols, b.rows = _box_range(sp, idx, part, g.span_cols, g.span_rows)
                if bid != gid:
                    new[bid] = b
        order = list(sp.groups.items())
        sp.groups.clear()
        for gid, g in order:
            sp.groups[gid] = g
            for bid in boxes.get(gid, [])[1:]:
                sp.groups[bid] = new[bid]
        for e in sp.edges:
            if e.a in boxes or e.b in boxes:
                w = _end_boxes(sp, e, boxes, self.edge_lines[e.line]["loc"])
                if w:
                    warns.append(w)
        return sp, warns

    def ranges(self) -> None:
        """Group.cols / rows: the track range of descendants, over members, span, per row."""
        sp = self.spec
        idx = {t.id: t.index for t in sp.cols + sp.rows}

        def merge(cur, ids):
            ids = [i for i in ids if i is not None]
            if not ids:
                return cur
            lo, hi = min(ids, key=idx.get), max(ids, key=idx.get)
            if cur is None:
                return (lo, hi)
            return (min(cur[0], lo, key=idx.get), max(cur[1], hi, key=idx.get))

        on_by_parent: Dict[Optional[str], List[Node]] = {}
        for node in sp.nodes.values():
            if node.on is not None:
                on_by_parent.setdefault(node.parent, []).append(node)

        def node_cells(node: Node):
            return [node.col, node.col2], [node.row]

        def visit(gid: str):
            g = sp.groups[gid]
            cols, rows = None, None
            for c in g.children:
                cc, rr = visit(c)
                cols, rows = merge(cols, list(cc or ())), merge(rows, list(rr or ()))
            for nid in g.nodes + [n.id for n in on_by_parent.get(gid, [])]:
                cc, rr = node_cells(sp.nodes[nid])
                cols, rows = merge(cols, cc), merge(rows, rr)
            if g.template is not None and g.instance is not None and g.template in self.graw \
                    and self.graw[g.template]["per"]:
                rows = merge(rows, [self.graw[g.template]["per"][g.instance - 1]])
            cols = merge(cols, list(g.span_cols or ()))
            rows = merge(rows, list(g.span_rows or ()))
            g.cols, g.rows = cols, rows
            return cols, rows

        for gid, g in sp.groups.items():
            if g.parent is None and not g.overlay:
                visit(gid)
        for g in sp.groups.values():
            if g.overlay:
                cols, rows = None, None
                for nid in g.over:
                    cc, rr = node_cells(sp.nodes[nid])
                    cols, rows = merge(cols, cc), merge(rows, rr)
                g.cols = merge(cols, list(g.span_cols or ()))
                g.rows = merge(rows, list(g.span_rows or ()))

    def overlay_strays(self) -> None:
        """An overlay is one box around its members: a node on a track cell inside the rows ×
        columns it covers but not in `over:` would be drawn inside it (an ASG over the EC2s
        of two AZ columns on different rows also holds the other two EC2s of that grid). A
        colspan node (`at: [b1..b2, r]`) counts when its span meets those columns."""
        sp = self.spec
        idx = {t.id: t.index for t in sp.cols + sp.rows}

        def meets(lo, hi, rng):
            return lo <= idx[rng[1]] and idx[rng[0]] <= hi

        def tracks(kind, a, b):
            return f"{kind} {a}" if a == b else f"{kind}s {a}–{b}"

        for gid in self.gorder:
            g = sp.groups.get(gid)
            if g is None or not g.overlay or not g.cols or not g.rows:
                continue
            (c0, c1), (r0, r1) = [(idx[a], idx[b]) for a, b in (g.cols, g.rows)]
            stray = [n.id for n in sp.nodes.values()
                     if n.id not in g.over and n.xy is None and n.col is not None and n.row is not None
                     and meets(c0, c1, (n.col, n.col2 or n.col)) and meets(r0, r1, (n.row, n.row))]
            nest = _nest_parts(sp, g.over) if stray else []
            if len(nest) > 1 and not any(i not in g.over for part in _overlay_parts(sp, idx, g, nest)
                                         for i in _box_holds(sp, idx, part, g.span_cols, g.span_rows)):
                self.split_needed.append(gid)      # its boxes hold none: split_overlays draws them
                continue
            if stray:
                self.err(self.graw[gid]["loc"],
                         f"over: its box covers {tracks('column', *g.cols)} and {tracks('row', *g.rows)}, "
                         f"so it would also hold {', '.join(stray)} (not members); list them in `over:`, move them "
                         f"off those tracks, or split the overlay")

    def border_sides(self) -> None:
        sp = self.spec
        for node in sp.nodes.values():
            if node.on is None or node.on not in sp.groups:
                continue
            vpc = sp.groups[node.on]
            if node.col is None or node.xy is not None:
                if node.xy is None:
                    self.err(node.src, "on: a border node needs a column")
                continue
            if vpc.cols is None:
                if self.problems:      # most likely a broken member already reported
                    continue
                self.err(node.src, f"on: {vpc.id!r} has no columns (nothing inside it), so its border is undefined")
                continue
            ni = self.track_by[node.col].index
            lo, hi = self.track_by[vpc.cols[0]].index, self.track_by[vpc.cols[1]].index
            if ni < lo:
                node.side = "left"
            elif ni > hi:
                node.side = "right"
            else:
                self.err(node.src, f"on: column {node.col!r} is inside {vpc.id!r}'s columns "
                                   f"({vpc.cols[0]}..{vpc.cols[1]}); put the node left or right of them "
                                   "(top/bottom borders are phase 2)")

    # ---- edges
    def edges(self, items) -> None:
        if items is None:
            items = []
        if not isinstance(items, list):
            self.err("spec", "edges: expected a list")
            return
        for line, d in enumerate(items):
            if not self.edge_line(line, d):
                self.edge_failed = True

    def edge_line(self, line: int, d) -> bool:
        """One spec edge → its instances in Spec.edges; False when the line was dropped."""
        sp = self.spec
        loc = f"edges[{line}]"
        if isinstance(d, str):
            d = {"e": d}
        if not isinstance(d, dict):
            self.err(loc, f"expected {{e: \"a -> b\", …}}, got {d!r}")
            return False
        self.keys(loc, d, EDGE_KEYS)
        e = d.get("e")
        if not isinstance(e, str):
            self.err(loc, f"e: required, a string \"a OP b\" with OP one of {' '.join(OPS)}")
            return False
        m = EDGE_RE.match(e)
        if not m:
            self.err(loc, f"e: cannot parse {e!r}; write \"a OP b\" with spaces around OP "
                          f"({' '.join(OPS)}), several targets as \"a -> b, c\"")
            return False
        a_pat, op, rhs = m.group(1), m.group(2), m.group(3)
        if "," in a_pat:
            self.err(loc, f"e: several sources {a_pat!r}; only the right side takes a comma list")
            return False
        b_pats = [p.strip() for p in rhs.split(",")]
        if any(not p or " " in p for p in b_pats):
            self.err(loc, f"e: cannot parse the targets {rhs!r} (comma-separated ids)")
            return False
        loc_e = f"{loc} {e.strip()}"
        pairs = self.pair(loc_e, a_pat, b_pats)
        opts = self.edge_opts(loc_e, d)
        if pairs is None or opts is None:
            return False
        n0 = len(self.problems)
        steps = self.steps(loc_e, d, pairs)
        for k, ((a, b), step) in enumerate(zip(pairs, steps)):
            sp.edges.append(Edge(n=len(sp.edges), a=a, b=b, op=op, a_kind=sp.kind(a), b_kind=sp.kind(b),
                                 step=step, line=line, k=k, src=loc, **opts))
        self.edge_lines.append({"loc": loc_e, "d": d})
        return len(self.problems) == n0

    def pair(self, loc: str, a_pat: str, b_pats: List[str]) -> Optional[List[Tuple[str, str]]]:
        A = self.pattern(loc, "e", a_pat)
        Bs = [self.pattern(loc, "e", p) for p in b_pats]
        if A is None or any(B is None for B in Bs):
            return None
        out: List[Tuple[str, str]] = []
        for b_pat, B in zip(b_pats, Bs):
            # pair each target against the whole source list: cutting A to one target's
            # instances would leave the next target only what the previous one shared
            if a_pat.endswith(".*") and b_pat.endswith(".*"):
                na, nb = [n for n, _ in A], [n for n, _ in B]
                As, Bt = A, B
                if na != nb:
                    common = [n for n in na if n in nb]
                    cut = {a_pat[:-2], b_pat[:-2]} & self.restricted
                    if not cut:
                        self.err(loc, f"e: {a_pat} has {len(na)} instances and {b_pat} has {len(nb)}; "
                                      "a.* OP b.* pairs instances with the same number")
                        return None
                    if not common:
                        self.err(loc, f"e: {a_pat} is drawn in instance {', '.join(map(str, na))} and {b_pat} in "
                                      f"{', '.join(map(str, nb))} (`only:`), so no number pairs them; name the "
                                      f"instances, e.g. {A[0][1]} -> {B[0][1]}")
                        return None
                    As = [(n, i) for n, i in A if n in common]
                    Bt = [(n, i) for n, i in B if n in common]
                out += [(a, b) for (_, a), (_, b) in zip(As, Bt)]
            else:
                out += [(a, b) for _, a in A for _, b in B]
        for a, b in out:
            if a == b:
                self.err(loc, f"e: {a!r} connects to itself")
                return None
        return out

    def edge_opts(self, loc: str, d: dict) -> Optional[dict]:
        o: Dict[str, Any] = {}
        n0 = len(self.problems)
        for k in ("label", "verb"):
            if d.get(k) is not None:
                t = _text(d[k])
                if t is None:
                    self.err(loc, f"{k}: expected a string, got {d[k]!r}")
                else:
                    o[k] = t
        if "step_at" in d:
            v = d["step_at"]
            if isinstance(v, list):
                o["step_at"] = self.place(loc, "step_at", {"x": v[0], "y": v[1]} if len(v) == 2 else None, v)
            elif v in STEP_AT:
                o["step_at"] = v
            else:
                self.err(loc, f"step_at: expected {' | '.join(STEP_AT)} or [x, y], got {v!r}")
        if d.get("label_at") is not None:
            v = d["label_at"]
            if isinstance(v, dict):
                o["label_at"] = self.place(loc, "label_at", v, v)
            elif v in LABEL_AT:
                o["label_at"] = v
            elif v != "auto":
                self.err(loc, f"label_at: expected {' | '.join(LABEL_AT)} or {{x, y, anchor}}, got {v!r}")
        if "trunk" in d:
            if not isinstance(d["trunk"], bool):
                self.err(loc, f"trunk: expected true or false, got {d['trunk']!r}")
            else:
                o["trunk"] = d["trunk"]
        if d.get("fork") is not None:
            if d["fork"] != "bus":
                self.err(loc, f"fork: expected bus, got {d['fork']!r}")
            else:
                o["fork"] = "bus"
        if d.get("shape") is not None:
            if d["shape"] not in SHAPES:
                self.err(loc, f"shape: expected one of {' '.join(SHAPES)}, got {d['shape']!r}")
            else:
                o["shape"] = d["shape"]
        for k in ("bend_x", "bend_y"):
            if d.get(k) is not None:
                o[k] = "gap" if d[k] == "gap" else self.expr(loc, k, d[k])
        for k in ("from_side", "to_side"):
            if d.get(k) is not None:
                if d[k] not in SIDES:
                    self.err(loc, f"{k}: expected one of {' | '.join(SIDES)}, got {d[k]!r}")
                else:
                    o[k] = d[k]
        if o.get("shape") in SHAPE_SIDES:
            # a side must leave along the shape's end piece: HVH's first and last pieces
            # are horizontal, so from_side: top would start a horizontal piece off a top port
            for k, want in zip(("from_side", "to_side"), SHAPE_SIDES[o["shape"]]):
                if o.get(k) is not None and o[k] not in want:
                    piece = "first" if k == "from_side" else "last"
                    axis = "horizontal" if want == HSIDES else "vertical"
                    self.err(loc, f"{k}: {o[k]} does not fit shape {o['shape']}, whose {piece} piece is {axis}; "
                                  f"use {' or '.join(want)}, or drop shape and let the sides pick it")
        for k in ("from_offset", "to_offset"):
            if d.get(k) is not None:
                if not _num(d[k]):
                    self.err(loc, f"{k}: expected a number (px along the side), got {d[k]!r}{_nf(d[k])}")
                else:
                    o[k] = float(d[k])
        if d.get("points") is not None:
            v = d["points"]
            if not (isinstance(v, list) and len(v) >= 2 and all(isinstance(p, list) and len(p) == 2 for p in v)):
                self.err(loc, f"points: expected [[x, y], [x, y], …] (two or more, ends included), got {v!r}")
            else:
                o["points"] = [(self.expr(loc, f"points[{i}][0]", p[0]), self.expr(loc, f"points[{i}][1]", p[1]))
                               for i, p in enumerate(v)]
        return o if len(self.problems) == n0 else None

    def place(self, loc: str, key: str, d, orig) -> Optional[Place]:
        if not isinstance(d, dict):
            self.err(loc, f"{key}: expected [x, y] or {{x, y, anchor}}, got {orig!r}")
            return None
        self.keys(f"{loc} {key}", d, PLACE_KEYS)
        if "x" not in d or "y" not in d:
            self.err(loc, f"{key}: needs both x and y")
            return None
        anchor = d.get("anchor", "middle")
        if anchor not in ANCHORS:
            self.err(loc, f"{key}.anchor: expected start | middle | end, got {anchor!r}")
            anchor = "middle"
        return Place(self.expr(loc, f"{key}.x", d["x"]), self.expr(loc, f"{key}.y", d["y"]), anchor)

    def expr(self, loc: str, key: str, v) -> Expr:
        """Parse now (grammar); references are checked in exprs() once every id exists."""
        try:
            e = parse_expr(v)
        except SpecError as ex:
            self.err(loc, f"{key}: {ex.problems[0]}")
            return Expr("num")
        self.pending.append((loc, key, v, e))
        return e

    def steps(self, loc: str, d: dict, pairs: List[Tuple[str, str]]) -> List[Optional[int]]:
        out: List[Optional[int]] = [None] * len(pairs)
        step, steps, each = d.get("step"), d.get("steps"), d.get("step_each")

        def ok_num(v) -> bool:
            return isinstance(v, int) and not isinstance(v, bool) and v >= 1

        if each is not None and not isinstance(each, bool):
            self.err(loc, f"step_each: expected true or false, got {each!r}")
            each = None
        if step is not None and steps is not None:
            self.err(loc, "step / steps: give `step` (first instance, or every one with step_each) or `steps` "
                          "(per instance), not both")
            return out
        if each and step is None:
            self.err(loc, "step_each: needs `step`")
        if step is not None:
            if not ok_num(step):
                self.err(loc, f"step: expected a badge number ≥ 1, got {step!r}")
                return out
            if each:
                return [step] * len(pairs)
            out[0] = step
            return out
        if steps is not None:
            if not isinstance(steps, dict) or not steps:
                self.err(loc, f"steps: expected {{instance id: number, …}}, got {steps!r}")
                return out
            for key, num in steps.items():
                if not ok_num(num):
                    self.err(loc, f"steps.{key}: expected a badge number ≥ 1, got {num!r}")
                    continue
                hit = [i for i, (a, b) in enumerate(pairs) if key in (a, b)]
                if not hit:
                    ends = sorted({x for p in pairs for x in p})
                    self.err(loc, f"steps: {key!r} is not an endpoint of this edge's instances "
                                  f"({', '.join(ends)})")
                    continue
                for i in hit:
                    out[i] = num if out[i] is None else out[i]
        return out

    # ---- note and raw
    # ---- route-table associations (layout_model decision t)
    def associations(self) -> None:
        """`for:` / `via:` → Node.assoc: the ends (`*` expanded) and the hub whose lines to
        them are the associated attachments (None: a subnet association)."""
        sp = self.spec
        nbr: Dict[str, set] = {}             # id → the nodes it has an edge to (either direction)
        for e in sp.edges:
            if e.b_kind == "node":
                nbr.setdefault(e.a, set()).add(e.b)
            if e.a_kind == "node":
                nbr.setdefault(e.b, set()).add(e.a)

        def err(node: Node, key: str, msg: str) -> None:
            self.err(node.src, f"{key}: {msg}")

        for nid in self.norder:
            r = self.nraw[nid]
            if r.get("for") is None:
                continue
            n0 = len(self.problems)
            insts = self.inst.get(nid, []) if self.count(r["tmpl"]) else [(None, nid)]
            for n, iid in insts:
                if iid in sp.nodes:
                    self.assoc(r, sp.nodes[iid], _pick(r["for"], n), _pick(r.get("via"), n), n, nbr, err)
                if len(self.problems) > n0:
                    break                        # one report per spec item: the first failing instance
                                                 # (the others repeat it with their own ids)

    def own_instance(self, r: dict, pat: str, n: Optional[int]) -> str:
        """In a template, a bare id of an item of the same template is the node's own instance."""
        if n is None or pat.endswith(".*"):
            return pat
        raw = self.nraw.get(pat) or self.graw.get(pat)
        if raw is not None and raw.get("tmpl") is not None and raw["tmpl"] == r["tmpl"]:
            return _inst_id(pat, n)
        return pat

    def assoc(self, r: dict, node: Node, pats: List[str], via: Optional[str], n: Optional[int],
              nbr: Dict[str, set], err) -> None:
        sp = self.spec
        key = "for" if n is None else f"for ({node.id})"
        ends: List[str] = []
        for pat in pats:
            got = self.pattern(node.src, "for", self.own_instance(r, pat, n))
            if got is None:
                return
            ends += [i for _, i in got if i not in ends]
        if node.id in ends:
            err(node, key, f"{node.id!r} lists itself; name what the table is associated with")
            return
        quiet = self.edge_failed                 # a dropped edge line: its lines are missing, not wrong
        if via == VIA_NONE:
            hub: Optional[str] = None            # declared: no hub (a subnet or other hubless association)
        elif via is None and all(x in sp.groups and sp.groups[x].type in SUBNET_TYPES for x in ends):
            hub = None                           # a subnet association, even when lines reach the subnets
        elif via is not None:
            vkey = "via" if n is None else f"via ({node.id})"
            via = self.own_instance(r, via, n)
            if via not in sp.nodes:
                if via in sp.groups:
                    err(node, vkey, f"{via!r} is a group; the hub is a node (the TGW the attachment lines meet)")
                elif self.pattern(node.src, "via", via, want=("node",)) is not None:
                    err(node, vkey, f"{via!r} names several nodes; the hub is one node id")
                return
            if via == node.id:
                err(node, vkey, f"{via!r} is the table itself; name the node its attachment lines meet")
                return
            missing = [x for x in ends if via not in nbr.get(x, ())]
            if missing:
                if not quiet:
                    err(node, vkey, f"{via!r} has no line to {', '.join(map(repr, missing))}; an association is "
                                    f"the line between the hub and each `for:` id — draw it, or fix for: / via:")
                return
            hub = via
        else:
            cands = set.intersection(*(nbr.get(x, set()) for x in ends)) - {node.id} if ends else set()
            if len(cands) == 1:
                hub = next(iter(cands))
            elif not cands and all(x in sp.groups for x in ends):
                hub = None                       # boxes no node draws a line to
            elif not cands:
                if quiet:
                    return
                seen = "; ".join(f"{x}: {', '.join(sorted(nbr.get(x, ()))) or 'no line'}" for x in ends)
                err(node, key, f"no node has a line to every listed id ({seen}); list the ends of one hub's "
                               "lines (the attachments associated with the table), or name the hub with `via:`")
                return
            else:
                # Transit Gateways first, then spec order: with one listed id every node with a line
                # to it is a candidate (a VPN's Internet beside its TGW), so no single one is suggested
                order = sorted((i for i in sp.nodes if i in cands),
                               key=lambda i: sp.nodes[i].icon not in TGW_ICONS)
                err(node, key, f"{', '.join(map(repr, order))} each have a line to every listed id (Transit "
                               f"Gateways first); name the hub with `via: <one of them>` — the node whose lines "
                               f"are the associated attachments — or `via: {VIA_NONE}` if the table has none")
                return
        endset = set(ends)
        edges = [e.n for e in sp.edges if hub is not None
                 and ((e.a == hub and e.b in endset) or (e.b == hub and e.a in endset))]
        node.assoc = Assoc(hub=hub, ends=ends, edges=edges)

    def note(self, d) -> None:
        if d is None:
            return
        loc = "note"
        if not isinstance(d, dict):
            self.err(loc, f"expected a mapping {{place, width, steps, summary, rows}}, got {d!r}")
            return
        self.keys(loc, d, NOTE_KEYS)
        ns = NoteSpec()
        pl = d.get("place", "auto")
        if pl not in NOTE_PLACES:
            self.err(loc, f"place: expected {' | '.join(NOTE_PLACES)}, got {pl!r}")
        else:
            ns.place = pl
        w = d.get("width")
        if w not in (None, "auto"):
            if not _num(w) or w <= 0:
                self.err(loc, f"width: expected a pane width in px or auto, got {w!r}{_nf(w)}")
            else:
                ns.width = float(w)
                if ns.place not in ("pane", "auto"):
                    self.warn(loc, f"width: only a pane uses it (place is {ns.place})")
        for key in ("steps", "rows"):
            v = d.get(key)
            if v is None:
                continue
            if not isinstance(v, list):
                self.err(loc, f"{key}: expected a list of [{'hop' if key == 'steps' else 'label'}, text] pairs")
                continue
            out = []
            for i, it in enumerate(v):
                if not (isinstance(it, list) and len(it) == 2 and all(_text(x) is not None for x in it)):
                    self.err(f"note.{key}[{i}]", f"expected [{'hop' if key == 'steps' else 'label'}, text] "
                                                 f"(two strings), got {it!r}")
                    continue
                out.append((_text(it[0]), _text(it[1])))
            setattr(ns, key, out)
        if d.get("summary") is not None:
            t = _text(d["summary"])
            if t is None:
                self.err(loc, f"summary: expected a string, got {d['summary']!r}")
            else:
                ns.summary = t
        if not ns.steps and not ns.rows and ns.summary is None:
            self.err(loc, "give steps, summary or rows (or drop the note)")
        if self.spec.mode == "slide" and ns.place == "panel":
            self.warn(loc, "place: slides use a pane or plain lines, not a panel")
        self.spec.note = ns

    def raw(self, items) -> None:
        if items is None:
            return
        if not isinstance(items, list):
            self.err("spec", "raw: expected a list of {layer, svg}")
            return
        for i, d in enumerate(items):
            loc = f"raw[{i}]"
            if not isinstance(d, dict):
                self.err(loc, f"expected {{layer: below|above, svg: '…'}}, got {d!r}")
                continue
            self.keys(loc, d, RAW_KEYS)
            layer = d.get("layer", "above")
            if layer not in ("below", "above"):
                self.err(loc, f"layer: expected below or above, got {layer!r}")
                layer = "above"
            svg = d.get("svg")
            if not isinstance(svg, str) or not svg.strip():
                self.err(loc, "svg: required, an SVG fragment with {expression} placeholders")
                continue
            rs = RawSpec(layer=layer, svg=svg, src=loc)
            for ph in PLACEHOLDER_RE.findall(svg):
                if ph not in rs.exprs:
                    rs.exprs[ph] = self.expr(loc, f"{{{ph}}}", ph.strip())
            self.spec.raw.append(rs)

    # ---- expression references (every id exists now)
    def exprs(self) -> None:
        sp = self.spec
        # a template node's xy is resolved per instance below (its template's ids and rows
        # name that instance's own), not once for the shared expression
        per_inst = {id(c) for r in self.nraw.values() if r.get("tmpl") and r.get("xy")
                    for c in r["xy"] if isinstance(c, Expr)}
        text: Dict[int, str] = {}
        fixed: Dict[int, Expr] = {}
        for loc, key, v, e in self.pending:
            if not isinstance(v, str):
                continue
            if id(e) in per_inst:
                text[id(e)] = v
                continue
            try:
                fixed[id(e)] = parse_expr(v, sp)
            except SpecError as ex:
                self.err(loc, f"{key}: {ex.problems[0]}")

        def fx(e):
            return fixed.get(id(e), e) if isinstance(e, Expr) else e

        def fplace(p):
            return Place(fx(p.x), fx(p.y), p.anchor) if isinstance(p, Place) else p

        for edge in sp.edges:
            edge.bend_x, edge.bend_y = fx(edge.bend_x), fx(edge.bend_y)
            edge.step_at, edge.label_at = fplace(edge.step_at), fplace(edge.label_at)
            if edge.points:
                edge.points = [(fx(x), fx(y)) for x, y in edge.points]
        for rs in sp.raw:
            rs.exprs = {k: fx(e) for k, e in rs.exprs.items()}
        bad = set()

        def report(node, i, why):
            if why and (node.src, i) not in bad:          # one report per spec item (templates)
                bad.add((node.src, i))
                self.err(node.src, f"xy[{i}]: {why}")

        for node in sp.nodes.values():
            if node.xy is None:
                continue
            xy = []
            for i, c in enumerate(node.xy):
                if isinstance(c, Expr) and id(c) in text:
                    c, why = self.inst_expr(node, c, text[id(c)])
                    report(node, i, why)
                xy.append(fx(c))
            node.xy = tuple(c.offset if isinstance(c, Expr) and c.kind == "num" else c for c in xy)
            for i, c in enumerate(node.xy):
                report(node, i, self.xy_problem(node, i, c))
        for node, i, why in self.xy_cycles():
            report(node, i, why)

    def inst_expr(self, node: Node, e: Expr, v: str) -> Tuple[Expr, Optional[str]]:
        """A template node's xy expression for its own instance n: an item of the same
        template named by its base id is that item's instance n (`e1.cy` → `e1.2.cy`), and
        `row.<a per row>` is the instance's own row; explicit instance ids stay. Returns the
        resolved Expr (Expr("num") on a problem) and the problem, if any."""
        sp, n, tmpl = self.spec, node.instance, node.template
        per = self.graw[tmpl]["per"] or []
        if e.kind == "row" and e.ref in per:
            e = Expr("row", ref=per[n - 1], offset=e.offset)
        elif e.kind in ("node", "label") and e.ref not in sp.nodes and e.ref not in sp.groups:
            raw = self.nraw.get(e.ref) or self.graw.get(e.ref)
            iid = _inst_id(e.ref, n)
            if raw is not None and raw.get("tmpl") == tmpl:
                if iid in self.dropped:
                    return Expr("num"), (f"expression {v!r}: {e.ref} has no instance {n} (left out by `only:`), "
                                         f"so {node.id} has nothing to follow there")
                e = Expr(e.kind, ref=iid, attr=e.attr, offset=e.offset)
        try:
            return _resolve_expr(e, v, sp), None
        except SpecError as ex:
            return Expr("num"), ex.problems[0]

    @staticmethod
    def xy_hint(i: int) -> str:
        axis, attrs = ("col", ("x0", "cx", "x1")) if i == 0 else ("row", ("y0", "cy", "y1"))
        return (f"xy[{i}] takes a number, {axis}.<track>, <node>.({'|'.join(attrs)}) or "
                f"<group>.({attrs[0]}|{attrs[2]}), each with an optional ±n")

    def xy_cycles(self):
        """xy references that come back to their node on one axis (q.cx → s.cx → t.cx →
        q.cx; or q itself): no solve can hold them. One axis at a time — q's y on s and s's
        x on q is fine. Yields (node, axis index, problem)."""
        sp = self.spec
        for i in (0, 1):
            refs: Dict[str, Tuple[str, Expr]] = {}
            for node in sp.nodes.values():
                c = node.xy[i] if node.xy is not None else None
                if isinstance(c, Expr) and c.kind == "node" and c.ref in sp.nodes:
                    refs[node.id] = (c.ref, c)
            for nid, (to, c) in refs.items():
                path, cur = [nid], to
                while cur in refs and cur not in path:
                    path.append(cur)
                    cur = refs[cur][0]
                if cur == nid:
                    loop = " → ".join(path + [nid])
                    yield sp.nodes[nid], i, f"{c.ref}.{c.attr} refers back to {nid} ({loop}); {self.xy_hint(i)}"

    def xy_one_y(self, node: Node, e) -> Optional[str]:
        """A template node's xy[1] that is the same y for every instance (a number, a node or
        group outside its template, a row not in the template's `per`), while the template
        draws it in two or more instances, each on its own row: no solve can hold them all."""
        sp, tmpl = self.spec, node.template
        k = sum(1 for n in sp.nodes.values() if n.src == node.src)
        if k < 2:
            return None
        per = self.graw[tmpl]["per"] or []
        if isinstance(e, Expr):
            if e.kind == "row" and e.ref not in per:
                what = f"row.{e.ref} is not a row of the per template {tmpl!r} ({', '.join(per)})"
            elif e.kind in ("node", "group"):
                t = sp.nodes.get(e.ref) if e.kind == "node" else sp.groups.get(e.ref)
                if t is None or t.template == tmpl:
                    return None
                what = f"{e.ref}.{e.attr} is outside the per template {tmpl!r}"
            else:
                return None
        elif isinstance(e, (int, float)):
            what = f"{fmt_num(e)} is a fixed y"
        else:
            return None
        base = node.id.rsplit(".", 1)[0]
        return (f"{what}, so it puts all {k} instances of {base} on one y, a row away from every instance "
                f"but one; follow each instance's own (another item of the template by its id, <item>.cy, "
                f"or row.<{'|'.join(per)}>), or keep {base} in one instance (only: [n])")

    def xy_problem(self, node: Node, i: int, e) -> Optional[str]:
        """Why an `xy` expression cannot be tied to the solve, or None. A difference
        constraint can hold a node to a track, another node's icon edge / center, or a
        group's edge — not a group's center, a label stack or a gap() corridor. (A loop of
        references is xy_cycles'.)"""
        sp = self.spec
        if i == 1 and node.template is not None:
            why = self.xy_one_y(node, e)
            if why:
                return why
        if not isinstance(e, Expr):
            return None
        axis, attrs = ("col", ("x0", "cx", "x1")) if i == 0 else ("row", ("y0", "cy", "y1"))
        hint = self.xy_hint(i)
        if e.kind in ("col", "row"):
            return None if e.kind == axis else f"{e.kind}.{e.ref} is on the other axis; {hint}"
        if e.kind in ("node", "group"):
            t = sp.nodes.get(e.ref) if e.kind == "node" else sp.groups.get(e.ref)
            if i == 1 and t is not None and node.template is not None and t.template == node.template \
                    and t.instance != node.instance:
                base = e.ref.rsplit(".", 1)[0]
                return (f"{e.ref}.{e.attr} is in instance {t.instance} of the per template {node.template!r}, a row "
                        f"away from {node.id} (instance {node.instance}); write {base}.{e.attr} to follow each "
                        f"instance's own")
        if e.kind == "node":
            t = sp.nodes.get(e.ref)
            if e.attr not in attrs:
                return f"{e.ref}.{e.attr} is on the other axis; {hint}"
            if t is not None and i == 0 and t.col2 is not None:
                return f"{e.ref} spans two columns (its center is no single variable); use col.<track>; {hint}"
            return None
        if e.kind == "group":
            if e.attr in ("cx", "cy"):
                return f"{e.ref}.{e.attr}: a group's center is no single variable; {hint}"
            return None if e.attr in attrs else f"{e.ref}.{e.attr} is on the other axis; {hint}"
        return f"{e.kind} expressions depend on the drawn result; {hint}"

    def same_sides(self) -> None:
        """from_side = to_side while the ends share a row (left / right) or a column (top /
        bottom): nothing can draw it (layout_route.same_side_problems)."""
        if self.problems:
            return
        for loc, msg in layout_route.same_side_problems(self.spec):
            self.err(loc, msg)

    # ---- lint (DESIGN 4.1)
    def lint(self) -> None:
        sp = self.spec
        cloud_types = {"cloud"}
        warned = set()
        has_for = {self.nraw[i]["loc"] for i in self.norder if "for" in self.nraw[i]["d"]}
        for node in sp.nodes.values():
            if node.icon in RT_ICONS and node.src not in has_for and ("rt", node.src) not in warned:
                warned.add(("rt", node.src))
                self.warn(node.src, "a route table without `for:`; add `for: [<ids>]` — the attachments (the hub's "
                                    "lines to them) or subnets it is associated with — so the rule checker can "
                                    "verify it sits beside them")
            chain = sp.node_chain(node.id) if node.parent in sp.groups or node.parent is None else []
            if node.icon in check_layout.OUTSIDE_CLOUD and node.src not in warned:
                inside = [g for g in chain if sp.groups[g].type in cloud_types]
                if inside:
                    warned.add(node.src)
                    self.err(node.src, f"{node.icon} is not in AWS; put it outside the AWS Cloud group "
                                       f"({inside[0]!r}), between on-premises and the Cloud")
            if node.template is not None and (node.icon in LB_ICONS or node.icon.startswith(LB_PREFIX)) \
                    and ("lb", node.src) not in warned:
                warned.add(("lb", node.src))
                ttype = self.graw[node.template]["d"].get("type")
                if ttype == "az":
                    base = node.id.rsplit(".", 1)[0]
                    self.warn(node.src, f"{base} ({node.icon}) is inside the AZ template {node.template!r}, so it is "
                                        f"drawn once per AZ; a load balancer or firewall spans the AZs — put it "
                                        f"in the VPC on the row between them (in: <vpc>, at: [<col>, <row>])")
        # a hop folded into another node's sub-caption (DynamoDB "Streams 켬", EventBridge "규칙")
        for node in sp.nodes.values():
            if node.template is not None and node.instance not in (None, 1):
                continue
            for ref, word in _folded_hops(node.icon, node.sub):
                key = ("fold", node.src, ref)
                if key in warned:
                    continue
                warned.add(key)
                self.warn(node.src, f"sub-caption names {word!r}, which has its own icon ({ref}); if it is "
                                    "a step of the flow, draw it as a node on the line instead of a caption")
        # service names in connector labels
        for ln in getattr(self, "edge_lines", []):
            for k in ("label", "verb"):
                t = _text(ln["d"].get(k))
                if not t:
                    continue
                for phrase, ref in check_layout.services_in_label(t):
                    self.err(ln["loc"], f"{k} {t!r} names {phrase!r}, which has an official icon ({ref}); draw it "
                                        "as a node (SERVICE AS TEXT)")
        # step badges ↔ note.steps, 1:1
        nums = sorted({e.step for e in sp.edges if e.step is not None})
        rows = len(sp.note.steps) if sp.note else 0
        if nums and not rows:
            self.err("note", f"steps: edges have step badges {', '.join(map(str, nums))} but the note has no steps "
                             "rows (one [hop, description] per number)")
        elif rows:
            for k in range(1, rows + 1):
                if k not in nums and not self.edge_failed:
                    self.err(f"note.steps[{k - 1}]", f"no edge has step {k} (each note.steps row needs one edge "
                                                     "with that badge number)")
            for k in nums:
                if k > rows:
                    first = next(e for e in sp.edges if e.step == k)
                    self.err(first.src, f"step {k}: note.steps has only {rows} row{'s' if rows > 1 else ''}")


# Sub-resources that are steps of a flow (a line runs through them), with the words a caption
# uses for them; other sub-resource icons (Bucket, Table, Item …) are just the service again.
FLOW_PARTS = {"Stream": ("stream", "streams", "스트림"), "Rule": ("rule", "rules", "규칙"),
              "Pipes": ("pipe", "pipes", "파이프"), "Scheduler": ("scheduler", "스케줄러")}


def _folded_hops(icon: str, sub: Sequence[str]):
    """(ref, word) for each flow sub-resource of the node's own service its sub-caption names."""
    if not icon or not sub or "/" not in icon:
        return []
    name = icon.split("/", 1)[1]
    service, _, own = name.partition("_")          # a resource icon: its service and its own part
    text = " ".join(sub).lower()
    out = []
    for part, words in FLOW_PARTS.items():
        ref = f"resource/{service}_{part}"
        if part == own or ref.split("/", 1)[1] not in find_icon.SETS.get("resource", {}):
            continue
        for w in words:
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", text):
                out.append((ref, w))
                break
    return out


def load(path_or_dict, mode: Optional[str] = None, title: Optional[bool] = None) -> Spec:
    """Read, validate and expand a spec (see the module docstring). Raises SpecError."""
    data, source, stem = _read(path_or_dict)
    return _Loader(data, source, stem, mode, title).run()


def main(argv: Sequence[str]) -> int:
    """`python3 scripts/layout_spec.py spec.layout.yaml`: print the expanded spec summary."""
    if not argv:
        print(__doc__)
        return 1
    try:
        sp = load(argv[0])
    except SpecError as e:
        for p in e.problems:
            print(p)
        print(f"{len(e.problems)} problems")
        return 1
    print(f"{sp.name}: {sp.mode}, {len(sp.groups)} groups, {len(sp.nodes)} nodes, {len(sp.edges)} edges")
    for n in sp.nodes.values():
        if n.icon_query:
            print(f"  icon {n.id}: {n.icon_query!r} → {n.icon}")
    for w in sp.warnings:
        print(f"warning: {w}")
    print("Spec OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
