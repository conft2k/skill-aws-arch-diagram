"""Constants for the layout engine (layout.py): mode tables, group styles, text, lines, notes.

Pure data plus a few tiny pure helpers (mode(), style(), top_inset(), group_type_of(),
slide_pt(), slide_max(), smallest_text(), smallest_pt()); no imports from the rest of the
skill, so every layout_* module and the tests can import it freely. The contract (data
model, function signatures, z order, ids, text width) is in layout_model.py's docstring.

Sources, cited per value:
  QR <n>    references/quick_reference.md, line n
  DG "x"    references/diagram_guide.md, the section named x
  ex <name> measured in docs/examples/<name>-reference-architecture.svg after
            `embed.py --unembed` (doc = the document example, slide = docs/examples/slides/);
            "skeleton" is docs/example.svg
  CL        what scripts/check_layout.py enforces: the checker imports every number it shares
            with the engine from here (it needs nothing but this module and find_icon), so
            the two cannot drift; tests/test_layout_model.py asserts the couplings between
            the engine's offsets and the checker's reaches (ConstTest.test_couplings)
  DESIGN    the layout-engine design (4.4 mode table, 2.2 group table)
Where the design and the examples disagree the measured example value wins and the comment
says so ("examples win").

Every length is in canvas px (SVG user units of a viewBox "0 0 W H"), at icon size S = 48.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

MODES_ORDER = ("document", "slide")

# --------------------------------------------------------------------------------------
# Icon and node label stack (mode-independent)

S_DEFAULT = 48            # QR 84: every node icon 48x48
NODE_LABEL_DY = 18        # QR 91: label baseline = icon.y + S + 18 (= icon.y + 66, every example); CL
SUB_PITCH = 16            # QR 92 / 110: each sub-caption line 16 below the previous line (every example),
                          # and +16 mask height per extra label line; CL
END_GAP = 4               # QR 142: a connector stops 4px from an icon (cx ± (S/2 + 4)) or a box border
EMPHASIS = 64             # QR 87: E = 64, phase 2


def label_size(S: float = S_DEFAULT) -> int:
    """Node label font size: 14 at S = 48, ≈ 0.3 × S, never below 12 (QR 130)."""
    return max(12, int(round(0.3 * S)))


# --------------------------------------------------------------------------------------
# Text (QR 118-132 "Text size"); TextStyle = (size px, font-weight or "" for regular, fill)

@dataclass(frozen=True)
class TextStyle:
    size: int
    weight: str     # "" = regular (attribute omitted), "600", "700"
    fill: str


INK = "#232F3E"           # QR 122: squid ink, node labels, lines, badges
GRAY = "#545B64"          # QR 126: sub-captions, verbs, note text
WHITE = "#FFFFFF"

TEXT_NODE = TextStyle(14, "", INK)          # QR 122
TEXT_SUB = TextStyle(12, "", GRAY)          # QR 126 (examples: every sub-caption #545B64)
TEXT_TITLE_SIZE = 14                        # QR 123: container title 14 / 600 / the border color
TEXT_TITLE_WEIGHT = "600"
TEXT_CLOUD_TITLE = TextStyle(15, "600", INK)  # QR 124
TEXT_CIDR = TextStyle(12, "", INK)          # QR 44: CIDR line 12px regular #232F3E (CL CIDR COLOR)
TEXT_PROTO = TextStyle(12, "", INK)         # QR 125: protocol/port connector label
TEXT_VERB = TextStyle(12, "", GRAY)         # QR 126: verb / attachment-type label
TEXT_HOP = TextStyle(12, "600", INK)        # QR 127: legend hop, note row label
TEXT_NOTE = TextStyle(12, "", GRAY)         # QR 126: note description, summary, slide note line
TEXT_BADGE = TextStyle(12, "700", WHITE)    # QR 128: step badge digit
MIN_FONT = 12                               # QR 130; CL SMALL TEXT

# Root font-family (every example's root <svg>). W1 picks the first installed of
# FONT_CANDIDATES (fc-list) and lists the others after it; with Noto installed (this
# machine) the result is exactly FONT_FAMILY_DEFAULT.
FONT_CANDIDATES = ("Noto Sans CJK KR", "Pretendard")   # QR 131
FONT_FAMILY_DEFAULT = "'Noto Sans CJK KR', 'Pretendard', Arial, sans-serif"   # ex all

# Text width estimate (layout_model.text_width / layout_text_width use these).
CHECK_LATIN_EM = 0.55     # CL text_width: the checker's Latin estimate; also what the examples' computed x's use
LAYOUT_LATIN_EM = 0.60    # QR 111 / DESIGN 4.2: conservative estimate for reserving space
WIDE_EM = 1.0             # QR 111: Hangul / CJK / arrows U+2190-U+2BFF; CL text_width
GLYPH_ASCENT = 0.75       # QR 79: glyph box = baseline − 0.75 × size …  (CL collect)
GLYPH_DESCENT = 0.25      # … to baseline + 0.25 × size

# --------------------------------------------------------------------------------------
# Lines, markers, badges

LINE_COLOR = INK          # QR 136
LINE_WIDTH = 1.5          # QR 136 (ex all: 126 connectors, all 1.5 #232F3E)
DASH_DASHED = "5,4"       # QR 140: dashed connectors (return/outbound/DNS/management), every example
TGW_RT_LINK = ("#8C4FFF", 1.5, "4 3")   # QR 152: TGW ↔ its route-table table; phase 2 (no example)
JUNCTION_DOT_R = 6        # CL collect: a circle r ≤ 6 on its own line is a junction dot (< BADGE_R); phase 2

# One marker each, exactly as in every example's <defs> (W5 indents them). arrowStart only
# when some element has marker-start (QR 137).
MARKER_ARROW = ('<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">'
                '<path d="M0,0 L8,3 L0,6 Z" fill="#232F3E"/></marker>')
MARKER_ARROW_START = ('<marker id="arrowStart" markerWidth="10" markerHeight="10" refX="0" refY="3" orient="auto">'
                      '<path d="M8,0 L0,3 L8,6 Z" fill="#232F3E"/></marker>')
MARKER_END_ATTR = "url(#arrow)"
MARKER_START_ATTR = "url(#arrowStart)"

# Edge operators (DESIGN 2.4) → (dashed, marker at the far end, marker at the near end)
EDGE_OPS: Dict[str, Tuple[bool, bool, bool]] = {
    "->": (False, True, False),
    "<->": (False, True, True),
    "--": (False, False, False),
    "..>": (True, True, False),
    "<..>": (True, True, True),
    "..": (True, False, False),
}

BADGE_R = 10              # QR 158
BADGE_FILL = INK          # QR 158
BADGE_DY = 14             # QR 161: badge cy = line.y − 14 (bottom 4 above the line); ex all H badges
BADGE_TEXT_DY = 4         # QR 159: digit baseline cy + 4
VBADGE_DX = 22            # DESIGN 4.6: on a vertical piece cx = x − 22 (ex bedrock-dx, nlb-mtls: 22)

PORT_SIDE = 8             # QR 146: several lines into one side: ±8 on a left/right side
PORT_TOPBOT = 10          # QR 146: ±10 on a top/bottom side
PORT_PITCH = 12           # DESIGN 4.4: 3 or more lines on one side: 12 apart
BREAK_APART = 40          # QR 149: where a path leaves and rejoins the main line, ≥ 40 apart
GROUP_END_GAP = 4         # QR 143 / DESIGN 2.4: an edge ending on a group stops 4 from its border

# --------------------------------------------------------------------------------------
# Clearances and reaches check_layout enforces (it imports them from here; the layout keeps
# the clearances with margin and its offsets inside the reaches, ConstTest.test_couplings)

LABEL_CLEAR = 8           # CL TEXT AT BORDER: label ↔ container border (QR 71)
BORDER_CLEAR = 4          # CL TEXT AT BORDER: a container title ↔ a border (it sits at a fixed offset)
ICON_CLEAR = 8            # CL TEXT / BADGE NEAR ICON: label / group badge ↔ an icon it doesn't label (QR 72-73)
HEADER_ICON_CLEAR = 6     # CL TEXT NEAR ICON: header label ↔ icon (QR 72)
LINE_CLEAR = 4            # CL LINE NEAR TEXT: connector ↔ node or header label, and ↔ a connector
                          # label's top or sides (QR 74)
TEXT_GAP = 4              # CL TEXT TOO CLOSE: label ↔ label side by side (QR 75)
HEADER_CLEAR = 8          # CL HEADER CLEARANCE: header label ↔ nested box top
MIN_ARROW = 20            # CL SHORT ARROW: arrowhead segment ≥ 20 (QR 144)
HUG_CLEAR = 12            # CL LINE HUGS BORDER: connector alongside a border ≥ 12 (QR 145, slide trunk 12) …
HUG_OVERLAP = 20          # … for more than this along it
LABEL_REACH = 14          # CL: a text whose box comes within this of a connector is a connector label
END_REACH = 6             # CL: a connector end this close to a node (icon and label lines) or a border ends on it
JOIN_REACH = 3            # CL: a line end this close to another line joins it (a stem a px or two off its bar)
BOTTOM_PORT_GAP = 8       # a line out of a node's bottom starts this far below its last label baseline
                          # (the glyph bottom is GLYPH_DESCENT × size above it: within END_REACH)
ON_LINE_GAP = 2           # CL LINE ON LINE: two connectors this close side by side read as one line …
ON_LINE_RUN = 8           # … when they share more than this along it
IN_LINE_GAP = 2 * PORT_SIDE        # CL LINE ON LINE: two flows' pieces on one line with facing ends closer
                                   # than this read as one line through the gap (16: two lines into one
                                   # side ±8 apart read as two; 12 = PORT_PITCH, two fallbacks, as one) …
IN_LINE_CROSS_GAP = 2 * PORT_PITCH  # … and up to this (24) with a third line crossing the gap (a "+")
IN_LINE_EPS = 0.25                 # … a gap at a limit is not under it (the commonest is exactly 16: two
                                   # lines out of one side at ±8 turning apart along one line; float noise
                                   # must not report it)
LB_CLEAR = 8              # QR 76: load balancer node ↔ AZ and subnet borders
MASK_CLEAR = 8            # QR 77: IGW/VGW mask ↔ next container border and canvas edge
MASK_TEXT_PAD = 8         # QR 110: mask width = max(S, label width + 8)

# --------------------------------------------------------------------------------------
# Mode table (DESIGN 4.4, checked against the examples)

@dataclass(frozen=True)
class Mode:
    name: str
    index: int              # 0 document, 1 slide: index into the (document, slide) pairs below
    canvas_margin: float    # drawing ↔ canvas edge
    pad: float              # container side and bottom border ↔ a child box
    pad_node: float         # container side border ↔ a directly contained node's footprint
    label_bottom: float     # a node's last label baseline → its container's bottom border
    sibling_gap: float      # box ↔ box and box ↔ node side by side in one parent
    label_gap: float        # two neighbour nodes' label lines side by side (0.6 em widths); icons keep sibling_gap
    box_node_gap: float     # a box's bottom border ↔ the icon of a node below it in one parent
    az_gap_center: bool     # the rows between two AZ boxes sit at least az_gap / 2 from each box
    even_instances: bool    # instances of a template on different rows get equal top / bottom insets
    badge_clear_x: bool     # a group's first-row nodes sit right of its badge (else the row moves down)
    stack_gap: float        # a node's label stack ↔ the icon of a node below it in one parent
    peer_gap: float         # side-by-side Region / VPC boxes
    node_pitch: float       # neighbour node centers in one container and row
    az_gap: float           # bottom of the AZ (row) above ↔ top of the AZ below, when a node of the VPC
                            # (LB, IGW) sits on a row between them; otherwise sibling_gap
    mask_extra: float       # IGW/VGW mask height = S + mask_extra (+16 per extra label line)
    arrow_target: float     # preferred arrowhead segment length
    arrow_min: float        # hard minimum (= MIN_ARROW)
    trunk_clear: float      # trunk ↔ the boxes it runs past
    flow_pitch: float       # center pitch in a flow row (regional services row)
    label_above: float      # connector label above its line: baseline = line.y − label_above
    label_below: float      # below its line: baseline = line.y + label_below
    vlabel_dx: float        # label beside a vertical piece: x = line.x ± vlabel_dx (anchor end/start)


DOCUMENT = Mode(
    name="document", index=0,
    canvas_margin=16,       # QR 58 (examples 16)
    # DESIGN 4.4 had Cloud→Region and Region→VPC sides 20; examples win: alb (Region right
    # 16, VPC right 16), nlb-mtls (Region left/right/bottom 16), bedrock-dx (16) use 16, so
    # 16 is the minimum at every level (QR 54 "examples 16–20"). bedrock-dx and the
    # skeleton go down to 8–12 in places; the engine stays at 16.
    pad=16,
    pad_node=16,            # DESIGN 4.4 "내용 ↔ 테두리 16"
    label_bottom=12,        # DESIGN 4.4 (ex nfw, nlb-mtls, bedrock-dx: 12; alb/nlb 20–22 where the row is taller)
    sibling_gap=16,         # DESIGN 4.4 (ex nfw subnets 16; alb 20, nlb 24, gwlb 32)
    label_gap=16,           # = sibling_gap: documents keep their label spacing
    box_node_gap=16,
    az_gap_center=True,
    even_instances=True,    # ex documents: both AZ boxes alike (same height, icons at the same depth)
    badge_clear_x=False,
    stack_gap=16,
    peer_gap=32,            # DESIGN 4.4, QR 59 "24–40" (ex gwlb VPCs 32)
    node_pitch=100,         # QR 55 (ex alb/nlb EC2s 100)
    az_gap=110,             # QR 56 (ex alb 110, nlb 110, gwlb 118, nfw 132, nlb-mtls 162)
    mask_extra=24,          # QR 110: 48 × 72 in documents (ex all)
    arrow_target=48,        # QR 144 "document ~48"
    arrow_min=20,           # QR 144; CL MIN_ARROW
    trunk_clear=28,         # QR 145 "document ~28" (ex nfw: 1136 − 1108 = 28)
    flow_pitch=160,         # QR 63 (ex alb/nlb regional services 160 apart)
    label_above=9,          # DESIGN 4.6; examples 8–9 (protocol labels 9, verbs 8), QR 151 "4–8px above"
    # DESIGN 4.6 said 15; examples win: 16 below the line (gwlb GENEVE, tgw IPsec, nlb-mtls, bedrock-dx).
    label_below=16,
    vlabel_dx=10,           # DESIGN 4.6 (ex alb "동기식 복제" 10, bedrock-dx "AWS 네트워크" 10)
)

SLIDE = Mode(
    name="slide", index=1,
    canvas_margin=4,        # QR 58 "hug the content (examples 2–16)"; slide examples' Cloud top 2–4
    pad=8,                  # QR 54 "may shrink to 8 (examples 8–12)"; every slide example ≥ 8
    pad_node=8,
    label_bottom=12,        # ex slides: 12
    sibling_gap=12,         # ex slides alb/nfw subnets 12
    label_gap=4,            # CL TEXT_GAP; the 0.6 em widths leave ~0.05 em per glyph more (ex slide tgw: Dev VPC's
                            # 10.3.0.0/16 beside TGW A RT's VPC·VPN 경로 전파 at a 100 pitch)
    box_node_gap=8,         # ex slides: the AZ-gap row's icon top 8 below the AZ above (main = AZ.B + 32)
    az_gap_center=False,    # ex slides: the gap row hugs the AZ above, its label stack fills the rest
    even_instances=False,   # ex slide gwlb: AZ 1 144 tall, AZ 2 152 (the ASG bottom); each AZ hugs its own
    badge_clear_x=True,     # ex slide nfw: TGW ENI / NAT right of the subnet badge, not a row lower
    stack_gap=8,            # ex slide nfw: Firewall RT's sub ~9 above the TGW icon
    peer_gap=24,            # QR 59
    node_pitch=92,          # DESIGN 4.4 (ex slide alb 96, nlb 92)
    az_gap=86,              # QR 56 (every slide example exactly 86)
    mask_extra=22,          # QR 110: 48 × 70 on slides (ex all slides)
    arrow_target=20,        # QR 144 (slides keep the minimum)
    arrow_min=20,
    trunk_clear=12,         # QR 145
    flow_pitch=160,         # slides put regional services in a column instead (QR 63); kept for a flow row
    label_above=9,          # ex slides 8–9
    label_below=16,
    vlabel_dx=8,            # ex slide alb "동기식 복제" 8 (document 10)
)

MODES: Dict[str, Mode] = {"document": DOCUMENT, "slide": SLIDE}


def mode(name: str) -> Mode:
    return MODES[name]


# --------------------------------------------------------------------------------------
# Group styles (DESIGN 2.2, QR 17-32, header geometry QR 42-48)

BADGE_SIZE = 24           # QR 34: every example 24 for every group but the AWS Cloud
CLOUD_BADGE_SIZE = 32     # QR 19/34
TITLE_DX_BADGE = 32       # QR 42: title x = box.x + 32 with a badge (24 badge + 8)
TITLE_DX_PLAIN = 12       # QR 42: box.x + 12 without
TITLE_DY = 18             # QR 42: title baseline box.y + 18
CLOUD_TITLE_DX = 42       # QR 43
CLOUD_TITLE_DY = 22       # QR 43
CIDR_DY = 34              # QR 44: CIDR baseline box.y + 34, same x as the title
HEADER_TAIL = 8           # DESIGN 4.3 #4: box width ≥ title_dx + tw(title) + 8 (same for the CIDR line)
# A box that shows a CIDR pushes what is nested in it lower (QR 46-47), any group type:
CIDR_TOP_BOX = (46, 46)   # QR 46: nested box top ≥ box.y + 46 (ex all VPCs → AZ 46; nlb-mtls subnet → SG 46)
CIDR_TOP_ICON = (50, 46)  # DESIGN 4.4 / QR 47: first icon ≥ box.y + 46 (slides); documents +4 like 32 vs 28


@dataclass(frozen=True)
class GroupStyle:
    type: str
    stroke: str
    width: float
    dash: Optional[str]              # stroke-dasharray, None = solid
    badge: Optional[str]             # bundle ref ("group/Region_32") or None = label only
    label: Optional[str]             # default title; None = no title unless the spec gives one
    top_box: Tuple[float, float]     # (document, slide): nested box top ≥ box.y + this (no CIDR)
    top_icon: Tuple[float, float]    # (document, slide): directly contained icon top ≥ box.y + this (no CIDR)
    any_dash: bool = False           # the spec may set `dash` (generic only)

    @property
    def badge_size(self) -> int:
        return CLOUD_BADGE_SIZE if self.type == "cloud" else BADGE_SIZE

    @property
    def title_size(self) -> int:
        return TEXT_CLOUD_TITLE.size if self.type == "cloud" else TEXT_TITLE_SIZE

    @property
    def title_fill(self) -> str:
        return self.stroke      # QR 123 (cloud: #232F3E = its stroke)

    @property
    def title_dx(self) -> float:
        if self.type == "cloud":
            return CLOUD_TITLE_DX
        return TITLE_DX_BADGE if self.badge else TITLE_DX_PLAIN

    @property
    def title_dy(self) -> float:
        return CLOUD_TITLE_DY if self.type == "cloud" else TITLE_DY


def _g(type, stroke, width, dash, badge, label, top_box, top_icon, any_dash=False):
    return GroupStyle(type, stroke, width, dash, badge, label, top_box, top_icon, any_dash)


GROUP_STYLES: Dict[str, GroupStyle] = {s.type: s for s in (
    # cloud: Region at +40 in documents (every example but bedrock-dx, which uses the slide
    # value 34), +34 on slides (ex all slides); QR 46 "≥ 34 (document examples 40, slides 34)".
    # Icons directly in the Cloud: ex alb Route 53 +72 (doc), slide +40 → same minimum as a box.
    _g("cloud", "#232F3E", 2, None, "group/AWS-Cloud-logo_32", "AWS Cloud", (40, 34), (40, 34)),
    _g("account", "#E7157B", 2, None, "group/AWS-Account_32", "AWS Account", (30, 30), (30, 28)),
    # region: VPC at +32 doc (ex gwlb, nlb-mtls, skeleton; nfw 34, bedrock-dx 36), +30 slide.
    _g("region", "#00A4A6", 2, "3,3", "group/Region_32", "Region", (32, 30), (32, 30)),
    # az: subnet at +30 (ex all, both modes). Label "Availability Zone {n}" (W1 substitutes n).
    _g("az", "#00A4A6", 1.5, "8,4", None, "Availability Zone {n}", (30, 30), (32, 28)),
    _g("vpc", "#8C4FFF", 2, None, "group/Virtual-private-cloud-VPC_32", "VPC", (30, 30), (32, 28)),
    # subnets: first icon +32 doc (ex nfw 32, gwlb 34, alb/nlb 54–56 under the ASG; the
    # docs/example.svg skeleton 30), +28 slide (= the checker's 21.5 + 6 floor, QR 47).
    _g("public", "#7AA116", 1.5, None, "group/Public-subnet_32", "Public subnet", (30, 30), (32, 28)),
    _g("private", "#00A4A6", 1.5, None, "group/Private-subnet_32", "Private subnet", (30, 30), (32, 28)),
    # sg: icon +28 (ex nlb-mtls backend-sg and nlb-sg, a document).
    _g("sg", "#DD344C", 1.5, None, None, "Security group", (30, 30), (28, 28)),
    # asg (overlay): icon +30 doc (ex alb, skeleton), +28 slide (ex slide alb, nlb). Applies to
    # member icons under the header only (ex gwlb: icons right of the short "ASG" title sit +26/+20).
    _g("asg", "#ED7100", 1.5, "6,3", "group/Auto-Scaling-group_32", "Auto Scaling group", (30, 30), (30, 28)),
    _g("ec2contents", "#ED7100", 1.5, None, "group/EC2-instance-contents_32", None, (30, 30), (30, 28)),
    _g("spotfleet", "#ED7100", 1.5, None, "group/Spot-Fleet_32", None, (30, 30), (30, 28)),
    # beanstalk: QR 28 lists the Elastic Beanstalk container (no badge); not in DESIGN 2.2.
    _g("beanstalk", "#ED7100", 1.5, None, None, None, (30, 30), (30, 28)),
    # onprem: icon +34 (ex tgw doc and slide; bedrock-dx 36). DESIGN 34/30 kept as the minimum.
    _g("onprem", "#7D8998", 2, None, "group/Corporate-data-center_32", "On-premises", (30, 30), (34, 30)),
    _g("server", "#7D8998", 2, None, "group/Server-contents_32", None, (30, 30), (34, 30)),
    # generic: dash from the spec (ex bedrock-dx "6,4"), solid by default; icon +32 (ex bedrock-dx).
    _g("generic", "#7D8998", 1.5, None, None, None, (30, 30), (32, 30), any_dash=True),
    _g("sfn", "#E7157B", 1.5, None, None, None, (30, 30), (30, 28)),
    # cloudwan: phase 2. QR 32 "dashed" without a pattern; 6,3 like the other dashed groups is a guess.
    _g("cloudwan", "#8C4FFF", 2, "6,3", "service/AWS-Cloud-WAN", None, (30, 30), (30, 28), any_dash=True),
)}

OVERLAY_TYPES = ("asg",)               # DESIGN 2.2 `over:` groups (ASG, target group)
OVERLAY_HEADER_GAP = 8                 # QR 48: ASG box 8 inside its subnet, 8 right of / below each header label it crosses


def style(group_type: str) -> GroupStyle:
    return GROUP_STYLES[group_type]


def top_inset(group_type: str, mode_name: str, what: str, cidr: bool = False) -> float:
    """Minimum distance from a group's top border to what it nests directly.

    what = "box" (a nested group's top border) or "icon" (a directly contained node's icon
    top). A group that shows a CIDR line uses CIDR_TOP_BOX / CIDR_TOP_ICON (never less than
    the type's own value)."""
    st, i = GROUP_STYLES[group_type], MODES[mode_name].index
    if what == "box":
        return max(st.top_box[i], CIDR_TOP_BOX[i]) if cidr else st.top_box[i]
    if what == "icon":
        return max(st.top_icon[i], CIDR_TOP_ICON[i]) if cidr else st.top_icon[i]
    raise ValueError(what)


def group_type_of(stroke: str, dash: Optional[str], badge: Optional[str]) -> Optional[str]:
    """Reverse lookup for drafts (tests, compare_structure): a container rect's stroke color,
    stroke-dasharray (None = solid) and the bundle ref of the badge image on its top-left
    corner (None = none) → group type, or None when no style matches."""
    stroke = (stroke or "").upper()
    dash = dash or None
    for st in GROUP_STYLES.values():
        if st.stroke.upper() != stroke or st.badge != badge:
            continue
        if st.any_dash or st.dash == dash:
            return st.type
    return None


# --------------------------------------------------------------------------------------
# The note (QR 169-183, DG "The note — one place per diagram")

NOTE_FILL = "#F8F9F9"     # QR 180
NOTE_STROKE = "#D5DBDB"   # QR 180
NOTE_STROKE_W = 1         # QR 180

PANE_RATIO = 0.7          # QR 174: document pane when drawing height > 0.7 × width (with a step legend)

# bottom panel (QR 181; ex nfw, gwlb, tgw step rows; alb, nlb summary)
PANEL_X = 16              # x = 16, width = canvas − 32
PANEL_GAP = 16            # y = drawing bottom (the Cloud's) + 16; canvas ends 16 below the panel
PANEL_FIRST = 26          # first baseline panel.y + 26
PANEL_PITCH = 24          # rows 24 apart
PANEL_LAST = 18           # height = 26 + 24 × (rows − 1) + 18 (one row: 44)
PANEL_ROW_X = 28          # rows start at x 28 (summary text x = 28; step badge left edge = 28)
PANEL_BADGE_CX = 38
PANEL_HOP_X = 56
PANEL_DESC_GAP = 16       # description x = 56 + widest hop + 16, widths by text_width (0.55 em):
                          # ex nfw 56 + 107.4 + 16 = 179.4 exactly; tgw 222.6 → 223; gwlb 159.6 → 165

# left legend pane (QR 182; ex nlb-mtls 320 wide, bedrock-dx 456 = left column)
PANE_X = 16               # x = 16, y = Cloud.y
PANE_W = 300
PANE_W_WIDE = 320         # when a description would run past PANE_WIDE_LINES lines at 300
PANE_WIDE_LINES = 4
PANE_GAP = 24             # AWS Cloud x ≥ pane right + 24 (ex bedrock-dx 472 + 24 = 496)
PANE_BADGE_CX = 38
PANE_FIRST_CY = 22        # first badge cy = pane.y + 22; hop baseline cy + 4 at x 56
PANE_HOP_X = 56
PANE_DESC_DY = 20         # first description baseline = hop baseline + 20
PANE_DESC_PITCH = 16
PANE_WRAP_INSET = 52      # wrap descriptions to pane width − 52
PANE_NEXT_HOP = 28        # next hop baseline = last description baseline + 28
PANE_END = 14             # pane bottom = last baseline + 14
PANE_CLIENT_GAP = 16      # client node icon top ≥ pane bottom + 16 (centered on the pane's center x)
PANE_OUTER_GAP = 24       # a top-level group below the pane: its top ≥ pane bottom + 24 (ex bedrock-dx 652 + 24 = 676)

# slide plain lines (QR 183; ex slides gwlb, nfw, tgw)
LINES_BADGE_DX = 10       # badge cx = Cloud.x + 10
LINES_TEXT_DX = 28        # its text at Cloud.x + 28 (= cx + 18), plain 12px #545B64
LINES_FIRST_CY = 18       # preferred first badge cy; reuse top space to fit the whole badge (≥ LINES_END clear)
LINES_TEXT_ONLY_DY = 17   # a text-only line: baseline ≥ Cloud bottom + 17, x = Cloud.x
LINES_ITEM_GAP = 20       # text end (text_width, 0.55 em) → next badge's left edge (ex: next cx = end + 30)
LINES_ROW_PITCH = 24      # a second row of badge items 24 below (DESIGN 4.7)
LINES_TEXT_PITCH = 16     # text-only lines 16 apart
LINES_MAX = 3
LINES_END = 4             # text bottom allowance and minimum legend top clearance; include the whole badge too

# --------------------------------------------------------------------------------------
# Canvas and slide fit (QR 185-192; svg2pptx MARGIN 0.25 in, TITLE_H 0.75 in, 13.333 × 7.5 in)

# The largest canvas on which 12px text (MIN_FONT: the smallest a draft may use, and the
# note's size) comes out at ≥ 10pt; a draft whose smallest text is F px fits F / 12 times it.
SLIDE_MAX_W = 1108                     # QR 190: ≤ 1108 × 540 titled for text ≥ 10pt (slide_pt rounded down)
SLIDE_MAX_H = {True: 540, False: 600}  # titled / untitled (QR 190-191; untitled 604.8 kept at 600)
SLIDE_AVAIL_W_PT = 924                 # (13.333 in − 2 × 0.25 in) × 72
SLIDE_AVAIL_H_PT = {True: 450, False: 504}   # 7.5 in − 2 × 0.25 in (− 0.75 in title) in pt
SLIDE_MIN_PT = 10                      # svg2pptx MIN_PT
SLIDE_FLOOR_PT = 8                     # svg2pptx FLOOR_PT
DOCUMENT_COLUMN_PX = 760              # rules-design §6: body column, never upscale
DOCUMENT_TARGET_PX = 11
DOCUMENT_FLOOR_PX = 9


def effective_text(mode: str, canvas_w: float, canvas_h: float, min_px: float,
                   title: bool = True) -> Tuple[float, str, float, float]:
    """Smallest text as the reader sees it: (size, unit, target, floor).

    Slides use svg2pptx's available 16:9 area; documents/web images shrink to a
    760px body column, retaining their native size when narrower.
    """
    if mode == "slide":
        return slide_pt(canvas_w, canvas_h, title, min_px), "pt", SLIDE_MIN_PT, SLIDE_FLOOR_PT
    if mode == "document":
        return (min_px * min(1, DOCUMENT_COLUMN_PX / canvas_w), "px",
                DOCUMENT_TARGET_PX, DOCUMENT_FLOOR_PX)
    raise ValueError(f"unknown text medium: {mode!r}")


def slide_pt(w: float, h: float, title: bool = True, px: float = MIN_FONT) -> float:
    """Point size px-size text gets when svg2pptx fits a w × h canvas on the slide: its
    Deck.pt(px) = px × k / 12700, k = min(avail w / w, avail h / h) EMU per canvas px."""
    return px * min(SLIDE_AVAIL_W_PT / w, SLIDE_AVAIL_H_PT[bool(title)] / h)


def slide_max(title: bool = True, px: float = MIN_FONT) -> Tuple[int, int]:
    """The largest canvas (w, h) on which px-size text still comes out at ≥ SLIDE_MIN_PT:
    SLIDE_MAX_* (set for 12px text) scaled by px / 12."""
    return (math.floor(SLIDE_MAX_W * px / MIN_FONT), math.floor(SLIDE_MAX_H[bool(title)] * px / MIN_FONT))


def smallest_text(texts: Iterable[Tuple[float, str]]) -> Optional[Tuple[float, str]]:
    """The (font-size, text) of the smallest among the texts a slide draws (the pairs
    check_layout.slide_texts gives, what svg2pptx puts on the slide), or None without any."""
    return min(texts, key=lambda t: t[0], default=None)


def smallest_pt(w: float, h: float, title: bool, texts: Iterable[Tuple[float, str]]
                ) -> Tuple[float, Optional[Tuple[float, str]]]:
    """(pt, smallest) for the smallest text drawn on a w × h slide canvas: the size svg2pptx
    gives it (slide_pt) and its (font-size, text); no text at all is no text too small (inf)."""
    t = smallest_text(texts)
    return (math.inf if t is None else effective_text("slide", w, h, t[0], title)[0]), t


# --------------------------------------------------------------------------------------
# z layers (DESIGN 4.9). Emit order is ascending z; within a layer, the order elements were
# produced in. GROUP holds every group (outer → inner, overlays last; per group rect, badge,
# title, CIDR), NODE every node (mask → icon → label lines).

# Legacy width preference for routing feedback (do not widen past this only for a
# shape miss). Reader-visible text fit is measured separately by effective_text().
DOC_WIDE = 1800

Z_RAW_BELOW = 0
Z_GROUP = 10
Z_NODE = 20
Z_EDGE = 30
Z_EDGE_LABEL = 40
Z_BADGE = 50
Z_NOTE = 60
Z_RAW_ABOVE = 70
Z_LABEL_TOP = 80          # a connector label on its line, over a background rect: on top of everything
Z_ORDER = (Z_RAW_BELOW, Z_GROUP, Z_NODE, Z_EDGE, Z_EDGE_LABEL, Z_BADGE, Z_NOTE, Z_RAW_ABOVE, Z_LABEL_TOP)
# `<g id>` suffix for an owner's elements in a layer other than its home layer
# ("edge:3" lines → "edge:3:label", "edge:3:badge"); see layout_model "Element ids".
Z_PART = {Z_EDGE_LABEL: "label", Z_BADGE: "badge", Z_LABEL_TOP: "masked"}
# The background behind a label set on its line (the canvas color) and its margin round the
# label's conservative glyph box.
LABEL_BG = "#FFFFFF"
LABEL_BG_PAD = 2
