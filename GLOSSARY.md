# AWS architecture diagram layout

These are the words that the layout engine, the rule checker, the corpus and their documents share. They cover what a diagram declares, how the engine draws it and how a drawing is judged. Each word has one meaning in all of them.

## Spec

**Spec**:
A YAML (or JSON) file that declares what a diagram holds: groups, nodes, edges and the note. It places nodes on tracks and uses coordinates (`xy`, `points`) only where the author pins them.
_Avoid_: layout file, config

**Mode**:
The medium a spec is drawn for: `document` (a page or web column) or `slide` (16:9). A slide is drawn with or without a title.
_Avoid_: target, format

**Track**:
A named column or row of the spec's grid. A node is placed on a track; its icon centre sits there unless an offset, a column span or a pin moves it.

**Flow column**:
A column whose nodes give only `col:`. The engine stacks them in spec order instead of putting them on rows.
_Avoid_: auto column

**Flow row**:
A row whose nodes give only `row:`. The engine lays them out side by side in spec order instead of putting them on columns.
_Avoid_: auto row

**Stack**:
The vertical run of a flow column's nodes inside one parent box.
_Avoid_: pile

**Group**:
A box the spec declares: cloud, region, account, VPC, AZ, subnet or generic. It may sit inside one parent group (`in:`).
_Avoid_: container, frame, cluster

**Overlay**:
A group drawn over the nodes it lists (`over:`) instead of containing them, such as an Auto Scaling group, target group or security group across AZs. It is not part of the containment tree.
_Avoid_: floating group

**Template instance**:
One copy of a group made by `per:`, with the instance number in its id (`az.1`, `az.2`).
_Avoid_: clone, replica

**Twins**:
Boxes the engine judges to have the same structure, by the test in `references/layout_spec.md` (groups → twins). Template instances twin only with boxes of the same instance number; an AZ's own title may differ by its identifier (the number or letter after AZ / Zone). Twins are drawn the same size, with the same inner offsets. Boxes that would be twins but for the order of their rows are not twins: the engine keeps the spec's row order and R-twin reports them (TWR).
_Avoid_: copies, mirrors

**Route table**:
A node drawn with the official Route-Table icon. It stands for a table that applies to certain subnets or attachment lines.
_Avoid_: RT box, routing node

**Association**:
What a route table applies to: the nodes or groups listed in `for:`, and the lines that reach them from its hub, if it has one.
_Avoid_: binding

**Hub**:
The node that a route table's associated lines meet, such as a Transit Gateway or firewall endpoint. The loader finds it or `via:` names it; `references/layout_spec.md` (nodes → `for:`) gives when a table has none.

**Note**:
The text block beside or under a diagram: numbered steps that match the badges on the lines, or unnumbered summary rows.
_Avoid_: caption, footer

## Drawing

**Trellis**:
The layout engine: it reads a spec, computes every coordinate and draws the draft. "The engine" in these documents means Trellis.
_Avoid_: layout script, renderer, generator

**Draft**:
The SVG the engine draws from a spec, before icons are embedded.
_Avoid_: output, render, preview

**Owner**:
The spec item a drawn element is grouped under in a draft. It can be an edge, an edge's label, badge or mask, a node, a group, the note, or a raw block. Background and definitions have no owner.
_Avoid_: owning element

**Edge instance**:
One line pair that a spec edge expands to. An edge with wildcards or `per:` targets yields one instance per pair.
_Avoid_: sub-edge

**Flow**:
The data path one edge instance carries. Instances of one edge drawn as a trunk share a single flow. Lines of different flows must never read as one line.
_Avoid_: wire

**Header band**:
The rectangle from a group's top-left corner to the far edge of its own badge, title and CIDR line. A group that shows none of these has no header band. No connector may run through it.
_Avoid_: title bar

**Effective text size**:
The size of a drawing's smallest text as its reader sees it: points on a 16:9 slide, or pixels in a 760px page column.
_Avoid_: apparent size

**Text scale**:
One factor applied to every font of a spec. By default the engine chooses it, enlarging all fonts when the effective text size is below target; `text_scale: off` disables it, and a number fixes it (smaller than 1 shrinks).
_Avoid_: zoom, magnification

