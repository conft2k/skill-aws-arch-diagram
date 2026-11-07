# Rule checker design

Written on main 38c44fd; step 1 (report-only `scripts/rules.py`) is done. §6 holds the user's threshold decisions. Remaining steps: [backlog.md](backlog.md).

## 0. Facts
- Drafts wrap each owner run in `<g id>`: `edge:n`, `edge:n:label`, `edge:n:badge`, `edge:n:masked`, `node:<id>`, `group:<id>`; connectors carry `data-flow` ("<line>" trunk/fork, "<line>.<k>" otherwise).
- Geometry: icon boxes, footprint(), group rects, track centres; twin measures are variable pairs; `layout.value(var, geom, axis)` evaluates them.
- Route-table association is NOT derivable from the spec (RT nodes have no edges; nfw has two tables on one hub) → explicit key needed.

## 1. Rules and predicates
`Drawn.parse(draft)`: runs check_layout.collect once, keeps the owner map (today inline in layout.problems_of): paths {n: [seg]}, labels {n: [text]}, badges {n: [(cx,cy,digit)]}, masked {n: rect}.

### R-flow (pairs of connectors with different data-flow)
- F1 on-line: check_layout.lines_on_lines (reuse).
- F2 in-line: check_layout.lines_in_line (reuse).
- F3 junction crossing (new): two segments of different flows cross properly at c; violation if within JUNCTION_REACH = K.PORT_PITCH (12) of c there is a bend of either line or the icon box of a node where either line ends. Generalises router `_conflicts` crossing clause. Write as pure fn check_layout.crossings_at_joins(paths, feet).
- F4 arrow target (spec): head tip must hit geom.nodes[e.b].icon via end_icon, no other footprint within ICON_CLEAR (8); group end: tip within END_REACH of group rect border, no other border within BORDER_CLEAR.
- F5 attribution: per label box/badge of edge n: d_own = distance to n's net, d_other = nearest other-flow connector; violation if d_own > LABEL_REACH (14) or d_other ≤ d_own + TEXT_GAP (4).

### R-rt
Spec: node key `for: [ids]` (+ optional `via: <hub>`). W1 resolves to Node.assoc = Assoc(hub, ends, edges): hub = unique node with an edge to every listed id; `*` expands; no hub and all ids groups → subnet association; zero/many hubs → SpecError asking for `via`. RT icon without `for` → lint warning, unchecked.
Declarations: nfw (doc+slide) rtsp for [vpca, vpcb], rtfw for [eni.*]; centralized-egress rtsp for [enia.*, enib.*], rtfw for [seni.*]; tgw (doc+slide) rta for [vpn, svcs, prod, dev, test, peer], rtb for [peer, dr, ana].
Bracket(A): hub h, associated edges A, others N. P_e drawn path oriented from h; o_e end footprint (or tip point for a group end). Order all edges at h cyclically by port angle (tie: far tip angle). For cyclically consecutive i,j both in A: W_ij = polygon(P_i + reverse(P_j)) closed port_j→port_i, ∪ hull(o_i ∪ o_j). Bracket = union; wedges with a non-associated bound don't count.
- RT1: |A| ≥ 2 → centre(r) ∈ Bracket(A) (even-odd).
- RT2: |A| = 1 → gap(foot(r), P) ≤ S + sibling_gap, P = nearest connector, segment r→P crosses no connector.
- RT3: segment centre(r)→centre(h) crosses no connector of N nor other hub's line more than 12 px from h's icon.
- RT4: gap(r,h) < gap to any other hub and to any end object of N.
- RT5 subnet RT: closer to each associated subnet rect than any other subnet by ≥ 8 px, inside none of the others.
Checked on goldens: nfw Spoke RT (296,382) inside spoke paths + chord x=216 (stacked x<216 is outside); nfw Firewall RT x=532 inside TGW top/bottom→ENI wedge; tgw TGW A RT inside hull of Dev/Test.

### R-twin
Public `layout_solve.twin_classes(spec)` (today _Model.twin_sets/_twin_measures) + node centres rel. to twin L/T; violation if spread > 0.5 px (cost = spread). Negative half is a unit test of twin_classes.

### R-label
- L1: own nearest piece horizontal and box bottom ≤ line y with x overlap; or vertical and box x0 ≥ line x with y overlap; or masked[n] covers it and the piece passes under. Explicit label_at exempt.
- L2: drawn digits multiset == {1..len(note.steps)} once each.

### R-fit
Slide cost = max(0, 10 − K.slide_pt).

