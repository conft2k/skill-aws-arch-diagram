# 03: Later stages never trade a rule for a check

**What to build:** The stages that run after a drawing is chosen keep a result only if it adds no violation of any rule, whether or not that rule is enabled for selection. These stages are the feedback rounds, header repair, fixed-answer repairs and text scale. Today the feedback rounds compare check problems, slide fit, document width and shape misses, but not rule violations, so they can add one. A rule checker failure never costs the user a draft: every stage that consults the rules treats a failure as "no rule information", and the summary warns once.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] A feedback round or header repair that adds a rule violation is not kept, and the earlier result stands.
- [ ] With the rule checker forced to fail, the engine still writes a draft and warns once, in every stage.
- [ ] On the corpus (ticket 01's report against the baseline): 0 cases worse, total violations not higher, and check problems not higher. Every changed draft has fewer violations, or the same violations and fewer check problems.
- [ ] Runtime stays within the spec's limits (at most 3× per diagram and never over 30 s; corpus wall time at most 3×).
- [ ] Tests cover a round rejected for a new violation, and the checker-failure fallback.
