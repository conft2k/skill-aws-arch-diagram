# Layout spec reference

A spec (`<name>.layout.yaml`) declares *what* the diagram holds and *which track* each
thing sits on; Trellis, the layout engine (`scripts/layout.py`), computes every coordinate and writes a draft that
already passes `check_layout.py`. You write tracks, nesting and edges — never a pixel.
Start from the closest `docs/examples/specs/*.layout.yaml` (every one regenerates its
example; `docs/examples/specs/slides/` for a slide) and change it. The guide's rules still decide the content (which icons, which
groups, left → right tiers, technical correctness); this file covers only how to say it.

The smallest complete spec is the skeleton, `docs/examples/specs/example.layout.yaml`:

```yaml
# full: example.layout.yaml
name: example
mode: document
cols: [igw, pub, app]
rows: [az1, main, az2]

groups:
  - {id: cloud,  type: cloud}
  - {id: region, type: region, label: Region ap-northeast-2, in: cloud}
  - {id: vpc,    type: vpc, label: VPC, cidr: 10.0.0.0/16, in: region}
  - {id: az,     type: az, in: vpc, per: [az1, az2]}
  - {id: pubsn,  type: public, label: Public subnet, in: az, span: {cols: [pub, pub]}}
  - {id: appsn,  type: private, label: App subnet, in: az}
  - {id: asg,    type: asg, label: ASG · target group, over: [ec2.*], header: right}

nodes:
  - {id: ec2, icon: service/Amazon-EC2, label: EC2, in: appsn, col: app}
  - {id: alb, icon: resource/Elastic-Load-Balancing_Application-Load-Balancer, label: ALB, in: vpc, at: [pub, main]}
  - {id: igw, icon: resource/Amazon-VPC_Internet-Gateway, label: IGW, on: vpc, at: [igw, main]}

edges:
  - {e: "igw -> alb"}
  - {e: "alb -> asg"}
```

## Top level

| Key | Meaning |
|---|---|
| `name` | output stem (`<name>.draft.svg`); defaults to the file stem |
| `mode` | `document` (default) or `slide` (slide spacing; reports the slide pt size) |
| `title` | slide only: `true` (default) = a title band, canvas limit 1108 × 540; `false` = 1108 × 600 |
| `S` | node icon size, default 48 — leave it |
| `font` | root font-family; leave it out (the default puts an installed Korean font first) |
| `text_scale` | `auto` (default), `off`, or a positive numeric font multiplier (e.g. `1.4`); see below |
| `cols` / `rows` | the tracks, left → right / top → bottom |
| `groups`, `nodes`, `edges`, `note`, `raw` | below |

Ids match `[A-Za-z0-9_-]+`; node and group ids share one namespace; track ids are unique
across cols and rows (a node may share its track's name, `igw` above).

**Tracks.** A track is a grid line: a node's icon center sits on one column and one row,
and the engine spaces the tracks by what lies between them. Name columns after tiers
(`users, igw, pub, app, db`) and, for two AZs, use rows `[az1, main, az2]`: `main` is the
gap row between the AZs where Users, the IGW and the load balancer sit. Stacked AZ boxes
get the full AZ gap only when a node of their VPC (or one on its border) sits on a row
between them; with nothing between, they are just siblings (16px apart). A box and a node
(or two boxes) of one parent on different columns *and* different rows — diagonal, like a
route table at `[tgw, a1]` above-left of a VPC that starts on `a2` — sit beside each other
when the solved columns already keep them apart, when below each other the node would
be stacked between two boxes of one column outside the lines they draw past it (a box
above its row and one below, both on one side of its column, each drawing a line to
something on the node's other side: a Spoke RT in the spoke column between VPC A and
VPC B, on the far side of their lines to the TGW, instead of beside them — always beside,
not weighed, wherever its center, label or `dx` falls and on whichever side the spokes
are; this can widen the drawing, and a slide with a long table label may then come out
under 10pt — shorten the label or move its route into `note.steps`), or when keeping
them apart below each other would push the drawing down a sibling gap or more and beside
each other widens it no more than that + a sibling gap: their columns already order
them, so the node never pushes the box's rows (and every other box on those rows) down,
and the box only stays no higher than the node; a box on one side only (a route table
above a lone VPC) or boxes drawing no line past the node are weighed so. A pair below
each other for less (an IGW on the AZ gap row beside the AZ boxes, a GWLB on its VPC's AZ
gap row: the AZs' lines end at it), and two diagonal nodes, separate on the axis whose
tracks are farther apart (equal: on y). The weighing counts a px of width and a px of
height alike; when that leaves a slide under 10pt with a pair below each other, the
engine lays it out again with every such pair beside each other and keeps whichever gives
the larger text (a 1108 × 540 slide has half as much room down as across). No empty
column is needed to keep a route table beside the spoke VPCs or a VPC beside the TGW, on
a document or a slide, titled or not (slides/nfw, centralized-egress). An item is a name
or `{id, min_gap_before: px, min_w: px, flow: px, align: top|center|bottom}`.
`min_gap_before` is the least distance from the previous track's center to this one's. Two columns whose nodes share no row may
land on the same x (only their order is kept) — a column outside the AZ boxes next to
one inside them (an endpoint on the gap row beside a cache column): give the later one
`min_gap_before`. `flow: 160` makes a *flow row*: its nodes give `row:` only and are laid
out in list order at that pitch, centered in their parent (the regional services row).
On a column, `flow: 110` makes a *flow column*: its nodes give `col:` only and are stacked
top → bottom in list order, each icon center that pitch below the one above it (or the
label stack above it + the stack gap, whichever is larger), one stack per parent,
centered in the parent's height (`align: top` / `bottom` pins it there; a top-level stack
aligns in the height of the rest of the drawing; `--explain` prints a `y flow` line per
node). As far as every constraint allows: an `xy` node tied to a stack node's y and an
overlay over stack members only move with it; anything else below it stops it.
A flow column makes no rows, so the nodes beside a VPC stay off its AZ rows and never push
it down (alb slide: the services beside the VPC; Route 53 at the top of the Cloud).
What else shares the column in the same parent — a node pinned with `at: [flowcol, row]`,
a box whose columns cover it (a template node on that column inside the VPC), a box of
stack nodes — is kept off the stack on y: above it when the middle of its rows lies in
the upper part of the parent's rows (above the middle; an odd middle row counts below),
else below; with `align: top` everything goes below the stack, with `bottom` above it.
A flow row in the same parent has no column, so once x is solved each of its nodes that
comes within the sibling gap of the stack's x is kept off it on y, as a node pinned on that
row — except at the parent's edge: a flow row on the parent's first row stays above a
top-aligned stack and one on its last row below a bottom-aligned stack, so the stack stops
at the row (the parent grows by at most the overlap) instead of pushing the row a stack
height inward (a services row on the region's last row stays under the VPC, a
bottom-aligned stack beside the VPC ends above it). Such a row node keeps twice the column's
own spacing from the stack (at least that spacing + the sibling gap), so it never reads as
the column's next node.
A box holding only flow-column nodes (a `Monitoring` group of them) takes its height from
them and is aligned in its parent like its first column.
`flow: true` takes the mode's pitch (160). A flow-column node takes no `dy` (the stack
sets its y). An edge into one picks its shape as if the node sat between rows, never on
one: above the parent's first row (`align: top`), below its last (`bottom`), at the
parent's middle (center) — so EC2 → a centered CloudWatch beside the VPC bends (HVH)
instead of a planned H (alb slide `users ..> r53`: VH, up out of Users); give `shape:`
for another. Two nodes of one column join with a straight V.

