# AWS Architecture Diagram Guide

How to compose a correct, professional AWS architecture diagram using the bundled
official icons. The numbers for drawing are collected in `quick_reference.md` (read it
first); this guide holds the full rules with their reasons and edge cases. Read the
sections your diagram touches and "Technical correctness"; read all of it for a
diagram kind none of the examples shows. You lay the diagram out as an SVG draft in a
restricted subset (see "Composing the layout SVG"); `export.py` turns that one draft
into a portable SVG, a PNG and/or a slide of native PowerPoint shapes, so every rule
below — coordinates, colors, dash patterns, sizes — carries over to every format.

## The AWS visual grammar

AWS diagrams are not arbitrary boxes and arrows. They follow a nesting convention
that readers recognize instantly. Respect the containment order:

```
AWS Cloud (group)
└── Region (group)
    └── VPC (group)
        └── Availability Zone (group, no icon) — when HA matters
            └── Subnet (public or private, group)
            └── Service icons (EC2, ECS, RDS, ...)
```

Not every diagram needs every layer — a serverless diagram may skip VPC/subnets
entirely. But when you show networking (EC2, ALB, RDS, NAT), draw the containers.
Putting a private-only service (like RDS) outside a subnet box is a red flag to
any AWS reviewer.

### Group containers (borders/backgrounds, from the `group` set)
- **AWS-Cloud-logo_32** — outermost "AWS Cloud" boundary, solid dark border, with the
  AWS logo badge top-left. **Always** use the `-logo` variant; never the logo-less
  plain-cloud `AWS-Cloud_32` / `AWS-Cloud_32_Dark` (find_icon hides them and export.py
  fails on them). On a dark background use `AWS-Cloud-logo_32_Dark`.
- **Region_32** — dashed border.
- **Virtual-private-cloud-VPC_32** — solid purple border, VPC icon top-left.
- **Public-subnet_32** — green border.
- **Private-subnet_32** — teal border (same hue as Region; the solid line and badge tell them apart).
- **Corporate-data-center_32** — for on-prem / hybrid (e.g. EKS Hybrid Nodes, Direct Connect).
- **AWS-Account_32**, **Auto-Scaling-group_32**, **Server-contents_32** — as needed.
- **Availability Zone, Security group, Generic group** — groups with **no badge icon**:
  a labeled rect in the color below, nothing in the corner (`find_icon.py az` says so).

In the layout SVG you draw these as: a **square-cornered** `<rect>` (no `rx`/`ry`) with the
group's signature border color + a small `<image>` of the group icon pinned to the
top-left corner + a text label next to it. The group icon PNGs/SVGs are 32px corner
badges, NOT full frames. The official toolkit draws every group as a plain rectangle;
a rounded border leaves the square badge's corner sticking out past the curve, so
export.py rejects a rounded rect that carries a group badge.

### Group border colors (use these exact hex values)

A container's border and label color is the color of its own group icon. These values
come from the 2026-07-31 Icon package and the "Groups" slide of its PPTx toolkit
(the toolkit is the only source for groups without an icon, such as Availability
Zone). If a newer package changes a group icon, the border follows it
(`grep -o '#[0-9A-F]\{6\}'` on the group SVG tells you).

| Group | Border / label | Style | Badge |
|---|---|---|---|
| AWS Cloud | `#232F3E` (squid ink) | solid 2px | `AWS-Cloud-logo_32` |
| AWS Account | `#E7157B` | solid 2px | `AWS-Account_32` |
| Region | `#00A4A6` (teal) | dashed 2px, short dashes (`stroke-dasharray="3,3"`) | `Region_32` |
| Availability Zone | `#00A4A6` (teal) | dashed 1.5px, long dashes (`stroke-dasharray="8,4"`) | none — label only |
| VPC | `#8C4FFF` (purple) | solid 2px | `Virtual-private-cloud-VPC_32` |
| Public subnet | `#7AA116` (green) | solid 1.5px | `Public-subnet_32` |
| Private subnet | `#00A4A6` (teal) | solid 1.5px | `Private-subnet_32` |
| Security group | `#DD344C` (red) | solid 1.5px | none — label only |
| Auto Scaling group | `#ED7100` (orange) | dashed 1.5px | `Auto-Scaling-group_32` |
| EC2 instance contents, Spot Fleet, Elastic Beanstalk container | `#ED7100` | solid 1.5px | `EC2-instance-contents_32`, `Spot-Fleet_32`, none |
| Corporate data center, Server contents | `#7D8998` (grey) | solid 2px | `Corporate-data-center_32`, `Server-contents_32` |
| Generic group | `#7D8998` (grey) | dashed or solid 1.5px | none — label only |
| Step Functions workflow | `#E7157B` | solid 1.5px | none — label only |

The official toolkit draws every group with **no fill**. A very light tint of the
border color behind subnets is acceptable when it helps readability; if you use one,
apply it to every subnet of both kinds, never to the VPC or Region.

Both subnets and the AZ share the Region's teal in the private case, so the dash
pattern and the badge are what tell them apart: Region short-dashed with its badge,
AZ long-dashed with only a label, private subnet solid with its badge. Don't color the
VPC green — that's the public-subnet color, and it will clash with the purple VPC badge.

## Service icons

All icons live in one bundle, `assets/icons.json` (built from the official AWS package on
first use), organized into sets. Reference them
by `set/name` (see "Finding the right icon"). The relevant sets:

- `service` — service product icons (the primary set).
- `resource` — resource-level icons (`<Service>_<Resource>`, e.g.
  `Amazon-VPC_Internet-Gateway`, `Amazon-EC2_Instance`, `Amazon-DynamoDB_Table`),
  plus the general icons (`Users`, `User`, `Client`, `Internet`, ...). General icons
  default to the light-background variant; append `_Dark` for dark backgrounds.
- `category` — category icons (Compute, Storage...), for legends/agendas.

Load balancers: `alb`, `nlb` and `gwlb` resolve to the typed resource icon
(`resource/Elastic-Load-Balancing_Application-Load-Balancer` etc.); use the generic
`service/Elastic-Load-Balancing` (`elb`) only when the type is unspecified.

### Fully managed multi-AZ services are one node

In a standard reference architecture, a fully managed service that AWS runs across
AZs for you — ALB, NLB, GWLB (and the Auto Scaling group that spans the AZs) — is
drawn **once**, as a single node, not once per AZ. Its per-AZ nodes, ENIs and IPs are
AWS's implementation detail; drawing them makes the reader think they manage
separate load balancers.

- **One icon per load balancer**, placed in the gap between the AZ rows, in the column
  of the tier it serves (public subnets for internet-facing, private for internal), so
  it visibly belongs to every AZ it spans. Keep it clear of the AZ and subnet borders
  (≥8px). Make the gap ≥110px in a document; on a slide 86px is the minimum (the
  70px IGW mask plus 8px above and below), label it with the short type:
  "ALB", "NLB", "GWLB". Put the IGW on the VPC border at the same height so the path
  IGW → load balancer is one straight line. Keep Users and the IGW in that gap in
  every diagram of the set, even when the IGW fans out to per-AZ nodes (e.g. GWLB
  endpoints) — consistent placement matters more than saving a bend.
- **Keep the main nodes on one line; number the steps when the path detours.** If
  the traffic leaves the line and comes back (e.g. IGW → per-AZ GWLBe → GWLB), keep
  Users, the IGW and the load balancer on the same line anyway. Break the line where
  the branches leave and rejoin it (≥40px apart, so it never looks like one direct
  connector), and add numbered step badges — a 10px-radius squid-ink circle with a
  white bold 12px number on **every** hop from where the path leaves the main line until
  it rejoins it (① IGW → GWLBe,
  ② GWLBe → GWLB, ...), its bottom 4px above that hop's own line, at the middle of the
  longest horizontal part of the line between container borders — except a hop whose
  point is crossing between two containers (a TGW peering between Regions), whose
  number sits in the gap between them (a connector's protocol or name
  label goes near the middle of that same part) (a hop drawn inside an AZ row gets its number
  inside that row, above its line — never on another hop's line; hops that share or run side by side through the AZ gap
  get one number between them, and on a slide the "keep it clear of the AZ boxes" rule
  wins over the middle-of-the-line rule); when the hop also has a protocol
  label, the number and the label sit side by side above the line (number left, label
  6px right of it); only when the line is too short for both does the number go below. The legend in the note names exactly the hop
  each number sits on, and draws each number as the same badge (see **Step legend**),
  never as a circled-digit glyph (①). Don't move nodes to separate lanes to avoid the
  ambiguity; the numbers resolve it and the alignment stays consistent across the set.
