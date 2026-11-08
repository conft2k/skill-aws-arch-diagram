# Step 2: the engine picks its drawing by rule verdict

Status: ready-for-agent

## Problem Statement

Someone who writes a spec gets a draft that the drawing checks call fine, but a reader still misreads it. A line runs through another node's icon. A replication label sits closer to the SQL line than to its own. Two flows cross right beside a bend and look like a junction. A route table lands outside the lines it is associated with. The rule checker already names these violations, but it only reports them: the engine draws one layout and fixes only check problems through feedback rounds. So the author has to add spec hints by hand (shape, bend_y, label_at, from_offset), often several rounds of them, and many violations remain anyway. Past attempts to fix each case with its own placement heuristic kept producing new edge cases in every review (ADR 0001).

## Solution

The engine draws a small, fixed set of candidates for each spec and keeps the one with the best verdict. The verdict compares, in order: the canvas clipping check count (critical like tier 0), the tier-0 violation count, the tier-0 cost, the check problem count, the effective text size shortfall, the shape misses and the canvas area. The default drawing is replaced only when a candidate is strictly better. Placements the author wrote in the spec are kept as written. The summary names the candidate that won and what it fixed. When no candidate removes a violation, the engine still draws the best one and warns with the spec change that would remove it. Rule groups are added to selection one at a time: R-border and R-flow first, then R-rt, then R-twin and R-label. Each group is accepted only when the corpus shows its bad cases improving and no other case getting worse.

## User Stories

1. As a spec author, I want the engine to avoid drawing a line through another node's icon or name, so that the reader does not think the flow passes through that node.
2. As a spec author, I want a connector label to sit closer to its own line than to any line of another flow, so that the reader attributes the label to the right flow.
3. As a spec author, I want a step badge placed on its own flow, so that the numbered note reads in the right order.
4. As a spec author, I want two flows not to cross right next to a bend or an end icon, so that a crossing is not read as a junction.
5. As a spec author, I want two flows never drawn on top of each other or in line, so that two flows are not read as one line that splits.
6. As a spec author, I want no connector running through a group's header band, so that group titles and CIDR lines stay readable.
7. As a spec author, I want no connector running along a group border, so that the line is not read as part of the box.
8. As a spec author, I want each arrow to end clearly on its target icon or group border, so that the reader sees what it points at.
9. As a spec author, I want a route table drawn inside the bracket of its associated lines, so that the reader sees which attachments it serves.
10. As a spec author, I want a route table with one associated line drawn close to that line, so that its association is obvious.
11. As a spec author, I want a route table drawn nearer its own hub than any other hub, so that it is not read as another hub's table.
12. As a spec author, I want a subnet route table drawn clearly nearer its own subnets than any other subnet, so that the association is unambiguous.
13. As a spec author, I want twins drawn the same shape, so that identical AZs or VPCs look identical.
14. As a spec author, I want connector labels above horizontal lines and to the right of vertical lines, so that labels follow one convention.
15. As a spec author, I want every note step drawn as a badge on the edges it is written on (once per edge, or once per instance with `step_each` or `steps`), so that no step is missing or misplaced.
16. As a spec author, I want the engine to keep my drawing unchanged when no candidate is strictly better, so that a diagram that is already fine does not move for no reason.
17. As a spec author, I want the placements I wrote (shape, bend_y, label_at, xy, offsets) kept as written, so that the engine never overrides my intent.
18. As a spec author, I want a warning when one of my own placements is what leaves a violation, so that I know which hint to change.
19. As a spec author, I want a warning naming the spec change that would remove a violation the engine could not remove, so that I can finish the diagram myself.
20. As a spec author, I want the summary to say which candidate won and which violations it removed, so that I understand why the drawing changed.
21. As a spec author, I want the same spec to give a byte-identical draft every time, so that reviews and diffs stay meaningful.
22. As a spec author, I want a diagram to take at most three times as long as today and never more than 30 seconds, so that iterating stays practical.
23. As a spec author, I want a drawing that reads correctly to beat one that is merely bigger or has larger text, so that readability comes first.
24. As a spec author, I want fit and text size still to count after readability, so that a correct drawing is not needlessly small.
25. As a spec author, I want the final summary line to keep telling me how many rule violations remain, so that I know whether the diagram is ready to deliver.
26. As a slide author, I want the selection to keep slide text at or above the target whenever a candidate allows it, so that slides stay presentable.
27. As a reviewer, I want each rule group's effect shown on the corpus (bad cases fixed, nothing worse), so that I can accept or reject it on evidence.
28. As a reviewer, I want every changed example diagram shown side by side with its previous version, so that I can confirm it did not get worse before it is replaced.
29. As a reviewer, I want the corpus to show which cases changed and why, so that a change is never silent.
30. As a maintainer, I want candidate generation limited to a fixed budget, so that runtime stays predictable.
31. As a maintainer, I want selection to reuse the rule checker's definitions and thresholds, so that the engine and the checker cannot disagree about a rule.
32. As a maintainer, I want rule groups added to selection one ticket at a time, so that a regression can be traced to one group.
33. As a maintainer, I want a case that no candidate can fix to stay tagged bad with its reason, so that the corpus records what the engine still cannot do.
34. As a maintainer, I want the case-by-case placement heuristics marked as removable once selection covers them, so that step 3 can delete them one at a time.
35. As a maintainer, I want the existing feedback rounds and text scale to keep working on the winning candidate, so that check problems and text size are still repaired.
36. As a maintainer, I want selection to fall back to today's single drawing if the rule checker fails, so that a checker bug never costs the user a diagram.
37. As a first-time user, I want the QA cases (lines through icons, labels on other lines, false junctions, header band crossings) to come out readable without hand-written hints, so that the skill works on realistic specs out of the box.