## groups

`{id, type, label?, cidr?, in?, per?, only?, over?, span?, pad?, pad_top?, pad_left?, pad_right?, pad_bottom?, min_w?, min_h?, dash?, header?}`

| `type` | Default title | | `type` | Default title |
|---|---|---|---|---|
| `cloud` | AWS Cloud | | `asg` | Auto Scaling group (overlay, `over:`) |
| `account` | AWS Account | | `ec2contents`, `spotfleet`, `beanstalk` | none |
| `region` | Region | | `onprem` | On-premises |
| `az` | Availability Zone {n} | | `server` | none |
| `vpc` | VPC | | `generic` | none (`dash` allowed, e.g. `"6,4"`) |
| `public` / `private` | Public subnet / Private subnet | | `sfn` | none |
| `sg` | Security group | | `cloudwan` | none (phase 2: dash is a guess) |

The type fixes border color, width, dash, badge and header insets (quick reference
"Groups"); you never write them.

- `in`: parent group. Omitted = top level, outside the AWS Cloud (on-premises boxes).
- `label`: the title; `cidr`: drawn as its own 12px line under the title.
- `per: [az1, az2]`: a template — the group and everything inside it is copied once per
  row, ids get `.1`, `.2`, `{n}` in text becomes the instance number. Any field but `id,
  type, in, per, only, over, span, header, on` may differ per instance: `cidr: {1: 10.0.0.0/24,
  2: 10.0.1.0/24}`. Nodes inside give `col:` only (the row is the instance's). One
  template level only. In a document the instances come out alike (same top and bottom
  insets); on a slide each hugs its own content (an ASG header deepens only AZ 1's top).
- **Twins**: containers of one structure anywhere in the drawing are drawn the same shape —
  two App VPCs, the TGW subnet of each, the AZ boxes of two VPCs, two subnets in different
  AZs. One structure = the same group type tree, the same titles (a VPC's, Account's or
  Region's own title may differ; an AZ's own title may differ by its identifier only, the
  first number or letter after AZ / Zone (`AZ 1`, `AZ: 1`, `AZ-1`) or a region name's zone
  letter when that comes first: AZ 1 / AZ 2, Availability Zone A / C (Seoul),
  ap-northeast-2a / 2c, but not (IPv4) / (IPv6) or (DR: us-east-1a) / (DR: us-east-1b)), CIDR line or not, the same node icons with the same
  number of caption lines, the same overlays (`over:`, an Auto Scaling group) with the
  same title and `header` over the same nodes, on the same pattern of rows and columns
  (counted within each twin, so twins on other tracks qualify). An overlay that reaches
  into a box from outside (an ASG across a VPC's AZs) counts by the part inside it: the
  nodes it covers there, which of its edges lie inside, and whether the box holds its
  first member row (its header) or its last, its leftmost member subnets or its rightmost
  — so AZ 1 of two VPCs, each with its own ASG across its AZs, twin, while AZ 1 and AZ 2
  of one VPC under one ASG do not, whether the AZs are hand-written or template instances.
  Twins get the same width and height, and every box, overlay, track and node inside them
  the same offset from their top-left corner (in a VPC: the same AZ spacing), each at the largest any twin needs (an ASG the
  wider one) — sizes and offsets, never positions, so they stay on their own tracks.
  Template instances keep their own rule above: an instance twins only with boxes of its
  own instance number. When other constraints keep twins apart (a requirement, tracks
  they share with each other's content), the solve keeps the closest it found and warns
  `same structure as … but drawn N px unlike it`. Same title with other nodes, a node with
  a sub-caption where the other has none, or an ASG over one VPC's EC2s (or reaching into
  one VPC's AZ) but not the other's: not twins.
  Rows are drawn in the order `rows:` lists them; the engine never reorders them. Boxes of
  one structure whose rows come in another order (AZ 1 Public above Appliance subnet, AZ 2
  Appliance above Public) read as two structures: the checker reports `rule: R-twin TWR`
  with the row order to write in its `try:` (AZ 2's rows `b2, b1`, like AZ 1's `a1, a2`);
  an overlay wholly inside the boxes (a security group over one AZ's firewall) moves with
  its rows. When the boxes share rows (AZs side by side), it says which rows' content to
  move instead: change those nodes' `at` rows, not the order of `rows:`.
- `only: [1]` (or `only: 2`) on a group or node inside a template draws it in those
  instances only: the Aurora writer in AZ 1, a reader in AZ 2, a subnet one AZ lacks. A
  group's `only` leaves out everything inside it. `a.* -> b.*` then pairs the shared
  numbers; with none shared, name the instances (`writer.1 ..> reader.2`). Per-instance
  maps need values only for the kept instances.
- `over: [ec2a.*, ec2b.*]`: an overlay drawn around its member nodes, outside the
  containment tree (no `in`) — `asg` for an Auto Scaling group / target group, any other
  type (`generic` with a `dash`) for a box with no group icon, such as an ECS service. `header: right` (default) or `below`
  says where its title goes relative to the subnet titles it crosses. A title no wider than
  an icon (`ASG`) puts the first member row right of the badge and title, at the subnet's
  own icon inset (gwlb); a longer one (`ASG · target group`) sits above the members and
  pushes their row down (alb, nlb). The short title goes beside only when the first member
  row is its subnet's first; over a member lower in its subnet (another node above it) or in
  no box, it sits above the member like a long one. Over subnets stacked on rows (AZs on
  rows) it stays 8 inside each; over subnets side by side (an ASG across AZ columns `aza |
  azb`) its left edge stays in the leftmost ones and its right edge in the rightmost,
  crossing the AZ borders between, and its title goes below the subnet titles whatever
  `header` says (level with them its top would cross the next AZ's subnet title; a given
  `header: right` then warns). Side by side is judged by the AZs: a subnet on a lower row
  of AZ a with nothing beside it in AZ b still keeps only the left edge (an L-shaped ASG
  over AZ a's App and Worker subnets and AZ b's App subnet). Its box
  covers every row and column its members are on, so a node on those tracks that is not a
  member is rejected (an ASG over EC2s at `[c1, r1]` and `[c2, r2]` would also hold ones
  at `[c1, r2]` / `[c2, r1]`; a colspan node counts when its span meets those columns):
  list it in `over:`, move it, or split the overlay.
  Members in nested containers (one member's group holds another's: an EC2 in a subnet
  of the VPC and CloudWatch in the Region outside it) stay one box when that box can be
  drawn, stretching across the borders between (an EC2 in a subnet, one beside the subnet
  in its VPC and one in the next VPC, stacked on rows). When it cannot — the solve finds it
  contradictory, or the box would hold a node that is not a member — the overlay is drawn
  as several boxes with the same title and style, none crossing a group border: the members
  in the innermost containers (none holding another member's), then the next ones out; a
  level whose box would hold a member of another level, by container; one box per member
  where that still would. The box with the first member listed keeps the id, the others
  are `<id>.2`, `<id>.3`, and a warning names two members and the border between them.
  An edge to the overlay's id goes to the box on the other end's side: the one sharing its
  innermost container, then the one fewer borders away (`acm ..> og` goes to the box
  around CloudWatch beside ACM, `alb -> og` to the one in the VPC); between two split
  overlays the pair of boxes is chosen together the same way (the EC2's and the NAT's in
  one AZ). When pairs are as near, it takes the one whose members sort first and warns;
  point the edge at a member node to pick another. For one box, list in `over:` only
  members on one side of the border, or move them into one group.
- A group covers the tracks of what it contains. `span: {cols: [pub, pub], rows: [a, b]}`
  stretches it over tracks with no node of its own (an empty public subnet); the spanned
  track centers keep `pad` (or the node padding) from the border, `pad_left` / `pad_right` /
  `pad_bottom` on those sides.
- `pad`, `pad_top`, `pad_left`, `pad_right`, `pad_bottom`, `min_w`, `min_h` (px): extra room — `pad_top`
  sets the box top → first icon distance (bedrock-dx 88: a bus above the endpoints);
  `pad_left` / `pad_right` replace `pad` on one side only (room for a label right of a
  vertical line near the border, without widening the other side); `pad_bottom` replaces `pad` at the bottom only
  (child box → border; a node keeps at least 12 from its last baseline, so it only grows
  the room below a label) — gwlb slide `pad_bottom: 6` on the outer boxes saves height
  without narrowing their sides; `min_h` grows the box down.

## nodes

`{id, icon, label, sub?, in? | on?, at? | col? | row? | xy?, dx?, dy?, for?, via?}`

- `icon`: the full `set/name` ref that `find_icon.py` printed. A bare alias is accepted
  only when it has exactly one score-95 hit (`ec2` works; `alb`, `igw` score 85 and fail,
  and the error lists the candidates) — write full refs.
- `label` (required, 14px); `sub`: a string or a list of 12px grey lines under it.
  In a template, `label: {1: RDS Primary, 2: RDS Standby}`.
- Position: `at: [col, row]`; `at: [b1..b2, main]` centers between two columns (a colspan
  node, tgw `tgwb`; its labels take room from that center, so a wide route table under two
  spokes needs no column of its own); `col:` alone inside a `per` template or on a flow column;
  `row:` alone on a flow row (`at: [col, flowrow]` pins one node of that row to a grid column:
  alb Route 53; `at: [flowcol, row]` pins one to a grid row).
- `in: <group>` for containment; leave it out for things outside AWS (Users, Internet,
  Client) — the loader rejects Internet, Direct Connect and Site-to-Site VPN in the Cloud.
- `on: <vpc>` puts an IGW or VGW on that VPC's border: its column left of the VPC's
  columns → left border, right of them → right border. Only left/right borders, and not
  inside a template.
- A load balancer or Network Firewall goes in the VPC on the gap row, `in: vpc, at: [pub,
  main]`, never inside the AZ template (the loader warns: it would be drawn once per AZ).
- `for: [ids]` (+ `via: <node>`): what a route table is associated with — give it on every
  route-table node (`resource/Amazon-Route-53_Route-Table`; the loader warns without it).
  For a TGW table list the far ends of its associated attachments' lines, node or group ids,
  `<id>.*` for a template's instances: nfw `rtsp` `for: [vpca, vpcb]`, `rtfw` `for:
  [eni.*]`. The loader takes as the hub the one node with a line (either direction, any
  operator) to every listed id — the TGW. For a subnet table list the subnet boxes
  (`public` / `private` groups): when every id is one, there is no hub, even if lines reach
  the subnets (bedrock-dx's VGW bus to `sn.*`); a VPC or other box still gets one. No such
  node, or several, is a spec error; `via: <node>` then names the hub, which must have a
  line to each id, and `via: none` declares that the table has none (`none` is never read
  as a node id there). Several is common for a table of one attachment: every node with a
  line to that end is a candidate (tgw `for: [vpn]` finds TGW A and the Internet), so such
  a table usually needs `via:`; the error lists the candidates, Transit Gateways first.
  It is the association, not propagation: a TGW's only table lists every attachment of
  that TGW (tgw `rta` `for: [vpn, svcs, prod, dev, test, peer]`). In a template, a bare id
  of an item of the same template in `for` or `via` means the node's own instance, and
  either takes a per-instance map (`for: {1: [eni.1], 2: [eni.2]}`); an error is reported
  for the first failing instance only. The key moves nothing
  (the draft is byte-identical with or without it); it records the association so a rule
  checker can verify the table sits beside it. `for` on a node that is no route table (a
  per-attachment table with another icon) is accepted, without a warning.
- Two nodes on one row are spaced by what sits level: icon by icon and label line by label
  line, so a route table's long last route line under a VPC's two-line label takes no room
  between them (tgw `rta` beside `dev`). Don't push such a pair apart with `xy` or
  `min_gap_before`.
- `dx` / `dy`: offset from the track position (the engine still keeps clearances
  around it). `xy: [cx, cy]`: the icon center — last resort. Each value is a number
  (absolute px) or an expression the solve keeps: `xy: ["col.a2", "row.bot+10"]` follows the
  tracks wherever they land; `<node>.(x0|cx|x1)` / `.(y0|cy|y1)` (icon edges / center) and
  `<group>.(x0|x1)` / `.(y0|y1)` (box edges) work too, each `±n` — not a group's `cx`, a
  `.label.` or `gap()`, nor a chain of `xy` references that comes back to the node on
  the same axis (`q` on `s.cx`, `s` on `q.cy` is fine). An `xy` node never pushes its row
  neighbours apart (they don't see it), except on a `col.` / `row.` track no grid node sits
  on: that track gets the room of a node on it instead of folding onto the next one
  (`xy: [col.c, …]` with nothing else on c). An `xy` center its boxes, its label room or the
  canvas margin cannot hold is not refused: the solve moves it, on that axis, to the
  nearest center they allow (rounded up to a whole px) and warns with the old and new
  value and what it keeps — `nodes[8] kms kms: xy y 30 moved 10 px down to 40 to keep
  canvas margin 16; …` (template instances moved unalike: each, and the farthest to
  write). A box edge with `in:` that box means its inner edge: `in: cloud, xy:
  [cloud.x0, row.r]` lands the pad + half the node's footprint (icon or label, the wider)
  right of the border (a node across a border is `on: <vpc>`, IGW / VGW only). A sibling
  the moved node — or an xy following it (`t: [q.cx, …]`) — then lands on (closer than the
  grid's gap on both axes) is kept apart from it on the axis it moved along, in the order
  their centers have there — a box counted with its border nodes, so a node moved off the
  Cloud's right edge goes right of a VPC and its IGW alike (a tie: the sibling gives way —
  `p` goes right of `q`, the Cloud below KMS); if that order contradicts the drawing the
  other order, then the other axis is tried. That is warned too; writing the moved value yourself then also
  needs that sibling moved, as the warning says. Only a cycle no `xy` is part of is still
  refused. In a `per` template,
  another item of the template named by its own id means the same instance's
  (`xy: [col.b, e1.cy]` puts each `e2.n` level with `e1.n`) and `row.<a per row>` means the
  instance's own row; an explicit instance (`e1.1.cx`) stays as written, on x only — another
  instance's y sits a row away. For the same reason a template node drawn in two or more
  instances can't take one y for all of them on `xy[1]`: a number, a node or box outside
  the template, or a row not in its `per` is rejected; follow an item of the template or
  `row.<per row>`, or keep the node in one instance (`only: [n]`).

## edges

`{e: "a OP b", label?, verb?, step? | steps?, step_each?, step_at?, label_at?, trunk?, shape?, bend_x?, bend_y?, from_side?, to_side?, from_offset?, to_offset?, points?}`

| OP | Line | OP | Line |
|---|---|---|---|
| `->` | solid arrow | `..>` | dashed arrow (return, outbound, management) |
| `<->` | solid, both heads | `<..>` | dashed, both heads |
| `--` | solid, no heads (topology) | `..` | dashed, no heads |

- Ends: a node, an instance (`rds.1`), a group (the line stops 4px off its border:
  `alb -> asg`, nfw `vpca <-> tgw`), or a pattern `x.*` (every instance). The right side may
  list several: `"a -> b, c"`.
- Pairing: `a.* -> b.*` pairs equal numbers; `a.* -> b` is many-to-one; `a -> b.*`
  one-to-many. Each pair is its own line, each labelled — unless `trunk: true`, which
  merges many-to-one into one stem (nfw `nat.* -> igw`) or forks one-to-many from one
  stem (gwlb `igw -> gwlbe.*`; into group boxes, nlb-mtls `nlb -> besg.*`), label and
  badge drawn once. Whatever shape its lines take, a trunk's shared end leaves (enters)
  one port: two VH from a source whose facing side is taken run down one stem
  (serverless `sfn -> reserve.*`), with no `from_offset: 0`. A branch always reaches the
  stem: when the first instance has to take another shape (an HV into the TGW's bottom),
  the others are drawn onto its line where they meet it (or, failing that, whole with
  their own arrowheads); check_layout flags a line end left on nothing (LOOSE END). Lines that are not a trunk
  never share a run: when the instances' bends would put their legs on top of each other
  (the target past every source on one side — `ec2.* ..> cw` with CloudWatch in a
  bottom-aligned flow column — or one source to targets all on one side), each instance
  gets its own lane, 12px apart and ordered so they don't cross, and the gutter grows by
  12 per extra lane. A line drawn in another shape than its rule's (a detour `UHVH` /
  `UVHV` back into a node, or an alternative) never lands on the port another line uses on
  that side: it takes its own, 12px past theirs toward its other end (alb → ec2.2 coming
  back into EC2's right side, where `ec2.2 ..> cw` leaves) or past them on the far side,
  whichever keeps its leg off the lines already drawn from there, and a detour onto such
  a side is drawn only when no other shape is clean; nor does it land on a port another
  fallback already drawn there took (two lines that both fall back to a VH out of one
  node's bottom leave 12px apart, not as one stem). A fallback that would cross a line out
  of the same node, or lie on one line with another flow's piece, comes after the other
  clean shapes, level with a detour; one with no port of its own left on the side (a
  fourth line onto a 48px side) is drawn only as the last resort and warned about
  (`no room for a port of its own`). Two different lines on one run are a `LINE ON LINE`
  problem — an arrow into a node's port and the next flow out of that same port included,
  and two edges out of (or into) one port that share its stem — and so are two spec lines
  with a piece each on one line less than 16px apart (24px with a third line crossing the
  gap): read as one straight line, the two flows join through the gap (one out of a
  port to the left, the other 12px beside it to the right; a gap of exactly 16 or 24px
  is not under the limit); layout.py's feedback widens the gap along that line where
  they part, so the fallback can take its planned shape, except a gap between two ports
  of one node, which no track sets. A feedback round that takes a document past the
  1800px width warning to redraw missed shapes is not kept over a round under it with
  no more check problems, however many shapes it redraws.
  For the instances of one `.*` line on one run, write `trunk: true` when they are meant
  to merge. Lines that meet one side of a group at one point (a group end takes the other
  end's coordinate where it faces the side, else the group's row / column center) are
  split as on a node's side, two ±8 (±10 on top / bottom) apart, more 12px apart, in the
  order of their other ends; on a tie (two other ends on one row) the nearer one takes
  the point toward the side both come from, and of every order the one whose routes
  cross least wins, so no two of them cross beside the border; a `to_offset`
  (`from_offset`) sets an end's own.
- `label`: protocol and port, 12px squid ink (`"HTTPS :443"`). `verb`: a verb or
  attachment type, 12px grey (`DNS 조회`, `VPC attachment`). The loader rejects either one
  when it names a service with an official icon (SERVICE AS TEXT) — make it a node.
- Step badges: `step: n` (first instance only), plus `step_each: true` (every instance),
  or `steps: {gwlbe.1: 4, gwlbe.2: 4}` per instance. Every number needs exactly one
  `note.steps` row and the reverse (the loader checks).
- `step_at`: `mid` (default: the longest piece), `start`, `end`, `gap` (the piece outside
  every container), `stem` / `branch` (trunks), or `[x, y]` expressions. `label_at`: auto
  (above a horizontal piece, right of a vertical one; with a badge on the piece the two
  sit side by side above it), `above`, `below`, `left` / `right` (vertical pieces), or
  `{x, y, anchor: start|middle|end}`. Don't ask for `below` / `left`: labels go above a
  horizontal line and right of a vertical one. Without room there the engine puts the
  label on its line over a background rect in the top layer, then (last) on the other
  side, and warns either way — widen that side (`min_gap_before`, `pad`, `min_w`).
- The shape is picked by rule (straight when the ends share a row or column, else HVH /
  VHV / HV / VH by which sides are free; headless spokes from one node up — or down — to
  both its left and its right are all VHV, so a hub's two sides mirror; a spoke forced to
  another shape takes no part, a spoke forced VHV does). Override only when the render shows a bad path:
  `shape: H|V|HVH|VHV|HV|VH`, `bend_x` / `bend_y` (an expression or `gap`), `from_side` /
  `to_side` (`left|right|top|bottom`), `from_offset` / `to_offset` (px along the side),
  `points: [[x, y], …]` (the whole polyline, ends included; `e:` still names the ends).
  A side must leave along the shape's end piece (`HVH`: `left` / `right`, `VHV`: `top` /
  `bottom`, `HV`: horizontal then vertical); the loader rejects a mismatch.
  The same side at both ends of a `HVH` / `VHV` (`from_side: right, to_side: right`)
  draws an out-and-back on that side without `bend_x`: the leg sits at the nearest spot
  past both end segments that clears the labels along it, ≥ 12 from parallel borders and
  inside the box holding both ends (or the canvas) — on `top`, below that box's header
  (badge, title, CIDR), so the leg and its label never sit in the header row. The engine
  reserves that room, and the line's label beside the leg, between each end and that box's
  border (header) on that side — nothing between the two ends (a labelled leg runs outside
  boxes holding one end only, such as two AZs; a `bend_x` / `bend_y` expression places it
  yourself and reserves nothing); a refused one says which `pad_<side>` to give the box.
  The ends must differ along the leg: `left` / `right` at both ends needs them on
  different rows, `top` / `bottom` on different columns — the loader rejects ends sharing
  a row (column) and names the sides that work (`top` / `bottom` with `shape: VHV`).

```yaml
# from: slides/nfw-reference-architecture.layout.yaml
  - {e: "vpca <-> tgw", step: 1}
  - {e: "tgw <-> eni.1", shape: VH, verb: VPC attachment, step: 2, step_at: start}   # up / down around the Firewall RT
  - {e: "tgw <-> eni.2", shape: VH}
  - {e: "eni.* <-> fwe.*", step: 3}
  - {e: "fwe.* -> nat.*", step: 4}
  - {e: "nat.* -> igw", trunk: true, step: 5}
```

## note

One of `steps` (the step legend, `[hop, description]` per badge number, in order),
`summary` (one line) or `rows` (`[label, text]` pairs), plus `place: auto|panel|pane|lines`
and `width` (a pane's px). Leave `place` on auto: a document with steps gets a left pane
when the drawing is taller than 0.7 × its width or something left of the Cloud leaves
room above it, else the bottom panel; a slide gets a pane when it fits the 1108px width,
else ≤ 3 plain lines, never a panel.

```yaml
# from: gwlb-reference-architecture.layout.yaml
note:
  steps:
    - ["IGW → GWLBe", "IGW 엣지 RT가 App 서브넷 CIDR(10.0.1.0/24, 10.0.2.0/24)을 같은 AZ의 GWLBe로 보내, 들어오는 트래픽이 EC2보다 먼저 검사 경로로 갑니다."]
```

## Expressions and raw

Hints that take a position (`bend_x`, `bend_y`, `points`, `step_at` / `label_at` `[x, y]`,
`raw` placeholders, and a node's `xy` within the subset above) take a number or an
expression, each with an optional `±n`:
`<id>.(x0|x1|cx|y0|y1|cy)` (a node's icon box, a group's rect), `<node>.label.(…)` (its
label stack), `col.<track>` / `row.<track>` (a track center), `gap(<a>,<b>)` (the middle
of the widest free corridor between two tracks of one axis). Examples: `"besg.1.x0-22"`,
`"res.1.y0-36"`, `"gap(br,ext)"`.

`raw: [{layer: below|above, svg: '…'}]` adds an SVG fragment of the draft subset with
`{expression}` placeholders — for a mark nothing above can say; prefer `sub` for text.
`- {layer: above, svg: '<text x="{alb.cx}" y="{alb.label.y1+16}" font-size="12" text-anchor="middle" fill="#545B64">internet-facing</text>'}`
Raw text without `font-size` starts at 16px and scales with the other fonts.
A parent `<g font-size="…">` is flattened onto its text before checking/export, so
inherited sizes and explicit overrides use the same multiplier.

## Running it and reading the output

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/layout.py arch.layout.yaml -o arch.draft.svg   # --explain, --mode slide, --title / --no-title
```

`--explain` also prints, per track, the chain of constraints that set its position (the
draft is still written).
PyYAML is needed for `.yaml`; without it run `uv run --with pyyaml python ...`.

- Text is measured at the reader's size: the smallest drawn font on a fitted 16:9 slide
  (target 10pt, floor 8pt), or in a 760px document/web column without enlargement
  (target 11px, floor 9px). `text_scale: auto` enlarges all fonts together and lays out
  again, at most twice, by `min(1.8, target / actual)` each time, rounded to integer px.
  It keeps the previous result if text becomes smaller or check/other rule counts increase.
  `text_scale: off` preserves the original layout; a number fixes the multiplier and
  disables retries. Text still below the floor needs a split diagram or a `mode: slide` spec.
- **Spec errors** (exit 1, nothing written): one line each, located — `nodes[1] alb: icon:
  alias 'alb' has no match scoring ≥ 95; write the full ref — candidates: …`, then `N
  problems in the spec`. Fix them all, re-run.
- **Summary**: `draft:` path, `canvas: W × H (mode); smallest text Fpx → Npx in a 760px column (target 11)`
  for documents, or `on a 16:9 slide the smallest text (Fpx) → N pt` (the smallest
  font-size the draft draws, at the size svg2pptx gives it; `SLIDE TOO SMALL` under 10pt),
  `note:` place and size, `icons`, `alias` resolutions, `warning:` lines (read them —
  an LB inside a template, note text past the canvas, a phase-2 key drawn another way;
  `drew X instead of Y`: something blocks the planned shape — the engine re-solves with
  the gaps the edge spans widened (a feedback round, even when the check is clean) and
  keeps the warning only when that didn't help; run `--explain` to see
  which tracks coincide, then separate them with `min_gap_before`; when Y was your own
  `shape` / `from_side` / `to_side`, the line goes on with `refusing the requested …`, what
  blocked it (`bend_y tgwa.y0-60 = 148: LINE OVER TEXT '10.1.0.0/16' of svcs`) and what to
  try — a clean `bend_y: 181`, widening the gap between the ends, or for a same-side
  out-and-back `give <box> pad_right`; a refused request runs no re-solve of its own).
- `check: …` lines: what the engine already widened or repaired on its own — e.g. `line
  leaves box (vpc bottom): node:a → group:vpc.B ≥ 94` when a route went round the outside of
  the box both ends are in (or `line off canvas (canvas top)` past the canvas edge): it
  grew the room on that side so the route runs inside. A round never trades a slide that
  fits for one under 10pt.
- **Problems**: `check_layout.py`'s message, then up to three lines — `fix:` the draft
  coordinate correction (spec path: ignore it; it applies only once you edit the draft),
  `spec:` the spec items behind the problem (`edges[3] alb -> asg (label)`), `try:` the
  spec change to make (`label_at: …`, `shape / bend_x / …`, `dx / dy` (a flow-column
  node: `dx` and the column's `flow` / `align`), `pad / min_w`,
  `cols: {id: app, min_gap_before: 140}`; for `LINE LEAVES BOX` / `LINE OFF CANVAS` the
  room that side of the box needs, `groups[0] cloud: pad_bottom: 41`). `SLIDE TOO SMALL` lists the constraint chain of
  the overflowing axis.
- **Rules**: `rule: R-flow F3 …` and the other `rule:` lines judge the written draft.
  Each remaining enabled-rule violation also has a `warning: unresolved R-flow F3
  (edge:3, edge:5); spec hint (not a guarantee): …` in the summary. It names the owners
  and reuses their existing spec-fix hints; if none applies, the warning says why.
  Try the suggested spec change and draw again to check it.
  They are report-only: they change neither the draft nor the exit status. The last line
  starts with `Layout OK` (exit 0) or `N problems` (exit 1), followed, when needed, by
  `— 3 rule violations remain (R-flow F3 ×2, R-flow F5 ×1): fix them with the spec hints before delivering`.
  Change the spec and re-run until `Layout OK` **and no rule violations remain**; see
  [the rule-to-spec table in SKILL.md](../SKILL.md#6-run-the-engine-until-layout-ok-with-no-rule-violations).
  R-fit alone is a text-size issue: adjust `text_scale`, shorten labels, rearrange tracks
  or split the diagram. For a document spec run with `--mode slide`, write a slide spec
  (see `docs/examples/specs/slides/`) and check again. A rule checker error also appears
  in the last line; resolve it before delivering. Then look at the PNG.
  The same spec always gives a byte-identical draft.

## Common patterns (all from `docs/examples/specs/`)

- **Long pipeline** (serverless-order-pipeline; more than ~8 nodes in one row): fold it into
  lanes. A lane is one main row read left → right plus the helper rows it needs (a node
  above or below the line, such as an authorizer or a payment step, or a VPC's AZ rows);
  every lane shares the same columns. The wrap edge from the end of one lane goes back left
  in the corridor above the next lane's main row (`shape: VHV, from_side: bottom, to_side:
  top`; the router finds the bend and reserves the corridor — give `bend_y` as the gap
  between the previous lane's main row and the next one's only when you must pin it). Put
  side nodes in empty slots of an existing row rather than in a row of their own, so no
  row is left mostly empty, and fill a row's slots from the left with none empty between
  (the top row's regional services). A row of its own is fine when it adds no height: AWS
  WAF sits under CloudFront in the global strip, on a `waf` row inside the request →
  analytics wrap, because CloudFront → S3 leaves upward through `[edge, web]`. The shared
  columns take the widest pitch any lane needs, and a VPC lane's rows usually set it: keep
  the labels in the VPC short and put a long one on the hop with room. A HVH reserves its
  label's run before the bend (`proxy -> writer.1` is `shape: HV`, so "PostgreSQL :5432"
  sits on the proxy's own row), and an overlay over both AZs keeps its left edge right of
  each crossed subnet's header — an empty strip in every one of them — so the Aurora
  cluster has none: an `Aurora writer` in AZ 1 and an `Aurora reader` per AZ, the DB
  subnet `span`ning both DB columns so the two AZs match. A per-AZ fork is `trunk: true`
  (one stem from one port, forking to each AZ). layout.py warns past 1800 px wide.

- **AZ template** (nlb): `az` with `per`, subnets `in: az`, nodes `col:` only, an ASG
  overlay over both EC2 columns and one arrow into it; the LB (`in: vpc, at: [pub, main]`)
  and the IGW (`on: vpc, at: [igw, main]`) on the gap row.
- **Regional services row** (alb, nlb): a flow row, services `in: region, row: svc`, Route
  53 `in: cloud, at: [r53, svc]` (global); as a column instead, on the AZ slots (nlb-mtls
  `at: [svc, az1]` …) or, evenly spaced and free of the AZ rows, a flow column `{id: svc,
  flow: 110}` beside the VPC with services `in: region, col: svc` and Route 53 `in: cloud,
  col: r53` on `{id: r53, flow: true, align: top}` (slides/alb).
- **Trunks**: merge `nat.* -> igw`, fork `igw -> gwlbe.*`, both `trunk: true`.
- **Numbered flow** (gwlb, nfw, tgw): `step` on the edges + `note.steps`.
- **Hub and topology** (tgw): `--` edges, `at: [b1..b2, main]` under two spokes, route
  tables as nodes with routes in `sub` and `for:` every attachment of their TGW (its only
  table), `step_at: gap` for a badge between Regions.
- **TGW route tables beside their attachments** (nfw slide): a column for each table on the
  TGW's row — `rtsp` between the spoke VPCs and the TGW, `rtfw` between the TGW and the
  inspection VPC — `shape: VH` on `tgw <-> eni.*` so the inspection lines leave the TGW's
  top and bottom around `rtfw`; each table says which attachments it is associated with,
  `rtsp` `for: [vpca, vpcb]` and `rtfw` `for: [eni.*]` (centralized-egress: `for: [enia.*,
  enib.*]` and `for: [seni.*]`, the TGW's lines from the TGW ENIs). Neither the document
  nor the slide needs an empty column: the engine keeps the Spoke RT beside VPC A and VPC B
  (diagonal neighbours) on x, since apart on y the table would sit in the spoke column
  between the two VPCs, left of their lines to the TGW (the slide titled or not, and as a
  document). The nfw document example takes the narrower form: `rtsp` at `[spoke, main]`
  between VPC A and VPC B, the spoke lines `shape: VHV` with `from_offset: -60` into the
  TGW's top and bottom so the table sits inside their bracket, and `tgw <-> eni.*`
  `shape: HVH` with `bend_x: "rtfw.label.x0-14"` so the inspection lines bend just left of
  the Firewall RT.
- **Two VPCs** (gwlb): two `vpc` groups in one Region, each with its own `az` template.

```yaml
# from: alb-reference-architecture.layout.yaml
rows: [{id: svc, flow: 160}, az1, main, az2]
  - {id: acm,   icon: service/AWS-Certificate-Manager, label: ACM, sub: HTTPS 리스너 인증서, in: region, row: svc}
  - {id: rds,   icon: service/Amazon-RDS, label: {1: RDS Primary, 2: RDS Standby}, in: dbsn, col: db}
  - {id: alb,   icon: resource/Elastic-Load-Balancing_Application-Load-Balancer, label: ALB, in: vpc, at: [pub, main]}
  - {e: "rds.1 ..> rds.2", verb: 동기식 복제, label_at: left}
```

## What the engine cannot do yet, and the way out

- **Slides from a document spec**: `--mode slide` uses slide spacing but shortens nothing;
  the document examples come out at 7.4–8.2pt. Write a slide spec (short labels and
  captions, a note of ≤ 3 short lines, the services row as a column), or take the draft
  path from `docs/examples/slides/`.
- **A bus with drops** (`fork: bus`, phase 2) is drawn as a trunk fork with a warning;
  bedrock-dx draws its buses as `points` edges, one per segment.
- **Gateways on a top / bottom border**, border nodes inside a template, nested or
  multi-row templates, emphasis size (64), a TGW route table drawn as a table, Cloud WAN,
  multi-account layouts: not in the engine.
- **No key picks the label / badge piece** beyond `step_at` / `label_at`; **no key aligns a
  node to another group's side**; `gap()` treats every icon footprint as an obstacle.
- **`points`** reserve no space (widen with `min_gap_before` / `pad_top`) and cannot use
  `*`: write one edge per instance (bedrock-dx).
- **Extra rows between the AZs** keep the full AZ gap, so such a layout comes out larger
  than a hand-drawn one (bedrock-dx).

The way out, in order: (1) spec hints — `shape`, `bend_x`/`bend_y`, `from_side`/`to_side`,
`step_at`, `label_at`, `min_gap_before`, `pad`/`pad_top`/`min_w`/`min_h`, `dx`/`dy`;
(2) `points`, `xy`, `raw`; (3) edit the generated draft with Edit and
`check_layout.py --fix`, as for any draft. From the first hand edit on, the draft is the
source: do not regenerate it from the spec (that would drop the edits).
