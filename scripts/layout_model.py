"""Data model and module contract of the layout engine (spec → draft SVG).

The engine turns a declarative spec (`<name>.layout.yaml`) into a draft SVG that passes
check_layout.py and export.py. It is split into modules that are developed in parallel;
this docstring is the contract they share. Constants (numbers, colors, group styles, z
layers) are in layout_const.py. Python 3.9, standard library only (PyYAML in W1).

=========================================================================================
1. Modules and signatures
=========================================================================================

  layout_spec.py   (W1)
    load(path_or_dict, mode=None, title=None) -> Spec
        path_or_dict: a .yaml/.yml/.json path (str or Path) or an already parsed dict.
        mode: "document" | "slide" overrides the spec's `mode` (CLI --mode); title: bool
        overrides `title` (CLI --title/--no-title). Returns a fully expanded, validated
        Spec: templates (`per`) instantiated, `*` edges paired, per-instance values
        picked, defaults applied, icons resolved to full `set/name` refs, expressions
        parsed into Expr. Raises SpecError(problems) with every problem found (not just
        the first). Non-fatal lint goes to Spec.warnings.
    parse_expr(s, spec=None) -> Expr   the expression grammar of section 6. Without spec,
        `<id>.attr` parses as kind "node"; with it, a group id gives kind "group". W5 takes
        raw placeholders from RawSpec.exprs (already resolved), or passes spec.

  layout_route.py  (W3)
    plan(spec) -> list[Requirement]
        Picks every edge's shape (pure function of the spec) and returns the space the
        routes need as difference constraints: gutters, label runs, arrow segments,
        trunk corridors. Reads Spec only. Lines that draw() bends at one shared value
        whose legs would overlap (lane_counts: `.*` instances that are no trunk, or
        lines on one node side) get LANE_PITCH (12) more gutter per extra lane.
    draw(spec, geom, skip=None) -> (list[Element], list[str])
        Routes every edge on the solved Geometry and returns its Elements (z Z_EDGE,
        Z_EDGE_LABEL, Z_BADGE) and warnings. skip: {edge n: k} skips the first k
        candidates of edge n (the W5 feedback loop's "use the next candidate"). Must make
        the same shape choices as plan() (recompute them; no module state). Lines that
        share a bend never share a leg unless they are one `trunk` line's instances: an
        overlapping leg gets its own lane (LANE_PITCH apart, the order with the fewest
        crossings); only when no clean set of lanes exists do they share the bend (and
        check_layout reports LINE ON LINE).
    same_side_problems(spec) -> list[(where, message)]
        Lines whose two ends leave one side (from_side / to_side, given or implied) while
        sharing the row (left / right) or column (top / bottom) the out-and-back's leg
        would need; W1's load() raises them as SpecError problems.

  layout_solve.py  (W2)
    solve(spec, reqs, note_block=None) -> Geometry
        Footprints, constraint generation (DESIGN 4.3 items 1-11) + reqs, longest-path
        solve per axis, hug, border nodes, flow rows / columns, overlays, colspan, canvas. With
        note_block it also applies note_block.requirements (W5 passes them inside reqs as
        well; duplicates are harmless) and sizes the canvas for the note (section 4).
        Raises SolveError(problems) on a positive cycle, naming the Requirement.why/owner
        and spec ids of the constraints in it (after dropping soft requirements first).
    draw(spec, geom) -> list[Element]
        The Elements of every group (z Z_GROUP: rect, badge, title, CIDR, in Geometry.groups
        order) and node (z Z_NODE: mask, icon, label lines, in Geometry.nodes order),
        built with the el_* factories below from Geometry alone.
        (Added to the design's list: W2 owns header and label geometry, so it also draws it.)

  layout_note.py   (W4)
    block(spec, geom, place=None, width=None) -> NoteBlock
        Decides the note's place ("panel" | "pane" | "lines" | "none") by the auto rule
        (DESIGN 4.7) unless spec.note.place or `place` fixes it, its size, its Elements
        (z Z_NOTE, owner "note") positioned for *this* geom, and the Requirements the
        place needs (pane coupling). `width` fixes the pane width. Pure: no geom mutation.

  layout.py        (W5)  CLI, pipeline, emit, in-process check, feedback loop, --explain.
    main(argv) -> exit status; build(spec, extra_reqs, skip, place, source) -> Build (one
    pass of the pipeline below); emit(spec, geom, elements, source) -> bytes.
    The pipeline (W5 owns it; the others rely on this call order):
        spec  = layout_spec.load(path, mode, title)
        reqs  = layout_route.plan(spec)
        geom0 = layout_solve.solve(spec, reqs)                       # no note yet
        nb0   = layout_note.block(spec, geom0)                       # place, size, reqs
        geom  = layout_solve.solve(spec, reqs + nb0.requirements, note_block=nb0)
        nb    = layout_note.block(spec, geom, place=nb0.place, width=nb0.w if nb0.place == "pane" else None)
        edges, warns = layout_route.draw(spec, geom)
        elements = layout_solve.draw(spec, geom) + edges + nb.elements + raw elements
        svg = emit(spec, geom, elements)        # stable sort by z, wrap owners in <g id>
        then check_layout.run_checks in process; on what is left add Requirements or
        `skip` entries and go back to solve (≤ 5 rounds, DESIGN 4.10); the round with the
        fewest problems gets check_layout --fix's fixed-answer repairs (Advisor.plan +
        write_edits) and is written. Feedback by kind:
          SHORT ARROW, LINE HUGS BORDER, TEXT AT BORDER / TOO CLOSE / OVERLAP / NEAR ICON,
            BADGE NEAR ICON (a short piece's label or badge too): the neighbouring tracks
            around the spot, on the axis that separates the two things, get
            "track b − track a ≥ current + 16" (owner the element's id, why "feedback: …").
          LINE OVER TEXT / ICON, LINE NEAR TEXT on a connector: skip[n] += 1 (≤ 3), then widen.
          LINE ON LINE (two flows on one run): the tracks around the run, across it, get
            current + 16 (room for the router's lanes).
          LINE LEAVES BOX / LINE OFF CANVAS on a connector: the box's border on that side
            (group:<gid>.L/R/T/B) or the canvas ("drawing" / "origin") ≥ current + the
            overshoot + 12 from the edge's end; when that room is already there, skip[n] += 1.
          route.draw's "drew X instead of Y" warning: widen the gaps between the edge's ends
            (not for an edge given room above that round, nor a refused requested shape).
          The round kept: fewest problems (+1 for SLIDE TOO SMALL), then fewest such misses.
        Later rounds keep the note place of the first (only the pane width is recomputed).
    nb.requirements must hold on geom (same place and width as nb0); W5 checks that and
    warns when one is short by more than 0.5 px.
    spec.note is None → W4 returns NoteBlock("none").

  layout_const.py / layout_model.py (W0)  this contract. W6 (docs/examples/specs/*.yaml,
    tests/compare_structure.py) relies on the spec format (DESIGN 2-3, as refined in
    section 9 below) and on layout_const.group_type_of() to name a draft rect's group type.

=========================================================================================
2. Coordinates and units
=========================================================================================
Every coordinate in Geometry, Element, Requirement and NoteBlock is an absolute canvas px
in the final SVG's user space: viewBox "0 0 canvas_w canvas_h", origin top-left, x right,
y down. Never relative to a group, never translate(). Floats; Element numbers are written
with fmt_num (≤ 2 decimals, integers without ".0"). Lengths are px at the spec's S (48 by
default); text sizes are px.

=========================================================================================
3. Who fills what
=========================================================================================
Spec / Track / Group / Node / Edge / NoteSpec / RawSpec / Expr   — W1 fills, all read.
Requirement   — W3 (plan) and W4 (block) create; W5 may add (feedback); W2 consumes.
Geometry, GroupGeom, NodeGeom, TextLine, Box — W2 fills; W3, W4, W5 read; nobody mutates
                a Geometry after solve returns (W5 re-solves instead).
NoteBlock     — W4 fills; W2 reads place/w/h/below() for the canvas; W5 emits elements.
Element       — W2 (groups, nodes), W3 (edges, edge labels, badges), W4 (note),
                W5 (raw); W5 emits.

Geometry fields each reader uses:
  W3 draw:  nodes[*].icon/cx/cy/lines/stack()/mask/side, groups[*].rect/header(),
            cols/rows/col_extent/row_extent, canvas_w/h (bend search, obstacles, ports).
  W4 block: drawing (bottom, for panel/lines y), groups[cloud].rect (pane y, lines x),
            canvas_w (panel width), cols/col_extent and nodes (pane width "left column",
            client node), mode via spec.
  W5:       canvas_w/h, explain, warnings, everything for expression evaluation (eval_expr).

=========================================================================================
4. Requirement variables, and the note in the canvas
=========================================================================================
A Requirement says  value(b) − value(a) ≥ d  on one axis (d may be negative; an equality
is two Requirements). Variable names (strings):
  "origin"                       the canvas origin, fixed 0 (both axes)
  "col:<track>" / "row:<track>"  a track center (x / y)
  "group:<gid>.L" / ".R"         a group rect's left / right edge (x axis)
  "group:<gid>.T" / ".B"         its top / bottom edge (y axis)
  "node:<nid>"                   the node's icon center on that axis (track center + dx/dy,
                                 a flow-row node's solved x, a flow-column node's solved y,
                                 a border node's border).
  "drawing"                      only as `b`: the drawing's far edge (right on x, bottom on
                                 y); W2 extends Geometry.drawing to it, so the canvas (and a
                                 panel note below) follows — W3's room for an out-and-back
                                 leg right of / below the outermost items (decision n).
W2 maps "node:<nid>" of a colspan node (center between X_b1 and X_b2) to its center: for
an assumed span s it takes X_b1 + s/2 (as `b`) / X_b2 − s/2 (as `a`); s = 0 is the
conservative first solve (any center in the span). The span g(s) a solve gives back grows
at a slope below 1, so W2 finds the fixed point g(s) = s (secant steps, regula falsi once
a step overshoots; SPAN_TOL 0.01 px, ≤ SPAN_ROUNDS 12 solves, then the closest with a
warning) and solves the answer once more, whole, with X_b2 − X_b1 ≥ s held — so its
footprint and requirements are reserved from its center, not from both end tracks
(DESIGN 4.3 #7). Node footprint widths are not variables: a requirer adds the
half widths it needs into d (icon edge = S/2 + END_GAP; labels by layout_text_width).

Canvas (W2): every drawn thing ≥ canvas_margin from "origin" on both axes, and
  canvas_w = max(drawing.x1, pane rect x1) + canvas_margin
  canvas_h = max(drawing.y1 + canvas_margin, drawing.y1 + note_block.below(),
                 pane: cloud.y0 + note_block.h + canvas_margin)
  drawing = union of every group rect and node footprint (no edges, no note), extended
            to the "drawing" variable when a Requirement names it.
Note rects (W4 computes them; W2 needs only place/w/h):
  panel  Box(PANEL_X, drawing.y1 + PANEL_GAP, canvas_w − PANEL_X, … + h); below() = 16 + h + 16
  pane   Box(PANE_X, cloud.y0, PANE_X + w, cloud.y0 + h); below() = 0. Width (auto):
         300, 320 when a description would wrap past 4 lines at 300, or — when top-level
         items sit left of the Cloud — the left column floor(cloud.x0 − PANE_GAP − PANE_X)
         measured on geom0, if wider (ex bedrock-dx 456)
  lines  h = canvas bottom − drawing.y1 (first badge cy = drawing.y1 + 18 … last baseline + 4); below() = h;
         rect = Box(cloud.x0, drawing.y1, rightmost text end, drawing.y1 + h), w its width.
         Items: a step = badge + "{hop} {desc}" as one grey 12px line; text-only notes:
         the summary, then each row as "{label} {text}" (W6's slide specs follow this)
  none   below() = 0
"cloud" is spec.cloud_id(), the first group of type cloud. Pane Requirements (W4):
  x: origin → group:<cloud>.L ≥ PANE_X + w + PANE_GAP;  the client node pinned to
     PANE_X + w/2 (two requirements) only when the pane is 300 / 320 wide and the top-level
     items left of the Cloud are nodes of one col and no group;
  y: group:<cloud>.T → node:<client> ≥ h + PANE_CLIENT_GAP + S/2;
     group:<cloud>.T → group:<g>.T ≥ h + PANE_OUTER_GAP for a top-level group under it.

=========================================================================================
5. z order, Element ids and <g> wrapping
=========================================================================================
Layers (layout_const.Z_*), emitted in ascending z; inside a layer, in production order
(W2 groups then nodes, W3 edges in Edge.n order, W4 note, W5 raw):
  Z_RAW_BELOW  raw `layer: below`, right after the background rect
  Z_GROUP      groups outer → inner (Geometry.groups order: containment preorder, overlay
               groups last); each: rect, badge image, title, CIDR line
  Z_NODE       nodes in Geometry.nodes order; each: mask rect (border nodes) → icon → label
               → sub lines
  Z_EDGE       connector lines (line / polyline), Edge.n order
  Z_EDGE_LABEL connector labels (label, verb)
  Z_BADGE      step badges (circle, then digit)
  Z_NOTE       note rect and text
  Z_RAW_ABOVE  raw `layer: above`
  Z_LABEL_TOP  a connector label set on its line: background rect, then the text
Element.owner is the id of what the element draws:
  "group:<gid>"  "node:<nid>"  "edge:<n>" (n = Edge.n, 0-based)  "note"  "raw:<i>"
Each producer emits an owner's elements contiguously within a layer. emit() wraps each
run in <g id="...">: the owner itself in its home layer (group → Z_GROUP, node → Z_NODE,
edge → Z_EDGE, note → Z_NOTE, raw → its layer), and "<owner>:<part>" in any other layer,
part = layout_const.Z_PART[z] ("edge:3:label", "edge:3:badge"; any other layer "z<z>").
So every id is unique and maps back with split_eid(). Spec ids match [A-Za-z0-9_-]+
(W1 enforces): "." is reserved for template instances ("nat.1"), "*" for edge patterns,
":" for element ids. svg2pptx accepts <g> with id only (no transform, no presentation
attributes). check_layout reports an element's own id only, so W5 maps an Issue's
elements to spec ids through their enclosing <g>.

The root header (W5): <svg viewBox="0 0 W H" xmlns=… font-family=spec.font>, one comment
"generated by layout.py from <file> — edit the spec and re-run; hand edits are lost on
regeneration", <defs> with MARKER_ARROW (+ MARKER_ARROW_START only if some element has a
marker-start), the background <rect width=W height=H fill="#FFFFFF"/>. Output is a pure
function of the spec: same spec → byte-identical draft (sorted nothing by hash/set order).

=========================================================================================
6. Expressions (escape hatches: bend_x/bend_y, points, step_at/label_at [x, y], raw {…}, xy)
=========================================================================================
  <number>                               Expr("num", offset=v)
  <id>.(x0|x1|cx|y0|y1|cy) [±n]          node id → its icon box; group id → its rect
  <nid>.label.(x0|x1|cx|y0|y1|cy) [±n]   the node's label stack (stack(), 0.55 em)
  col.<track> / row.<track> [±n]         a track center
  gap(<a>,<b>) [±n]                      middle of the widest free corridor between two
                                         tracks of one axis (Geometry.gap)
Track ids are unique across cols and rows (W1 enforces), so gap() knows its axis.
raw: RawSpec.exprs maps a placeholder's inner text to its Expr ("{br.cx+4}" → key
"br.cx+4"); W5 substitutes fmt_num(eval_expr(...)) and checks the result against the draft
subset (svg2pptx.collect's tags; <g> with id / translate only; bundle: hrefs).
eval_expr(expr, geom) below evaluates one (W3 for hints, W5 for raw). A node's `xy` takes the
subset a difference constraint can hold (W1 rejects the rest): col.<t> / row.<t>, <node>.attr
of a node that is not a colspan (x0/x1, y0/y1 = icon edges), <group>.(x0|x1|y0|y1), ±n, with
no chain of node references back to itself on one axis; W2 pins "node:<nid>" to it with two
Requirements, so the node follows the solved tracks. A `per` template node's xy is resolved
per instance n: a template item's base id names its instance n, `row.<per row>` the
instance's row; a y reference to another instance of the template is rejected, and so is
a y that is one for every instance of a node drawn in two or more (a number, a node or group
outside the template, a row not in its `per`).

=========================================================================================
7. Text width
=========================================================================================
  text_width(s, size)         = check_layout.text_width: 0.55 em Latin, 1.0 em Hangul/CJK/
                                arrows. Use it where the result must agree with the checker
                                and the examples: glyph boxes for the checker-equal obstacle
                                tests (headers), the note description column (56 + widest
                                hop + 16), slide line flow and pane wrapping (decision j).
  layout_text_width(s, size)  conservative 0.6 em Latin (wide characters unchanged). Use it
                                to reserve space: node footprints, header width constraints,
                                label runs, mask widths; and for the router's node-label
                                obstacles (a line should miss the rendered glyphs, which run
                                wider than 0.55 em on capitals / underscores).
Both live here (layout_model), importing check_layout (which loads the icon bundle via
find_icon on import, ~0.1 s); layout_const stays import-free.

=========================================================================================
8. Errors
=========================================================================================
LayoutError(problems) base; SpecError (W1) and SolveError (W2) subclass it. `problems`
is a list of one-line strings, each starting with the spec location ("nodes[3] nat: ...",
"edges[5]: ...", "groups[2] az: ..."). W5 prints them and exits 1.

=========================================================================================
9. Decisions that refine the design (DESIGN = the layout-engine design document)
=========================================================================================
 a. Documents pad 16 at every nesting level (DESIGN 4.4 had 20 for Cloud→Region and
    Region→VPC sides): alb, nlb-mtls and bedrock-dx use 16 there (examples win).
 b. Connector label below its line: baseline +16 (DESIGN 15; every example 16). Slide
    vertical-piece label 8 from the line (document 10).
 c. Slide shrink steps (DESIGN 4.8 "pad → 8, AZ gap → 86, pitch → 92") dropped: slide mode
    already solves at those minima and the solution is minimal, so there is nothing to
    shrink. W5 reports layout_const.slide_pt(); below 10pt it fails with the --explain
    evidence (widest column, the label behind it, px over).
 d. The note is computed twice (geom0, then the final geom with place/width fixed) and
    reaches the canvas through NoteBlock.below() / pane h (section 4). Panel y = drawing
    bottom + 16, which is the Cloud bottom in every example.
 e. W2 also draws groups and nodes (layout_solve.draw); W3.draw takes skip= for the
    feedback loop; W1.load takes title=; Requirement.soft for preferences (arrow 48 soft
    + 20 hard): W2 drops soft requirements before reporting a cycle.
 f. Overlay (ASG) top inset (+30/+28) binds only member icons under its header title;
    other members keep ≥ 8 below the ASG top (ex gwlb +26 / +20). A title no wider than an
    icon goes beside the first member row instead (x: the row right of badge + title) when
    every first-row member sits on the first row of its subnet and the header inset would
    push it below the subnet's icon inset; those members then keep the subnet's icon inset
    less the overlay's own top inset in it (doc 32 − 8, slide 28 − 8), so the hugged top
    lands 8 under the subnet top and follows a row that sits lower. A member in no box or
    below something else of its box gets the title above it (no subnet header to sit by).
 g. Default font-family is the examples' fixed string (layout_const.FONT_FAMILY_DEFAULT);
    W1 reorders only when Noto Sans CJK KR is not installed, so output stays stable.
 h. edge.label_at None = auto (above a horizontal piece, right of a vertical one; a badge on
    the same piece sits beside the label, both above; no room: on the line over a
    background rect at Z_LABEL_TOP; then the other side). Edge.step is the
    badge on that instance after step / step_each / steps resolution.
 i. Track ids are unique across cols and rows; spec ids match [A-Za-z0-9_-]+ (section 5).
 j. Positions the examples computed from text widths (panel description column, slide
    line flow, pane wrapping) use text_width (0.55 em), not the conservative
    layout_text_width (at 0.6 em nlb-mtls step 2 and bedrock-dx step 2 wrap differently).
 k. Subnet / VPC / AZ icon top +32 doc, +28 slide; Cloud → Region +40 doc. Two examples
    are tighter on purpose (bedrock-dx Region +34, the skeleton's AZ 2 EC2 +30); the
    engine keeps the table value (tests/test_layout_model.py TIGHTER).
 l. Shared interpretations (W1 → W2 / W3): Group.nodes excludes `on` nodes (their col
    counts toward the VPC's parent's cols); `xy` nodes have col / row None; flow-row nodes
    given a `col` (flow-column nodes given a `row`) have flow_index None; a flow-column node
    has row None and col set (Spec.flow_stacks lists them): its y is a "node:" variable,
    stacked in spec order, then aligned in its parent (Track.align; the top level: the
    rest of the drawing's height) as far as every constraint allows, carrying `xy` nodes
    tied to it and overlays over its nodes only. Its stack sits at a fractional row index,
    Spec.flow_slot (top: parent's first row − 0.5, bottom: last + 0.5, center: between the
    rows above and below the middle, an odd middle row below): the router's row range for
    the node (never a grid row, so no rule-1 H to a grid node), and the side a same-parent
    sibling sharing the column's x goes to (above when the middle of its rows is before the
    slot, else below; a flow-row node of the parent, once solved x shows its footprint
    within sibling_gap of the stack's, by Spec.flow_row_above: a row on the parent's first
    row stays above a top-aligned stack and one on its last row below a bottom-aligned
    stack, so the stack stops at the row instead of pushing it inward; any other row by
    the slot as on its row; a flow-row node and a stack node it meets keep twice the
    column's own spacing between their footprints, at least that spacing + sibling_gap,
    so the row never reads as the column's next node). A box with no row that holds
    flow-column nodes (Spec.float_align) is such a block too: its slot is its first
    column's in its own parent; overlays over
    stack members take only a top-aligned stack's first node as a first-row member;
    Edge.src = "edges[i]"; template instances are Group.instance / Node.instance plus the
    ".n" id suffix.
 m. Group `pad_top` (spec key, px): box top → its first icon / nested box when larger than
    the type's header inset (room for a `points` bus above endpoints, bedrock-dx 88; DESIGN
    "no key for a subnet top inset"). `min_h` grows a box downward, not its top inset.
    `pad_left` / `pad_right` replace `pad` on one side only (room for a label beside a line
    on that side); `pad_bottom` replaces it at the
    bottom (child box → border, the header-height minimum; a node's footprint bottom →
    border, never closer than Mode.label_bottom from its last baseline). A `span` keeps
    pad_node from its track centers, or pad_left / pad_right / pad_bottom on those sides.
 n. Router space plan() adds beyond DESIGN 4.3 #10 (W5, from the golden renders):
    a vertical leg at a node through the top border of the node's boxes the other end is
    outside of passes right of their header (hard: checker width + 5; soft: 0.6 em + 8;
    alb RDS replication); the same soft 0.6 em + 8 with the arrow at its target length for
    a fork trunk past a header (gwlb); a HVH / VHV label run before the bend (soft: text
    + 8 from the box + 4 to the bend, then the arrow; nfw "VPC attachment"); an overlay
    (ASG) a line leaves sideways keeps 16 to its member subnets' parallel border (alb
    816 → 836, nlb). `points` routes get no route warnings (check_layout judges them).
    A same-side HVH / VHV (out-and-back, from_side = to_side along the shape's end
    pieces, the ends on different rows / columns: W1 rejects a shared one) gets none of
    the between-ends gutter / label run / footprint reqs: each end instead keeps port +
    end segment (+ the labels its leg runs past) + max(HUG_CLEAR, the line's label beside
    the leg + 8) from the innermost common box's border on that side ("origin" /
    "drawing" − canvas margin when the ends share no box; on top inside a box, its header
    band — badge, title, CIDR glyphs — counts too in the hard reqs, so leg and label sit
    below the header: slide vtop); a labelled one also HUG_CLEAR + that room past the
    boxes of one end only (its leg runs outside them); one with a bend_x / bend_y
    expression gets nothing (the spec placed its leg).
 o. Note auto rule (DESIGN 4.7) also picks the pane for a document when top-level items sit
    left of the Cloud and the pane fits above them without a push (bedrock-dx 1040 <
    0.7 × 1498 and nlb-mtls 764 vs 763 drew panes; the specs no longer force `place`).
 p. Default output: <spec dir>/<name>.draft.svg. The emitted header comment names the
    spec's file name only (no directory, so the draft does not depend on the cwd).
 q. Two nodes side by side on one row are separated band by band (W2): the icon and each
    label line (its glyph box) of one against those of the other that overlap it
    vertically — lines Mode.label_gap apart (document 16, slide 4 = CL TEXT_GAP at 0.6 em),
    an icon sibling_gap from anything within ICON_CLEAR of its height. A long last line
    below the neighbour's shorter stack takes no room (slide tgw: TGW A RT beside Dev VPC,
    100 instead of 134). plan() gives back the whole footprints where a HVH leaving a node
    sideways drops past its labels between it and the next node of its row (bedrock-dx
    PC → Internet), and asks (soft, documents) a labelled VHV's horizontal piece for its
    label + 8 each side past a split port. A node with lines through its bottom (top)
    port — V, VHV, the vertical end of a VH / HV — keeps every same-row sibling's icon or
    label line below (above) that port its half width + OBST_CLEAR + 1 (+ the port split:
    PORT_TOPBOT for two lines, PORT_PITCH per extra line) from its center, so the vertical
    line clears a neighbour's long last line (hard; the narrow band below the stack only).
 r. Diagonal siblings (W2; disjoint on both axes, decision DESIGN 4.3 #2 said "rows first"):
    the axis with the wider track gap, ties → y, for two nodes. A pair with a box in it that
    this sends to y goes on x instead when the solved x already keeps it its x gap apart,
    or when y would push the drawing's extent ≥ sibling_gap and x grows it ≤ that +
    sibling_gap (solve(): x cost per pair from an x solve with it; y cost from y solves
    without the open pairs and with each, the pairs put on y held, again until none
    moves; the rest re-solve x with their x separation). On x such a pair only keeps its
    row order on y: the later rows' top ≥ the earlier one's (nfw: VPC B beside the TGW,
    the slide spec's empty `att` column no longer needed; a Spoke RT above-left of a
    Security VPC no longer pushes its rows, and the spoke VPC AZ sharing them, down; the
    centralized-egress spec's empty `sp` column no longer needed).
 s. Twins (W2, layout_solve twin_sets): tree groups anywhere whose subtree has one
    signature — group types, titles (a vpc / account / region / onprem / cloud root's own
    excluded), CIDR or not, per box its nodes' icons, caption line counts (1 + sub) and
    border sides, every range as ranks among the tracks the subtree covers, each overlay
    whose members all lie in the subtree (type, title, header, ranges, members by index;
    an overlay crossing the subtree's boundary rules the box out) — plus, for a template
    instance, its instance number (instances of one template keep DESIGN 2.2's rule).
    Per axis each twin's measures from its L / T edge (its R / B, each subtree box's two
    edges in signature order, each covered track) are raised to the class's
    largest by soft lower bounds (why "twins alike …", dropped first in a positive cycle),
    re-solving x (with hug and flow centering) and y (with even_insets) until they hold, at
    most TWIN_ROUNDS; a round that leaves them less alike than the best one stops the loop
    and the best is kept; still unlike → one warning per class and axis.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_layout  # noqa: E402  (text_width, seg_hits_box; loads the icon bundle)
import layout_const as K  # noqa: E402

Number = Union[int, float]


# =======================================================================================
# Errors

class LayoutError(Exception):
    def __init__(self, problems: Sequence[str]):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


class SpecError(LayoutError):
    """W1: the spec is invalid (every problem, each prefixed with its spec location)."""


class SolveError(LayoutError):
    """W2: contradictory constraints (a positive cycle), named by Requirement.why/owner."""


# =======================================================================================
# Text width

def text_width(s: str, size: float) -> float:
    """The checker's estimate (0.55 em Latin, 1.0 em wide). See docstring section 7."""
    return check_layout.text_width(s, size)