## 2. scripts/rules.py
Violation(rule, owners, message, cost, tier) — tier 0 hard, 2 fit.
check(spec, geom, draft, drawn=None) -> [Violation]  (= corpus hook); score(viol, probs, geom, spec, misses) -> tuple.
Single source: import thresholds/helpers from check_layout (ON_LINE_GAP, IN_LINE_GAP, LABEL_REACH, END_REACH, node_stacks, footprints, end_icon, collinear_run, in_line_gap). Drawn.parse replaces owner walk in layout.problems_of; Advisor(root=) parses once; layout.value → M.var_value; LINE ON LINE promoted to rule tier, not counted twice.

## 3. Engine selection
Decisions(diag: FrozenSet[pairkey]|None, overlay: ((gid, beside|above)), skip: ((n,k)), place) — solve(spec, reqs, note_block, decisions) replaces diag_x; Geometry.diag_pairs lists open pairs with default axis and x/y cost (prior).
Neighbours from violations, sorted (tier, rule, owners): R-rt on r → flip each diag pair with r (x first), then all r's pairs; R-flow/R-label on n,m → skip[n]+=1, skip[m]+=1 (max 3); R-twin → copy A's pair decisions to B; overlay header text → flip; R-fit → all pairs on x, then alt note places.
Hill-climb best improvement, strictly lower score, ties → earlier; budget count MAX_CANDIDATES 12 (16 slides); skip-only reuse cached geometry; rules before check_layout, prune worse tier 0; then existing feedback loop (≤5) on winner; a round adding a rule violation never kept.
Score: (n tier-0, Σ tier-0 cost, n check problems, R-fit pt short, shape misses, canvas area).
Removable later: _stacked_between, lines_past/_inside/_past, diag_boxes, decision r stacked clause; layout.build slide diag_x retry + Geometry.diag_y; router _conflicts (→ shared F2/F3); nfw `shape: VH` workaround. _diagonals weighing stays as prior.

## 4. Migration (each verified on tests/corpus via run_corpus.py)
- Step 0 refactor (Drawn.parse, M.var_value, twin_classes, Advisor(root=)): corpus drafts byte-identical, tests pass.
- Step 1 checker only (rules.py, for/via key, for in 5 RT examples, `rule:` lines in summary, exit unchanged): good-tagged cases 0 violations of their rule; bad-tagged cases ≥1 naming the owner; drafts byte-identical; ≤10% time.
- Step 2 engine selection: total violations ≤ step 1, 0 on fixable; no check-count rise; changed drafts = listed; deterministic; ≤3× time.
- Step 3 remove heuristics one commit each: verdicts/check counts unchanged or better.

## 5. Risks / scope
Run time (budget, caching, pruning); false verdicts (report-only first, corpus tags both ways, shared constants, RT3 ignores within 12 px of hub); over-constraining (lexicographic min + report; R-rt > R-fit; R-twin vs R-rt by tiers). Out of scope: AWS correctness of `for`, grid reordering, global optimisation, spec rules on hand-drawn SVGs, geometric "not forced alike", PPTX.

## 6. User decisions (2026-11-07, after seeing tgw / nlb-mtls / latest2 cases)
- RT1: a route table right beside its hub passes when every line at that hub is associated with it (the "only table
  beside the hub" case, tgw TGW B RT) — no bracket needed then.
- F5: labels and badges the spec places itself (label_at / step_at coordinates) are exempt, like L1.
- L1: near a corner, the label passes when it is on the rule side of ANY own piece within LABEL_REACH (above a
  horizontal piece or right of a vertical one), not only the single nearest piece.
- RT2 (2026-11-07, saw rt2.png): a one-line RT passes within 2S + sibling_gap of its line (document 112, slide 108);
  was S + sibling_gap (64/60). rt/single (88) and rt/hub (97) pass; rt/nd-single document 135 stays a violation.
- RT1 (saw rt1.png): stays strict — rt/three-b Firewall RT (beside TGW, below both associated lines) is a violation;
  step 2 should steer the layout to wrap the RT like nfw.
- Border hug (saw hug.png): a line running along a group border closer than 12px (check_layout LINE HUGS BORDER)
  becomes a tier-0 rule (R-border) avoided first in step 2; also flag a line crossing a group's header band
  (between its icon and title), which check_layout misses today.

Implementation update (`b2-check`, 2026-11-07): B2 now shares check_layout's public
`header_bands` / `lines_in_headers` predicates and reports `LINE IN HEADER`. Feedback
repairs the retained draft's remaining B2 with header routing obstacles, then wall-to-end
space requirements, keeping other check/rule counts and fitting slides from regressing.
Corpus B2 is 63→6; [validation and remaining cases](b2-check.md).
