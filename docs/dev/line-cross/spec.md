# Line-cross rule: a line over a node's icon or name is a tier-0 violation

Status: ready-for-agent (2026-11-09; Q19–Q23 confirmed)

## Problem Statement

A reader who sees a connector run over a node's icon or over its name reads the flow as passing through that node, or cannot read the name at all. The drawing checks already see this (LINE OVER ICON, LINE OVER TEXT), but only as check problems: they read the SVG alone, know nothing about which edge or node is involved, and do not exclude the line's own ends. The rule checker has no matching violation, so selection never weighs it at tier 0, and the author gets no owner, no hint and no spec change to try. Four of the seven QA cases that still carry a misread blocking after step 2 are crossings of this kind (privatelink, dns-trunk, nat-route-table, three-az-writer), and one more (ssm-trunk) is a trunk line passing over the name of the very node it ends at.

## Solution

The rule checker reports a new R-flow violation whenever a connector passes over a node's icon body or over its name lines. The violation is tier 0 and owned by the pair (edge, crossed node). The line's own ends are exempt only where the line attaches: touching its own end icon at the arrival or departure point is fine, but running over its own end node's name, or across its own end icon's body beyond the attach point, is a violation. Group titles, CIDR lines, other edges' labels and step badges stay with the rules that already own them (R-border B2, R-flow F5, R-label), so no defect is counted twice.

The engine picks drawings by this verdict through the existing selection: the generic edge branch moves to the next routing alternative. Edges with author-written `points` or `bend_*` are reported, not repaired, with a try value. A second ticket adds new candidate moves for the cases the first ticket leaves: a trunk split into separate lines, and a widened channel around the crossed node.

## User Stories

1. As a spec author, I want a line that runs over another node's icon reported as a rule violation, so that I know the reader may think the flow passes through that node.
2. As a spec author, I want a line that runs over another node's name reported, so that I know the name is unreadable.
3. As a spec author, I want a line that runs over its own end node's name reported, so that a trunk arriving across the label of its target is not silently accepted.
4. As a spec author, I want a line that touches its own end icon only where it attaches not reported, so that every normal arrival is clean.
5. As a spec author, I want a line that cuts across its own end icon's body beyond the attach point reported, so that an arrow drawn through its target is caught.
6. As a spec author, I want the sub caption lines under a node name treated like the name, so that a line through "(private subnet)" is caught.
7. As a spec author, I want a line over a group title or CIDR line reported only by R-border, so that I get one message and one hint for one defect.
8. As a spec author, I want a line over another edge's label or step badge reported only by the existing label and badge rules, so that the score is not cut twice.
9. As a spec author, I want each violation to name the edge and the crossed node, so that I can find both in the spec.
10. As a spec author, I want the message to use the nodes' display names, so that I can match it to the picture.
11. As a spec author, I want the violation counted at tier 0, so that a drawing with a crossing never beats one without it on size or text alone.
12. As a spec author, I want the engine to try the edge's next routing alternative when the current one crosses a node, so that crossings disappear without my help where a clean route exists.
13. As a spec author, I want my own `points` and `bend_*` placements kept as written, so that the engine never overrides my intent.
14. As a spec author, I want a crossing on an edge I placed by hand reported with a try value, so that I know which hint to change and to what.
15. As a spec author, I want a crossing the engine could not remove reported with a spec change to try, so that I can finish the diagram myself.
16. As a spec author, I want a trunk whose shared stem crosses a node tried as separate lines, so that trunks are not stuck with a crossing.
17. As a spec author, I want a candidate with a wider channel around the crossed node tried, so that a crossing caused by a tight gap can go away.
18. As a spec author, I want a drawing without crossings to stay byte-identical, so that diagrams that are already fine do not move.
19. As a spec author, I want the same spec to give the same draft every time, so that reviews and diffs stay meaningful.
20. As a spec author, I want the run time to stay within three times the step-2 time and under 30 seconds, so that iterating stays practical.
21. As a spec author, I want the LINE OVER ICON and LINE OVER TEXT checks to keep working, so that the SVG-only safety net remains for anything the rule misses.
22. As a reader, I want no connector drawn over a service's icon or name, so that I read every flow correctly from the picture.

