# 01: Corpus baseline comparison

**What to build:** A maintainer runs the corpus with a baseline (the result and drafts of a main commit). The runner reports, for each case and mode, whether the verdict is better, the same or worse than the baseline. It also reports which drafts changed, the change in check problems and in violations per rule, and the wall-time and summed-time ratio. Every later ticket's acceptance is read from this report.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Given a baseline result and its drafts, the runner prints a comparison section and writes it into its result file. Without a baseline, it behaves exactly as today.
- [ ] A verdict is compared in the spec's order: tier-0 violation count, tier-0 cost, check problem count, effective text shortfall, shape misses, canvas area. Each case and mode is classed as better, same or worse.
- [ ] Changed drafts are listed by case and mode, with byte identity as the test.
- [ ] Deltas are reported: check problem codes, violations per rule, and the runtime ratio (wall and summed).
- [ ] Comparing a baseline with itself reports 0 worse, 0 changed, and every delta 0.
- [ ] Tests cover the comparison on small hand-made results.
