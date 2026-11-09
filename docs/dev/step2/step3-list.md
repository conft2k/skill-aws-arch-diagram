# Step 3 list: placement heuristics and the corpus evidence for removing them

Ticket 09, second item. For each case-by-case placement heuristic, the engine was run with that heuristic disabled, on the full corpus (the nfw spec hint on its nfw entries only), with the rule checker. Each run is compared with main 601099d (`~/.cache/skill-design/baseline/main-601099d.json` and `main-601099d-drafts`). The disabled copy is a scratch copy and was not committed. Each patch is in the evidence directory as `patch.diff`.

## How to read this

- **Removable now:** 0 runs worse, no new tier-0 identity, and check problems do not rise.
- **Removable after a prerequisite:** what blocks removal is named. Selection needs that prerequisite before it can do the heuristic's job.
- **Keep:** selection does not do the job yet. The worse cases are listed.
- A *new tier-0 identity* is a rule, code and owner set that the baseline run does not have, counted per run.
- **Runtime is not judged here.** These runs used `-j 2` on a loaded machine, and the baseline used `-j 6`. A run that changes only the slide nfw spec measured a summed ratio of 1.66× from load alone.
- **"Cases served"** means two things here:
  - the cases the code, its tests and its commit name;
  - the corpus runs whose draft changes when the heuristic is off.
- Evidence for each heuristic is under `~/.cache/skill-design/improve/t09/<slug>/`:
  - `report.json` (the `comparison` key holds the per-run verdicts)
  - `summary.txt` (counts, deltas, new identities, changed runs)
  - `worse.txt` (the first verdict term that got worse)
  - `patch.diff`
  - `drafts/`
- The scripts that made these files are `run.sh`, `patches/*.py`, `analyze.py` and `worse.py` in the same directory.

## Summary