- **One connector from the load balancer to its targets.** Wrap the targets in one
  Auto Scaling group / target group box that spans the AZs, and point a single arrow
  at that box, instead of one arrow per AZ or per instance. **Exception — fork
  instead of boxing** when the box can't be placed without an empty column: the box
  must start 8px right of every header it crosses (see "ASG and target group boxes"),
  and if that leaves ≥ 48px (one icon) of empty subnet between the subnet's left
  padding and the box in every row it crosses — after shortening the headers per
  "Short container labels" — draw a trunk in the gap between the tier columns (≥ 12px
  from both subnet borders, ~28px in a document) with one arrow (≥ 20px, ~48px in a
  document) into each AZ's target, and name the target group in the step description
  or in a 12px sub-caption under the first target (the nlb-mtls example).
- **Zonal resources stay per AZ**: NAT gateways, subnets, EC2 instances, interface
  endpoint ENIs and RDS primary/standby are drawn in each AZ they live in.
- **Per-AZ nodes only on request**: draw one LB node per AZ only when the diagram is
  about that behavior (static EIP per AZ, cross-zone load balancing, AZ failover) and
  the user asked for it. Say so in the reply.

Each service icon is a self-contained square SVG with the product's colored gradient
tile. Always put a text label directly below the icon (product name), centered, at
the node label size from "Text size" below (14px at S=48).

### One icon size for every node

In a standard architecture diagram every node icon — services and resources (gateways,
endpoints, ALB, users, servers) alike — is drawn at **one size, 48px by default**.
Mixed sizes make some components look more important than others and break the grid.
Pick the size once (`S`) and use it for every `<image>` that represents a component.

- Don't shrink resources such as IGW, NAT gateway or endpoints, and don't enlarge a
  service just because it feels central. Some icons look lighter (outline resource icons vs filled service
  tiles); that is the official artwork — keep the box size the same anyway.
- Exceptions: group/container badges in a container's corner (22–32px, one size per
  container level) and legend or category icons outside the architecture itself.
- If space runs out, enlarge the canvas or shorten labels rather than shrinking a few
  icons. Change `S` for the whole diagram only (e.g. 40px for a dense one).

#### Emphasis is the one exception

Make some icons bigger **only when specific services are meant to stand out** — the
user asked to highlight them, or the diagram's point is that part (e.g. "the new
AgentCore layer", "what changes in this migration"). Then:

- Enlarge only those services, to **one emphasis size `E`, about 1.33 × S**
  (64px when S is 48). Every emphasized icon uses the same `E`; don't grade sizes.
- Keep emphasis rare: a few icons, one group of related services. If most of the
  diagram is "important", nothing is emphasized — keep everything at `S`.
- Keep the icon's center on the grid point it would have at `S` (`x = cx - E/2`), so
  rows and connectors stay aligned; connectors end `E/2 + 4` from the center.
- Shift its label down to `cy + E/2 + 18`, and make it bold if that helps. Don't
  change label size or the icon's colors.
- Never shrink the other icons to make the emphasized ones look bigger.
- Say in the reply which services were emphasized and why.

### VPC networking resources

Gateways and endpoints are resources, not services, so they live in the `resource`
set. Draw every one of them as its icon — never as a text chip, pill or labeled box.

