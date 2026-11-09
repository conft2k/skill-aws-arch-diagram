# 02: New candidate moves for crossings that ticket 01 leaves

**What to build:** For the crossings ticket 01 could not remove, selection tries two new moves: (a) draw a trunk's members as separate lines when the shared stem crosses a node, and (b) widen the gap next to the crossed node. Both go through the same strict-improvement verdict as every other candidate; hand-placed edges stay as written.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] The crossing count on the bad-tagged cases is lower than after ticket 01; tags fixed by the evidence move from bad to good with the reason.
- [ ] Corpus against the ticket 01 baseline: 0 worse cases and 0 new tier-0 identities.
- [ ] Runtime within 3× and 30 s of the step-2 time.
- [ ] Codex re-judges the PNGs of privatelink, dns-trunk, nat-route-table and three-az-writer: misread blockings go down and no new blocking appears.
- [ ] Codex review: 0 blocking.
