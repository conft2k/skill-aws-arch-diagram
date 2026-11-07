# 03: Later stages never trade a rule for a check

**What to build:** The stages that run after a drawing is chosen keep a result only if it adds no violation of any rule, whether or not that rule is enabled for selection. These stages are the feedback rounds, header repair, fixed-answer repairs and text scale. Today the feedback rounds compare check problems, slide fit, document width and shape misses, but not rule violations, so they can add one. A rule checker failure never costs the user a draft: every stage that consults the rules treats a failure as "no rule information", and the summary warns once.

**Blocked by:** 01

**Status:** implementation written; final corpus acceptance pending

- [x] A feedback round or header repair that adds a rule violation is not kept, and the earlier result stands. Evidence: `scripts/layout.py:147`; `tests/test_later_stage_rules.py:31` (six rules), `:48` (header), `:68` (fixed answers), `:144` (text scale).
- [x] With the rule checker forced to fail, the engine still writes a draft and warns once, in every stage. Evidence: `tests/test_later_stage_rules.py:84` (four stages), `:106` (transient), `:126` (branch information), `:174` (verdict); `scripts/layout.py:123`.
- [ ] On the corpus (ticket 01's report against the baseline): 0 cases worse, total violations not higher, and check problems not higher. Every changed draft has fewer violations, or the same violations and fewer check problems.
- [ ] Runtime stays within the spec's limits (at most 3× per diagram and never over 30 s; corpus wall time at most 3×).
- [x] Tests cover a round rejected for a new violation, and the checker-failure fallback. Evidence: 17 stage tests; 739 pytest tests and 2539 subtests pass; 21 examples pass. Initial red: 11 failures. Logs: `~/.cache/skill-design/t03-guard/{red,pytest-final,stage-tests-final,examples-final}.log`.

## Implementation evidence

The guard compares every rule's violation count, including R-fit and independently of
selection groups. It judges a feedback round after repairing its temporary header
crossing. Checker failures mean no rule information; the first failure is reported once,
including failures in rejected rounds.

The CLI first chooses the existing default draft, then guards further feedback and
repairs against that result. It keeps the default unless the new draft improves
violations or check problems, adds no violation of any rule, adds no check problems and
has a strictly better verdict. This avoids restoring an unfinished earlier feedback
round. `tests/test_later_stage_rules.py:160` covers `rt/sgw-ret` slide: its chosen draft
keeps clear flow despite its existing R-fit violation; no R-fit exception is needed.

The first full corpus run exposed regressions in the initial implementation. The final
implementation is checked on affected cases with baseline comparison. The user's one
full-run limit leaves final full-corpus acceptance unverified.

Final selected comparison: 30 runs, 4 better / 26 same / 0 worse; violations 69 → 61; check problems 65 → 61; all four changed drafts qualify. Maximum time 16.545 s, maximum baseline ratio 1.700×, summed ratio 1.364×. The full initial run had 3 worse runs and check problems 389 → 441; it was rejected and repaired. Final full-corpus and full wall-time evidence remain pending. Reports and directly viewed PNGs: `~/.cache/skill-design/t03-guard/validation.json`.
