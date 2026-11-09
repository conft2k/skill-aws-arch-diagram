# 03: A shape move for lines that cross a node on its own row or column

**What to build:** Some crossings remain after ticket 02 because the line runs straight along the crossed node's own row or column. There is no gap to widen, so channel widening cannot help. This is the case for dns-trunk, nat-route-table and three-az-writer: 24 F6 at main after ticket 02. For such an F6, selection tries candidates that draw the owning edge with a different shape, so that it detours around the node: H to HVH or VHV, V to VHV or HVH, or a different side pair. For trunk members, the shared stem moves as one. Author-written placements stay as written: shape, bend_*, points, sides, offsets and trunk. Candidates go through the same strict-improvement verdict and the ticket 02 acceptance guard: the tier-0 identity set must be a strict subset that drops an F6, no new floor misses, and check problems must not grow.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] The F6 count on the bad-tagged cases is lower than after ticket 02 (28), and dns-trunk, nat-route-table or three-az-writer loses at least one crossing.
- [ ] Corpus against the ticket 02 baseline: 0 worse cases and 0 new tier-0 identities. Drafts without F6 at baseline are byte-identical.
- [ ] Runtime within 3× and 30 s per run.
- [ ] Codex re-judges the PNGs of privatelink, dns-trunk, nat-route-table and three-az-writer. Misread blockings go down and no new blocking appears. (This criterion was moved here from ticket 02.)
- [ ] Codex review: 0 blocking.
- Time box: 3 hours.
