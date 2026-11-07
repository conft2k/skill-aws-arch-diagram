# 02: Prefactor: layout decisions replace the diagonal-pair switch

**What to build:** The solve takes a set of layout decisions instead of its single "put every diagonal pair on x" switch. The set records, per open diagonal pair, which axis keeps the pair apart; per overlay, where its header goes; per connector, which routing alternative to skip; and the note's place. The default set reproduces today's drawing exactly. The engine's existing slide retry (every pair on x when the text is too small) is expressed as a second decision set. The engine reports which open pairs and alternatives a drawing has, so that later tickets can propose neighbours.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Every corpus draft and every example draft is byte-identical to the baseline (0 changed).
- [ ] The slide retry still picks the larger text, now as a decision set instead of a flag.
- [ ] A drawing exposes its open diagonal pairs (with the default axis and the x/y cost) and its skippable routing alternatives.
- [ ] Two runs of the same spec and decision set give byte-identical drafts.
- [ ] Existing tests pass. Runtime stays within the spec's limits (at most 3× per diagram and never over 30 s; corpus wall time at most 3×).