| Thing in the system | Icon | Placement |
|---|---|---|
| Internet gateway | `resource/Amazon-VPC_Internet-Gateway` | on the VPC border; label **"IGW"** (the full name only if the user asks) |
| NAT gateway | `resource/Amazon-VPC_NAT-Gateway` | inside the public subnet |
| Gateway endpoint (S3, DynamoDB) | `resource/Amazon-VPC_Endpoints` | inside the VPC box (outside any subnet — it is a route-table target, not an ENI), near the edge facing the service, on the flow line to it; never on the border |
| Interface endpoint (PrivateLink) | `resource/Amazon-VPC_Endpoints` | inside the subnet that holds its ENIs |
| EC2 Instance Connect Endpoint | `resource/Amazon-VPC_Endpoints` (no dedicated icon) | inside its subnet, labeled "EICE" |
| Gateway Load Balancer endpoint | `resource/Amazon-VPC_Endpoints` (no dedicated icon) | one per AZ in its GWLBe subnet, labeled "GWLBe"; the GWLB itself is one node in the appliance VPC |
| Virtual private gateway (VGW) / customer gateway | `resource/Amazon-VPC_VPN-Gateway` / `_Customer-Gateway` | on the VPC border / on-prem side |
| VPC peering connection / TGW peering attachment | `resource/Amazon-VPC_Peering-Connection` (AWS uses it for both) | on the link between the two VPCs or the two TGWs, the line broken at the icon; across Regions or accounts, in the gap between their boxes (it belongs to neither); label "VPC peering" / "TGW peering" |
| Route table (VPC subnet route table, TGW route table) | `resource/Amazon-Route-53_Route-Table` (the package's only route table icon; filed under Route 53 but used for every route table) | beside what it is associated with (see below): a subnet route table inside the VPC, outside the subnets, right next to the subnet(s) it serves — or only its routes, as that subnet node's sub-caption; a TGW route table beside the attachment lines associated with it where they reach the TGW (a TGW's only table: next to the TGW). The table name as label and the key route as a 12px sub-caption ("10.0.0.0/8 → TGW"); never a text chip |
| Router, NACL, ENI, Flow Logs | `resource/Amazon-VPC_Router`, `_Network-Access-Control-List`, `_Elastic-Network-Interface`, `_Flow-Logs` | as needed |

#### A route table sits beside what it is attached to

A route table means nothing until the reader knows which subnet or attachment uses it.
Put every route table as close as the layout allows to the object it is associated
with, so a reader sees at a glance which resource it belongs to without reading the
legend. Its position is the association: no line ties a route-table node to anything
(only a TGW table drawn as a table of routes keeps its dashed tie to the TGW, below).

- **Subnet route table:** its routes as the 12px sub-caption of the node in that subnet
  (EC2 "0.0.0.0/0 → TGW", TGW ENI "0.0.0.0/0 → 같은 AZ 방화벽" — what the examples do),
  or, drawn as an icon, inside the VPC right next to that subnet's box (a table shared by
  several subnets between them). The IGW edge route table goes inside the VPC beside the
  IGW.
- **TGW route table: beside its associated attachments, not just beside the TGW.** Put
  it where the attachment lines associated with it reach the TGW, on their side of the
  TGW, and keep it out of the reach of attachments it is not associated with. A table
  above or below the TGW, between one table's attachment lines and another's, reads as
  belonging to either — that is the mistake to avoid.
  - **Hub and spoke with centralized inspection** (nfw): the spoke VPCs left of the TGW,
    the inspection VPC right of it. The Spoke RT (associated with the spoke VPC
    attachments, `0.0.0.0/0 → inspection attachment`) goes between the spoke VPCs and
    the TGW, on the TGW's row, inside the bracket the two spoke lines draw into the TGW's
    left side. The Firewall (inspection) RT (associated with the inspection VPC
    attachment, spoke CIDRs propagated) goes between the TGW and the inspection VPC, on
    the TGW's row, inside the bracket the inspection lines draw: they leave the TGW's top
    and bottom (the bottom one below its label) and run across to the TGW ENI in each AZ,
    so they pass around the table, never through it. Each table then sits between the
    TGW and the VPCs whose attachments use it.
  - **Several segments** (prod / dev / shared tables): each table beside its own
    attachments, on the side of the TGW they come in from; group a segment's spokes on
    one side so its table has one place to go.
  - **One table for every attachment** (tgw): next to the TGW, above or below it, clear
    of the attachment lines ("TGW A RT" under Transit Gateway A, inside the fork of its
    lower spokes).
- **Tight slide:** keep each table beside its attachments and win the room elsewhere, in
  this order: move a table's route sub-caption into the step legend, which names the
  table ("Spoke RT 0.0.0.0/0 → 검사 VPC"); put the attachment-type label on the piece
  that has room (the inspection line instead of a spoke); shorten a container label
  (App subnet → Subnet) — never drop the subnet box, which would read as a VPC without
  subnets; then split the slide. Never move a table back onto the TGW's column to save
  width.

#### Internet gateway and VGW sit on the VPC border

An IGW or VGW is the VPC's door, so draw it straddling the VPC rectangle's edge —
half inside, half outside — never fully inside a subnet or floating outside the VPC.
Only these two straddle the border. Everything else that belongs to the VPC, gateway
endpoints included, goes fully inside the VPC box with at least 8px between its label
and the border.

- **Center the icon on the border line.** For a VPC `<rect x=X y=Y width=W height=H>`
  and an icon of size S: on the left edge use `x = X - S/2`, on the right edge
  `x = X + W - S/2`, on the top edge `y = Y - S/2`, on the bottom edge `y = Y + H - S/2`.
  The other coordinate lines it up with the flow it carries.
- **Pick the edge that faces what it connects to.** IGW on the side toward
  Internet/Users; VGW on the side toward the corporate data center / customer gateway.
  When both exist, put them on different edges (or well apart on the same edge) so
  their connectors don't cross.
- **Center the label under the icon**: `text-anchor="middle"` at the icon's center x
  (= the border x on a left/right edge), baseline 18px below the icon's bottom.
  Keep gateway labels short so they fit the mask and don't crowd the border: **"IGW"**
  and **"VGW"** by default; write out "Internet gateway" only when the user asks.
- **Mask the border behind the icon *and* the label with one white rect**, drawn before
  both. The icons have transparent backgrounds, and a centered label sits right on the
  border line, which a text halo does not hide (the line still shows between glyphs).
  Size the rect from the label's width:
  - text width `tw` ≈ `0.6 × font-size` per Latin character, `1.0 × font-size` per
    Hangul character (14px: "IGW" ≈ 25px, so the mask is just the icon width; a
    spelled-out "Internet gateway" ≈ 135px needs a 143px mask);
  - `mask_w = max(S, tw + 8)`, `mask_x = cx - mask_w/2`;
  - `mask_y = icon_y`, `mask_h = S + 24` in a document (icon plus the label line at +18 and its glyph box), `S + 22` on a slide whose 86px AZ gap leaves no more room (the glyph box ends at +21.5, so it is still covered); add 16 per extra line.

  No line may cross the label: besides the VPC border, check that no connector, subnet
  border or other container border passes through the mask area. Move the label
  connector or the icon along the edge until the mask covers only the VPC border, and
  check it in the render.
- **Leave room around the mask.** Keep the next container border (Region, subnet) and
  the canvas edge at least 8px clear of the mask on both sides of the VPC edge.
- **Connectors:** the outside flow (Internet → IGW, customer gateway → VGW) ends at the
  outer half; the inside flow (IGW → public subnet / ALB, VGW → private subnet) starts
  at the inner half, both at the icon's center line, never through the label.

```svg
<!-- VPC: x=60 y=70 width=780 height=480 → right edge at x=840, left edge at x=60 -->
<!-- IGW on the right edge, facing the Internet (S=48 → x = 840 - 24 = 816).
     Label "IGW" at 14px ≈ 25px < S → mask_w = S = 48, mask_x = 816 -->
<rect x="816" y="290" width="48" height="70" fill="#FFFFFF"/>
<image href="bundle:resource/Amazon-VPC_Internet-Gateway" x="816" y="290" width="48" height="48"/>
<text x="840" y="356" font-size="14" text-anchor="middle" fill="#232F3E">IGW</text>
<!-- If the user wants the full name: "Internet gateway" ≈ 135px → mask_w = 143, mask_x = 840 - 71.5 = 768.5 -->
<!-- VGW on the left edge, facing on-prem (x = 60 - 24 = 36); label is narrower than the icon -->
<rect x="36" y="400" width="48" height="70" fill="#FFFFFF"/>
<image href="bundle:resource/Amazon-VPC_VPN-Gateway" x="36" y="400" width="48" height="48"/>
<text x="60" y="466" font-size="14" text-anchor="middle" fill="#232F3E">VGW</text>
```

Render resource icons at the same size `S` as service icons, with a short label
below. When an icon sits on a container border or a connector, break the line at the
icon instead of drawing it underneath, and keep its label off the line: put a white rect
behind the label (as for IGW/VGW above) where a line would cross it. Don't use text
halos (a white-stroked copy of the text): PowerPoint text boxes have no stroke, so
export.py rejects stroked text — the white mask rect is the only way to keep a line
off a label.

**A service with an official icon is never just text.** If a connector would carry
the name of an AWS service or resource — "Site-to-Site VPN", "Direct Connect",
"PrivateLink", "VPC peering" — and `find_icon.py` finds its icon, put that icon on the
path as a node (with its label below, the same size `S` as every node) and keep only
the protocol on the connector ("IPsec", "GENEVE :6081"). Place it where the reader
expects it on the path: a Site-to-Site VPN is the link between on-premises and AWS, so
its icon sits **outside the AWS Cloud box**, between the Internet icon and the Cloud
border (see below). Don't add a duplicate when
another node already is that service (a GWLBe is the PrivateLink endpoint). A TGW
peering is drawn the way the AWS docs draw it: the peering connection icon
(`resource/Amazon-VPC_Peering-Connection`) on the TGW–TGW line, labeled "TGW peering".
Only a connection with no icon in the bundle stays a connector label.

**Show what a hybrid connection runs over.** A Site-to-Site VPN is IPsec over the
public Internet, so its path is customer gateway → `resource/Internet` →
`service/AWS-Site-to-Site-VPN` → TGW/VGW, with the Internet and VPN icons both
**outside the AWS Cloud box**, between the on-premises group and the Cloud border, and
"IPsec" on the Internet → VPN segment. Leave 220–280px between the on-premises group and
the Cloud border for those two hops (enough for both icons, their labels and the
"IPsec" label with 8px around each), and pull the Cloud and Region borders in so they
hug their contents rather than leaving the space empty inside. A Direct
Connect path is private and never passes the Internet icon: customer router →
`service/AWS-Direct-Connect` — the DX location, a colocation facility that is **not in
AWS**, so the icon sits **outside the AWS Cloud box**, between the on-premises group and
the Cloud border, with "private VIF" (or "transit VIF") as its sub-caption → the Direct
Connect gateway, which is an AWS resource: inside the AWS Cloud, outside every Region (a
global resource), on the same line → VGW / TGW. Leave 140–180px between the on-premises
group and the Cloud border for the DX icon and its label. check_layout.py reports
OUTSIDE CLOUD for a DX, Internet or VPN icon drawn inside the Cloud. When both exist, draw them as two separate paths so the difference is
visible.

**Never invent or hand-draw a service icon.** If a service isn't in the bundle,
use the closest category icon or a plain labeled rounded rect — don't approximate the
official mark.

## Bedrock and AgentCore

Bedrock is `service/Amazon-Bedrock`; the AgentCore service as a whole is
`service/Amazon-Bedrock-AgentCore`. AgentCore *components* (Runtime, Gateway, Memory,
Identity, Code Interpreter, Browser, Observability, Policy) have no official icon in
the package yet. Draw them with the no-icon rule: a plain labeled rounded rect in a
neutral color, or one `service/Amazon-Bedrock-AgentCore` tile per component with the
component name as the label. Don't invent component marks. Re-check the package when
a new release lands — once a `Res_Amazon-Bedrock-AgentCore_*` resource icon appears,
`build_bundle.py` picks it up automatically.

## Finding the right icon

Do not guess names — they're specific (`Amazon-EC2`, `AWS-Lambda`, `Amazon-API-Gateway`,
`Amazon-Simple-Storage-Service`, `Amazon-VPC_Internet-Gateway`). Run (`<skill-dir>` is the
skill's directory, `${CLAUDE_SKILL_DIR}` in SKILL.md):

```bash
python3 <skill-dir>/scripts/find_icon.py "s3" "step functions" "cloudfront"
```

It prints ranked `set/name` references. List a whole set with
`python3 <skill-dir>/scripts/find_icon.py --list service`.

## Composing the layout SVG

The SVG is a layout draft, not the deliverable: `scripts/export.py` checks it and writes
the formats asked for — a portable SVG with every icon inlined, a PNG, and/or a slide of
native PowerPoint shapes. Reference each icon with the `bundle:` href scheme; the export
looks it up in the bundle (inlined as base64 in the SVG, an SVG picture on the slide):

```
<image href="bundle:service/AWS-Lambda" x="200" y="200" width="48" height="48"/>
```

Use the same subset whatever the format, so one draft serves them all — the export checks
it even when only an SVG or PNG is wanted:

| SVG | PowerPoint |
|---|---|
| `<rect>` (`fill`, `stroke`, `stroke-width`, `stroke-dasharray`, `rx` for no-icon boxes only) | rectangle / rounded rectangle; the dash pattern is kept exactly |
| `<image href="bundle:set/name">` (or an inlined `data:` URI) | picture with the official SVG icon and a PNG fallback |
| `<text>` (`font-size`, `font-weight`, `fill`, `text-anchor`), one line each | text box, no wrap, same anchor |
| `<line>`, `<polyline fill="none">` with `marker-start` / `marker-end` | straight connector / open freeform with triangle arrowheads |
| `<circle>` | oval (step badges, junction dots) |
| `<g transform="translate(x,y)">` | offset applied to its children |
| `<defs>`, `<marker>` | read for the arrowheads only |

No `<path>` outside markers, no other transforms (scale, rotate), no CSS classes or
`style=""`, no stroked text. Colors as `#RRGGBB`. The full-canvas white background rect
is dropped (the slide is white). One draft is one slide; the export scales it to fit a
16:9 slide, so the canvas size decides the slide's text size (see "Text size").

### Skeleton

Copy this as the starting point; it follows the nesting order, compact 16–24px
container padding, 14px labels, one icon size, AZs as rows and tiers as columns, one
ALB node in the gap between the AZ rows, the IGW-on-the-border rule, and one arrow to
a target group spanning the AZs with a zonal EC2 instance in each (it is
`docs/example.svg`, exported with inlined icons; copy it as a draft the way SKILL.md's
draft path copies an example, or start from `docs/examples/specs/example.layout.yaml`). Grow containers only as far as their contents need.

```svg
<svg viewBox="0 0 670 594" xmlns="http://www.w3.org/2000/svg" font-family="'Noto Sans CJK KR', 'Pretendard', Arial, sans-serif">
  <!-- one arrowhead marker, reused by every connector; arrowStart is its mirror for
       two-way links (marker-start), since cairosvg ignores orient="auto-start-reverse" -->
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6 Z" fill="#232F3E"/>
    </marker>
    <marker id="arrowStart" markerWidth="10" markerHeight="10" refX="0" refY="3" orient="auto">
      <path d="M8,0 L0,3 L8,6 Z" fill="#232F3E"/>
    </marker>
  </defs>
  <rect width="670" height="594" fill="#FFFFFF"/>

  <!-- AWS Cloud boundary -->
  <rect x="16" y="16" width="638" height="562" fill="none" stroke="#232F3E" stroke-width="2"/>
  <image href="bundle:group/AWS-Cloud-logo_32" x="16" y="16" width="32" height="32"/>
  <text x="58" y="38" font-size="15" fill="#232F3E" font-weight="600">AWS Cloud</text>

  <!-- Region: 20px inside the Cloud, below its header -->
  <rect x="36" y="56" width="598" height="502" fill="none" stroke="#00A4A6" stroke-width="2" stroke-dasharray="3,3"/>
  <image href="bundle:group/Region_32" x="36" y="56" width="24" height="24"/>
  <text x="68" y="74" font-size="14" fill="#00A4A6" font-weight="600">Region ap-northeast-2</text>

  <!-- VPC: left edge at x=96 leaves room for the IGW mask (72–120) inside the Region -->
  <rect x="96" y="88" width="518" height="450" fill="none" stroke="#8C4FFF" stroke-width="2"/>
  <image href="bundle:group/Virtual-private-cloud-VPC_32" x="96" y="88" width="24" height="24"/>
  <text x="128" y="106" font-size="14" fill="#8C4FFF" font-weight="600">VPC</text>
  <text x="128" y="122" font-size="12" fill="#232F3E">10.0.0.0/16</text>

  <!-- AZs as rows (label only, long dashes); the 86px gap between them (288–374) — the slide minimum; a document uses ≥110 — holds
       the main line y=320: IGW → ALB → target group -->
  <rect x="106" y="134" width="498" height="154" fill="none" stroke="#00A4A6" stroke-width="1.5" stroke-dasharray="8,4"/>
  <text x="118" y="152" font-size="14" fill="#00A4A6" font-weight="600">Availability Zone 1</text>
  <rect x="106" y="374" width="498" height="154" fill="none" stroke="#00A4A6" stroke-width="1.5" stroke-dasharray="8,4"/>
  <text x="118" y="392" font-size="14" fill="#00A4A6" font-weight="600">Availability Zone 2</text>

  <!-- tiers as columns: public subnet (118–264) → app subnet (276–592), one of each per AZ.
       The public subnets hold the ALB's per-AZ nodes, which are not drawn: the ALB is one node. -->
  <rect x="118" y="164" width="146" height="116" fill="none" stroke="#7AA116" stroke-width="1.5"/>
  <image href="bundle:group/Public-subnet_32" x="118" y="164" width="24" height="24"/>
  <text x="150" y="182" font-size="14" fill="#7AA116" font-weight="600">Public subnet</text>
  <rect x="276" y="164" width="316" height="116" fill="none" stroke="#00A4A6" stroke-width="1.5"/>
  <image href="bundle:group/Private-subnet_32" x="276" y="164" width="24" height="24"/>
  <text x="308" y="182" font-size="14" fill="#00A4A6" font-weight="600">App subnet</text>

  <rect x="118" y="404" width="146" height="116" fill="none" stroke="#7AA116" stroke-width="1.5"/>
  <image href="bundle:group/Public-subnet_32" x="118" y="404" width="24" height="24"/>
  <text x="150" y="422" font-size="14" fill="#7AA116" font-weight="600">Public subnet</text>
  <rect x="276" y="404" width="316" height="116" fill="none" stroke="#00A4A6" stroke-width="1.5"/>
  <image href="bundle:group/Private-subnet_32" x="276" y="404" width="24" height="24"/>
  <text x="308" y="422" font-size="14" fill="#00A4A6" font-weight="600">App subnet</text>

  <!-- one Auto Scaling group / target group spanning both AZs, 8px inside the app subnets and
       right of their headers (so its border crosses no header); zonal EC2 instances stay per AZ -->
  <rect x="400" y="172" width="184" height="340" fill="none" stroke="#ED7100" stroke-width="1.5" stroke-dasharray="6,3"/>
  <image href="bundle:group/Auto-Scaling-group_32" x="400" y="172" width="24" height="24"/>
  <text x="432" y="190" font-size="14" fill="#ED7100" font-weight="600">ASG · target group</text>

  <!-- nodes: every node icon uses the same S=48; 14px labels, baseline 18px below the icon (icon.y + 66) -->
  <image href="bundle:service/Amazon-EC2" x="468" y="202" width="48" height="48"/>
  <text x="492" y="268" font-size="14" text-anchor="middle" fill="#232F3E">EC2</text>
  <image href="bundle:service/Amazon-EC2" x="468" y="434" width="48" height="48"/>
  <text x="492" y="500" font-size="14" text-anchor="middle" fill="#232F3E">EC2</text>

  <!-- one ALB (a managed multi-AZ service), in the gap between the AZ rows, in the public column -->
  <image href="bundle:resource/Elastic-Load-Balancing_Application-Load-Balancer" x="167" y="296" width="48" height="48"/>
  <text x="191" y="362" font-size="14" text-anchor="middle" fill="#232F3E">ALB</text>

  <!-- Internet gateway centered on the VPC left border (96 - 48/2 = 72), on the main line.
       Label "IGW" (≈ 25px) is narrower than the icon → mask_w = 48, mask_h = S + 24 = 72 (70 on a slide),
       8px clear of both AZ rows and 36px clear of the Region border at x=36. -->
  <rect x="72" y="296" width="48" height="72" fill="#FFFFFF"/>
  <image href="bundle:resource/Amazon-VPC_Internet-Gateway" x="72" y="296" width="48" height="48"/>
  <text x="96" y="362" font-size="14" text-anchor="middle" fill="#232F3E">IGW</text>

  <!-- connectors on the main line, all pointing right; the first starts at the IGW's inner half,
       the second ends at the target group box (one arrow to the group, not one per instance) -->
  <line x1="124" y1="320" x2="163" y2="320" stroke="#232F3E" stroke-width="1.5" marker-end="url(#arrow)"/>
  <line x1="219" y1="320" x2="396" y2="320" stroke="#232F3E" stroke-width="1.5" marker-end="url(#arrow)"/>
</svg>
```

## Layout rules that make it look professional

- **Traffic flows left to right.** When the diagram shows how traffic moves (requests,
  packets, data), lay it out so the flow reads left → right: users/clients/on-prem on
  the left (an on-premises group goes on the left; only when it cannot, at the bottom —
  never on the right or on top, even when larger text forces a vertical layout),
  entry points (Route 53, CloudFront, IGW, VGW) next, then load balancers,
  compute, and data stores on the right. Every main-path arrow points right; only
  return, outbound (e.g. to a NAT gateway) or control/management connectors may go
  another way, and those are dashed. To make that work in a VPC, put the **tiers in
  columns** (public subnet → private subnet → data subnet) and the **AZs in rows**;
  the IGW then sits on the VPC's left border. Use top-to-bottom only for diagrams that
  aren't about traffic (account/org structure, a deployment pipeline) or when the user
  asks for it.
- **Align icons on a grid.** Same y for a horizontal tier, same x for a vertical tier.
  Even spacing. Misaligned icons look amateurish.
- **Label everything.** Every icon gets a product-name label. Every connector that
  isn't obvious gets a verb/protocol label ("HTTPS", "invoke", "read/write").
- **No filler text.** Never write a caption into an empty container to make it look
  used ("NLB 노드 (대상 없음)", "reserved"). An empty public subnet is accurate when
  nothing of its own lives there; narrow the column instead.
- **Compact, not empty.** Size every container to what it holds: 16–24px between a
  container's border and its children (the header row — badge + label — takes 30px, 46px with a CIDR line under the title,
  at the top), and node centers about 2–2.5 × S apart (100–120px at S=48). Don't leave
  empty quadrants or a subnet much larger than its contents; shrink the box or the
  canvas instead. The diagram should fill its canvas with ≤24px outer margin. Only the
  rules that need room get it: ≥8px around an IGW/VGW mask, ≥8px between labels and
  borders, and a gap between AZ rows tall enough for a load balancer and its label.
