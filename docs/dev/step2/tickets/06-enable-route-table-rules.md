# 06: Enable R-rt in selection

**What to build:** Selection judges the second rule group, R-rt, so that route tables land beside what they are associated with. For an R-rt violation on a route table, the neighbours flip that table's diagonal pairs, x first, and then all of its pairs. Known cases: rt/three-b (wrap the Firewall RT like nfw) and the rt/single family.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] The tier-0 part of the verdict now counts R-rt as well.
- [ ] Corpus (ticket 01 report): 0 cases worse, R-border and R-flow not higher, and check problems not higher. Each R-rt bad-tagged case is listed with its before and after counts, the group's bad-tagged cases have fewer violations in total, and tags the evidence fixes move from bad to good with the reason.
- [ ] rt/three-b and the rt/single cases are reported with their before and after verdicts; any that stay bad keep a reason.
- [ ] Runtime stays within the ticket 04 limits.