## Implementation Decisions

- **Selection wrapper.** Candidate comparison happens at the engine's existing comparison point: the step that today keeps the best feedback round and then tries text scale candidates. It gains a candidate loop before the feedback rounds. The winning candidate then goes through the existing feedback rounds, header repair, fixed-answer repairs and text scale. These stages now also judge the rules, so they cannot undo what selection gained. For now, as an interim guard more conservative than the verdict, header repair, fixed-answer repairs, text scale and feedback rounds after the chosen draft keep a result only if no rule's violation count rises (enabled for selection or not). Ticket 04 replaces this with the full verdict comparison (Q2 order), applied from the first render on, as part of the selection wrapper and within the runtime budget. Enabling rules group by group applies to candidate search and selection only.
  - The historical complete default is constructed once as the fallback and fixed text reference, before it becomes an incumbent. The guarded replay of the original spec constructs a candidate and uses selection's fixed text-size limit; its rule comparisons still apply the identity gate. Once a drawing is held, all subsequent feedback, header, fixed-answer and text-scale replacements also apply the 1% text-retention gate.
  - A newly routed, rule-clean winner has not exhausted text scale. If its feedback keeps it unchanged, it retains its feedback geometry for up to two small font enlargements (one canvas font unit per attempt). These later-stage replacements pass the same gates and verdict. A completed drawing that already tried text scale does not repeat the attempts.
  - Tried and rejected on 2026-11-08: forbidding any rule increase from the first feedback round on. It blocked the rounds that fix check problems (127 cases worse, check problems 389→828).
  - Also measured on 2026-11-08: comparing every round by the verdict from the first render on cut R-flow by 30, but it raised check problems by 44 and slowed the worst diagram 5.9×. The selection wrapper must therefore keep this within the runtime budget (reference branch `t03-verdict`).
