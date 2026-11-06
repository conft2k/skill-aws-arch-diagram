# Quick reference

A new diagram is written as a layout spec ([`layout_spec.md`](layout_spec.md)); the engine applies the numbers below.

Every number and rule needed to draw a diagram, in one place, at the default icon size
S = 48. Each value comes from `diagram_guide.md` (the section is named after the
value, in quotes) and was measured in `docs/examples/`; where the examples differ from the
guide, both are given. Read a guide section only for the reasoning or an edge case.
`check_layout.py` measures all of the clearances below, so place things roughly and let
its `fix:` lines give the exact values.

## Groups

Every group is a square-cornered `<rect>` (no `rx`), `fill="none"`. Its title is in the
border color, 14px bold (`font-weight="600"`); the badge `<image>` sits on the rect's
top-left corner (`x`, `y` of the rect). A very light tint is allowed only behind
subnets, then behind every subnet of both kinds ("Group border colors").

| Group | Border | Width | Dash (`stroke-dasharray`) | Badge `bundle:` ref | Badge |
|---|---|---|---|---|---|
| AWS Cloud | `#232F3E` | 2 | solid | `group/AWS-Cloud-logo_32` (`_Dark` on dark), never `AWS-Cloud_32` | 32 |
| AWS Account | `#E7157B` | 2 | solid | `group/AWS-Account_32` | 24 |
| Region | `#00A4A6` | 2 | `3,3` | `group/Region_32` | 24 |
| Availability Zone | `#00A4A6` | 1.5 | `8,4` | none, label only | — |
| VPC | `#8C4FFF` | 2 | solid | `group/Virtual-private-cloud-VPC_32` | 24 |
| Public subnet | `#7AA116` | 1.5 | solid | `group/Public-subnet_32` | 24 |
| Private subnet | `#00A4A6` | 1.5 | solid | `group/Private-subnet_32` | 24 |
| Security group | `#DD344C` | 1.5 | solid | none, label only | — |
| Auto Scaling group / target group | `#ED7100` | 1.5 | dashed; guide gives no pattern, examples use `6,3` | `group/Auto-Scaling-group_32` | 24 |
| EC2 instance contents, Spot Fleet, Elastic Beanstalk container | `#ED7100` | 1.5 | solid | `group/EC2-instance-contents_32`, `group/Spot-Fleet_32`, none | 24 |
| Corporate data center, Server contents | `#7D8998` | 2 | solid | `group/Corporate-data-center_32`, `group/Server-contents_32` | 24 |
| Generic group | `#7D8998` | 1.5 | dashed or solid (bedrock-dx: `6,4`) | none, label only | — |
| Step Functions workflow | `#E7157B` | 1.5 | solid | none, label only | — |
| Cloud WAN core network | `#8C4FFF` | 2 | dashed | `service/AWS-Cloud-WAN` as the badge | 24 |

Badge size: the guide allows 22–32px, one size per container level; every example uses
32 for the AWS Cloud and 24 for everything else. Subnet color follows the route table:
green only when `0.0.0.0/0 → IGW`, otherwise teal.

## Header geometry ("Fixed header geometry")

| What | Value |
|---|---|
| Title baseline | `box.y + 18`; `x = box.x + 32` with a badge, `box.x + 12` without |
| AWS Cloud title | 15px bold, baseline `Cloud.y + 22`, `x = Cloud.x + 42` |
| CIDR line | same x as the title, baseline `box.y + 34`, 12px regular `#232F3E` (never the group color, never on the title line) |
| Nested box top | `≥ box.y + 30`; `≥ box.y + 46` when the box shows a CIDR |
| Region inside the Cloud | `≥ Cloud.y + 34` (document examples 40, slides 34) |
| First node icon in a subnet | `≥ subnet.y + 28`; `≥ subnet.y + 46` with a CIDR (slides 28; documents 26–56, icon centered in a taller row) |
| ASG / target group box | 8px inside its subnet, and either 8px right of each header label it crosses or 8px below it; its badge and title inside the first subnet it covers |

## Spacing ("Compact, not empty", "Padding between nested containers")

| What | Document | Slide |
|---|---|---|
| Padding, container border ↔ child | 16–24 (examples 16–20) | may shrink to 8 (examples 8–12) |
| Node centers apart | 100–120 (2–2.5 × S); examples 95–120 inside one container, 150–230 with a subnet border between | same |
| Gap between AZ rows (holds the LB, IGW, Users) | ≥ 110 (examples 110–162) | 86 minimum |
| AZ row height, two-AZ slide | — | 144; 152 with an ASG header in the row; +18 when subnets show a CIDR |
| Canvas margin around the drawing | ≤ 24 (examples 16) | hug the content (examples 2–16) |
| Side-by-side Regions or VPC boxes | 24–40 apart | 24–40 |
| Users ↔ AWS Cloud border | ≈ 80 (room for a 12px protocol label) | same |
| On-premises ↔ Cloud border, VPN path (Internet + VPN icons) | 220–280 | same |
| On-premises ↔ Cloud border, Direct Connect icon | 140–180 | same |
| Regional services row above the VPC | ~160 between centers | column beside the VPC, one per AZ row or gap |