- **Text size.** Labels must stay readable when the diagram is scaled down into a doc
  or slide. At S=48: node labels **14px**, container labels **14px bold** (AWS Cloud
  15px), connector and secondary labels (protocol, sub-captions, notes) **12px**.
  Never go below 12px. Scale the sizes with `S` (≈ 0.3 × S for node labels) if you
  change it, and give each label line 16–18px of height when you compute spacing.
  On the slide the px sizes become points through the fit-to-slide scale, so the
  canvas size decides the result: every label must come out at **≥ 10pt** (a titled
  canvas of at most 1108 × 540), and only when that is unavoidable down to **8pt**
  (~1380 × 675), never smaller. Tighten or split the diagram before going under 10pt.
- **Color discipline.** Icons carry their own colors; keep containers, text, and
  connectors in the AWS neutrals (squid ink `#232F3E`, group border colors above).
  Don't add rainbow connectors.
- **One arrowhead style, one stroke width** (1.5px) for all connectors, inter-Region
  links included: a TGW peering is marked by its icon and label, a Cloud WAN backbone by
  its "AWS 백본" label, not by a thicker line (the AWS docs draw every line alike). A
  genuinely two-way link
  (GWLBe ⇄ GWLB, GWLB ⇄ appliances over GENEVE, TGW ⇄ an inspection attachment) gets
  the mirrored `arrowStart` marker on its other end; ordinary request/response flows
  stay one-way.