- **Layout decisions.** The solve's single switch for diagonal pairs (put all open pairs on x) becomes a set of layout decisions. The set records, per open diagonal pair, which axis keeps the pair apart; per overlay, where its header goes; per connector, which routing alternative to skip; and the note's place. The default set reproduces today's drawing exactly.
- **Candidate generation.** Candidates come from violations, not from enumerating everything. The engine starts from the default drawing and its violations, sorted by tier, rule and owners. For each violation it proposes neighbouring decision sets:
  - R-rt on a route table: flip that table's diagonal pairs.
  - R-flow or R-label on two edges: skip the next routing alternative for each.
  - R-border on an edge (against a group's border or header band): skip that edge's next routing alternative.
  - R-twin: copy one twin's decisions to the other.
  - Header text conflicts: flip the overlay header.
  - R-fit: put every pair on x, or try the other note place.
- **Search.** Bounded, deterministic hill-climb on best improvement. A candidate replaces the current one only with a strictly better verdict; ties keep the earlier one. The budget is 12 candidates for documents and 16 for slides. Rules are judged before the drawing checks, and a candidate worse on tier 0 is pruned early. Skip-only changes reuse the cached geometry. Candidate selection keeps the fixed text-size limit: exclude text below both the medium's target (slide 10pt; document 11px in a 760px column) and 90% of the completed default's. Later stages also reject more than 1% text shrink from the drawing they hold when that drawing is below target. This applies to feedback rounds, header repairs, fixed-answer repairs and text scale.
- **Verdict.** The ordered tuple starts with canvas clipping check count (LINE OFF CANVAS, OFF CANVAS, BADGE OFF CANVAS), critical like tier 0, then tier-0 violation count, tier-0 cost, check problem count, effective text shortfall, shape misses and canvas area. Tiers come from the rule checker: tier 0 is a rule whose breach makes the reader misread the diagram (R-flow, R-rt, R-border, R-twin, R-label); tier 2 is fit (R-fit). The rule checker exposes this ordering for selection and later stages. The engine does not keep a copy. A gate precedes this unchanged order in every replacement comparison: a violation's identity is its rule, code and owner set, independent of coordinates and owner order. A drawing with a tier-0 identity absent from the held drawing is eligible only if its total tier-0 violation count is strictly lower, including rules outside the enabled search group. Candidate selection and every later stage apply this gate. The text-size gates described under Search also precede the verdict.
- **Enabling rules by group.** The tier-0 part of the verdict counts only the rule groups enabled so far: group 1 is R-border and R-flow, group 2 is R-rt, group 3 is R-twin and R-label. Each group is a separate ticket and is enabled only after its corpus evidence passes. R-fit always counts, as the effective text shortfall, from the first ticket on. When the default has an R-rt violation, retain group 1's winner as the incumbent before searching with group 2; both searches share the same 12/16 candidate budget. This keeps a new group's greedy move from making the previous group's better drawing unreachable.
- **Hard spec placements.** Decisions never vary what the spec fixes: explicit shape, bend coordinates, label_at, step_at, xy, offsets or points. If the best candidate still has a violation whose owner carries such a hint, the summary warns that this hint keeps the violation.
- **Unfixable violations.** If no candidate in the budget removes a violation, the engine draws the best candidate and warns with the spec change the existing spec-fix hints suggest for that owner. The case stays tagged bad in the corpus, with the reason.
- **Summary.** A new summary line names the winning candidate (index and the decisions that differ from the default) and the violations it removed, or says that the default was kept. The existing final line that counts remaining rule violations stays.
- **Failure safety.** If the rule checker raises, the draft is still produced. Selection is skipped and the default drawing is used. Every later stage that consults the rules (feedback, header repair, text scale) treats a checker failure as "no rule information" instead of failing. One warning says so.
- **Runtime.** Each diagram takes at most 3× its current time and never over 30 seconds. Corpus wall time stays within 3×.
- **Determinism.** The candidate order, tie-breaking and budget are fixed, so the same spec always yields byte-identical drafts.
- **Heuristics.** Placement heuristics are not removed in this step. Each one selection makes redundant is listed for step 3 (rules design, "Removable later").

## Testing Decisions

- **A good test judges external behaviour:** a spec goes in; the draft, the rule verdict and the summary come out. No test asserts which internal decision was flipped or how candidates were ordered.
- **Main seam: the corpus.** Each ticket's acceptance is a full corpus run compared with the shared baseline of the main commit it starts from. Today the corpus runner only records results and judges tags. The first ticket adds a baseline comparison to it: per case and mode, verdict better, same or worse; changed drafts; check problem and violation deltas; runtime ratio. Required results:
  - The enabled group's bad-tagged cases have fewer violations. Each fixed case's tag moves from bad to good, with the reason.
  - No case's verdict gets worse.
  - The check problem count does not rise.
  - Changed drafts are listed, and each one is explained by an improved verdict.
  - Runtime stays within the limit.
- **Secondary seam: the engine command line.** Pytest covers a few small specs:
  - Drawing twice gives byte-identical drafts.
  - The summary names the winner, or says the default was kept.
  - A spec whose default is already best is left byte-identical to today.
  - A spec with a hard placement keeps it and warns.
  - A checker failure falls back to the default.
- **No new seam.** The layout decision set is internal and is not unit-tested directly.
- **Examples.** When a selection changes an example diagram, Codex reviews it side by side with the previous version, and the golden is replaced only after it passes.
- **Final acceptance for the whole step.** Codex re-judges the 15 QA cases and the 21 examples. Blocking misreadings must be fewer than today, and there must be no new blocking defect.
- **Prior art:**
  - The corpus runner's tag judging.
  - The text scale tests, which assert that a rejected candidate keeps the previous result.
  - The layout main tests, which read the summary lines.
  - The examples test, which checks goldens and determinism.

## Out of Scope

- Removing the case-by-case placement heuristics. That is step 3, one heuristic per change.
- New rules or new rule predicates. Selection uses the rule checker as it is. One exception: a membership check (a node drawn inside an overlay it is not listed in) is a prerequisite for redoing the dropped overlay-title work, and it belongs to that work, not to this step.
- Global optimisation, grid reordering, and changing which track a node is on.
- Overriding anything the spec author wrote explicitly.
- Splitting a diagram into several slides automatically.
- PPTX-specific layout, and rules on hand-drawn SVGs.
- The remaining placement refusals that ADR 0002 lists as backlog.

## Further Notes

- These decisions came from the 2026-11-07 grilling session (Q1–Q11):
  - Q1 runtime limit.
  - Q2 verdict order.
  - Q3 rule groups as separate tickets.
  - Q4 strictly better only.
  - Q5 hard spec placements.
  - Q6 golden replacement after review.
  - Q7 winner in the summary.
  - Q8 done criteria with no numeric target.
  - Q9 unfixable cases warn and stay tagged bad.
  - Q10 One Codex writer per ticket, each in its own `wt` worktree, following the implement-spec flow: Codex review, one fix round, Codex re-review in the same session, commit, `git rebase main`, `wt done`. No push unless the user asks. The user runs `/to-tickets` and `/implement-spec` themselves; those skills are user-invoked.
  - Q11 This spec is `docs/dev/step2/spec.md`. Tickets are `docs/dev/step2/tickets/NN-<name>.md`, each with a `Blocked by:` line.
- Today's tier-0 totals on the corpus (main 36c7ea3, 760 runs): R-flow 82, R-rt 94, R-border 17, R-twin 6, R-label 2. Step 2 is done when that total falls, with no case worse, and the re-acceptance above passes.
- Design background: the rules design document (§3 Engine selection, §4 Step 2), ADR 0001 (the rule verdict picks the layout), ADR 0002 (relax, do not refuse) and ADR 0003 (text judged at reader size). Vocabulary follows the root glossary.
- Some cases are known to need selection:
  - rt/three-b: wrap the Firewall RT like nfw.
  - The rt/single family.
  - flowcol/r2-float-two-wide: a narrower round adds a fan-out crossing.
  - merge-v3az, slide with no title: 10pt costs two UHVH lines.
  - The QA reproductions under the corpus's qa directory.
