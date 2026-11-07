# Layout spec reference

A spec (`<name>.layout.yaml`) declares *what* the diagram holds and *which track* each
thing sits on; `scripts/layout.py` computes every coordinate and writes a draft that
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
| `cols` / `rows` | the tracks, left → right / top → bottom |
| `groups`, `nodes`, `edges`, `note`, `raw` | below |

Ids match `[A-Za-z0-9_-]+`; node and group ids share one namespace; track ids are unique
across cols and rows (a node may share its track's name, `igw` above).

**Tracks.** A track is a grid line: a node's icon center sits on one column and one row,
and the engine spaces the tracks by what lies between them. Name columns after tiers
(`users, igw, pub, app, db`) and, for two AZs, use rows `[az1, main, az2]`: `main` is the
gap row between the AZs where Users, the IGW and the load balancer sit. Stacked AZ boxes
get the full AZ gap only when a node of their VPC (or one on its border) sits on a row
between them; with nothing between, they are just siblings (16px apart). An item is a name
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
  no box, it sits above the member like a long one.
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

`{id, icon, label, sub?, in? | on?, at? | col? | row? | xy?, dx?, dy?}`

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
  the same axis (`q` on `s.cx`, `s` on `q.cy` is fine). An `xy` node stays inside its boxes
  but never pushes its row neighbours apart (they don't see it). In a `per` template,
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
  (serverless `sfn -> reserve.*`), with no `from_offset: 0`.
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
# from: nfw-reference-architecture.layout.yaml
  - {e: "vpca <-> tgw", verb: VPC attachment, label_at: above, step: 1, step_at: end}
  - {e: "tgw <-> eni.*", step: 2, step_at: start}
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

## Running it and reading the output

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/layout.py arch.layout.yaml -o arch.draft.svg   # --explain, --mode slide, --title / --no-title
```

`--explain` also prints, per track, the chain of constraints that set its position (the
draft is still written).
PyYAML is needed for `.yaml`; without it run `uv run --with pyyaml python ...`.

- **Spec errors** (exit 1, nothing written): one line each, located — `nodes[1] alb: icon:
  alias 'alb' has no match scoring ≥ 95; write the full ref — candidates: …`, then `N
  problems in the spec`. Fix them all, re-run.
- **Summary**: `draft:` path, `canvas: W × H (mode); on a 16:9 slide 12px text → N pt`,
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
- Last line `Layout OK` (exit 0) or `N problems` (exit 1). Change the spec, re-run, until
  `Layout OK`; then look at the PNG. The same spec always gives a byte-identical draft.

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
  tables as nodes with routes in `sub`, `step_at: gap` for a badge between Regions.
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