def layout_text_width(s: str, size: float) -> float:
    """Conservative estimate for reserving space: 0.6 em Latin, wide characters 1.0 em."""
    w = 0.0
    for c in s:
        cw = check_layout.text_width(c, size)
        w += cw if cw >= size * K.WIDE_EM else size * K.LAYOUT_LATIN_EM
    return w


# =======================================================================================
# Input model (W1 output: expanded, validated)

@dataclass(frozen=True)
class Expr:
    """A parsed expression (section 6). kind: "num" | "node" | "label" | "group" | "col" |
    "row" | "gap". ref: the node/group/track id (gap: first track); ref2: gap's second
    track; attr: x0|x1|cx|y0|y1|cy for node/label/group, "" otherwise; offset: the ±n
    (for "num" the value itself)."""
    kind: str
    ref: str = ""
    attr: str = ""
    ref2: str = ""
    offset: float = 0.0


@dataclass(frozen=True)
class Place:
    """An explicit position: label_at {x, y, anchor} or step_at [x, y] (anchor ignored)."""
    x: Expr
    y: Expr
    anchor: str = "middle"          # start | middle | end


@dataclass
class Track:
    id: str
    axis: str                       # "col" (x, left → right) | "row" (y, top → bottom)
    index: int                      # position in spec cols / rows, 0-based
    min_gap_before: float = 0.0     # px: center − previous center ≥ this (0 = no extra)
    min_w: float = 0.0              # px: band width ≥ this (cols: width, rows: height)
    flow: Optional[float] = None    # pitch (px) of a flow row / flow column, None = grid track
    align: str = "center"           # flow columns: top | center | bottom in the parent's height


