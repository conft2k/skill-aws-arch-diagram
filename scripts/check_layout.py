#!/usr/bin/env python3
"""Check an SVG diagram for layout defects that only show up in a render.

    python scripts/check_layout.py draft.svg [more.svg ...]
    python scripts/check_layout.py --fix draft.svg      # also repair the fixed-answer ones in place

Reports, and exits with status 1 on any of them:
  LINE OVER TEXT   a connector or container border crosses a label
  LINE OVER ICON   a connector or container border crosses an icon or badge
  TEXT OVERLAP     two labels overlap, or a label overlaps an icon
  TEXT TOO CLOSE   two labels side by side are less than 4px apart (a label and its
                   sub-caption stack 16px apart and are not checked)
  TEXT AT BORDER   a label is closer than 8px to a container border (a bold header
                   label: 4px)
  OFF CANVAS       a label runs past the edge of the viewBox
  LINE NEAR TEXT   a connector skims a node or header label (< 4px) without crossing it
  BADGE NEAR ICON  a group badge (e.g. an ASG's) is within 8px of a node icon
  TEXT NEAR ICON   a label is within 8px of a node icon it doesn't label (a header
                   label: 6px, so nodes start at subnet.y + 28 or lower)
  HEADER CLEARANCE a container title (or its CIDR line) has a nested box's top border
                   < 8px below it (nested boxes start at container.y + 30, + 46 with a CIDR)
  SMALL TEXT       a label is smaller than 12px
  SERVICE AS TEXT  a connector label names an AWS service or resource that has an
                   official icon in the bundle — draw it as an icon node instead
                   (labels centered under an icon are node labels and are skipped)
  SHORT ARROW      the segment carrying an arrowhead is shorter than 20px (a head
                   stuck on a bend or trunk junction)
  LINE HUGS BORDER a connector runs alongside (or on top of) a container border less
                   than 12px from it for more than 20px
  TITLE OFFSET     a container title not on its box's header row (baseline box.y + 18;
                   the 15px AWS Cloud title + 22)
  OUTSIDE CLOUD    a Direct Connect location, Internet or Site-to-Site VPN icon inside the
                   AWS Cloud box (drafts only: needs bundle: refs)
  CIDR IN TITLE    a container title that carries its CIDR (the CIDR is its own line)
  CIDR OFF HEADER  a bare CIDR label neither right under a container title nor a
                   node's sub-caption
  CIDR COLOR       a CIDR line under a title that isn't squid ink #232F3E
  GLYPH STEP       a label numbers steps with circled digits (①) — draw the legend's
                   numbers as the diagram's step badges instead

Fix hints. Under every problem a `  fix: ...` line gives the change to make, with the
values already computed: which element (its text, id, bundle ref or coordinates as
written in the draft — inside a <g transform="translate(...)"> they are the local values
and the line says so) and the attribute values to set. A move ("move text 'NAT gateway'
down 6px: y=406→412") is the smallest one the checker found that clears the problem
without raising a new one — it re-runs the check with the move applied, and prefers a
move that also clears the element's other problems (several problems of one element get
the same move); "(still leaves its ...)", "but then: ..." or "(unverified)" says when it
found no such move. A line ending in "[--fix]" is one --fix applies by itself.

--fix repairs, in place, only the problems whose answer is fixed, and only when the
re-check shows the change clears the problem and raises no new one:
  SMALL TEXT       font-size="12"
  TITLE OFFSET     the title's y (and its CIDR line's) back to box.y + 18 / + 22
  CIDR IN TITLE    the CIDR moved out of the title onto its own 12px #232F3E line
  CIDR OFF HEADER  the CIDR line set to the title's x, baseline 16px lower — or, when the
                   title itself drifted (≤ 12px) from its header slot, both put back there
  CIDR COLOR       fill="#232F3E"
  label centering  a node label a few px off its icon's center (seen as TEXT NEAR ICON
                   or SERVICE AS TEXT) gets text-anchor="middle" and x = icon center; a
                   node label overlapping its own icon gets baseline icon bottom + 18
  masks            a white mask rect that covers only part of the icon or label it hides
                   the border behind is grown to cover all of it (when nothing else
                   would disappear under it)
  arrow ends       a connector end inside an icon is pulled back to 4px short of its edge
Every other move (labels, lines, icons, boxes) can collide with something the checker
can't judge, so it stays a hint — apply those, then re-run. Only the changed attribute values are rewritten; the
rest of the file (indentation, attribute order, comments) is left as it was. After the
fix the file is checked again and the fixed items and what remains are printed.

The last line is "Layout OK", or "N problems (M auto-fixable with --fix)".

Anything covered by a white mask rect drawn later (the IGW/VGW on the VPC border)
is not reported, nor is a small junction dot (circle, r ≤ 6) sitting on its own line. Text widths are estimated (0.55 × font-size per Latin character,
1.0 × per Hangul/CJK character, arrow or circled digit), so a hit within a pixel or two is worth a look in
the render rather than a blind fix. Only translate() transforms are understood,
which is all the skill's diagrams use.
"""
import functools
import math
import re
import sys
import xml.etree.ElementTree as ET
import xml.parsers.expat
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import find_icon  # noqa: E402  (same directory; reuses the icon search and aliases)

NS = "{http://www.w3.org/2000/svg}"
MIN_FONT = 12
WHITE = {"#fff", "#ffffff", "white"}


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def translate(el):
    m = re.search(r"translate\(\s*([-\d.]+)[ ,]*([-\d.]*)\s*\)", el.get("transform", ""))
    return (num(m.group(1)), num(m.group(2))) if m else (0.0, 0.0)


def text_width(s, fs):
    w = 0.0
    for c in s:
        # Hangul, CJK, and the arrows / circled digits / symbols (U+2190–U+2BFF) that CJK
        # fonts draw full-width ("→", "①").
        wide = ("ᄀ" <= c <= "ᇿ" or "\u2190" <= c <= "\u2bff" or "　" <= c <= "鿿"
                or "가" <= c <= "힣")
        w += fs * (1.0 if wide else 0.55)
    return w


def shrink(b, d=1.0):
    x0, y0, x1, y1 = b
    return (x0 + d, y0 + d, x1 - d, y1 - d)


