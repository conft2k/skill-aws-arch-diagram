# 06: Enable R-rt in selection

**What to build:** Selection judges the second rule group, R-rt, so that route tables land beside what they are associated with. For an R-rt violation on a route table, the neighbours flip that table's diagonal pairs, x first, and then all of its pairs. Known cases: rt/three-b (wrap the Firewall RT like nfw) and the rt/single family.

**Blocked by:** 04

**Status:** implemented and validated

Evidence: [ticket 06 validation](../results/06-enable-route-table-rules.md).
Review fix: [90% effective-text-size floor](../results/06-text-size-review-fix.md).
Target exception: [target-sized text and occlusion backlog](../results/06-target-size-exception.md).

The review decision rejects a shrink of more than 10% only when the resulting effective
text size is below target; at or above target, every group follows the verdict.
It supersedes the original no-worse/fewer-violations corpus gate for
documented text-limit rollbacks; the pre-review evidence remains in the first report.

- [x] The tier-0 part of the verdict now counts R-rt as well.
- [x] Corpus (review-adjusted gate): every selected draft reaches the target effective text size or retains at least 90% of the completed default's. The remaining 06 changes and every 04 winner rolled back by this limit are listed, with per-rule/check deltas. All baseline verdict regressions are explained by text-limit rollbacks, and tags reflect the saved evidence.
- [x] rt/three-b and the rt/single cases are reported with their before and after verdicts; any that stay bad keep a reason.
- [x] Runtime stays within the ticket 04 limits.
