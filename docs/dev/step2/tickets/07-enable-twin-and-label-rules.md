# 07: Enable R-twin and R-label in selection

**What to build:** Selection judges the third rule group, R-twin and R-label. For an R-twin violation, the neighbour copies one twin's decisions to the other. For a header text conflict, the overlay's header is flipped. For a label violation between edges, the next routing alternative of each edge is skipped.

**Blocked by:** 06

**Status:** done (2026-11-08). Codex review: no regressions; its one blocking finding (the mirrored-AZ case is not tagged `bad R-twin`) moves to the AZ twin follow-up the user approved (docs/dev/improve/plan.md, stage 2b).

Evidence: [ticket 07 validation](../results/07-enable-twin-and-label-rules.md).

- [x] The tier-0 part of the verdict now counts all tier-0 rules.
- [x] Corpus (ticket 01 report): 0 cases worse, earlier groups not higher, and check problems not higher. Each R-twin and R-label bad-tagged case is listed with its before and after counts, the group's bad-tagged cases have fewer violations in total, and tags the evidence fixes move from bad to good with the reason.
- [x] Runtime stays within the ticket 04 limits.
