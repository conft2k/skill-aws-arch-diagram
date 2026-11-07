# 02: Prefactor: layout decisions replace the diagonal-pair switch

**What to build:** The solve takes a set of layout decisions instead of its single "put every diagonal pair on x" switch. The set records, per open diagonal pair, which axis keeps the pair apart; per overlay, where its header goes; per connector, which routing alternative to skip; and the note's place. The default set reproduces today's drawing exactly. The engine's existing slide retry (every pair on x when the text is too small) is expressed as a second decision set. The engine reports which open pairs and alternatives a drawing has, so that later tickets can propose neighbours.

**Blocked by:** None (can start immediately)

**Status:** implemented; awaiting independent review

- [x] Every corpus draft and every example draft is byte-identical to the baseline (0 changed). Corpus 744/744, examples 21/21; [evidence](../results/02-layout-decision-set.md).
- [x] The slide retry still picks the larger text, now as a decision set instead of a flag. 9.342561pt → 10.037175pt; `scripts/layout.py:179`, `tests/test_layout_main.py:222`.
- [x] A drawing exposes its open diagonal pairs (with the default axis and the x/y cost) and its skippable routing alternatives. NFW: 2 pairs; on request, 7 connectors and 53 distinct alternatives; `scripts/layout_solve.py:93`, `scripts/layout.py:159`.
- [x] Two runs of the same spec and decision set give byte-identical drafts. `tests/test_layout_main.py:150`; [evidence](../results/02-layout-decision-set.md).
- [x] Existing tests pass. Runtime stays within the spec's limits (at most 3× per diagram and never over 30 s; corpus wall time at most 3×). 689 tests + 2539 subtests; max 1.348× / 10.707 s, wall 2.481×; reviewed cases at most 1.078× (-j 1, warm alternating medians); [evidence](../results/02-layout-decision-set.md).