| # | Heuristic | Better / same / worse | New tier-0 ids | Check Δ | Tier-0 Σ (160 at base) | Classification |
|---|---|---|---|---|---|---|
| 1 | `_stacked_between` + `lines_past` / `_inside` / `_past` / `diag_boxes` (rule r stacked clause) | 31 / 730 / 14 | 8 | 0 | 168 | keep |
| 2 | slide diag_x retry in `layout.build_at_size` + `Geometry.diag_y` | 7 / 763 / 5 | 5 | −2 | 158 | after prerequisite |
| 3 | router `_conflicts` in `ranked_routes` | 1 / 765 / 9 | 3 | 0 | 164 | keep |
| 4 | nfw slide `shape: VH` workaround (spec hint) | 0 / 3 / 2 (nfw filter) | 0 | 0 | 0 → 0 | after prerequisite |
| 5 | note `_pane_free` (document pane when items sit left of the Cloud) | 1 / 771 / 3 | 1 | +3 | 161 | keep |
| 6 | `_overlay_beside` default rule (short overlay title beside the first row) | 18 / 738 / 19 | 0 | −7 | 159 | after prerequisite |
| 7 | router `_u_taken` rank tier (a detour onto a side another edge's shape uses ranks last) | 5 / 768 / 2 | 2 | −2 | 162 | keep |
| 8 | router `_crowded` (a fallback end < PORT_PITCH from another port is unclean) | 0 / 775 / 0, 0 drafts changed | 0 | 0 | 160 | removable now |
| 9 | `_Model._x_apart` pre-open rule (a pair the solved x keeps apart goes on x before it is open) | 40 / 717 / 18 | 4 | −6 | 160 | keep |

The baseline has 775 runs. A run counts as changed when its draft bytes differ from the baseline draft.

## 1. `_stacked_between` and its helpers

- **Location:**
  - `scripts/layout_solve.py`: `_stacked_between`, `_Model.lines_past`, `_Model._inside`, `_Model._past`, `_Model.diag_boxes` (appended in `_Model._siblings`), and the `stacked` branch of `_diagonals`.
  - `scripts/layout_model.py`: the "stacked between" clause of rule r.
- **Disabled by:** `stacked = []` in `_diagonals`.
- **Cases it names:**
  - the Spoke RT between VPC A and VPC B (nfw);
  - in tests (commits 2d40d4a and 38c44fd): nfw slide, mirrored columns, wide label, nudged table, unequal spokes, node between boxes inside / without their lines.
- **Changed drafts:** 48 runs in 26 cases:
  - `rt/` alb-nat, alb-ret, att, ce-right, ce-three, dash, dx30, fork, gw-ret, hub, longlabel, longvpc, nfw-colspan, nfw-dx, nodeends, onelines, rtsub, sgw-ret, tgwside, three, tmpl, tmpl-doc, tmpl-rev, tmpl-trunk, wide-a;
  - `trunk/merge-vfan`.
  - The docs/examples nfw drafts do not change.
- **Result:**
  - 31 better, 730 same, 14 worse.
  - R-rt +7, R-flow +1, tier-0 160 → 168, check problems ±0.
  - 1 tag miss: `rt/hub` document, good R-rt.
- **Worse:**
  - New tier-0, 8 runs:
    - R-rt RT1 rtsp in `rt/longvpc`, `dash`, `fork`, `rtsub`, `tmpl-doc` and `tmpl-rev` (document);
    - R-rt RT2 in `rt/hub` (document);
    - R-flow F5 in `rt/sgw-ret` (document).
  - Canvas area: `rt/longvpc` and `rt/wide-a` (slide, slide-no-title).
  - Text shortfall: `rt/att` (slide, slide-no-title).
- **Better:** all 31 by text shortfall (20) or canvas area (11), none by rules. Without the clause the pairs are weighed, so the drawings come out smaller.
- **Why selection does not cover it:** in the worse runs the engine warns `unresolved R-rt RT1 (node:rtsp, node:tgw)`. The R-rt neighbours (flip the table's diagonal pairs) do not bring the table back inside its bracket within the budget.
- **Classification:** keep.
- **Evidence:** `~/.cache/skill-design/improve/t09/stacked-between/`

## 2. Slide diag_x retry

- **Location:** `scripts/layout.py` `build_at_size`, the `b.geom.diag_y and slide_problem(...)` block, and `Geometry.diag_y` (`scripts/layout_solve.py` `_solve_once`, `scripts/layout_model.py`).
- **Disabled by:** `if False and ...` on that block.
- **Cases it names:**
  - slides/nfw without the `att` column (commit 2be286c);
  - tests: `test_slide_too_small_on_y_goes_on_x`, `test_a_fitting_slide_keeps_the_weighing`.
  - Neither docs/examples nfw draft changes.
- **Changed drafts:** 12 runs.
- **Result:**
  - 7 better, 763 same, 5 worse.
  - R-border −2, R-fit −1, tier-0 160 → 158, check problems −2.
- **Worse:**
  - `rt/onelines` slide-no-title: new F1 and F3 edge:0,edge:1, and LINE ON LINE +1.
  - `rt/sgw-ret` slide: a canvas clipping check (LINE OFF CANVAS) +1, new F3 edge:1,edge:8, checks +8.
  - `rt/gw-ret` slide: checks +1.
  - `rt/onelines` slide and `rt/single-below` slide: canvas area.
  - New tier-0 identities: 5. The 2 in `qa/t1-privatelink` come with fewer violations overall.
- **Better:**
  - `qa/t1-privatelink` slide and slide-no-title: tier-0 3→1 and 4→1, checks −6 each.
  - Text shortfall: `bench/latest3-pipeline` (2 runs), the gwlb and nlb examples (slide), and `rt/gw-ret` slide-no-title.
  - So the retry, which keeps the larger text without judging rules, costs `qa/t1-privatelink` two tier-0 violations on slides.
- **Classification:** removable after a prerequisite.
  - Prerequisite: the cases it still serves (`rt/onelines`, `rt/sgw-ret`, `rt/gw-ret`, `rt/single-below` slides) must come out at least as good through selection's own "every pair on x" R-fit candidate. Today that candidate does not reach them.
  - Judging the retry by the full verdict instead of by text size alone would also stop the `qa/t1-privatelink` loss.
- **Evidence:** `~/.cache/skill-design/improve/t09/slide-diag-retry/`

## 3. Router `_conflicts`

- **Location:**
  - `scripts/layout_route.py` `_conflicts`;
  - used in `draw` → `ranked_routes` → `last()`, which ranks a candidate misread against a drawn line (in line, or crossing a line out of the same node) with the detours.
- **Disabled by:** `last()` returns `r.shape.startswith("U")` only.
- **Cases it names:**
  - `trunk/x-fork-b` (commit 73103e7, `test_conflicts`). Its draft does not change with the heuristic off.
- **Changed drafts:** 10 runs.
- **Result:**
  - 1 better, 765 same, 9 worse.
  - R-flow +4, tier-0 160 → 164, check problems ±0.
  - 1 tag miss: `qa/t1-multiregion-dr` document, good R-flow.
- **Worse:**
  - New F5 badge attributions: `qa/t1-privatelink` slide and slide-no-title (edge:2,edge:7), and `qa/t1-multiregion-dr` document (edge:10,edge:4, 2 violations).
  - Text shortfall: `flowcol/r2-pin-bottom` (slide, slide-no-title), `ports/xnt` (slide, slide-no-title), `qa/t3-hybrid-dns` document and the nfw document example on a slide.
- **Better:** `qa/t4-shared-lane` document (canvas area).
- **Classification:** keep.
  - Selection's R-flow neighbours (skip the next routing alternative) do not undo these. F5 owners are reached only after the router has ranked.
  - The rules design suggests replacing it with the shared F2/F3 predicates. That still needs a check that the replacement also keeps the F5 attributions above away.
- **Evidence:** `~/.cache/skill-design/improve/t09/router-conflicts/`

## 4. nfw slide `shape: VH` workaround

- **Location:** `docs/examples/specs/slides/nfw-reference-architecture.layout.yaml`, edges `tgw <-> eni.1` and `tgw <-> eni.2` (commit 3f87465: around the Firewall RT). This is a spec hint, not engine code.
- **Disabled by:** removing `shape: VH` from both edges.
- **Run:** only the nfw entries (filter `nfw-reference-architecture`, 5 runs).
- **Result:**
  - 0 better, 3 same, 2 worse (slide, slide-no-title).
  - No rule or check change, canvas unchanged.
- **Worse:** shape misses 0 → 1. `tgw <-> eni.1` is drawn HVH out of the TGW's right side, so its badge 2 moves. `tgw <-> eni.2` then warns `drew VH instead of HVH`.
- **Classification:** removable after a prerequisite.
  - The default shape rule picks HVH. That costs a shape miss, and selection's verdict counts it as worse.
  - Prerequisite: the shape rule (layout_route `_topology` rule 3–5) would have to pick VH here. That is outside selection's decisions.
- **Evidence:** `~/.cache/skill-design/improve/t09/nfw-slide-vh/`

## 5. Note `_pane_free`

- **Location:** `scripts/layout_note.py` `_pane_free`, used by `_auto` (rule o).
- **Disabled by:** `return False`.
- **Cases it names:** the bedrock-dx example and nlb-mtls (both pane). Neither draft changes with it off.
- **Changed drafts:** 4 runs.
- **Result:**
  - 1 better, 771 same, 3 worse.
  - R-border +1, R-fit +1, tier-0 160 → 161, check problems +3.
- **Worse:**
  - `rt/sgw-ret` document: new R-border B1 edge:9,note, and LINE HUGS BORDER, LINE OVER TEXT and SERVICE AS TEXT +1 each.
  - Text shortfall: `rt/right` document, and the slides/gwlb spec drawn as a document.
- **Better:** the slides/tgw spec drawn as a document (text).
- **Classification:** keep.
  - Selection tries the other note place only as an R-fit neighbour. Here it does not win back the pane.
- **Evidence:** `~/.cache/skill-design/improve/t09/pane-free/`

## 6. `_overlay_beside` default rule

- **Location:** `scripts/layout_solve.py` `_Model._overlay_beside`, after the `overlay_choices` override.
- **Disabled by:** `return False` after that override, so an overlay without a spec `header:` defaults to above and selection may still flip it.
- **Cases it names:** gwlb (beside); alb and nlb (above).
- **Changed drafts:** 50 runs, mostly `twin/` and the gwlb examples.
- **Result:**
  - 18 better, 738 same, 19 worse.
  - R-flow −1, R-fit +3, tier-0 160 → 159, check problems −7.
  - No new tier-0 identity.
- **Worse:**
  - Text or area: `twin/tw-long`, `tw-side` and `tw-stack` (all modes); `twin/ce-a` (document, slide-no-title); `twin/ce-ab` slide-no-title; `rt/gw-ret` slides; `rt/sgw-ret` slide; the gwlb example (slide, slide-no-title).
  - Checks: the slides/gwlb spec on a slide, SLIDE TOO SMALL +1 (and as a document, text).
- **Better:**
  - `rt/sgw-ret` slide-no-title: canvas clipping 1→0, checks −8.
  - Text or area: `twin/ell`, `grid`, `v-firstonly`, `v-perazasg` (all modes), and the gwlb example document.
- **Classification:** removable after a prerequisite.
  - The header flip is proposed only on a header text conflict. Fit and area losses do not trigger it, so selection cannot pick beside for the cases that need the room.
  - Prerequisite: an R-fit neighbour that flips overlay headers.
- **Evidence:** `~/.cache/skill-design/improve/t09/overlay-beside/`

## 7. Router `_u_taken`

- **Location:** `scripts/layout_route.py` `_u_taken`, the third term of the `ranked_routes` sort key.
- **Disabled by:** `return False`.
- **Cases it names:** none in the code.
- **Changed drafts:** 8 runs.
- **Result:**
  - 5 better, 768 same, 2 worse.
  - R-flow +2, R-fit −2, tier-0 160 → 162, check problems −2.
- **Worse:**
  - `qa/t3-cache-label` document: new F5 edge:1,edge:2 and edge:1,edge:3.
  - `bench/latest3-pipeline` document: text.
- **Better:**
  - `flowcol/r2-pin-bottom` slides: SLIDE TOO SMALL −1 each.
  - `qa/t3-hybrid-dns`, all modes: canvas area.
- **Classification:** keep.
  - Selection's R-flow skips do not remove the F5 attributions.
- **Evidence:** `~/.cache/skill-design/improve/t09/u-taken/`

## 8. Router `_crowded`

- **Location:** `scripts/layout_route.py` `_crowded`, called from `draw` → `build`. It marks a route unclean and adds a "no room for a port of its own" problem.
- **Disabled by:** `return []`.
- **Cases it names:**
  - the fourth fallback onto a 48px side (`test_no_room_for_a_port_of_its_own`, commit 73103e7);
  - x-fork-b through its partner `_note_drawn`.
- **Result:**
  - 0 better, 775 same, 0 worse.
  - No draft changes, no rule or check delta.
- **Classification:** removable now by the corpus criteria. No corpus case reaches it any more.
  - Its unit test in `tests/test_layout_route.py` asserts its behaviour, so removing it means removing or rewriting that test.
  - Whether F1/F2 in selection covers the 48px-side case is untested, because the corpus has no case for it. A minimal case for it would belong in the corpus before the removal.
- **Evidence:** `~/.cache/skill-design/improve/t09/crowded/`

## 9. `_Model._x_apart` pre-open rule

- **Location:** `scripts/layout_solve.py` `_Model._x_apart`, used in `_Model._siblings`. A diagonal box pair whose solved x already keeps it apart goes on x and never becomes an open pair.
- **Disabled by:** `return False`, so those pairs become open pairs and are weighed and searched.
- **Cases it names:** none in the code. It is part of rule r (`scripts/layout_model.py`).
- **Changed drafts:** 58 runs.
- **Result:**
  - 40 better, 717 same, 18 worse.
  - R-flow −4, R-border +4, tier-0 160 → 160, check problems −6.
  - Summed runtime 2.13× against the baseline. The other runs on the same loaded machine measured 1.31–1.67×, so this one is the slowest.
- **Worse:**
  - All 18 by canvas area, +0.067% to +0.343%:
    - `trunk/` eng-egress-tgw, ce-tgw, v-fork slide, v-stem, v-three, x-fork-b;
    - `rt/` longlabel, notstacked, single, nd-single, nd-tgwside, rtsub (3 modes), tmpl-doc;
    - `ports/xnt`;
    - `qa/t3-nat-route-table` and `qa/t3-dns-trunk` (document).
  - New tier-0 identities: 4 R-border B2 in `qa/t3-dns-trunk` slides (edge:1 through az.2 / subnet.2 header bands). Those runs count as better overall: tier-0 cost 40 → 2, R-flow −2.
- **Better:**
  - Mostly text shortfall in documents (`rt/`, `slide-fit/nfw-*`, `ports/ce*`, `trunk/`, the centralized-egress example).
  - `qa/t3-nat-route-table` slides: LINE OVER ICON −2 each.
- **Classification:** keep. It fails the criteria with 18 worse and new B2 identities.
  - The results are mixed and lean better, so this is a candidate to revisit: if selection's text and area terms grew a tolerance, or the B2 crossings in `qa/t3-dns-trunk` got a neighbour, the rule could go.
- **Evidence:** `~/.cache/skill-design/improve/t09/x-apart/`

## Not tried: they decide things outside selection's decisions

The decisions are the diagonal axis, beside / above, routing skips and the note place. These heuristics decide something else, so selection cannot stand in for them. They stay until selection gains a matching decision.

- `scripts/layout_route.py` `_topology`:
  - rule 5 "hub spoke" and `_column_blocked`;
  - the "fan of spokes to both sides" VHV rule (slide tgw, TGW B).
  - Both pick the edge's chosen shape, and `plan()` reserves gutters for that shape.
- `scripts/layout_solve.py` `_Model._overlay_header`, the automatic `below` (an ASG across AZ columns). right / below is not the beside / above decision.
- `scripts/layout_route.py` `_end_offs`, the port order. It orders the candidates and does not choose among them.
- `_diagonals` weighing stays as the prior (rules design §3).