- **Topology diagrams may drop the arrowheads.** A diagram that shows what is attached
  to what rather than how traffic flows (TGW hub and spoke, VPC peering mesh) draws its
  attachment lines solid, without arrowheads, in any direction; the left → right and
  "other directions are dashed" rules apply to traffic-flow diagrams only.
- **A reference topology shows its connections and one flow — on the same lines.** In a
  TGW / peering diagram the attachment lines are the only lines; never draw a second,
  parallel "data flow" line next to them. Make the connections explicit and the flow
  visible with what the grammar already has:
  - **Label each attachment type once** with a 12px `#545B64` connector label on one of
    its lines — "VPC attachment" on one spoke, "VPN attachment" on the VPN line (below
    it when a step badge sits above). A peering attachment is named by the peering
    connection icon's sub-caption ("peering attachment"): as a connector label
    check_layout.py reads it as the peering service written as text.
  - **Draw each TGW route table as a node** (`resource/Amazon-Route-53_Route-Table`,
    "TGW A RT", "Spoke RT") beside the attachments associated with it (see "A route
    table sits beside what it is attached to"; a TGW's only table next to the TGW), with
    no line — its place says which attachments use it — and its propagations and static
    routes as 12px sub-captions ("VPC·VPN 경로 전파", "10.16.0.0/13 → peering").
  - **A TGW route table drawn as a table of routes may overlap containers** — an
    exception to the nesting convention (and to "only the IGW and VGW straddle a
    border"). Put it as close to the attachments associated with it (a TGW's only
    table: to the TGW) as the layout allows, even across a Region, AWS Cloud or VPC border, drawn last
    (on top) on a white background rectangle that hides the borders beneath it. It must
    still never cover an icon, a connector, a step badge or a label. Use this to keep
    the table beside its attachments instead of stretching containers to make room for it.
    Tie it to its TGW with a short purple dashed line (`#8C4FFF`, the TGW icon color,
    1.5px, `stroke-dasharray="4 3"`, no arrowhead), straight or with one bend, crossing
    nothing, so the reader sees at once which TGW the table belongs to.
  - **Show one representative flow** — the path that crosses the most attachment types
    (e.g. on-premises → a VPC in the remote Region) — as step badges on the attachment
    lines it uses, explained in the step legend with the route that sends it each way
    and the return path. One flow, not every pair: the route-table nodes cover the rest.
- **Several connectors into one node: separate when they are separate things, one
  trunk when they are the same route.** When each line is its own attachment, ENI or
  endpoint (spoke VPCs → TGW, GWLBe ⇄ GWLB per AZ), give each its own arrowhead, entering
  the node's side 8px above and below its center (10px left and right of center when
  they come in from above or below; topology lines without arrowheads too). When every
  line is the same route to the same target (each AZ's NAT gateway → the IGW), join them
  in a corridor outside the AZ boxes and enter the node as one line with one arrowhead
  on its center line — two arrowheads a few px apart only add noise. **Size the
  corridor for the trunk and the arrow:** the trunk runs ≥ 12px (document: ~28px)
  from the AZ boxes it passes, and the arrow from the trunk to the node is ≥ 20px
  (document: ~48px) so it has a visible shaft — a head sitting right at the junction
  looks like a glitch. When the node sits on a container border (the IGW on the VPC's
  right edge), widen that container — and everything right of it — rather than
  squeezing the trunk; on a slide keep the 1108px canvas width, since a wider canvas
  shrinks the text under 10pt. check_layout.py reports SHORT ARROW and LINE HUGS
  BORDER for these.
- **Outbound through a NAT gateway** is the dashed private-node → NAT gateway hop; the
  NAT gateway → IGW hop may be left implied when the IGW is already on the diagram
  for inbound traffic. Draw it when egress is the point of the diagram (centralized
  egress, inspection).
- **Regional services row.** Services that live in the Region but outside the VPC
  (ACM, AWS WAF for an ALB/API Gateway, CloudWatch, S3 for logs) go in one row inside
  the Region, above the VPC, on an even grid (~160px apart), each with its name and a
  12px sub-caption saying what it does here ("HTTPS 리스너 인증서", "ALB 액세스 로그").
  Draw a connector only for what is on the traffic path; a service attached to a
  resource (AWS WAF on an ALB, ACM on a listener) gets its caption, not a connector.
- **Global services sit outside the Region.** Route 53, CloudFront, AWS Global
  Accelerator, IAM and AWS WAF for CloudFront are global: put them inside the AWS Cloud
  box but outside every Region box, in a narrow strip to the left of the Region (the
  side the users are on), at the height of the request they serve (Route 53: where the
  users' dashed DNS lookup reaches it, any height that keeps that line short); the rest of that
  strip staying empty is expected, not an "empty area". Never put them in the regional
  services row. The DNS lookup from the users to Route 53 stays a dashed connector.
- **Regional services on a slide.** When a row above the VPC doesn't fit the slide's
  height, stack the regional services in a column beside the VPC (inside the Region),
  one per slot — a slot is an AZ row or the gap between rows — on the same grid; with
  more services than slots, use two columns. A slot may stay empty. Keep the node size S the same on every slide of a deck — fit the slide by
  re-arranging, not by shrinking the icons.
- **Database hops** carry the engine and port when known ("MySQL :3306",
  "PostgreSQL :5432"), otherwise "SQL".
- **Subnet color follows the route table.** A subnet is a public subnet (green) only if
  its route table sends traffic straight to an IGW (0.0.0.0/0 → IGW): NAT gateway,
  GWLBe and internet-facing load balancer subnets. A subnet whose default route goes to
  a GWLBe, a firewall endpoint, a NAT gateway or a TGW is private (teal), even when its
  instances have public IPs.
- **Write routes in full CIDR form** — "0.0.0.0/0", "10.0.0.0/8", "10.1.0.0/16" — the
  same way everywhere; add "같은 AZ" when the target is per-AZ.
- **ASG and target group boxes inside a subnet** keep 8px from the subnet's borders
  and 8px between their own border and every label inside; start the box to the right
  of the subnet's header label, or below it.
- **Short container labels.** Name subnets by role — "Public subnet", "App subnet",
  "DB subnet", "GWLBe subnet", "Appliance subnet" — not "Private subnet (App)": a long
  header runs into the badge or border of a box that spans it (an ASG, a replication
  line), and the badge color already says public or private.
- **Room outside the AWS Cloud.** Users/clients sit outside the AWS Cloud box; leave
  enough space between them and the Cloud border (≈80px at 12px) for the connector's
  protocol label to sit clear of the Cloud and Region borders.
- **The note — one place per diagram.** Everything that explains the drawing without
  being a node label or caption — the step legend, a one-line summary, routes that
  don't fit as sub-captions — is the note. It is 12px text (`#545B64`; hops and row
  labels bold `#232F3E`), sits outside the AWS Cloud box, and goes in exactly one of
  three places, decided in this order:
  1. **Left legend pane** — when the diagram has a step legend and either (document)
     the drawing without its note is taller than 0.7 × its width, or (slide) the pane
     plus the drawing fit in the 1108px slide width. The pane makes the figure
     landscape, which suits slides.
  2. **Bottom note panel** — every other document note.
  3. **Plain lines below the Cloud** — every other slide note. A slide never gets a
     bottom panel.
  Never two of them in one diagram, and never a note inside a container.
- **Bottom note panel.** A square rect, `x = 16`, `width = canvas width − 32`,
  `fill="#F8F9F9"`, `stroke="#D5DBDB"` 1px, with no badge and no header label (it must
  not read as an AWS group); its top is the AWS Cloud's bottom border + 16 (or the
  lowest element's), and the canvas ends 16px below it. Rows start at x = 28: first
  baseline at panel.y + 26, 24px apart, panel height = 26 + 24 × (rows − 1) + 18 (one
  row: 44). Three row kinds, never mixed in one panel: step rows (see **Step legend**);
  label rows — a bold 12px `#232F3E` label at x = 28 and a 12px `#545B64` text column
  starting at one x for every row, 16px right of the widest label (the TGW example);
  or one plain 12px `#545B64` summary row when there is a single line to say (the NLB
  and ALB examples).
- **Left legend pane.** Same style as the panel. `x = 16`, `y` = the AWS Cloud's y,
  width 300 (320 only if a description would otherwise exceed four lines) — or, when
  the left column below it is wider (an on-premises group plus a Direct Connect
  column), that column's width, so no empty column opens beside the pane; the
  AWS Cloud starts at the pane's right edge + 24; the client/Users node is centered on
  the pane's center x, on the main line, and the pane's bottom stays ≥ 16px above its
  icon. Inside the pane: first badge `cy = pane.y + 22` (`cx = 38`), the hop in bold at
  x = 56, baseline cy + 4; the description in 12px `#545B64` at x = 56 from 20px below
  the hop, 16px line pitch, wrapped to pane width − 52; the next hop's baseline is the
  last description baseline + 28; the pane ends 14px below the last baseline. Only
  step rows go in the pane. Regional services move to a column right of the VPC (one
  per AZ row and one on the main line) so the drawing stays short. Reference layout:
  `docs/examples/nlb-mtls-reference-architecture.svg`.
- **Plain lines on a slide.** Left-aligned with the **AWS Cloud box's left edge** (badge
  `cx = cloud.x + 10`, its text at `cloud.x + 28`, text-only lines at `cloud.x`) — the
  same x on every slide, even when Users or an on-premises box sit left of the Cloud.
  The first line's badge top is ≥ 8px below the Cloud's bottom border (badge
  `cy ≥ bottom + 18`, baseline cy + 4; a text-only first line: baseline ≥ bottom + 17).
  At most three 12px lines, 16px apart; a flowed legend row counts as one line. The
  canvas ends 3–4px below the last baseline and must stay ≤ 540 with every label
  ≥ 10pt — the Region's bottom padding may shrink to 8px to make room; if it still
  doesn't fit, drop the route line (the document version's step descriptions carry the
  routes) before shrinking anything. A qualifier shared by several routes may be said
  once ("방화벽 · NAT 경로는 같은 AZ").
