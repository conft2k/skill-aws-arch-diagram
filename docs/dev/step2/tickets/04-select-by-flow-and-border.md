# 04: Tracer bullet: pick the drawing by R-border and R-flow

**What to build:** The engine draws candidates for a spec and keeps the one with the best verdict, judging the first rule group: R-border and R-flow, plus R-fit as the text shortfall.
- Candidates come from the default drawing's violations, sorted by tier, rule and owners. For an R-flow violation between two edges, the neighbour skips the next routing alternative of each edge. For an R-border violation (an edge against a group's border or header band), the neighbour skips the next routing alternative of that edge. For R-fit, the neighbours put every diagonal pair on x and try the other note place.
- Selection uses the rule checker's definitions, thresholds and verdict order, not a copy of them. Each candidate is judged on the rules before the drawing checks, and a candidate already worse on tier 0 is pruned without running the checks. A skip-only change reuses the cached geometry.
- The search is a bounded, deterministic hill-climb on best improvement. A candidate replaces the current one only with a strictly better verdict; ties keep the earlier one.
- Placements the spec fixes (shape, bend coordinates, label_at, step_at, xy, offsets, points) are never varied. A violation that one of them keeps is warned about.
- A new summary line names the winning candidate (its index and the decisions that differ from the default) and the violations it removed, or says the default was kept. The existing final line that counts remaining rule violations stays.
- The winner then goes through the existing later stages (ticket 03).
- From ticket 03 review (carried over): the first render's feedback rounds and fixed-answer repairs are not yet guarded. The selection wrapper's verdict comparison must cover them within the runtime budget. Reference branch `t03-verdict` (8aadae3) guarded every round by verdict: R-flow −30, but check problems +44 and the worst diagram 5.9× slower. Do not copy it as is.

**Blocked by:** 01, 02, 03

**Status:** ready-for-agent

- [ ] Verdict order: tier-0 count, tier-0 cost, check problems, effective text shortfall, shape misses, canvas area. Tier-0 counts only R-border and R-flow, and R-fit always counts.
- [ ] Budget: at most 12 candidates for documents and 16 for slides, not counting the default drawing and not counting text scale tries.
- [ ] Determinism: the same spec gives byte-identical drafts on repeated runs.
- [ ] Corpus (ticket 01 report against the baseline of the starting main commit):
  - 0 cases worse.
  - Each R-border and R-flow bad-tagged case is listed with its before and after violation counts, and the group's bad-tagged cases have fewer violations in total.
  - Tags the evidence fixes move from bad to good, each with its reason.
  - Check problems not higher.
  - Each changed draft has a better verdict.
- [ ] Runtime is measured on this machine with the full corpus at `-j 4`, one run, under the same conditions as the baseline. Per diagram it is at most 3× and never over 30 s; corpus wall time is at most 3×.
- [ ] Tags change only on evidence. A bad tag becomes good only when every tagged mode passes. A case improved in some modes only gets a per-mode tag.
- [ ] Command-line tests on small specs:
  - The summary names the winner's index and differing decisions, and the final line still counts remaining violations.
  - A spec whose default is already best is unchanged.
  - A hard placement is kept and warned about.
  - A checker failure falls back to the default.