**Relaxation**:
The engine's answer to spec placements that cannot all hold: it changes a placement or requirement so the spec can still be drawn, and warns about the change, instead of refusing the spec.
_Avoid_: fallback, auto-fix

## Judging

**Check problem**:
A defect in a draft that the drawing checks report, such as a line over text, text overlap, a line in a header band, a service drawn as text, or a slide too small.
_Avoid_: error, lint

**Rule**:
One of the user's readability rules, judged on a draft against its spec: R-flow, R-rt, R-twin, R-label, R-border or R-fit.
_Avoid_: heuristic

**Violation**:
One instance of a rule that a draft breaks. It names the owners involved and carries a tier and a cost. Its identity is its rule, code and owner set; coordinates and owner order do not change that identity.
_Avoid_: failure, finding

**Line over node**:
An R-flow violation (F6, tier 0): a connector piece passes over a node's icon body or its name block (the name and its sub caption lines), so the flow reads as passing through that node or its name is hidden. It names the edge and the crossed node. Group titles and CIDR lines, edge labels and step badges are not counted here; R-border, F5 and R-label own them.
_Avoid_: crossing (two lines crossing each other), line through icon

**Attach piece**:
The piece of a line that ends on one of its own end nodes. It is the only part of the line exempt from line over node at that node, and only while it runs at most 4px into the icon (the icon box shrunk by 2px, as LINE OVER ICON measures). A line over its own end's name, or across its own end's icon anywhere else, is a line over node.
_Avoid_: end segment, stub

**Channel move**:
Selection's answer to a line over node that its routing alternatives leave: the track gap the crossing piece runs through, beside the crossed node, is widened so the router finds a clear stretch, and a trunk's shared bend is searched along every member's run. Like every candidate it replaces the drawing only on a strictly better verdict, and only when it removes a line over node without adding any tier-0 violation.
_Avoid_: spreading, push apart

**Tier**:
The rank of a rule when drawings are compared. Tier 0 means a reader misreads the diagram; tier 2 means fit and size. Tier 0 counts before tier 2.
_Avoid_: severity, priority

**Feedback round**:
One pass in which the engine reads a draft's check problems, adds space or routing requirements, and draws again. It keeps the new draft only if that draft is not worse.
_Avoid_: retry, repair loop

**Candidate**:
One complete drawing of a spec under one set of layout decisions. Candidates are compared by their verdicts after the replacement gates. For every rule group, the text-size limit excludes candidates whose effective text size is both below the medium's target (slide 10pt; document 11px in a 760px column) and below 90% of the completed default's; text at or above target follows the verdict regardless of shrink percentage. Later stages (feedback, header, fixed-answer and text-scale steps), including those inside candidate construction, allow more than 1% text shrink from a held drawing below target only when the total tier-0 violation count strictly decreases. Reducing check problems or tier-0 cost alone does not permit that shrink.
_Avoid_: attempt, variant

**Verdict**:
The ordered score of a candidate. Its parts, in order: canvas clipping check count (critical like tier 0, before all other parts), tier-0 violation count, tier-0 cost, check problem count, effective text shortfall, shape misses, canvas area. Before this unchanged order, every replacement comparison gates new tier-0 violation identities: a drawing that adds one is eligible only when its total tier-0 violation count is strictly lower than the held drawing's. Candidate selection and every later stage share the gate, including rules outside the enabled search group.
_Avoid_: grade, fitness

## Corpus

**Corpus**:
The regression set of specs, each run in its modes. Its drafts and rule results gate every engine change.
_Avoid_: fixtures, samples

**Case**:
One corpus entry: a spec, its modes, its expected load result (`expect`), what it exercises, and its tags.
_Avoid_: sample

**Tag**:
A case's statement about one rule. `good` means its drafts keep the rule; `bad` means they break it, naming the owner. The runner reports any run that disagrees.
_Avoid_: assertion

**Baseline**:
The corpus result and drafts of one main commit. Every writer and reviewer of a change made on top of that commit shares it.
_Avoid_: snapshot, reference run