@dataclass
class Group:
    id: str                         # expanded id ("az.2", "tgwsn.1")
    type: str                       # key of layout_const.GROUP_STYLES
    label: Optional[str]            # final title ({n} substituted, type default applied); None = no title
    cidr: Optional[str] = None      # CIDR line text
    parent: Optional[str] = None    # containing group id; None = top level (outside every group). Overlays: None
    children: List[str] = field(default_factory=list)   # child group ids, spec order
    nodes: List[str] = field(default_factory=list)      # ids of nodes directly inside (`in`, not `on`)
    over: List[str] = field(default_factory=list)       # overlay member node ids (expanded); non-empty = overlay
    header: str = "right"           # overlay: header label placement vs the subnet header it crosses (right | below)
    cols: Optional[Tuple[str, str]] = None   # first / last col track its cells (descendants, over, span) cover; None = none
    rows: Optional[Tuple[str, str]] = None   # same for rows (a template instance always covers its `per` row)
    span_cols: Optional[Tuple[str, str]] = None   # spec `span` (already merged into cols/rows)
    span_rows: Optional[Tuple[str, str]] = None
    pad: Optional[float] = None     # px, overrides Mode.pad / pad_node for this group's children
    pad_top: Optional[float] = None  # px: box top → its first icon / nested box, when more than the type's header inset (decision m)
    pad_left: Optional[float] = None   # px: overrides `pad` on the left side only (decision m)
    pad_right: Optional[float] = None  # px: overrides `pad` on the right side only
    pad_bottom: Optional[float] = None  # px: overrides `pad` on the bottom only (decision m)
    min_w: Optional[float] = None   # px
    min_h: Optional[float] = None   # px
    dash: Optional[str] = None      # resolved stroke-dasharray (style default or spec `dash`), None = solid
    template: Optional[str] = None  # template base id for `per` instances and their descendants ("az")
    instance: Optional[int] = None  # 1-based AZ number n of that instance
    depth: int = 0                  # 0 = top level
    src: str = ""                   # spec location, "groups[4]"

    @property
    def overlay(self) -> bool:
        return bool(self.over)