## Implementation Decisions

- **New violation code.** One new R-flow code (working name F6, line over node), tier 0, owners `(edge:<n>, node:<id>)`. It is computed in the rule checker from the engine's model (edge polylines and node icon/name boxes), not from the SVG, so it knows the edge, the node and the edge's ends, in the same way F4 already reads the edge's ends from the spec.
- **What counts as the node.** The icon box and the name block (name lines and sub caption lines). Group titles, CIDR lines, edge labels and badge digits are excluded; they belong to R-border B2, R-flow F5 and R-label.
- **Own-end exemption.** For the edge's from/to nodes, only the segment that reaches the icon at the attach point is exempt. Any other overlap with that node's icon body or name block is a violation. The exact tolerance (how far inside the icon the attach segment may run) is set in ticket 1 against the corpus and recorded in the results doc.
- **Hand placements.** An edge with `points` or any `bend_*` is reported with a `try:` value and is not skippable by selection; this matches the existing rule that pinned edges are never rerouted.
- **Selection.** No new selection code in ticket 1: the generic edge branch in `neighbours` already moves to the next routing alternative for an edge-owned R-flow violation, and the new code reaches `wanted`, the hard-placement warnings and tier-0 scoring automatically. The unfixable-warning kind table gets an entry so the hint text is right.
- **New candidate moves (ticket 2 only).** (a) trunk unbundling: draw the trunk's members as separate lines when the shared stem crosses a node; (b) channel widening: one candidate that widens the gap next to the crossed node. Both go through the same strict-improvement verdict as every other candidate.
- **Checks stay.** LINE OVER ICON and LINE OVER TEXT keep running on the SVG and keep counting as check problems.
- **Glossary and rules-design.** The new code and the own-end exemption are added to the glossary and rules-design in ticket 1.

## Testing Decisions

- **One seam:** the rule checker's `check()` and the tagged corpus, as in step 2. A good test drives a spec through the engine and asserts on the reported violations or on the corpus verdict, never on helper internals.
- **Bad tags:** dns-trunk slide, nat-route-table slide, three-az-writer, privatelink slide, ssm-trunk slide get `bad: {R-flow: <owner>}` for their crossing.
- **Good tags:** a paired case for each with the crossing removed, plus a case where a line only touches its own end icon at the attach point.
- **Prior art:** the step-2 rule tickets (03 R-flow, 07 R-twin) and their MANIFEST tags; `tests/test_rules*.py` for per-code unit cases.
- **Done criteria:**
  1. After ticket 2, the crossing violation count on the bad-tagged cases is lower than after ticket 1.
  2. Apart from the new code reporting crossings that already existed (counted as intended, as with R-twin), the corpus has 0 worse cases and 0 new tier-0 identities.
  3. Run time stays within 3× and 30 s.
  4. Codex re-judges the PNGs of privatelink, dns-trunk, nat-route-table and three-az-writer: misread blockings go down and no new blocking appears.
  5. Codex code review finds 0 blocking issues.

## Out of Scope

- The gwlb step-2 repro (line ② passing close beside EC2 and reading as connected): that is a near-miss, not a crossing. Backlog.
- false-junction, cache-label and order-14steps: their defects are F1/F5, not crossings.
- Making edge labels and step badges router obstacles.
- Rerouting edges the author placed by hand.

## Further Notes

- Time box: 1 day for both tickets (plan stage 4).
- Facts behind the own-end decision: on main 601099d, t3-ssm-trunk's edge 4 runs over its own end node's name and t1-privatelink's edge 12 runs over its own end S3; the router already treats all node icons and names as obstacles, so crossings remain only when no clean candidate exists or the edge is hand-placed.