def boxes_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def contains(outer, inner, tol=1.0):
    return (outer[0] - tol <= inner[0] and outer[1] - tol <= inner[1]
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def seg_hits_box(p, q, b):
    """Liang–Barsky: does segment p→q pass through the interior of box b?"""
    x0, y0, x1, y1 = b
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pk == 0:
            if qk <= 0:
                return False
        else:
            t = qk / pk
            if pk < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 >= t1:
                return False
    return True


def collect(svg_root):
    texts, segs, masks, icons = [], [], [], []
    canvas = svg_root.get("viewBox", "0 0 0 0").split()
    cw, ch = num(canvas[2]), num(canvas[3])
    order = 0

    def walk(el, ox, oy):
        nonlocal order
        dx, dy = translate(el)
        ox, oy = ox + dx, oy + dy
        tag = el.tag.replace(NS, "")
        order += 1
        if tag == "defs" or tag == "marker":
            return
        if tag == "text":
            s = "".join(el.itertext()).strip()
            if s:
                fs = num(el.get("font-size"), 16)
                x, y = num(el.get("x")) + ox, num(el.get("y")) + oy
                w = text_width(s, fs)
                anchor = el.get("text-anchor", "start")
                x0 = x - w / 2 if anchor == "middle" else x - w if anchor == "end" else x
                texts.append({"s": s, "fs": fs, "box": (x0, y - 0.75 * fs, x0 + w, y + 0.25 * fs), "o": order,
                              "fill": el.get("fill", "").lower(),
                              "cx": x0 + w / 2, "y": y,
                              "header": el.get("font-weight", "") in ("600", "700", "bold"),
                              "el": el, "off": (ox, oy)})
                texts[-1]["title"] = texts[-1]["header"] and fs >= 14
        elif tag in ("line", "polyline"):
            if tag == "line":
                pts = [(num(el.get("x1")) + ox, num(el.get("y1")) + oy),
                       (num(el.get("x2")) + ox, num(el.get("y2")) + oy)]
            else:
                pts = [num(v) for v in re.split(r"[ ,]+", el.get("points", "").strip()) if v]
                pts = [(pts[i] + ox, pts[i + 1] + oy) for i in range(0, len(pts) - 1, 2)]
            new = [{"p": p, "q": q, "kind": "connector", "o": order, "el": el, "i": k, "off": (ox, oy),
                    "n": len(pts) - 1}
                   for k, (p, q) in enumerate(zip(pts, pts[1:]))]
            # The segment an arrowhead sits on (last for marker-end, first for marker-start).
            if new and el.get("marker-end"):
                new[-1]["head"] = True
                new[-1].setdefault("heads", set()).add("end")
            if new and el.get("marker-start"):
                new[0]["head"] = True
                new[0].setdefault("heads", set()).add("start")
            segs.extend(new)
        elif tag == "rect":
            x, y = num(el.get("x")) + ox, num(el.get("y")) + oy
            w, h = num(el.get("width")), num(el.get("height"))
            stroke = el.get("stroke", "none").lower()
            fill = el.get("fill", "#000").lower()
            if stroke != "none":
                c = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
                for k, (p, q) in enumerate(zip(c, c[1:] + c[:1])):
                    segs.append({"p": p, "q": q, "kind": "border", "o": order, "el": el, "i": k, "off": (ox, oy)})
            elif fill in WHITE and not (w >= cw and h >= ch):
                masks.append({"box": (x, y, x + w, y + h), "o": order, "el": el, "off": (ox, oy)})
        elif tag == "image":
            x, y = num(el.get("x")) + ox, num(el.get("y")) + oy
            href = el.get("href") or el.get("{http://www.w3.org/1999/xlink}href") or ""
            icons.append({"box": (x, y, x + num(el.get("width")), y + num(el.get("height"))),
                          "o": order, "badge": "group/" in href[:40],
                          "ref": href[len("bundle:"):] if href.startswith("bundle:") else "",
                          "el": el, "off": (ox, oy)})
        elif tag == "circle":
            cx, cy, r = num(el.get("cx")) + ox, num(el.get("cy")) + oy, num(el.get("r"))
            # r <= 6: a junction dot drawn on a connector on purpose (e.g. segment membership)
            icons.append({"box": (cx - r, cy - r, cx + r, cy + r), "o": order, "badge": True,
                          "dot": (cx, cy) if r <= 6 else None, "el": el, "off": (ox, oy)})
        for child in el:
            walk(child, ox, oy)

    walk(svg_root, 0.0, 0.0)
    return texts, segs, masks, icons, (cw, ch)


# A connector label is any text whose box comes within this distance of a connector.
LABEL_REACH = 14
# A label closer than this to a container border reads as touching it.
BORDER_CLEAR = 4
# Node labels, captions and connector labels keep this much room from any border.
LABEL_CLEAR = 8
# A connector passing a node or header label keeps at least this much room.
LINE_CLEAR = 4
# Group badges and labels keep this much room from node icons that aren't theirs.
ICON_CLEAR = 8
HEADER_ICON_CLEAR = 6
# Two labels keep at least this much room between them.
TEXT_GAP = 4
# A header label (bold) needs this much room above the next box below it.
HEADER_CLEAR = 8
# The segment carrying an arrowhead is at least this long (an 8px head plus a 12px shaft), so the arrow reads as a line
# into the node, not a head stuck on a bend or junction.
MIN_ARROW = 20
# A connector running alongside a container border keeps at least this much room from it
# (a trunk squeezed into a corridor reads as part of the border).
HUG_CLEAR = 12
# Circled digits (①–⑳, ❶–➓): a step legend repeats the diagram's badges instead.
CIRCLED = re.compile("[\u2460-\u2473\u2776-\u2793]")
# A label that is nothing but a CIDR. A container's CIDR is its own line right under the
# container's title (same x, 16px lower); a bare one elsewhere is allowed only as the
# sub-caption of a node (single-icon VPC, customer gateway).
BARE_CIDR = re.compile(r"^\d{1,3}(\.\d{1,3}){3}/\d{1,2}$")
CIDR_IN = re.compile(r"\d{1,3}(\.\d{1,3}){3}/\d{1,2}")
CIDR_COLOR = "#232f3e"
# Things that are not in AWS: they sit between the on-premises group and the AWS Cloud box,
# never inside it (a Direct Connect location is a colocation facility, the Internet is the
# Internet, and a Site-to-Site VPN's IPsec runs over it). Checked on drafts (bundle: refs).
OUTSIDE_CLOUD = ("service/AWS-Direct-Connect", "resource/Internet", "service/AWS-Site-to-Site-VPN")
ICON_SETS = ("service", "resource")
# A node label's baseline sits this far below its icon's bottom (the guide's skeleton).
NODE_LABEL_DY = 18
# A label this close to an icon's center line (but not within 3px) is that icon's label, off-center.
OFF_CENTER = 24


@functools.lru_cache(maxsize=None)
def official_icon(phrase):
    """The bundle icon a phrase names exactly (score ≥ 95), or None."""
    if len(find_icon.norm(phrase)) < 3:
        return None
    for score, ref in find_icon.search(phrase, k=3):
        if score >= 95 and ref.split("/", 1)[0] in ICON_SETS:
            return ref
    return None


def services_in_label(s):
    parts = re.split(r"\s+·\s+|[(),→⇄↔]|\s+-\s+", s)
    return [(p.strip(), ref) for p in parts if p.strip() for ref in [official_icon(p.strip())] if ref]


def is_node_label(t, icons):
    """A label (or its sub-caption) centered under an icon names that node, not a connector."""
    for i in icons:
        x0, y0, x1, y1 = i["box"]
        if not i["badge"] and abs(t["cx"] - (x0 + x1) / 2) <= 3 and y1 < t["y"] <= y1 + 44:
            return True
    return False


def expand(b, d):
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


def through(dot, s):
    """Does segment s pass through point dot (a junction dot sits on its line)?"""
    (x1, y1), (x2, y2) = s["p"], s["q"]
    cx, cy = dot
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 or 1.0
    dist = abs((x2 - x1) * (y1 - cy) - (x1 - cx) * (y2 - y1)) / length
    return dist < 1.0


def masked(box, after, masks):
    return any(m["o"] > after and contains(m["box"], box) for m in masks)


def container_rects(root):
    """Bordered rects (containers) with translate offsets applied: (x, y, w, h, element)."""
    out = []
    def walk(el, ox, oy):
        dx, dy = translate(el)
        ox, oy = ox + dx, oy + dy
        if (el.tag.replace(NS, "") == "rect" and el.get("stroke", "none").lower() != "none"
                and el.get("fill", "none").lower() == "none"):
            out.append((num(el.get("x")) + ox, num(el.get("y")) + oy, num(el.get("width")), num(el.get("height")), el))
        for c in el:
            walk(c, ox, oy)
    walk(root, 0, 0)
    return out


class Issue:
    """One reported problem: its report line, a key that names the elements involved (so a
    re-check can tell whether this problem is gone), and the items the hint needs."""
    __slots__ = ("kind", "msg", "key", "ctx")

    def __init__(self, kind, msg, refs, ctx):
        self.kind, self.msg, self.ctx = kind, msg, ctx
        self.key = (kind,) + tuple(ref_id(r) for r in refs)


def key_ids(key):
    """The element ids a problem's key names."""
    return {p[0] if isinstance(p, tuple) else p for p in key[1:] if isinstance(p, (tuple, int))}


def ref_id(r):
    if isinstance(r, dict):
        return (id(r["el"]), r.get("i", -1)) if r.get("kind") else id(r["el"])
    if isinstance(r, tuple) and len(r) == 5:       # a container rect
        return id(r[4])
    return r


def run_checks(root):
    texts, segs, masks, icons, (cw, ch) = collect(root)
    issues = []

    def add(kind, msg, refs, **ctx):
        issues.append(Issue(kind, msg, refs, ctx))

    # A container title sits in its box's header row: x = box.x + 32 (with a badge) or
    # + 12 (label only), baseline box.y + 18. A title that drifted when content was moved
    # reads as belonging to nothing.
    rects = container_rects(root)
    clouds = [r for r in rects for i in icons
              if i.get("ref", "").startswith("group/AWS-Cloud-logo") and abs(i["box"][0] - r[0]) <= 1
              and abs(i["box"][1] - r[1]) <= 1]
    for i in icons:
        if i.get("ref") in OUTSIDE_CLOUD:
            x0, y0, x1, y1 = i["box"]
            for r in clouds:
                if r[0] <= x0 and x1 <= r[0] + r[2] and r[1] <= y0 and y1 <= r[1] + r[3]:
                    add("OUTSIDE CLOUD", f"OUTSIDE CLOUD   {i['ref']} at ({x0:g},{y0:g}) is inside the AWS Cloud box — "
                        "it isn't in AWS; place it between the on-premises group and the Cloud", [i], i=i, r=r)
                    break
    for t in texts:
        if not (t["title"] and t["fs"] in (14, 15)):
            continue
        base = 22 if t["fs"] == 15 else 18
        owners = [r for r in rects if any(abs(t["box"][0] - (r[0] + off)) <= 1 for off in (42, 32, 12))
                  and r[1] < t["y"] < r[1] + r[3]]
        if owners:
            r = max(owners, key=lambda r: r[1])
            if abs(t["y"] - (r[1] + base)) > 1:
                add("TITLE OFFSET", f"TITLE OFFSET    {t['s']!r} sits {t['y'] - r[1]:g}px below its box top "
                    f"— a container title's baseline is box.y + {base}", [t], t=t, r=r, base=base)
    for s in segs:
        if s.get("head"):
            (x1, y1), (x2, y2) = s["p"], s["q"]
            if 0 < math.hypot(x2 - x1, y2 - y1) < MIN_ARROW:
                add("SHORT ARROW", f"SHORT ARROW     {fmt(s)} is under {MIN_ARROW}px — widen the gap so the arrow "
                    "has a visible shaft", [s], s=s)
    for s in segs:
        if s["kind"] != "connector":
            continue
        (x1, y1), (x2, y2) = s["p"], s["q"]
        for b in segs:
            if b["kind"] != "border":
                continue
            (bx1, by1), (bx2, by2) = b["p"], b["q"]
            if abs(x1 - x2) < 0.5 and abs(bx1 - bx2) < 0.5:      # both vertical
                d, lo, hi = abs(x1 - bx1), max(min(y1, y2), min(by1, by2)), min(max(y1, y2), max(by1, by2))
            elif abs(y1 - y2) < 0.5 and abs(by1 - by2) < 0.5:    # both horizontal
                d, lo, hi = abs(y1 - by1), max(min(x1, x2), min(bx1, bx2)), min(max(x1, x2), max(bx1, bx2))
            else:
                continue
            if d < HUG_CLEAR and hi - lo > 20 and not masked((min(x1, bx1), lo, max(x1, bx1) + 0.1, hi), s["o"], masks):
                where = "on top of" if d == 0 else f"{d:g}px from"
                add("LINE HUGS BORDER", f"LINE HUGS BORDER {fmt(s)} runs {where} the border {fmt(b)} — "
                    f"keep {HUG_CLEAR}px or more", [s, b], s=s, b=b, d=d)
                break
    for t in texts:
        if t["title"] and CIDR_IN.search(t["s"]):
            add("CIDR IN TITLE", f"CIDR IN TITLE   {t['s']!r} — put the CIDR on its own 12px {CIDR_COLOR.upper()} line "
                "under the title (same x, baseline 16px lower)", [t], t=t)
        if BARE_CIDR.match(t["s"]) and not is_node_label(t, icons):
            titles = [h for h in texts if h["title"] and h is not t]
            under = any(abs(h["box"][0] - t["box"][0]) <= 1 and 14 <= t["y"] - h["y"] <= 18 for h in titles)
            if not under:
                near = min(titles, key=lambda h: abs(h["box"][0] - t["box"][0]) + abs(t["y"] - h["y"] - 16),
                           default=None)
                if near and abs(near["box"][0] - t["box"][0]) <= 8 and 8 <= t["y"] - near["y"] <= 24:
                    add("CIDR OFF HEADER", f"CIDR OFF HEADER {t['s']!r} is {t['box'][0] - near['box'][0]:+g}px off "
                        f"the x of {near['s']!r} and {t['y'] - near['y']:g}px below it — "
                        "same x as the title, baseline 16px lower", [t], t=t, title=near)
                else:
                    add("CIDR OFF HEADER", f"CIDR OFF HEADER {t['s']!r} floats inside a box — put it right under its "
                        "container's title and move whatever crosses the header instead", [t], t=t, title=None)
            elif not t["fill"]:
                add("CIDR COLOR", f"CIDR COLOR      {t['s']!r} has no fill attribute (inherits) — set "
                    f'fill="{CIDR_COLOR.upper()}"', [t], t=t)
            elif t["fill"] != CIDR_COLOR:
                add("CIDR COLOR", f"CIDR COLOR      {t['s']!r} under a title is {CIDR_COLOR.upper()} (squid ink), "
                    f"not {t['fill'].upper()}", [t], t=t)
        if CIRCLED.search(t["s"]):
            add("GLYPH STEP", f"GLYPH STEP      {t['s']!r} uses circled digits; draw step badges instead", [t], t=t)
        x0, y0, x1, y1 = t["box"]
        if cw and ch and (x0 < 0 or y0 < 0 or x1 > cw or y1 > ch):
            add("OFF CANVAS", f"OFF CANVAS      {t['s']!r} runs past the {cw:g} × {ch:g} canvas", [t], t=t)
        if t["fs"] < MIN_FONT:
            add("SMALL TEXT", f"SMALL TEXT      {t['fs']:g}px  {t['s']!r}", [t], t=t)
        b = shrink(t["box"])
        for s in segs:
            if seg_hits_box(s["p"], s["q"], b) and not masked(t["box"], s["o"], masks):
                add("LINE OVER TEXT", f"LINE OVER TEXT  {s['kind']} {fmt(s)} crosses {t['s']!r}", [t, s], t=t, s=s)
                break
        else:
            if t["title"]:
                x0, _, x1, y1 = t["box"]
                cidr = next((c for c in texts if BARE_CIDR.match(c["s"]) and abs(c["box"][0] - x0) <= 1
                             and 14 <= c["y"] - t["y"] <= 18), None)
                if cidr:
                    y1 = cidr["box"][3]
                below = (x0, y1, x1, y1 + HEADER_CLEAR)
                hit = next((s for s in segs if s["kind"] == "border" and s["p"][1] == s["q"][1]
                            and seg_hits_box(s["p"], s["q"], below)), None)
                if hit:
                    start = 46 if cidr else 30
                    add("HEADER CLEARANCE", f"HEADER CLEARANCE {t['s']!r} has a box border {fmt(hit)} less than "
                        f"{HEADER_CLEAR}px below it{' (under its CIDR line)' if cidr else ''} — "
                        f"start nested boxes at container.y + {start}", [t, hit], t=t, s=hit, cidr=cidr,
                        start=start, bottom=y1)
                    continue
            # A title sits at a fixed distance from its own container's border; every
            # other label (node, caption, connector label, legend row) keeps the full 8px.
            clear = BORDER_CLEAR if t["title"] else LABEL_CLEAR
            near = expand(t["box"], clear)
            for s in segs:
                if (s["kind"] == "border" and seg_hits_box(s["p"], s["q"], near)
                        and not masked(t["box"], s["o"], masks)):
                    add("TEXT AT BORDER", f"TEXT AT BORDER  {t['s']!r} is within {clear}px of the border "
                        f"{fmt(s)} — give it room", [t, s], t=t, s=s, clear=clear)
                    break
    connectors = [s for s in segs if s["kind"] == "connector"]
    for t in texts:
        # Node and header labels aren't connector labels, so a line skimming them is a
        # near miss, not a label sitting on its own line.
        if not (t["header"] or is_node_label(t, icons)):
            continue
        b = expand(t["box"], LINE_CLEAR)
        for s in connectors:
            if seg_hits_box(s["p"], s["q"], b) and not seg_hits_box(s["p"], s["q"], shrink(t["box"])) \
                    and not masked(t["box"], s["o"], masks):
                add("LINE NEAR TEXT", f"LINE NEAR TEXT  connector {fmt(s)} passes within {LINE_CLEAR}px of {t['s']!r}",
                    [t, s], t=t, s=s)
                break
    for t in texts:
        near = expand(t["box"], LABEL_REACH)
        if not is_node_label(t, icons) and any(seg_hits_box(s["p"], s["q"], near) for s in connectors):
            for phrase, ref in services_in_label(t["s"]):
                add("SERVICE AS TEXT", f"SERVICE AS TEXT {phrase!r} in connector label {t['s']!r} has an "
                    f"official icon ({ref}) — draw it as a node", [t, phrase], t=t, phrase=phrase, ref=ref)
    for i in icons:
        b = shrink(i["box"], 2.0)
        for s in segs:
            if i.get("dot") and through(i["dot"], s):
                continue
            if seg_hits_box(s["p"], s["q"], b) and not masked(i["box"], s["o"], masks):
                what = "badge" if i["badge"] else "icon"
                add("LINE OVER ICON", f"LINE OVER ICON  {s['kind']} {fmt(s)} crosses the {what} at "
                    f"({i['box'][0]:g},{i['box'][1]:g})", [i, s], i=i, s=s)
                break
    nodes = [i for i in icons if not i["badge"]]
    for g in (i for i in icons if i["badge"] and not i.get("dot") and i["box"][2] - i["box"][0] > 21):
        for n in nodes:
            if boxes_overlap(expand(g["box"], ICON_CLEAR), n["box"]) and not boxes_overlap(g["box"], n["box"]):
                add("BADGE NEAR ICON", f"BADGE NEAR ICON group badge at ({g['box'][0]:g},{g['box'][1]:g}) is within "
                    f"{ICON_CLEAR}px of the icon at ({n['box'][0]:g},{n['box'][1]:g})", [g, n], g=g, n=n)
                break
    for t in texts:
        # A header sits in its container's header row, so the first icon below it only
        # needs HEADER_ICON_CLEAR; every other label keeps ICON_CLEAR from icons it
        # doesn't label.
        clear = HEADER_ICON_CLEAR if t["title"] else ICON_CLEAR
        for n in nodes:
            x0, y0, x1, y1 = n["box"]
            own = abs(t["cx"] - (x0 + x1) / 2) <= 3 and y1 < t["y"] <= y1 + 44
            if not own and boxes_overlap(expand(t["box"], clear), n["box"]) \
                    and not boxes_overlap(shrink(t["box"]), shrink(n["box"], 2.0)):
                add("TEXT NEAR ICON", f"TEXT NEAR ICON  {t['s']!r} is within {clear}px of the icon at "
                    f"({x0:g},{y0:g})", [t, n], t=t, n=n, clear=clear)
                break
    for a_i, a in enumerate(texts):
        for b in texts[a_i + 1:]:
            if boxes_overlap(shrink(a["box"]), shrink(b["box"])):
                add("TEXT OVERLAP", f"TEXT OVERLAP    {a['s']!r} and {b['s']!r}", [a, b], a=a, b=b)
            elif (min(a["box"][3], b["box"][3]) - max(a["box"][1], b["box"][1]) > 0  # side by side
                  and boxes_overlap(expand(a["box"], TEXT_GAP), b["box"])):
                add("TEXT TOO CLOSE", f"TEXT TOO CLOSE  {a['s']!r} and {b['s']!r} are less than {TEXT_GAP}px apart",
                    [a, b], a=a, b=b)
        for i in icons:
            if not i["badge"] and boxes_overlap(shrink(a["box"]), shrink(i["box"], 2.0)):
                add("TEXT OVERLAP", f"TEXT OVERLAP    {a['s']!r} overlaps the icon at ({i['box'][0]:g},{i['box'][1]:g})",
                    [a, i], a=a, i=i)
    return issues


def check(path):
    """The report lines for one SVG file (no hints)."""
    return [i.msg for i in run_checks(ET.parse(path).getroot())]


def fmt(s):
    (x1, y1), (x2, y2) = s["p"], s["q"]
    return f"({x1:g},{y1:g})→({x2:g},{y2:g})"


# ---------------------------------------------------------------------------------------
# Edits. An edit is ("attr", el, name, value), ("text", el, value) or
# ("insert", el, tag, [(name, value), ...], text) — a new element right after el. They are
# applied to the parsed tree to re-check (and undone), and to the file's bytes by --fix.

NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def fnum(v):
    v = round(v, 2)
    return str(int(v)) if v == int(v) else f"{v:g}"


def apply_tree(root, edits):
    """Apply edits to the tree; return a function that undoes them."""
    undo, parents = [], None
    for e in edits:
        if e[0] == "attr":
            _, el, k, v = e
            old = el.get(k)
            el.set(k, v)
            undo.append(lambda el=el, k=k, old=old: el.attrib.pop(k, None) if old is None else el.set(k, old))
        elif e[0] == "text":
            _, el, v = e
            old = el.text
            el.text = v
            undo.append(lambda el=el, old=old: setattr(el, "text", old))
        elif e[0] == "insert":
            _, el, tag, attrs, txt = e
            if parents is None:
                parents = {c: p for p in root.iter() for c in p}
            p = parents[el]
            new = ET.Element(NS + tag, dict(attrs))
            new.text, new.tail = txt, el.tail
            p.insert(list(p).index(el) + 1, new)
            undo.append(lambda p=p, new=new: p.remove(new))

    def run():
        for u in reversed(undo):
            u()
    return run


START_TAG = re.compile(rb"<[\w:.-]+(?:\s+[\w:.-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*\s*/?>")


def start_offsets(data):
    """Byte offset of every element's start tag, in document order (= ElementTree's iter())."""
    offs = []
    p = xml.parsers.expat.ParserCreate()
    p.StartElementHandler = lambda name, attrs: offs.append(p.CurrentByteIndex)
    p.Parse(data, True)
    return offs


def xml_escape(s, attr=False):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s.replace('"', "&quot;") if attr else s


def set_attr_in_tag(tag, k, v):
    m = re.search(r"(\s" + re.escape(k) + r"\s*=\s*)([\"'])(.*?)\2", tag, re.S)
    if m:
        return tag[:m.start(3)] + xml_escape(v, True) + tag[m.end(3):]
    j = len(tag) - (2 if tag.endswith("/>") else 1)
    while j > 0 and tag[j - 1].isspace():
        j -= 1
    return tag[:j] + f' {k}="{xml_escape(v, True)}"' + tag[j:]


def write_edits(path, data, order, edits):
    """Rewrite only what the edits touch in the file's bytes: attribute values in their start
    tag, a text element's content, a new element on its own line after the anchor."""
    offs = start_offsets(data)
    reps = []                                     # (start, end, new bytes)
    by_el = {}
    for e in edits:
        by_el.setdefault(id(e[1]), []).append(e)
    for eid, es in by_el.items():
        start = offs[order[eid]]
        m = START_TAG.match(data, start)
        tag_end = m.end()
        tag = data[start:tag_end].decode("utf-8")
        for e in es:
            if e[0] == "attr":
                tag = set_attr_in_tag(tag, e[2], e[3])
        reps.append((start, tag_end, tag.encode("utf-8")))
        closing = None
        if not tag.endswith("/>"):
            name = re.match(r"<([\w:.-]+)", tag).group(1)
            closing = data.index(f"</{name}>".encode(), tag_end)
        for e in es:
            if e[0] == "text":
                reps.append((tag_end, closing, xml_escape(e[2]).encode("utf-8")))
            elif e[0] == "insert":
                _, el, tname, attrs, txt = e
                after = closing + len(f"</{name}>") if closing is not None else tag_end
                line_start = data.rfind(b"\n", 0, start) + 1
                indent = data[line_start:start]
                indent = indent if not indent.strip() else b""
                a = "".join(f' {k}="{xml_escape(v, True)}"' for k, v in attrs)
                markup = f"<{tname}{a}>{xml_escape(txt)}</{tname}>"
                reps.append((after, after, b"\n" + indent + markup.encode("utf-8")))
    out = data
    for s, e, b in sorted(reps, key=lambda r: (r[0], r[1]), reverse=True):
        out = out[:s] + b + out[e:]
    Path(path).write_bytes(out)


# ---------------------------------------------------------------------------------------
# Hints.

class Hint:
    """text: the fix line; auto: the edits --fix may apply; edits: the edits the text describes
    (a checked move's, for tests and tools); note: why an auto fix was held back."""
    __slots__ = ("text", "auto", "edits", "note")

    def __init__(self, text, auto=None, edits=None):
        self.text, self.auto, self.note = text, auto, ""
        self.edits = edits if edits is not None else auto


def direction(dx, dy):
    if dx and dy:
        return f"by ({fnum(dx)},{fnum(dy)})"
    if dx:
        return f"{'right' if dx > 0 else 'left'} {fnum(abs(dx))}px"
    return f"{'down' if dy > 0 else 'up'} {fnum(abs(dy))}px"


def away(box, ob, gap):
    """The four smallest whole-px shifts that put box `gap` px clear of obstacle box ob."""
    x0, y0, x1, y1 = box
    out = []
    up, down = math.floor(ob[1] - gap - y1), math.ceil(ob[3] + gap - y0)
    left, right = math.floor(ob[0] - gap - x1), math.ceil(ob[2] + gap - x0)
    for d, vertical in ((up, True), (down, True), (left, False), (right, False)):
        if d == 0:
            continue
        for extra in (0, 1, 2):
            dd = d + (extra if d > 0 else -extra)
            out.append((0, dd) if vertical else (dd, 0))
    return out


def seg_box(s):
    (x1, y1), (x2, y2) = s["p"], s["q"]
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


# Problems no move can clear (a move that leaves them is still a clean move).
NOT_POSITIONAL = {"SMALL TEXT", "CIDR COLOR", "GLYPH STEP", "SERVICE AS TEXT", "CIDR IN TITLE"}


class Advisor:
    """Computes the fix hint for each problem, checking a candidate change by re-running the
    check on the tree with the change applied."""

    MAX_TRIALS = 24

    def __init__(self, root):
        self.root = root
        self.order = {id(el): k for k, el in enumerate(root.iter())}
        self.refresh()

    def refresh(self):
        self.issues = run_checks(self.root)
        self.keys = {i.key for i in self.issues}
        self.texts, self.segs, self.masks, self.icons, self.canvas = collect(self.root)
        self.rects = container_rects(self.root)
        self.settled = {}                       # id(element) -> a checked move that clears all its problems
        self.last_keys = set()
        self.titles = {}                        # id(rect el) -> its title text item
        for r in self.rects:
            for t in self.texts:
                if t["header"] and any(abs(t["box"][0] - (r[0] + off)) <= 1 for off in (42, 32, 12)) \
                        and r[1] < t["y"] <= r[1] + 26:
                    self.titles[id(r[4])] = t
                    break

    # --- re-check ------------------------------------------------------------------
    def trial(self, edits, target):
        """(cleared, new problems) with edits applied."""
        undo = apply_tree(self.root, edits)
        try:
            after = run_checks(self.root)
        finally:
            undo()
        keys = {i.key for i in after}
        self.last_keys = keys
        return target not in keys, [i for i in after if i.key not in self.keys]

    def pick(self, target, cands, fallback=""):
        """cands: (size, edits, text). The smallest that clears the target without a new
        problem — preferring one that also clears the other problems of the element it
        moves, so one move settles them all; else the smallest that clears it, saying
        what it breaks."""
        cands = sorted(cands, key=lambda c: c[0])
        clean = dirty = None
        seen = set()
        for size, edits, text in cands:
            sig = tuple((e[0], id(e[1])) + tuple(e[2:]) for e in edits)
            if sig in seen:
                continue
            seen.add(sig)
            if len(seen) > self.MAX_TRIALS:
                break
            ok, new = self.trial(edits, target)
            if ok and not new:
                moved = {id(e[1]) for e in edits}
                related = {i.key for i in self.issues if i.key != target and key_ids(i.key) & moved
                           and i.kind not in NOT_POSITIONAL}
                left = related & self.last_keys
                if not left:
                    h = Hint(text, edits=edits)
                    for eid in moved:
                        self.settled[eid] = h
                    return h
                if clean is None:
                    kinds = sorted({k[0] for k in left})
                    clean = Hint(f"{text} (still leaves its {', '.join(kinds)})", edits=edits)
            if ok and dirty is None:
                dirty = (text, new, edits)
        if clean:
            return clean
        if dirty:
            text, new, edits = dirty
            more = f" (+{len(new) - 1} more)" if len(new) > 1 else ""
            return Hint(f"{text} — clears it, but then: {new[0].msg.strip()}{more}", edits=edits)
        if fallback:
            return Hint(fallback)
        if cands:
            return Hint(f"{cands[0][2]} (unverified: no move tried clears it)")
        return Hint("")

    def related_boxes(self, item):
        """Boxes of the other things this element has a problem with (to clear them all at once)."""
        me = ref_id(item)
        out = []
        for iss in self.issues:
            if me not in iss.key[1:]:
                continue
            for v in iss.ctx.values():
                if isinstance(v, dict) and "el" in v and ref_id(v) != me:
                    out.append(v["box"] if "box" in v else seg_box(v))
        return out

    # --- describing elements, in the draft's own values ---------------------------
    @staticmethod
    def local(item):
        ox, oy = item["off"]
        return f" [draft coords inside translate({fnum(ox)},{fnum(oy)})]" if (ox, oy) != (0, 0) else ""

    @staticmethod
    def el_id(el):
        return f' id="{el.get("id")}"' if el.get("id") else ""

    def tdesc(self, t):
        return f"text {t['s']!r}{self.el_id(t['el'])}"

    def idesc(self, i):
        el = i["el"]
        if el.tag.replace(NS, "") == "circle":
            return f"circle at cx={el.get('cx')} cy={el.get('cy')}"
        what = f"image {i['ref']}" if i.get("ref") else "icon"
        return f"{what}{self.el_id(el)} (x={el.get('x')}, y={el.get('y')})"

    def sdesc(self, s):
        el = s["el"]
        tag = el.tag.replace(NS, "")
        ox, oy = s["off"]
        (x1, y1), (x2, y2) = s["p"], s["q"]
        pts = f"({fnum(x1 - ox)},{fnum(y1 - oy)})→({fnum(x2 - ox)},{fnum(y2 - oy)})"
        if tag == "rect":
            return self.rdesc(el)
        return f"{tag}{self.el_id(el)} {'segment ' if tag == 'polyline' else ''}{pts}"

    def rdesc(self, el):
        t = self.titles.get(id(el))
        name = f" {t['s']!r}" if t else ""
        return (f"rect{name}{self.el_id(el)} (x={el.get('x')}, y={el.get('y')}, "
                f"width={el.get('width')}, height={el.get('height')})")

    # --- moves -----------------------------------------------------------------------
    def move_text(self, t, dx, dy, also=()):
        edits, parts = [], []
        for item in (t,) + tuple(also):
            el = item["el"]
            for axis, d in (("x", dx), ("y", dy)):
                if d:
                    old = num(el.get(axis))
                    edits.append(("attr", el, axis, fnum(old + d)))
                    if item is t:
                        parts.append(f"{axis}={el.get(axis) or 0}→{fnum(old + d)}")
        extra = f" (with {', '.join(repr(a['s']) for a in also)})" if also else ""
        return edits, f"move {self.tdesc(t)}{extra} {direction(dx, dy)}: {', '.join(parts)}{self.local(t)}"

    def own_labels(self, i):
        x0, _, x1, y1 = i["box"]
        return [t for t in self.texts if abs(t["cx"] - (x0 + x1) / 2) <= 3 and y1 < t["y"] <= y1 + 44]

    def move_icon(self, i, dx, dy):
        el = i["el"]
        edits, labels = [], self.own_labels(i)
        tag = el.tag.replace(NS, "")
        axes = (("cx", dx), ("cy", dy)) if tag == "circle" else (("x", dx), ("y", dy))
        parts = []
        for a, d in axes:
            if d:
                edits.append(("attr", el, a, fnum(num(el.get(a)) + d)))
                parts.append(f"{a}={el.get(a)}→{fnum(num(el.get(a)) + d)}")
        for t in labels:
            for a, d in (("x", dx), ("y", dy)):
                if d:
                    edits.append(("attr", t["el"], a, fnum(num(t["el"].get(a)) + d)))
        lab = f" and its label{'s' if len(labels) > 1 else ''} {', '.join(repr(t['s']) for t in labels)}" if labels else ""
        ends = any(s["kind"] == "connector" and (contains(expand(i["box"], 3), (*s["p"], *s["p"]), 0)
                                                 or contains(expand(i["box"], 3), (*s["q"], *s["q"]), 0))
                   for s in self.segs)
        tail = "; re-attach its connector ends" if ends else ""
        return edits, f"move {self.idesc(i)}{lab} {direction(dx, dy)}: {', '.join(parts)}{tail}{self.local(i)}"

    def move_run(self, s, dx, dy):
        """Shift one straight run of a line/polyline sideways (both its points)."""
        el = s["el"]
        tag = el.tag.replace(NS, "")
        if tag == "line":
            edits = [("attr", el, a, fnum(num(el.get(a)) + d))
                     for a, d in (("x1", dx), ("x2", dx), ("y1", dy), ("y2", dy)) if d]
        elif tag == "polyline":
            edits = [("attr", el, "points", shift_points(el.get("points", ""), {s["i"], s["i"] + 1}, dx, dy))]
        else:
            return None, ""
        ox, oy = s["off"]
        (x1, y1), (x2, y2) = s["p"], s["q"]
        new = f"({fnum(x1 + dx - ox)},{fnum(y1 + dy - oy)})→({fnum(x2 + dx - ox)},{fnum(y2 + dy - oy)})"
        ends = []
        if tag == "line" or s["i"] == 0:
            ends.append("start")
        if tag == "line" or s["i"] == s["n"] - 1:
            ends.append("end")
        tail = f" (this moves the line's {' and '.join(ends)} too: keep {'them' if len(ends) > 1 else 'it'} on the node)" if ends else ""
        return edits, f"move the run {self.sdesc(s)} {direction(dx, dy)} to {new}{tail}{self.local(s)}"

    def title_home(self, t):
        """(rect, dx, dy) for a title within 12px each way of its box's header slot — x = box.x
        + 12 (+ 32 beside a 24px badge, + 42 beside the Cloud's 32px one), baseline box.y + 18
        (+ 22 for the 15px Cloud title); dx = dy = 0 when it sits there, None for a bold label
        that is no box's title."""
        if not t["title"]:
            return None
        base = 22 if t["fs"] == 15 else 18
        best = None
        for r in self.rects:
            badge = next((i for i in self.icons if i["badge"] and abs(i["box"][0] - r[0]) <= 1
                          and abs(i["box"][1] - r[1]) <= 1), None)
            off = 12 if badge is None else 42 if badge["box"][2] - badge["box"][0] >= 30 else 32
            dx, dy = r[0] + off - t["box"][0], r[1] + base - t["y"]
            if abs(dx) <= 12 and abs(dy) <= 12 and (best is None or abs(dx) + abs(dy) < best[0]):
                best = (abs(dx) + abs(dy), r, dx, dy)
        if best is None:
            return None
        _, r, dx, dy = best
        return r, round(dx if abs(dx) > 1 else 0, 2), round(dy if abs(dy) > 1 else 0, 2)

    def home_cand(self, t):
        """Put a drifted title (and the CIDR line that should be under it) back in its header slot."""
        home = self.title_home(t)
        if not home or not (home[1] or home[2]):
            return []
        r, dx, dy = home
        cidr = next((c for c in self.texts if BARE_CIDR.match(c["s"]) and 10 <= c["y"] - t["y"] <= 22
                     and abs(c["box"][0] - t["box"][0]) <= 12), None)
        edits, text = self.move_text(t, dx, dy)
        if cidr:
            cdx = t["box"][0] + dx - cidr["box"][0]
            cdy = t["y"] + dy + 16 - cidr["y"]
            for a, d in (("x", cdx), ("y", cdy)):
                if abs(d) > 1e-6:
                    edits.append(("attr", cidr["el"], a, fnum(num(cidr["el"].get(a)) + d)))
            if abs(cdx) > 1e-6 or abs(cdy) > 1e-6:
                text += f" with its CIDR line {cidr['s']!r} (same x, baseline 16px lower)"
        return [(0.5, edits, f"{text} — back to the header slot of {self.rdesc(r[4])}")]

    def text_cands(self, t, ob, gap, axes="xy"):
        home = self.home_cand(t)
        # A node label stays on its icon's center line and a title on its header row's x.
        if self.title_home(t) or (BARE_CIDR.match(t["s"]) and self.header_of(t)):
            return home                         # a box's title (and CIDR line) only goes back to its header slot
        if any(not i["badge"] and abs(t["cx"] - (i["box"][0] + i["box"][2]) / 2) <= 3
               and i["box"][3] < t["y"] <= i["box"][3] + 44 for i in self.icons):
            axes = axes.replace("x", "")
        obs = [ob]
        rel = self.related_boxes(t)
        if rel:
            u = ob
            for b in rel:
                u = union(u, b)
            obs.append(u)
        out = []
        for dx, dy in (m for o in obs for m in away(t["box"], o, gap)):
            if (dx and "x" not in axes) or (dy and "y" not in axes):
                continue
            edits, text = self.move_text(t, dx, dy)
            # Prefer keeping a node label on its icon's center line: horizontal moves cost more.
            out.append((abs(dx) * 1.5 + abs(dy), edits, text))
        return home + out

    def run_cands(self, s, ob, gap):
        (x1, y1), (x2, y2) = s["p"], s["q"]
        out = []
        obs = [ob]
        rel = self.related_boxes(s)
        if rel:
            u = ob
            for b in rel:
                u = union(u, b)
            obs.append(u)
        if abs(x1 - x2) < 0.5:
            moves = [(d, 0) for o in obs for d in (math.floor(o[0] - gap - x1), math.ceil(o[2] + gap - x1))]
        elif abs(y1 - y2) < 0.5:
            moves = [(0, d) for o in obs for d in (math.floor(o[1] - gap - y1), math.ceil(o[3] + gap - y1))]
        else:
            return out
        for dx, dy in moves:
            for extra in (0, 1):
                ddx = dx + (extra if dx > 0 else -extra if dx < 0 else 0)
                ddy = dy + (extra if dy > 0 else -extra if dy < 0 else 0)
                edits, text = self.move_run(s, ddx, ddy)
                if edits:
                    out.append((abs(ddx) + abs(ddy) + 0.5, edits, text))   # a line move after an equal label move
        return out

    def icon_cands(self, i, ob, gap):
        box = i["box"]
        for t in self.own_labels(i):
            box = union(box, t["box"])
        out = []
        for dx, dy in away(box, ob, gap):
            edits, text = self.move_icon(i, dx, dy)
            out.append((abs(dx) + abs(dy), edits, text))
        return out

    # --- fixed-answer fixes ------------------------------------------------------------
    def center_fix(self, t):
        """A label a few px off the center line of the icon right above it: center it."""
        for n in self.icons:
            if n["badge"]:
                continue
            x0, _, x1, y1 = n["box"]
            cx = (x0 + x1) / 2
            if 3 < abs(t["cx"] - cx) <= OFF_CENTER and y1 < t["y"] <= y1 + 44 and not len(t["el"]) \
                    and not t["title"]:
                el = t["el"]
                new_x = fnum(cx - t["off"][0])
                edits = [("attr", el, "x", new_x)]
                anchor = el.get("text-anchor", "start")
                set_anchor = ""
                if anchor != "middle":
                    edits.append(("attr", el, "text-anchor", "middle"))
                    set_anchor = ' text-anchor="middle"'
                return edits, (f"center {self.tdesc(t)} under {self.idesc(n)}: x={el.get('x')}→{new_x}"
                               f"{set_anchor}{self.local(t)}")
        return None

    def mask_fix(self, box, seg, pad=0.0):
        """Grow the white mask drawn after the line that covers part of box to cover it all —
        and everything else on top of that mask the same line crosses (the gateway icon and
        its label take one mask)."""
        cands = [m for m in self.masks if m["o"] > seg["o"] and boxes_overlap(m["box"], box)]
        if not cands:
            return None
        m = max(cands, key=lambda m: (min(m["box"][2], box[2]) - max(m["box"][0], box[0]))
                * (min(m["box"][3], box[3]) - max(m["box"][1], box[1])))
        mb = m["box"]
        need = (box[0] - pad, box[1], box[2] + pad, box[3])
        for item in self.icons + self.texts:
            ib = item["box"]
            if item["o"] > m["o"] and boxes_overlap(ib, mb) and seg_hits_box(seg["p"], seg["q"], shrink(ib)):
                tp = 4.0 if "s" in item else 0.0
                need = union(need, (ib[0] - tp, ib[1], ib[2] + tp, ib[3]))
        need = union(need, mb)
        need = (math.floor(need[0]), math.floor(need[1]), math.ceil(need[2]), math.ceil(need[3]))
        if max(mb[0] - need[0], mb[1] - need[1], need[2] - mb[2], need[3] - mb[3]) > 60:
            return None
        # Nothing else may vanish under the bigger mask: no line, icon or label drawn before it
        # that the old mask didn't already cover.
        for s in self.segs:
            if s["o"] < m["o"] and seg_hits_box(s["p"], s["q"], need) and not seg_hits_box(s["p"], s["q"], mb) \
                    and s is not seg and ref_id(s) != ref_id(seg):
                return None
        for i in self.icons + self.texts:
            if i["o"] < m["o"] and boxes_overlap(i["box"], need) and not boxes_overlap(i["box"], mb):
                return None
        el, (ox, oy) = m["el"], m["off"]
        vals = {"x": need[0] - ox, "y": need[1] - oy, "width": need[2] - need[0], "height": need[3] - need[1]}
        edits = [("attr", el, k, fnum(v)) for k, v in vals.items() if abs(num(el.get(k)) - v) > 1e-6]
        if not edits:
            return None
        old = f"x={el.get('x')} y={el.get('y')} width={el.get('width')} height={el.get('height')}"
        new = " ".join(f"{k}={fnum(v)}" for k, v in vals.items())
        return edits, f"grow the white mask rect{self.el_id(el)} ({old}) to {new}{self.local(m)}"

    def endpoint_fix(self, s, i):
        """A connector end inside an icon: pull it back to 4px short of the icon's edge."""
        el = s["el"]
        tag = el.tag.replace(NS, "")
        box = i["box"]
        inner = shrink(box, 2.0)
        p, q = s["p"], s["q"]
        if contains(inner, (*q, *q), 0) and not contains(box, (*p, *p), 0) and s["i"] == s["n"] - 1:
            inside, outside, idx = q, p, s["i"] + 1
        elif contains(inner, (*p, *p), 0) and not contains(box, (*q, *q), 0) and s["i"] == 0:
            inside, outside, idx = p, q, 0
        else:
            return None
        # Where outside→inside enters the box.
        dx, dy = inside[0] - outside[0], inside[1] - outside[1]
        t0 = 0.0
        for pk, qk in ((-dx, outside[0] - box[0]), (dx, box[2] - outside[0]),
                       (-dy, outside[1] - box[1]), (dy, box[3] - outside[1])):
            if pk < 0:
                t0 = max(t0, qk / pk)
        # Connectors stop 4px short of the icon (the guide: E/2 + 4 from its center).
        length = math.hypot(dx, dy) or 1.0
        back = min(4.0, t0 * length)
        nx, ny = outside[0] + t0 * dx - back * dx / length, outside[1] + t0 * dy - back * dy / length
        mx, my = nx - inside[0], ny - inside[1]
        ox, oy = s["off"]
        if tag == "line":
            a = ("x2", "y2") if idx == 1 else ("x1", "y1")
            edits = [("attr", el, a[0], fnum(nx - ox)), ("attr", el, a[1], fnum(ny - oy))]
            which = "(x2,y2)" if idx == 1 else "(x1,y1)"
        elif tag == "polyline":
            edits = [("attr", el, "points", shift_points(el.get("points", ""), {idx}, mx, my))]
            which = "last point" if idx else "first point"
        else:
            return None
        return edits, (f"end {self.sdesc(s)} 4px short of {self.idesc(i)}: its {which} "
                       f"({fnum(inside[0] - ox)},{fnum(inside[1] - oy)})→({fnum(nx - ox)},{fnum(ny - oy)}){self.local(s)}")

    # --- per problem -------------------------------------------------------------------
    def hint(self, iss):
        h = self._hint(iss)
        if not h.text:
            if any(isinstance(v, dict) and "s" in v and (v["title"] or self.header_of(v)) for v in iss.ctx.values()):
                h.text = ("a container title stays on its box's header row (x = box.x + 12, + 32 beside a badge; "
                          "baseline box.y + 18; its CIDR line 16px lower): move the other element, or the box")
            else:
                h.text = "no single move found that clears it — move the other element or resize the box"
        return h

    def _hint(self, iss):
        c, k = iss.ctx, iss.kind
        for eid in key_ids(iss.key):
            if eid in self.settled:             # the move given for another problem of this element clears this too
                h = self.settled[eid]
                return Hint(h.text, edits=h.edits)
        fn = getattr(self, "h_" + k.lower().replace(" ", "_"))
        h = fn(iss, **c)
        if isinstance(h, str):
            h = Hint(h)
        return h

    def h_outside_cloud(self, iss, i, r):
        ob = (r[0], r[1], r[0] + r[2], r[1] + r[3])
        cands = []
        box = i["box"]
        for t in self.own_labels(i):
            box = union(box, t["box"])
        for dx, dy in ((math.floor(ob[0] - 16 - box[2]), 0), (math.ceil(ob[2] + 16 - box[0]), 0),
                       (0, math.floor(ob[1] - 16 - box[3])), (0, math.ceil(ob[3] + 16 - box[1]))):
            edits, text = self.move_icon(i, dx, dy)
            cands.append((abs(dx) + abs(dy), edits, text + f" (16px outside the AWS Cloud box, x={fnum(ob[0])}..{fnum(ob[2])})"))
        return self.pick(iss.key, cands)

    def cidr_under(self, t):
        return next((c for c in self.texts if BARE_CIDR.match(c["s"]) and abs(c["box"][0] - t["box"][0]) <= 1
                     and 14 <= c["y"] - t["y"] <= 18), None)

    def h_title_offset(self, iss, t, r, base):
        dy = r[1] + base - t["y"]
        cidr = self.cidr_under(t)
        edits, _ = self.move_text(t, 0, dy, also=(cidr,) if cidr else ())
        el = t["el"]
        text = (f"set y={fnum(num(el.get('y')) + dy)} on {self.tdesc(t)} (was {el.get('y')}; its box top is "
                f"y={fnum(r[1] - t['off'][1])}, + {base})")
        if cidr:
            text += f" and y={fnum(num(cidr['el'].get('y')) + dy)} on its CIDR line {cidr['s']!r}"
        return Hint(text + self.local(t), edits)

    def h_short_arrow(self, iss, s):
        (x1, y1), (x2, y2) = s["p"], s["q"]
        length = math.hypot(x2 - x1, y2 - y1)
        need = math.ceil(MIN_ARROW - length)
        heads = s.get("heads", {"end"})
        # Lengthen away from the arrowhead: move the far point of the head segment back.
        if "end" in heads and s["i"] == s["n"] - 1:
            tail, head, tail_idx = s["p"], s["q"], s["i"]
        else:
            tail, head, tail_idx = s["q"], s["p"], s["i"] + 1
        ux, uy = (tail[0] - head[0]) / (length or 1), (tail[1] - head[1]) / (length or 1)
        dx, dy = round(ux * need, 2), round(uy * need, 2)
        el = s["el"]
        tag = el.tag.replace(NS, "")
        ox, oy = s["off"]
        nt = f"({fnum(tail[0] + dx - ox)},{fnum(tail[1] + dy - oy)})"
        ot = f"({fnum(tail[0] - ox)},{fnum(tail[1] - oy)})"
        cands = []
        if tag == "polyline" and 0 < tail_idx < s["n"]:
            # The bend and the run before it move together, so the route stays orthogonal.
            prev = tail_idx - 1 if tail_idx == s["i"] else tail_idx + 1
            edits = [("attr", el, "points", shift_points(el.get("points", ""), {tail_idx, prev}, dx, dy))]
            text = (f"lengthen the head segment {fnum(length)}→{MIN_ARROW}px: move the bend {ot} to {nt} "
                    f"together with the run before it{self.local(s)} — or widen the gap between the nodes by {need}px")
            cands.append((need, edits, text))
        elif tag in ("line", "polyline"):
            if tag == "line":
                a = ("x1", "y1") if tail_idx == 0 else ("x2", "y2")
                edits = [("attr", el, a[0], fnum(tail[0] + dx - ox)), ("attr", el, a[1], fnum(tail[1] + dy - oy))]
            else:
                edits = [("attr", el, "points", shift_points(el.get("points", ""), {tail_idx}, dx, dy))]
            text = (f"lengthen it {fnum(length)}→{MIN_ARROW}px: move its tail {ot} to {nt}{self.local(s)} "
                    f"(or widen the gap between the nodes by {need}px)")
            cands.append((need, edits, text))
        return self.pick(iss.key, cands, fallback=f"widen the gap so the head segment grows by {need}px to {MIN_ARROW}px")

    def h_line_hugs_border(self, iss, s, b, d):
        (x1, y1), (x2, y2) = s["p"], s["q"]
        (bx, by), _ = b["p"], b["q"]
        vertical = abs(x1 - x2) < 0.5
        cur, line = (x1, bx) if vertical else (y1, by)
        sides = [1, -1] if d == 0 else [1 if cur > line else -1]
        cands = []
        for sign, extra in ((sign, extra) for sign in sides for extra in (0, 2, 4, 8, 12, 16, 24)):
            target = line + sign * (HUG_CLEAR + extra)
            delta = target - cur
            edits, text = self.move_run(s, delta if vertical else 0, 0 if vertical else delta)
            if edits:
                where = f"{'x' if vertical else 'y'}={fnum(target - (s['off'][0] if vertical else s['off'][1]))}"
                cands.append((abs(delta), edits, f"{text} ({where}, {HUG_CLEAR + extra}px from the border of "
                                                 f"{self.rdesc(b['el'])})"))
        return self.pick(iss.key, cands)

    def h_cidr_in_title(self, iss, t):
        el = t["el"]
        m = CIDR_IN.search(t["s"])
        cidr = m.group()
        rest = (t["s"][:m.start()] + " " + t["s"][m.end():])
        rest = re.sub(r"[(\[]\s*[)\]]", " ", rest)
        rest = re.sub(r"\s+", " ", rest).strip(" -–—·:,|/()[]")
        y = fnum(num(el.get("y")) + 16)
        attrs = [("x", el.get("x") or "0"), ("y", y), ("font-size", "12"), ("fill", CIDR_COLOR.upper())]
        if el.get("text-anchor"):
            attrs.insert(2, ("text-anchor", el.get("text-anchor")))
        new = "<text " + " ".join(f'{k}="{v}"' for k, v in attrs) + f">{cidr}</text>"
        text = (f"set the title {self.tdesc(t)} to {rest!r} and add {new} right after it "
                f"(nested boxes then start at container.y + 46){self.local(t)}")
        if not rest:
            return Hint(f"{self.tdesc(t)} is only a CIDR: title the box with its name and put {cidr!r} on its "
                        f'own line under it (same x, baseline 16px lower, font-size="12" fill="{CIDR_COLOR.upper()}", '
                        f"no font-weight){self.local(t)}")
        if len(el):
            return Hint(text)
        return Hint(text, [("text", el, rest), ("insert", el, "text", attrs, cidr)])

    def h_cidr_off_header(self, iss, t, title):
        el = t["el"]
        auto, route = True, ""
        if title is None:
            # Its own title right above it, drifted sideways: put whichever of the two is off its
            # box's header x back in line.
            above = [h for h in self.texts if h["title"] and 14 <= t["y"] - h["y"] <= 18
                     and abs(h["box"][0] - t["box"][0]) <= 80]
            for h in above:
                home = self.home_cand(h)
                if home:
                    return Hint(home[0][2], home[0][1])
        if title is None:
            # Under the title of the innermost container the CIDR sits in, if that title has none yet.
            inside = [r for r in self.rects if id(r[4]) in self.titles
                      and contains((r[0], r[1], r[0] + r[2], r[1] + r[3]), t["box"], 0)]
            route = (f" — or, if it is a route's destination, give it its target in the same label "
                     f"('{t['s']} → <target>') so it isn't a bare CIDR")
            if not inside:
                return "put it right under its container's title (same x, baseline title.y + 16)" + route
            r = min(inside, key=lambda r: r[2] * r[3])
            title = self.titles[id(r[4])]
            # Only a CIDR still in its box's header row is surely that box's CIDR.
            if self.cidr_under(title) or t["y"] - r[1] > 46:
                auto = False
        dx, dy = title["box"][0] - t["box"][0], title["y"] + 16 - t["y"]
        home = None if route else self.home_cand(title)
        if home:
            # The title drifted from its header slot: put it (and this CIDR under it) back.
            return Hint(home[0][2], home[0][1])
        edits = []
        parts = []
        for a, d in (("x", dx), ("y", dy)):
            if abs(d) > 1e-6:
                edits.append(("attr", el, a, fnum(num(el.get(a)) + d)))
                parts.append(f"{a}={el.get(a)}→{fnum(num(el.get(a)) + d)}")
        lead = f"if it is the CIDR of {title['s']!r}, " if route else ""
        text = (f"{lead}move {self.tdesc(t)} under {title['s']!r}: {', '.join(parts)} "
                f"(the title's x, baseline 16px below its y){self.local(t)}")
        if route and self.cidr_under(title):
            text = f"{title['s']!r} already has a CIDR line; delete this one" + route
        else:
            text += route
        return Hint(text, edits if auto and edits else None)

    def h_cidr_color(self, iss, t):
        return Hint(f'set fill="{CIDR_COLOR.upper()}" on {self.tdesc(t)}', [("attr", t["el"], "fill", CIDR_COLOR.upper())])

    def h_glyph_step(self, iss, t):
        plain = re.sub(r"\s+", " ", CIRCLED.sub("", t["s"])).strip()
        return (f"set {self.tdesc(t)} to {plain!r} and number the step with a badge instead: "
                '<circle r="10"> in the step color + a white bold 12px digit (baseline cy + 4)')

    def h_off_canvas(self, iss, t):
        cw, ch = self.canvas
        x0, y0, x1, y1 = t["box"]
        dx = math.ceil(4 - x0) if x0 < 0 else math.floor(cw - 4 - x1) if x1 > cw else 0
        dy = math.ceil(4 - y0) if y0 < 0 else math.floor(ch - 4 - y1) if y1 > ch else 0
        grow = []
        if x1 > cw:
            grow.append(f"width {fnum(cw)}→{math.ceil(x1 + 4)}")
        if y1 > ch:
            grow.append(f"height {fnum(ch)}→{math.ceil(y1 + 4)}")
        alt = f" — or grow the viewBox {' and '.join(grow)} (and the white background rect)" if grow else ""
        edits, text = self.move_text(t, dx, dy)
        return self.pick(iss.key, [(abs(dx) + abs(dy), edits, text + alt)])

    def h_small_text(self, iss, t):
        return Hint(f'set font-size="{MIN_FONT}" on {self.tdesc(t)} (was {t["el"].get("font-size") or "unset"})',
                    [("attr", t["el"], "font-size", str(MIN_FONT))])

    def h_line_over_text(self, iss, t, s):
        pad = 4.0 if s["kind"] == "border" else 0.0
        mf = self.mask_fix(t["box"], s, pad)
        if mf:
            return Hint(mf[1], mf[0])
        if s["kind"] == "border":
            for i in self.icons:
                if not i["badge"] and any(o["el"] is t["el"] for o in self.own_labels(i)):
                    gm = self.gateway_mask(i, s)
                    if gm:
                        return gm
            gap = BORDER_CLEAR if t["title"] else LABEL_CLEAR
            cands = self.text_cands(t, seg_box(s), gap)
        else:
            cands = self.text_cands(t, seg_box(s), LINE_CLEAR) + self.run_cands(s, t["box"], LINE_CLEAR)
        return self.pick(iss.key, cands)

    def header_of(self, t):
        """(title, box rect, CIDR line or None) when t is a container's title or its CIDR line."""
        title = t
        if BARE_CIDR.match(t["s"]):
            title = next((h for h in self.texts if h["title"] and abs(h["box"][0] - t["box"][0]) <= 1
                          and 14 <= t["y"] - h["y"] <= 18), None)
        if not title or not title["title"]:
            return None
        owner = next((r for r in self.rects if self.titles.get(id(r[4]), {}).get("el") is title["el"]), None)
        if owner is None:
            return None
        return title, owner, self.cidr_under(title)

    def push_down(self, t, s, bottom, start=None):
        """Move the nested box whose top border s sits under a header down far enough."""
        hy = s["p"][1]
        el = s["el"]
        head = self.header_of(t)
        need = math.ceil(bottom + HEADER_CLEAR - hy)
        goal = ""
        if head:
            title, owner, cidr = head
            start = start or (46 if cidr else 30)
            need = max(need, math.ceil(owner[1] + start - hy))
            goal = f" (nested boxes start at the y of the box titled {title['s']!r} + {start} = {fnum(owner[1] + start - s['off'][1])})"
        return (f"move {self.rdesc(el)} down {need}px to y={fnum(num(el.get('y')) + need)} with everything inside it"
                f"{goal}, or move the top of the box titled {(head[0] if head else t)['s']!r} up {need}px"
                f"{self.local(s)}")

    def h_header_clearance(self, iss, t, s, cidr, start, bottom):
        return self.push_down(t, s, bottom, start)

    def h_text_at_border(self, iss, t, s, clear):
        mf = self.mask_fix(t["box"], s, 4.0)
        if mf:
            return Hint(mf[1], mf[0])
        (x1, y1), (x2, y2) = s["p"], s["q"]
        if self.header_of(t) and abs(y1 - y2) < 0.5 and y1 > t["y"]:
            # A header line stays put: the box under it moves.
            return self.push_down(t, s, t["box"][3])
        return self.pick(iss.key, self.text_cands(t, seg_box(s), clear))

    def h_line_near_text(self, iss, t, s):
        cands = self.text_cands(t, seg_box(s), LINE_CLEAR) + self.run_cands(s, t["box"], LINE_CLEAR)
        return self.pick(iss.key, cands)

    def h_service_as_text(self, iss, t, phrase, ref):
        cf = self.center_fix(t)
        if cf:
            return Hint(cf[1] + " (then it reads as that icon's node label)", cf[0])
        rest = re.sub(r"\s+", " ", t["s"].replace(phrase, " ")).strip(" -·,()→")
        keep = f" and keep only {rest!r} on the connector" if rest else " and drop the connector label"
        return (f'draw {phrase!r} as a node: <image href="bundle:{ref}" width="48" height="48"/> on this '
                f"connector with {phrase!r} as its label 18px below it{keep}")

    def gateway_mask(self, i, s):
        """An icon centered on a container border sits there on purpose (IGW/VGW on the VPC
        edge): the fix is the white mask of the guide, mask_w = max(S, label width + 8),
        mask_h = S + 24 (+ 16 per extra label line)."""
        (x1, y1), (x2, y2) = s["p"], s["q"]
        x0, y0, xe, ye = i["box"]
        cx, cy = (x0 + xe) / 2, (y0 + ye) / 2
        if not ((abs(x1 - x2) < 0.5 and abs(x1 - cx) <= 2) or (abs(y1 - y2) < 0.5 and abs(y1 - cy) <= 2)):
            return None
        labels = self.own_labels(i)
        size = xe - x0
        tw = max((t["box"][2] - t["box"][0] for t in labels), default=0)
        mw = max(size, math.ceil(tw + 8))
        mh = size + 24 + 16 * max(0, len(labels) - 1)
        ox, oy = i["off"]
        mask = (f'<rect x="{fnum(cx - mw / 2 - ox)}" y="{fnum(y0 - oy)}" width="{fnum(mw)}" '
                f'height="{fnum(mh)}" fill="#FFFFFF"/>')
        return (f"{self.idesc(i)} sits on the border on purpose (a gateway): add the mask {mask} after the "
                f"border's rect and before the icon{self.local(i)}")

    def h_line_over_icon(self, iss, i, s):
        mf = self.mask_fix(i["box"], s)
        if mf:
            return Hint(mf[1], mf[0])
        if s["kind"] == "connector":
            ef = self.endpoint_fix(s, i)
            if ef:
                return Hint(ef[1], ef[0])
            return self.pick(iss.key, self.run_cands(s, i["box"], LINE_CLEAR))
        # A container border through the icon.
        gm = self.gateway_mask(i, s)
        if gm:
            return gm
        return self.pick(iss.key, self.icon_cands(i, seg_box(s), ICON_CLEAR))

    def h_badge_near_icon(self, iss, g, n):
        return self.pick(iss.key, self.icon_cands(n, g["box"], ICON_CLEAR))

    def h_text_near_icon(self, iss, t, n, clear):
        cf = self.center_fix(t)
        if cf:
            return Hint(cf[1], cf[0])
        return self.pick(iss.key, self.text_cands(t, n["box"], clear))

    def h_text_overlap(self, iss, a, b=None, i=None):
        if i is not None:
            x0, _, x1, y1 = i["box"]
            cx = (x0 + x1) / 2
            if abs(a["cx"] - cx) <= OFF_CENTER and a["y"] > (i["box"][1] + y1) / 2 and not len(a["el"]) \
                    and not a["title"]:
                # Its own label, too high or off-center: centered, baseline icon bottom + 18.
                el = a["el"]
                dy = y1 + NODE_LABEL_DY - a["y"]
                sub = [c for c in self.texts if c["el"] is not a["el"] and abs(c["cx"] - a["cx"]) <= 3
                       and 0 < c["y"] - a["y"] <= 20]
                edits, _ = self.move_text(a, 0, dy, also=tuple(sub))
                text = f"set y={fnum(num(el.get('y')) + dy)} on {self.tdesc(a)} (icon bottom + {NODE_LABEL_DY})"
                if sub:
                    text += f", moving {', '.join(repr(c['s']) for c in sub)} {direction(0, dy)} with it"
                if abs(a["cx"] - cx) > 3:
                    edits.append(("attr", el, "x", fnum(cx - a["off"][0])))
                    if el.get("text-anchor", "start") != "middle":
                        edits.append(("attr", el, "text-anchor", "middle"))
                    text += f', x={fnum(cx - a["off"][0])} text-anchor="middle"'
                return Hint(text + self.local(a), edits)
            return self.pick(iss.key, self.text_cands(a, i["box"], ICON_CLEAR))
        return self.pick(iss.key, self.text_cands(a, b["box"], TEXT_GAP) + self.text_cands(b, a["box"], TEXT_GAP))

    def h_text_too_close(self, iss, a, b):
        return self.pick(iss.key, self.text_cands(a, b["box"], TEXT_GAP) + self.text_cands(b, a["box"], TEXT_GAP))

    # --- the fixed-answer pass ------------------------------------------------------------
    def plan(self):
        """Hints for every problem, then the auto fixes that hold up, applied one by one to the
        tree (each re-checked against the state the earlier ones left). Returns
        [(issue, hint)], [(issue, hint)] accepted."""
        hints = [(iss, self.hint(iss)) for iss in self.issues]
        accepted = []
        for iss, h in hints:
            if not h.auto:
                continue
            if any(id(e[1]) not in self.order for e in h.auto):
                h.note = "not auto-fixed: it edits an element added by another fix"
                continue
            if iss.key not in self.keys:
                h.note = "cleared by an earlier fix"
                accepted.append((iss, h))
                continue
            ok, new = self.trial(h.auto, iss.key)
            if ok and not new:
                apply_tree(self.root, h.auto)
                self.keys = {i.key for i in run_checks(self.root)}
                accepted.append((iss, h))
            else:
                h.note = ("not auto-fixed: " + (f"then {new[0].msg.strip()}" if new else "it doesn't clear it"))
                h.auto = None
        return hints, accepted


def shift_points(points, idxs, dx, dy):
    """Shift the given point indexes of a points="..." string, keeping its other text as is."""
    out, last = [], 0
    for k, m in enumerate(NUMBER.finditer(points)):
        pi, axis = divmod(k, 2)
        v = m.group()
        if pi in idxs:
            v = fnum(float(v) + (dx if axis == 0 else dy))
        out.append(points[last:m.start()] + v)
        last = m.end()
    return "".join(out) + points[last:]


def report(hints, accepted):
    ok_ids = {id(h) for _, h in accepted if h.note != "cleared by an earlier fix"}
    lines = []
    for iss, h in hints:
        lines.append(iss.msg)
        text = h.text
        if id(h) in ok_ids:
            text += "  [--fix]"
        elif h.note:
            text += f"  ({h.note})"
        if text:
            lines.append(f"  fix: {text}")
    n_auto = len(ok_ids)
    return lines, n_auto


def run_file(path, fix):
    """Check (and with fix, repair) one file. Returns (lines, problems left)."""
    out, fixed = [], []
    for n in range(6 if fix else 1):
        data = Path(path).read_bytes()
        adv = Advisor(ET.fromstring(data))
        hints, accepted = adv.plan() if adv.issues else ([], [])
        real = [(iss, h) for iss, h in accepted if h.note != "cleared by an earlier fix"]
        if not fix or not real or n == 5:
            break
        write_edits(path, data, adv.order, [e for _, h in real for e in h.auto])
        fixed += [f"  {iss.msg.strip()}\n    → {h.text}" for iss, h in real]
    if fix:
        if fixed:
            out.append(f"Fixed {len(fixed)}:")
            out += fixed
        elif hints:
            out.append("Nothing to fix automatically.")
        if fixed and hints:
            out.append("Still to fix:")
    lines, n_auto = report(hints, accepted)
    out += lines
    if hints:
        out.append(f"{len(hints)} problem{'s' if len(hints) != 1 else ''} ({n_auto} auto-fixable with --fix)")
    else:
        out.append("Layout OK")
    return out, len(hints)


def main():
    args = sys.argv[1:]
    fix = "--fix" in args
    files = [a for a in args if a != "--fix"]
    if not files or any(a.startswith("--") for a in files):
        print(__doc__)
        sys.exit(1)
    bad = 0
    for f in files:
        lines, n = run_file(f, fix)
        if len(files) > 1:
            print(f"== {f}")
        print("\n".join(lines), flush=True)
        bad += n
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