@dataclass
class Node:
    id: str                         # expanded id ("nat.1")
    icon: str                       # resolved bundle ref "set/name"
    label: str                      # 14px label (per-instance value picked)
    sub: List[str] = field(default_factory=list)   # 12px sub-caption lines
    parent: Optional[str] = None    # containing group (`in`); for `on` nodes the VPC's parent; None = top level
    col: Optional[str] = None       # col track; colspan: first track (None = flow-row node)
    col2: Optional[str] = None      # colspan last track (`at: [b1..b2, r]`), None = no span
    row: Optional[str] = None       # row track (template instances: the instance's `per` row; None = flow-column node)
    on: Optional[str] = None        # border gateway: the VPC group id it straddles
    side: Optional[str] = None      # `on` nodes: "left" | "right" border (W1 from track indices); phase 2 top|bottom
    dx: float = 0.0                 # px nudges from the grid position
    dy: float = 0.0
    xy: Optional[Tuple[Union[float, "Expr"], Union[float, "Expr"]]] = None   # icon center (escape hatch); overrides
                                    # col/row: a number is absolute, an Expr (col/row, a node's icon attr, a group's
                                    # edge, ±n) ties the center to the solve (W2 equalities)
    flow_index: Optional[int] = None   # flow-row / flow-column node: 0-based order among the track's nodes in the same parent
    icon_query: Optional[str] = None   # the spec's alias when the icon was given as one (for the summary)
    template: Optional[str] = None
    instance: Optional[int] = None
    src: str = ""