- **Step legend.** A diagram with step badges explains them in the note with the
  **same badge** the diagram uses — a 10px-radius squid-ink `#232F3E` circle with the
  white bold 12px number (baseline cy + 4) — never a circled-digit glyph (①) or a bare
  "1.". Each item is the badge, then the hop in bold 12px `#232F3E`
  (`font-weight="600"`, e.g. "TGW ENI → 방화벽") starting 8px right of the badge
  (`x = cx + 18`, baseline cy + 4), then the description in 12px `#545B64`. Everything
  is left-aligned; never center the legend.
  - **Document (panel or pane):** one step per row, in step order; in a panel the
    description is a column starting at one x for every row (16px right of the widest
    hop), in a pane it wraps under the hop. A document has room, so the description
    explains the step instead of repeating the hop — one or two sentences: what sends
    the traffic there (the route table and entry, with the diagram's CIDRs), what the
    service does at that hop (inspects, translates, encapsulates, load-balances), and
    the return path or the exception where it matters ("VPC 간 트래픽은 ... TGW로
    돌아갑니다"). Use the diagram's own names. The descriptions carry the routes, so a
    document has no separate "라우팅: ..." line and never repeats a route.
  - **Steps only.** Don't append unnumbered rows (server certificate, security group
    rules, routes, test inputs) below the steps — mixing numbered and unnumbered rows
    reads as one confusing list. Put each such fact where it belongs: on the diagram
    as a node caption or container header, or in the document that embeds the diagram
    (the README, the test plan). If it is already in either place, drop it. A target
    group or ASG that the drawing doesn't box is named inside a step's description.
  - **Slide:** items stay short — the hop and at most a few words ("같은 AZ 방화벽에서
    검사"); the speaker or the document carries the rest. Flow the items in one row,
    20px between an item's text end (as check_layout.py estimates it) and the next
    badge's edge; when the row would run past the
    canvas, continue on a second row 24px below at the same left edge rather than
    shrinking the text.

  ```svg
  <!-- step rows in a bottom panel (panel x=16): rows start at x=28, badge cx=38, bold hop at x=56,
       one description column (x=172 here = 56 + widest hop + 16) -->
  <circle cx="38" cy="660" r="10" fill="#232F3E"/><text x="38" y="664" font-size="12" font-weight="700" text-anchor="middle" fill="#FFFFFF">1</text>
  <text x="56" y="664" font-size="12" font-weight="600" fill="#232F3E">IGW → GWLBe</text><text x="172" y="664" font-size="12" fill="#545B64">IGW 엣지 RT가 App 서브넷 CIDR을 같은 AZ의 GWLBe로 보내, 들어오는 트래픽이 EC2보다 먼저 검사 경로로 갑니다.</text>
  <circle cx="38" cy="684" r="10" fill="#232F3E"/><text x="38" y="688" font-size="12" font-weight="700" text-anchor="middle" fill="#FFFFFF">2</text>
  <text x="56" y="688" font-size="12" font-weight="600" fill="#232F3E">GWLBe ⇄ GWLB</text><text x="172" y="688" font-size="12" fill="#545B64">GWLBe는 PrivateLink로 GWLB에 연결된 엔드포인트로, 받은 패킷을 바꾸지 않고 넘깁니다.</text>
  ```
- **A container's CIDR goes on its own line right under the title.** The title stays
  the name ("VPC mtls-beta-vpc", "Private subnet"); the CIDR is the next line, same x,
  baseline 16px lower, 12px regular in squid ink `#232F3E` (not the container color).
  Nested boxes and the first node icon then start at container.y + 46 instead of + 30 /
  + 28 (see **Fixed header geometry**). Never move the CIDR into the box's body or
  onto the title line. Show a CIDR only where "When routes must be shown" asks for it.
  check_layout.py reports CIDR IN TITLE, CIDR OFF HEADER and CIDR COLOR.

  ```svg
  <text x="312" y="86" font-size="14" fill="#8C4FFF" font-weight="600">VPC</text>
  <text x="312" y="102" font-size="12" fill="#232F3E">10.0.0.0/16</text>
  ```
- **When routes must be shown.** A diagram whose point is the routing — inspection
  (Network Firewall, GWLB), centralized egress, ingress routing, TGW / peering between
  VPCs or Regions — lists every route its flows need (sub-captions, a document's step
  descriptions, or a slide's route line). Other
  diagrams may leave routes out. When routes are shown, every VPC (and on-premises
  network) carries its CIDR — on the line under its container title, or as a 12px sub-caption under a
  single-icon VPC node or the customer gateway — and the routes use those CIDRs, not
  placeholders like "app subnet CIDR". A route to a subnet CIDR names the subnet in
  parentheses: "10.0.1.0/24 (AZ1 App) → GWLBe". TGW propagation captions ("VPC A · B
  전파") name attachments and need no CIDR.
- **How gaps are measured.** Every "N px between a label and X" rule is measured from
  the label's glyph box — baseline − 0.75 × font size to baseline + 0.25 × font size —
  the same box check_layout.py uses.
- **Clearances at a glance:** label ↔ container border 8px (a container's own header
  label follows the fixed header geometry instead, 7.5px below its top border);
  label ↔ an icon it doesn't label 8px; group badge ↔ node icon 8px; connector ↔ a
  node or header label 4px; label ↔ label side by side 4px. check_layout.py enforces
  all of them.
- **Connector labels** (protocol, name) sit near the middle of the longest horizontal
  part of their line between container borders, 4–8px **above** it — also when a step
  number is on that part (side by side). On a vertical part the label goes to the
  **right** of the line (`text-anchor="start"`, x = line + 8–10). When the preferred side
  has no room (widen it first if you can), the second best is the label **on the line**:
  centered on it (baseline = line y + 3 on a horizontal part), with a rect in the
  background color (`#FFFFFF`) 2px larger than the text right behind it, both drawn last
  in the file so they sit on top of every line and box; the line shows on both sides of
  the label. The other side (below / left) is the last resort.
- **Fixed header geometry.** A container's header label sits at baseline container.y +
  18 (x + 32 with a badge, x + 12 without); any box nested inside starts at container.y
  + 30 or lower (VPC → AZ, AZ → subnet) — **+ 46 when the container shows its CIDR**
  (the CIDR line at y + 34 needs 8px under it). The AWS Cloud's 15px label sits at
  baseline Cloud.y + 22 (x + 42), so the Region starts at Cloud.y + 34 or lower. The
  first node icon inside a subnet starts at subnet.y + 28 or lower (6px under the
  header label) — + 46 when the subnet shows its CIDR. check_layout.py reports TITLE
  OFFSET and HEADER CLEARANCE.
- **Side-by-side Regions** (or VPCs drawn as boxes) sit 24–40px apart.
- **Slide vertical budget.** On a titled slide (540px) a two-AZ diagram fits with: Cloud
  header 34, Region / VPC headers 30 each (VPC 46 when it shows its CIDR), AZ rows of
  144 (AZ header 30 + a 106px subnet: icon at +28, 48px icon, label baseline 18 below
  it, 8px under the label — + 8px padding; ≈152 when an ASG header sits in the row,
  +18 when the subnets show their CIDR), an 86px AZ gap, 8px paddings and the note
  (one legend row ≈ 30, three lines ≈ 60). When split connectors (±8) and a step badge
  share the gap and there is no room beyond the 86px minimum, keep the badge
  horizontally clear of the AZ boxes instead. Budget these before placing nodes; if
  they don't add up, drop the route line, then split the diagram — never shrink icons
  or fonts.
- **Padding between nested containers:** 16–24px in a document; on a slide it may
  shrink to 8px to fit the 540px height. One draft shared by the document
  and the slide follows the slide values. Wider gaps are expected
  where something sits in them: the IGW/VGW mask on a VPC border, the global-services
  strip, a regional-services row or column, a connector and its label, or the width a
  container's header label needs. Two labels side by side keep at least 4px apart. A canvas hugs its contents even on a slide
  — "close to 16:8" is a target, not a reason to leave empty space.
- **An ASG / target group spanning AZ rows** crosses the AZ and subnet borders by
  design; put its badge and label inside the first subnet it covers, either to the
  right of that subnet's header label (8px clear of it, any height) or 8px below it,
  and 8px clear of every icon.
- **Symbol legend** (line styles, junction dots) only if the diagram has non-obvious
  symbols; it is one label row of the note. A step legend is covered above.

## Font

Put a Korean-capable family **that is installed on the machine doing the render** first
in the draft's root `font-family`. It is the font of the SVG deliverable and of the PNG,
and `check_layout.py` estimates widths from it. Browsers fall back per glyph, but
cairosvg (used for the PNG) uses only the first family, with no fallback when it is
missing: with Arial or an uninstalled font first, every Hangul label silently
disappears from the render. Check before choosing:

```bash
fc-list | grep -iE 'CJK KR|Pretendard'
```

- Noto Sans CJK KR installed → `font-family="'Noto Sans CJK KR', 'Pretendard', Arial, sans-serif"`
- Only Pretendard installed → `font-family="'Pretendard', 'Noto Sans CJK KR', Arial, sans-serif"`
- Neither → tell the user the PNG will drop Hangul, or keep labels in English.

The slide's fonts are set by the PowerPoint export, not by the `font-family`: Latin text
in **Arial** and Korean in **Malgun Gothic (맑은 고딕)** by default, which ship with
Windows and Microsoft Office. Override with `--font` / `--ea-font` when the deck uses
another typeface (AWS Korean decks often use Pretendard: `--ea-font Pretendard`), and
tell the user the font has to be installed where the deck is opened — PowerPoint
substitutes a missing font. The slide preview (`--preview`) picks an installed Korean
font by itself.

Korean labels are fine and common for FSI customer diagrams. Real fonts are a little
wider or narrower than the estimate, so slide text boxes get slack on both sides and
never wrap; keep ≥8px between a label and the nearest border, as the layout rules say.

## Technical correctness

A diagram that looks right but would not work as drawn is wrong. Before delivering,
check every hop and caption against how the services actually behave:

- **Label each hop with the protocol on that hop.** A load balancer that terminates
  TLS changes the protocol: the client hop is "HTTPS :443" / "TLS :443", and the target
  hop shows the target group protocol — plaintext on a plaintext port for offload
  ("HTTP :80", "TCP :8080"), or "HTTPS :443" / "TLS :443" for re-encryption. Never put a
  plaintext protocol on a TLS port ("TCP :443") after termination; a TCP listener
  (pass-through) carries "TCP :443" on both hops and needs no certificate.
- **Gateway Load Balancer.** GWLBe → GWLB runs over PrivateLink (the GWLBe node already
  says so; no protocol label). GENEVE (UDP 6081) is only between the GWLB and its
  appliances, so "GENEVE :6081" goes on that hop and nowhere else. In the distributed
  model the IGW's edge route table sends inbound traffic to the GWLBe in the same AZ.
- **Routes in both directions.** A route sub-caption must include every route the drawn
  flows need, return traffic included, or the reader builds a broken network. For a
  centralized inspection VPC behind a TGW (AWS Network Firewall or GWLB):
  spoke subnets `0.0.0.0/0 → TGW`; spoke TGW route table (associated with the spoke
  attachments) `0.0.0.0/0 → inspection attachment`; inspection (firewall) TGW route
  table (associated with the inspection attachment): spoke CIDRs propagated; TGW subnet
  `0.0.0.0/0 → firewall endpoint (same AZ)`; firewall subnet `0.0.0.0/0 → NAT`, `10.0.0.0/8 → TGW`;
  NAT (public) subnet `0.0.0.0/0 → IGW` **and** `10.0.0.0/8 → firewall endpoint (same AZ)`;
  appliance mode on the inspection VPC attachment. For distributed GWLB inspection of
  inbound traffic: IGW edge route table `<app subnet CIDR> → GWLBe (same AZ)` (one route
  per AZ, with the real CIDRs); app subnet
  `0.0.0.0/0 → GWLBe (same AZ)`; GWLBe subnet `0.0.0.0/0 → IGW`. When the routes don't
  fit as sub-captions, list them in the note.
- **TGW hub and spoke / peering routes:** VPC subnets `<all other VPCs' and
  on-premises CIDRs> → TGW` (or 0.0.0.0/0 → TGW); VPC and VPN (BGP) attachments
  propagate into the TGW route table; across a TGW peering only static routes work —
  each TGW needs `<remote Region CIDRs> → peering`, and the remote TGW needs
  `<on-premises CIDR> → peering` for on-premises ↔ remote-Region traffic.
- **TGW attachments are lines.** A VPC, VPN or peering attachment is the connector
  between the TGW and what it attaches (a peering attachment also carries the peering
  connection icon on its line, as above); `resource/AWS-Transit-Gateway_Attachment` is
  only for the attachment's ENIs drawn inside their subnets ("TGW ENI"). A VPC drawn as
  a single node uses `service/Amazon-Virtual-Private-Cloud`.
- **Credit each mechanism with what it does.** TGW appliance mode keeps both directions
  of a flow on the same AZ's attachment ENI; the per-AZ steering to the firewall is done
  by the subnet routes. A NAT gateway translates source addresses, it doesn't inspect.
- **Use AWS terms only in their AWS meaning.** "Shared VPC" is a VPC shared through
  AWS RAM; a VPC that hosts common services is a "Shared services VPC" (or "Services
  VPC"). Likewise "Transit VPC" is the legacy appliance-based hub, not a TGW.
- **Identical hops look identical.** The same hop repeated per AZ (IGW → GWLBe,
  GWLB ⇄ GWLBe) gets the same arrow ends, label and dash style in every AZ; when the
  per-AZ lines join into one trunk (NAT → IGW), they share its single arrowhead.
- **Captions say what the service does here, accurately.** Health checks are done by
  the load balancer (or Route 53 health checks), not CloudWatch — CloudWatch is
  "지표 · 경보" / "로그". An NLB access log needs a TLS listener; RDS Multi-AZ standby
  replicates synchronously and serves no reads; TGW peering is static-routed.
- **Global vs regional placement.** See "Global services sit outside the Region".

## Common diagram types & which layers to draw

- **3-tier web app**: AWS Cloud > Region > VPC > public subnet (ALB) + private subnets
  (ECS/EC2, RDS). Show AZ split if HA matters, with one ALB across the AZs (see
  "Fully managed multi-AZ services are one node").
- **Serverless**: skip VPC. API Gateway > Lambda > DynamoDB, with S3/CloudFront front.
- **Container (EKS/ECS)**: VPC > subnets > cluster; show ALB, node groups, ECR.
- **Hybrid (EKS Hybrid Nodes, Direct Connect)**: Corporate-data-center group on one side,
  AWS Cloud on the other, connected via Direct Connect / VPN / Transit Gateway icon.
- **Global network (AWS Cloud WAN)**: Regions as columns. The **core network is a
  container** that holds everything that belongs to it — the segments and the core
  network edges: a purple `#8C4FFF` dashed 2px band across every Region, with the
  `service/AWS-Cloud-WAN` icon as its 24px corner badge and the label "Core network"
  (no group icon exists for it; keep the label short so the Region borders don't cross
  it). Inside it, top to bottom: one segment row, the edge row on the main line (one
  `resource/AWS-Cloud-WAN_Core-Network-Edge` per Region, joined by an "AWS 백본"
  line), another segment row. Each segment row is a grey dashed box across every
  Region, led by a `resource/AWS-Cloud-WAN_Segment-Network` icon with the segment
  name. **VPCs stay outside the core network** (above and below it, in their Region
  column); each attachment is one plain line from the VPC through its segment row to
  its Region's edge, with a 5px grey junction dot where it crosses that row to mark
  the segment membership (explain the dot in the note).
- **Agentic AI (AgentCore)**: `service/Amazon-Bedrock` for the models,
  `service/Amazon-Bedrock-AgentCore` for the agent platform (see "Bedrock and
  AgentCore" for components), and standard icons for the surrounding infra.