Slide vertical budget (titled, 540px): Cloud header 34, Region and VPC headers 30 each
(VPC 46 with a CIDR), AZ rows 144, AZ gap 86, 8px paddings, the note (one legend row
≈ 30, three lines ≈ 60).

Clearances (all enforced by `check_layout.py`; "Clearances at a glance"):

- label ↔ container border 8 (a container's own header label follows the header geometry);
- label ↔ an icon it doesn't label 8 (a header label 6);
- group badge ↔ node icon 8;
- connector ↔ a node or header label 4;
- label ↔ label side by side 4;
- load balancer node ↔ AZ and subnet borders 8;
- IGW/VGW mask ↔ the next container border and the canvas edge 8.

Gaps are measured from the glyph box: baseline − 0.75 × font size to baseline + 0.25 ×
font size.

## Nodes ("One icon size for every node", "Emphasis is the one exception")

- Every node icon is `S = 48` (`<image ... width="48" height="48"/>`): services,
  resources, users, servers. Change S only for the whole diagram (e.g. 40), and keep it
  the same on every slide of a deck.
- Emphasis, only when asked: `E = 64` (≈ 1.33 × S) for those few icons, `x = cx − E/2`
  on the same grid center, label baseline `cy + E/2 + 18`, connectors end `E/2 + 4` from
  the center.
- Node label: 14px `#232F3E`, `text-anchor="middle"` at the icon's center x, baseline
  `icon.y + S + 18` (= `icon.y + 66`; every example).
- Sub-caption: 12px, 16px below the label line (every example), `#545B64` in the
  examples; route captions ("0.0.0.0/0 → TGW") are sub-captions.
- One load balancer (ALB, NLB, GWLB) is one node in the AZ gap, in its tier's column, on
  the main line with Users and the IGW; zonal resources (NAT gateway, GWLBe, instances,
  RDS primary/standby, endpoint ENIs) once per AZ.
- Short labels: "IGW", "VGW", "ALB", "NLB", "GWLB", "GWLBe", "EICE"; subnets by role
  ("Public subnet", "App subnet", "DB subnet").

## IGW and VGW on the VPC border ("Internet gateway and VGW sit on the VPC border")

For a VPC `<rect x=X y=Y width=W height=H>`:

| What | Value |
|---|---|
| Icon x on the left / right edge | `X − S/2` / `X + W − S/2` (= `X − 24` / `X + W − 24`) |
| Icon y on the top / bottom edge | `Y − S/2` / `Y + H − S/2` |
| Edge | the one facing what it connects to (IGW → Internet/Users, VGW → on-premises); IGW and VGW on different edges |
| Label | "IGW" / "VGW", 14px, at the border x (icon center), baseline `icon.y + S + 18` |
| Mask | one `fill="#FFFFFF"` rect drawn before the icon and label: `mask_w = max(S, tw + 8)`, `mask_x = cx − mask_w/2`, `mask_y = icon.y`, `mask_h = S + 24 = 72` (document) or `S + 22 = 70` (slide), +16 per extra label line. Examples: 48 × 72 in documents, 48 × 70 on slides |
| Text width `tw` | ≈ 0.6 × font size per Latin character, 1.0 × per Hangul ("IGW" at 14px ≈ 25 → mask = icon width). `check_layout.py` estimates 0.55 × per Latin character |
| Connectors | outside flow ends at the outer half, inside flow starts at the inner half, both on the icon's center line |

Only the IGW and VGW straddle the border. Gateway endpoints sit inside the VPC outside
the subnets; interface endpoints inside their subnet. A TGW route table drawn as a
table of routes may overlap borders (see the guide).

## Text ("Text size")

| Text | Size | Weight | Color |
|---|---|---|---|
| Node label | 14 | regular | `#232F3E` |
| Container title | 14 | 600 | the group's border color |
| AWS Cloud title | 15 | 600 | `#232F3E` |
| Protocol / port connector label ("HTTPS :443") | 12 | regular | `#232F3E` (examples) |
| Verb or attachment-type label ("아웃바운드", "VPC attachment"), sub-caption, note text | 12 | regular | `#545B64` |
| Legend hop, note row label | 12 | 600 | `#232F3E` |
| Step badge digit | 12 | 700 | `#FFFFFF` |

Never below 12px. Scale with S (≈ 0.3 × S for node labels) if S changes. Allow 16–18px
per label line. First root `font-family` is a Korean font installed on this machine
(`fc-list | grep -iE 'CJK KR|Pretendard'`).

## Connectors ("Layout rules that make it look professional")

- 1.5px `#232F3E` lines, one shared `arrow` marker (`refX="8" refY="3"`), its mirror
  `arrowStart` on the other end only for a genuinely two-way link (GWLBe ⇄ GWLB,
  GWLB ⇄ appliances). Same width for inter-Region links.
- Main path left → right. Return, outbound, DNS and management connectors are dashed;
  the guide gives no pattern, every example uses `stroke-dasharray="5,4"`.
- Topology (TGW hub and spoke, peering mesh): solid lines, no arrowheads, any direction.
- A connector stops 4px from what it meets: at `cx ± (S/2 + 4)` = `cx ± 28` from an
  icon center, 4px before a box border (the skeleton).
- Arrowhead segment ≥ 20 (document ~48). A trunk joining or forking per-AZ lines runs
  ≥ 12 (document ~28) from the boxes it passes.
- Separate lines into one node: enter its side 8px above and below center (10px left and
  right when entering from above or below). The same route from several AZs: one trunk,
  one arrowhead on the center line.
- Where the path leaves and rejoins the main line, break it ≥ 40 apart.
- Connector label: 12px, near the middle of the longest horizontal part between
  container borders, 4–8px above the line — with a step badge on that part, badge left
  and label 6px right of it, both above. Beside a vertical part: right of the line
  (anchor start, line x + 10 document / + 8 slide). No room there: on the line, over a
  `#FFFFFF` rect 2px larger than the text, both last in the file (top layer); below /
  left only after that.
- TGW route table drawn as a table: tie it to its TGW with a `#8C4FFF` 1.5px line,
  `stroke-dasharray="4 3"`, no arrowhead. The TGW example draws its route tables as
  nodes instead, so no example has this line.

## Step badges and legend ("Step legend")

- Badge: `<circle r="10" fill="#232F3E"/>` plus the digit, 12px 700 `#FFFFFF`,
  `text-anchor="middle"`, baseline `cy + 4`. Never ① glyphs.
- On the diagram: on every hop from where the path leaves the main line until it
  rejoins it, badge bottom 4px above the hop's line (`cy = line.y − 14`), at the middle
  of the longest horizontal part; a hop crossing between two containers gets its badge
  in the gap between them.
- Legend item: badge, then the hop 12px 600 `#232F3E` at `x = cx + 18`, baseline
  `cy + 4`, then the description 12px `#545B64`. Left-aligned, steps only. The slide
  examples write each item as one plain 12px `#545B64` text after the badge (no bold
  hop).

## The note ("The note — one place per diagram")

Decide in this order; exactly one place, always outside the AWS Cloud box:

1. **Left legend pane** — the diagram has a step legend and either (document) the drawing
   without the note is taller than 0.7 × its width, or (slide) pane + drawing fit 1108px.
2. **Bottom panel** — every other document note.
3. **Plain lines below the Cloud** — every other slide note. A slide never gets a panel.

| Layout | Values |
|---|---|
| Panel and pane style | square rect, `fill="#F8F9F9"`, `stroke="#D5DBDB"` 1px, no badge, no title |
| Bottom panel | `x = 16`, `width = canvas − 32`, `y = Cloud bottom + 16`, canvas ends 16 below; rows at x 28, badge `cx = 38`, hop x 56; first baseline `panel.y + 26`, rows 24 apart; `height = 26 + 24 × (rows − 1) + 18` (one row 44); description column 16px right of the widest hop (examples 165, 172, 223) |
| Left pane | `x = 16`, `y = Cloud.y`, width 300 (320 if a description would run past four lines; or the width of the left column below it — bedrock-dx 456); Cloud starts at pane right + 24; badge `cx = 38`, first `cy = pane.y + 22`; hop at x 56, baseline `cy + 4`; description from 20 below the hop, 16 pitch, wrapped to width − 52; next hop at last baseline + 28; pane ends 14 below the last baseline; the client node centered on the pane's center x, pane bottom ≥ 16 above its icon |
| Slide plain lines | badge `cx = Cloud.x + 10`, its text at `Cloud.x + 28`, text-only lines at `Cloud.x`; first badge `cy ≥ Cloud bottom + 18` (text-only baseline ≥ bottom + 17); ≤ 3 lines, 16 apart; items flowed in a row, 20px from an item's text end to the next badge, a second row 24 below; canvas ends 3–4 below the last baseline |

## Canvas

| Format | Limit |
|---|---|
| Document SVG/PNG | as large as the content needs (examples 1020 × 850 to 1514 × 1072) |
| Slide with a title | ≤ 1108 × 540 for text ≥ 10pt (examples 1020–1108 × 524–544; the GWLB slide at 544 comes out 9.9pt) |
| Slide without a title | ≤ 1108 × 600 |
| Slide, only when unavoidable | down to 8pt: ≈ 1380 × 675 titled, 1380 × 755 untitled; tell the user |

## Draft subset ("Composing the layout SVG")

`rect`, `image href="bundle:set/name"`, one-line `text`, `line`, `polyline fill="none"`,
`circle`, `g transform="translate(x,y)"`, `defs` + `marker`. Presentation attributes
only (no `style=`, no `class=`), `#RRGGBB` colors, no `<path>` outside markers, no
stroked text: mask with a white rect.