@dataclass
class Edge:
    n: int                          # 0-based index in Spec.edges; element id "edge:<n>"
    a: str                          # near endpoint id (node or group), as written left of OP
    b: str                          # far endpoint id
    op: str                         # "->" "<->" "--" "..>" "<..>" ".."
    a_kind: str = "node"            # "node" | "group"
    b_kind: str = "node"
    label: Optional[str] = None     # protocol / port, 12px #232F3E
    verb: Optional[str] = None      # verb / attachment type, 12px #545B64
    step: Optional[int] = None      # badge number on this instance (resolved)
    step_at: Union[str, Place] = "mid"     # mid | start | end | gap | stem | branch | Place
    label_at: Union[None, str, Place] = None   # None = auto; above | below | left | right | Place
    trunk: bool = False             # merge the instances of this spec line into one trunk
    fork: Optional[str] = None      # "bus" (phase 2)
    shape: Optional[str] = None     # H V HVH VHV HV VH (None = rule-based)
    bend_x: Union[None, str, Expr] = None   # "gap" or an Expr
    bend_y: Union[None, str, Expr] = None
    from_side: Optional[str] = None  # left | right | top | bottom
    to_side: Optional[str] = None
    from_offset: Optional[float] = None   # px along the side from its center
    to_offset: Optional[float] = None
    points: Optional[List[Tuple[Expr, Expr]]] = None   # full polyline incl. ends (escape hatch)
    line: int = 0                   # index of the spec edge this instance came from
    k: int = 0                      # instance index within that spec edge, 0-based
    src: str = ""                   # "edges[4]"

    @property
    def dashed(self) -> bool:
        return K.EDGE_OPS[self.op][0]

    @property
    def head_end(self) -> bool:     # arrowhead at b (marker-end)
        return K.EDGE_OPS[self.op][1]

    @property
    def head_start(self) -> bool:   # arrowhead at a (marker-start)
        return K.EDGE_OPS[self.op][2]


@dataclass
class NoteSpec:
    place: str = "auto"             # auto | panel | pane | lines
    width: Optional[float] = None   # pane width; None = auto (300 / 320 / left column)
    steps: List[Tuple[str, str]] = field(default_factory=list)   # (hop, description); number = index + 1
    summary: Optional[str] = None   # one-line summary (panel)
    rows: List[Tuple[str, str]] = field(default_factory=list)    # (row label, text) (panel)
    src: str = "note"


@dataclass
class RawSpec:
    layer: str                      # below | above
    svg: str                        # fragment with {expr} placeholders, as written
    exprs: Dict[str, Expr] = field(default_factory=dict)   # placeholder text → parsed Expr
    src: str = ""


@dataclass
class Spec:
    name: str                       # output stem (<name>.draft.svg)
    mode: str = "document"          # document | slide
    title: bool = True              # slide: a title band above the diagram (540 vs 600 limit)
    S: float = K.S_DEFAULT          # node icon size
    font: str = K.FONT_FAMILY_DEFAULT   # root font-family attribute value
    cols: List[Track] = field(default_factory=list)
    rows: List[Track] = field(default_factory=list)
    groups: Dict[str, Group] = field(default_factory=dict)   # containment preorder, overlays last
    nodes: Dict[str, Node] = field(default_factory=dict)     # spec order, template instances in place
    edges: List[Edge] = field(default_factory=list)          # Edge.n == index
    note: Optional[NoteSpec] = None
    raw: List[RawSpec] = field(default_factory=list)
    source: str = ""                # path, or "<dict>"
    warnings: List[str] = field(default_factory=list)

    @property
    def const(self) -> K.Mode:
        return K.mode(self.mode)

    def track(self, tid: str) -> Track:
        for t in self.cols + self.rows:
            if t.id == tid:
                return t
        raise KeyError(tid)

    def cloud_id(self) -> Optional[str]:
        return next((g.id for g in self.groups.values() if g.type == "cloud"), None)

    def kind(self, eid: str) -> str:
        """"node" or "group" for an endpoint / expression id."""
        if eid in self.nodes:
            return "node"
        if eid in self.groups:
            return "group"
        raise KeyError(eid)

    def ancestors(self, gid: Optional[str]) -> List[str]:
        """gid's chain upward, gid first (overlays: just themselves)."""
        out = []
        while gid is not None:
            out.append(gid)
            gid = self.groups[gid].parent
        return out

    def node_chain(self, nid: str) -> List[str]:
        """The groups containing a node, innermost first."""
        return self.ancestors(self.nodes[nid].parent)

    def flow_stacks(self) -> Dict[Tuple[Optional[str], str], List[str]]:
        """Flow columns: {(parent, col track): node ids top → bottom} — the nodes that give
        `col:` only (row None, outside a template), in flow_index order (decision l)."""
        out: Dict[Tuple[Optional[str], str], List[str]] = {}
        for n in self.nodes.values():
            if n.row is None and n.col is not None and n.col2 is None and n.xy is None and n.on is None:
                out.setdefault((n.parent, n.col), []).append(n.id)
        for ids in out.values():
            ids.sort(key=lambda i: self.nodes[i].flow_index or 0)
        return out

    def float_align(self, gid: str) -> Optional[str]:
        """A box that holds flow-column nodes and covers no row (decision l): the align of
        its first flow column (spec order); None for any other group."""
        g = self.groups[gid]
        if g.rows is not None or g.overlay:
            return None
        for (parent, col) in self.flow_stacks():
            if gid in self.ancestors(parent):
                return self.track(col).align
        return None

    def flow_slot(self, parent: Optional[str], align: str) -> Optional[float]:
        """Where a flow column's stack in `parent` (or a box holding only stacks) sits among
        the row tracks, as a fractional row index (decision l): half a row above the
        parent's first row (align top), below its last (bottom), centered between the rows
        above and below the middle (an odd middle row counts below). A box holding only
        stacks takes the slot it gets in its own parent; the top level spans every row.
        None when nothing gives rows."""
        if parent is None:
            if not self.rows:
                return None
            r0, r1 = 0, len(self.rows) - 1
        else:
            g = self.groups[parent]
            if g.rows is None:
                a = self.float_align(parent)
                return None if a is None else self.flow_slot(g.parent, a)
            r0, r1 = self.track(g.rows[0]).index, self.track(g.rows[1]).index
        if align == "top":
            return r0 - 0.5
        if align == "bottom":
            return r1 + 0.5
        return math.floor((r0 + r1) / 2 + 0.5) - 0.5

    def flow_row_above(self, parent: Optional[str], align: str, row: int) -> Optional[bool]:
        """Whether a flow row of `parent` on row index `row` goes above a stack block of
        the same parent aligned `align` (decision l), when its nodes meet the block on x: a
        row on the parent's first row above a top-aligned block and one on its last row below
        a bottom-aligned block (the row keeps the parent's edge and the block stops at it
        instead of taking that edge and pushing the row a block height inward); any other row
        above when it lies before the block's slot (Spec.flow_slot), else below. None when
        nothing gives rows."""
        slot = self.flow_slot(parent, align)
        if slot is None:
            return None
        if parent is None:
            r0, r1 = 0, len(self.rows) - 1
        else:
            g = self.groups[parent]
            if g.rows is None:
                return row < slot
            r0, r1 = self.track(g.rows[0]).index, self.track(g.rows[1]).index
        if align == "top" and row == r0:
            return True
        if align == "bottom" and row == r1:
            return False
        return row < slot


# =======================================================================================
# Geometry (W2 output)

@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @classmethod
    def xywh(cls, x: float, y: float, w: float, h: float) -> "Box":
        return cls(x, y, x + w, y + h)

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def t(self) -> Tuple[float, float, float, float]:
        """(x0, y0, x1, y1): the tuple check_layout's helpers (seg_hits_box, ...) take."""
        return (self.x0, self.y0, self.x1, self.y1)

    def expand(self, d: float) -> "Box":
        return Box(self.x0 - d, self.y0 - d, self.x1 + d, self.y1 + d)

    def union(self, o: "Box") -> "Box":
        return Box(min(self.x0, o.x0), min(self.y0, o.y0), max(self.x1, o.x1), max(self.y1, o.y1))

    def overlaps(self, o: "Box") -> bool:
        return self.x0 < o.x1 and o.x0 < self.x1 and self.y0 < o.y1 and o.y0 < self.y1

    def contains(self, o: "Box", tol: float = 0.0) -> bool:
        return (self.x0 - tol <= o.x0 and self.y0 - tol <= o.y0
                and o.x1 <= self.x1 + tol and o.y1 <= self.y1 + tol)

    def get(self, attr: str) -> float:
        """x0 | x1 | cx | y0 | y1 | cy (expression attributes)."""
        return getattr(self, attr)


def union_all(boxes: Sequence[Box]) -> Optional[Box]:
    out = None
    for b in boxes:
        out = b if out is None else out.union(b)
    return out


@dataclass
class TextLine:
    """One <text>: baseline position and style."""
    text: str
    x: float
    y: float                        # baseline
    size: float
    fill: str
    weight: str = ""                # "" regular | "600" | "700"
    anchor: str = "start"           # start | middle | end

    def width(self, conservative: bool = False) -> float:
        return (layout_text_width if conservative else text_width)(self.text, self.size)

    def box(self, conservative: bool = False) -> Box:
        """Glyph box: baseline − 0.75 size to baseline + 0.25 size (QR 79)."""
        w = self.width(conservative)
        x0 = self.x - w / 2 if self.anchor == "middle" else self.x - w if self.anchor == "end" else self.x
        return Box(x0, self.y - K.GLYPH_ASCENT * self.size, x0 + w, self.y + K.GLYPH_DESCENT * self.size)


@dataclass
class GroupGeom:
    id: str
    rect: Box
    badge: Optional[Box] = None     # badge image box (top-left = rect top-left; 24, cloud 32)
    title: Optional[TextLine] = None
    cidr: Optional[TextLine] = None

    def header(self, conservative: bool = False) -> Optional[Box]:
        """Union of badge, title and CIDR glyph boxes (what edges and labels avoid)."""
        parts = [self.badge] if self.badge else []
        parts += [t.box(conservative) for t in (self.title, self.cidr) if t]
        return union_all(parts)


@dataclass
class NodeGeom:
    id: str
    cx: float                       # icon center
    cy: float
    icon: Box                       # cx ± S/2, cy ± S/2
    lines: List[TextLine] = field(default_factory=list)   # label (baseline icon.y1 + 18) then sub lines (+16 each)
    mask: Optional[Box] = None      # border nodes: white mask (x = cx − w/2, y = icon.y0, h = S + mask_extra + 16·extra lines)
    side: Optional[str] = None      # border nodes: left | right

    def stack(self, conservative: bool = False) -> Optional[Box]:
        return union_all([t.box(conservative) for t in self.lines])

    @property
    def last_baseline(self) -> float:
        return self.lines[-1].y if self.lines else self.icon.y1

    def footprint(self, conservative: bool = True) -> Box:
        """Icon ∪ label stack ∪ mask: the space the node occupies (conservative by default)."""
        return union_all([self.icon] + ([self.stack(conservative)] if self.lines else [])
                         + ([self.mask] if self.mask else []))


@dataclass
class Geometry:
    mode: str
    S: float
    canvas_w: float
    canvas_h: float
    cols: Dict[str, float]          # col track id → center x (spec order)
    rows: Dict[str, float]          # row track id → center y
    col_extent: Dict[str, Tuple[float, float]] = field(default_factory=dict)   # (x0, x1) union of footprints centered on the track
    row_extent: Dict[str, Tuple[float, float]] = field(default_factory=dict)   # (y0, y1) likewise
    groups: Dict[str, GroupGeom] = field(default_factory=dict)   # draw order = Spec.groups order
    nodes: Dict[str, NodeGeom] = field(default_factory=dict)     # Spec.nodes order
    drawing: Box = field(default_factory=lambda: Box(0, 0, 0, 0))   # union of group rects and node footprints
    explain: List[str] = field(default_factory=list)   # --explain lines: which constraint set each gap
    warnings: List[str] = field(default_factory=list)

    def track(self, tid: str) -> float:
        return self.cols[tid] if tid in self.cols else self.rows[tid]

    def gap(self, a: str, b: str) -> float:
        """Middle of the widest free corridor strictly between tracks a and b (same axis).

        Obstacles: every node footprint (an interval) and every group border on that axis
        (a point) inside the range; the widest remaining interval wins, ties → the first.
        Escape-hatch helper (`gap(a,b)` expressions); W3 may search corridors better."""
        x_axis = a in self.cols
        if x_axis != (b in self.cols):
            raise KeyError(f"gap({a},{b}): tracks on different axes")
        lo, hi = sorted((self.track(a), self.track(b)))
        blocks = []
        for n in self.nodes.values():
            f = n.footprint()
            blocks.append((f.x0, f.x1) if x_axis else (f.y0, f.y1))
        for g in self.groups.values():
            r = g.rect
            for v in ((r.x0, r.x1) if x_axis else (r.y0, r.y1)):
                blocks.append((v, v))
        cuts = sorted((max(lo, s), min(hi, e)) for s, e in blocks if e > lo and s < hi)
        best, cur = None, lo
        for s, e in cuts + [(hi, hi)]:
            if s > cur and (best is None or s - cur > best[1] - best[0]):
                best = (cur, s)
            cur = max(cur, e)
        return (best[0] + best[1]) / 2 if best else (lo + hi) / 2


def eval_expr(e: Expr, geom: Geometry) -> float:
    if e.kind == "num":
        return e.offset
    if e.kind == "node":
        base = geom.nodes[e.ref].icon.get(e.attr)
    elif e.kind == "label":
        st = geom.nodes[e.ref].stack()
        base = (st or geom.nodes[e.ref].icon).get(e.attr)
    elif e.kind == "group":
        base = geom.groups[e.ref].rect.get(e.attr)
    elif e.kind == "col":
        base = geom.cols[e.ref]
    elif e.kind == "row":
        base = geom.rows[e.ref]
    elif e.kind == "gap":
        base = geom.gap(e.ref, e.ref2)
    else:
        raise ValueError(f"unknown expression kind {e.kind!r}")
    return base + e.offset


# =======================================================================================
# Requirements (W3 plan, W4 block, W5 feedback → W2 solve)

@dataclass(frozen=True)
class Requirement:
    axis: str                       # "x" | "y"
    a: str                          # variable (section 4)
    b: str                          # variable
    d: float                        # value(b) − value(a) ≥ d, px (may be negative)
    why: str                        # short reason for --explain / errors ("arrow 48 + end 4 into igw")
    owner: str                      # element id of the requirer ("edge:3", "note", "node:igw")
    soft: bool = False              # a preference W2 may drop to break a positive cycle


# =======================================================================================
# The note (W4 output)

@dataclass
class NoteBlock:
    place: str                      # panel | pane | lines | none
    w: float = 0.0                  # rect width (panel: canvas_w − 32 of the geom it was built on)
    h: float = 0.0                  # panel/pane: rect height; lines: canvas bottom − drawing bottom
    rect: Optional[Box] = None      # where it sits in that geom (None for none)
    elements: List["Element"] = field(default_factory=list)   # z Z_NOTE, owner "note"
    requirements: List[Requirement] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def below(self) -> float:
        """Canvas height added below the drawing's bottom (section 4)."""
        if self.place == "panel":
            return K.PANEL_GAP + self.h + K.PANEL_GAP
        if self.place == "lines":
            return self.h
        return 0.0


# =======================================================================================
# Elements (→ W5 emit)

@dataclass
class Element:
    kind: str                       # rect | image | text | line | polyline | circle | raw
    attrs: Dict[str, Union[str, Number]]   # SVG attributes in output order; numbers → fmt_num
    text: Optional[str] = None      # <text> content; raw: the SVG fragment
    z: int = K.Z_GROUP
    owner: str = ""                 # element id (section 5)


def fmt_num(v: Number) -> str:
    """≤ 2 decimals, integral values without a decimal point ("179.4", "222", "-8")."""
    s = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def node_eid(nid: str) -> str:
    return f"node:{nid}"


def group_eid(gid: str) -> str:
    return f"group:{gid}"


def edge_eid(n: int) -> str:
    return f"edge:{n}"


NOTE_EID = "note"


def raw_eid(i: int) -> str:
    return f"raw:{i}"


def split_eid(eid: str) -> Tuple[str, str, str]:
    """"edge:3:label" → ("edge", "3", "label"); "node:nat.1" → ("node", "nat.1", ""); "note" → ("note", "", "")."""
    parts = eid.split(":")
    return (parts[0], parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else "")


def g_id(owner: str, z: int) -> str:
    """The <g id> for an owner's run of elements in layer z (section 5)."""
    kind = owner.split(":", 1)[0]
    home = {"group": K.Z_GROUP, "node": K.Z_NODE, "edge": K.Z_EDGE, "note": K.Z_NOTE}.get(kind)
    if home is None or home == z:
        return owner
    return f"{owner}:{K.Z_PART.get(z, f'z{z}')}"


# Factories: one attribute order everywhere (the examples' most common order).

def el_rect(box: Box, *, fill: str = "none", stroke: Optional[str] = None, width: Optional[float] = None,
            dash: Optional[str] = None, z: int = K.Z_GROUP, owner: str = "") -> Element:
    a: Dict[str, Union[str, Number]] = {"x": box.x0, "y": box.y0, "width": box.w, "height": box.h, "fill": fill}
    if stroke:
        a["stroke"] = stroke
        a["stroke-width"] = width if width is not None else 1
    if dash:
        a["stroke-dasharray"] = dash
    return Element("rect", a, z=z, owner=owner)


def el_image(ref: str, box: Box, *, z: int = K.Z_NODE, owner: str = "") -> Element:
    return Element("image", {"href": f"bundle:{ref}", "x": box.x0, "y": box.y0, "width": box.w, "height": box.h},
                   z=z, owner=owner)


def el_text(t: TextLine, *, z: int = K.Z_NODE, owner: str = "") -> Element:
    a: Dict[str, Union[str, Number]] = {"x": t.x, "y": t.y, "font-size": t.size}
    if t.anchor != "start":
        a["text-anchor"] = t.anchor
    a["fill"] = t.fill
    if t.weight:
        a["font-weight"] = t.weight
    return Element("text", a, text=t.text, z=z, owner=owner)


def _stroke(a: Dict[str, Union[str, Number]], dash: Optional[str], start: bool, end: bool,
            color: str, width: float) -> None:
    a["stroke"] = color
    a["stroke-width"] = width
    if dash:
        a["stroke-dasharray"] = dash
    if start:
        a["marker-start"] = K.MARKER_START_ATTR
    if end:
        a["marker-end"] = K.MARKER_END_ATTR


def el_path(points: Sequence[Tuple[float, float]], *, dash: Optional[str] = None, start: bool = False,
            end: bool = False, color: str = K.LINE_COLOR, width: float = K.LINE_WIDTH,
            z: int = K.Z_EDGE, owner: str = "") -> Element:
    """A connector: <line> for two points, <polyline fill="none"> for more."""
    if len(points) < 2:
        raise ValueError("a path needs two points")
    if len(points) == 2:
        (x1, y1), (x2, y2) = points
        a: Dict[str, Union[str, Number]] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        _stroke(a, dash, start, end, color, width)
        return Element("line", a, z=z, owner=owner)
    a = {"points": " ".join(f"{fmt_num(x)},{fmt_num(y)}" for x, y in points), "fill": "none"}
    _stroke(a, dash, start, end, color, width)
    return Element("polyline", a, z=z, owner=owner)


def el_circle(cx: float, cy: float, r: float, fill: str, *, z: int = K.Z_BADGE, owner: str = "") -> Element:
    return Element("circle", {"cx": cx, "cy": cy, "r": r, "fill": fill}, z=z, owner=owner)


def el_badge(cx: float, cy: float, n: int, *, z: int = K.Z_BADGE, owner: str = "") -> List[Element]:
    """A step badge: circle r 10 #232F3E, digit 12px 700 #FFFFFF at baseline cy + 4 (QR 158)."""
    st = K.TEXT_BADGE
    digit = TextLine(str(n), cx, cy + K.BADGE_TEXT_DY, st.size, st.fill, st.weight, "middle")
    return [el_circle(cx, cy, K.BADGE_R, K.BADGE_FILL, z=z, owner=owner), el_text(digit, z=z, owner=owner)]


def el_raw(svg: str, *, z: int, owner: str) -> Element:
    return Element("raw", {}, text=svg, z=z, owner=owner)
