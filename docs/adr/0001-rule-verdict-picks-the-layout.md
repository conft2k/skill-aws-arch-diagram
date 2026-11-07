# The rule verdict picks the layout; the corpus is the gate

Case-by-case placement heuristics (route-table placement went centre test → overlap → lines-past → lone box) kept producing new edge cases each review, and the engine and the checker each defined the same concepts. So on 2026-11-07 we decided the engine draws a bounded, deterministic set of candidates and keeps the one with the best verdict from the rule checker (`scripts/rules.py`), and every engine change is judged on the regression corpus (`tests/run_corpus.py`) against the shared baseline, not on per-bug repros. Heuristics are removed one at a time once the verdict covers what they did.

## Consequences

- A rule that matters to the user must exist in the rule checker before the engine can be steered by it: add the predicate first, tag corpus cases good/bad, then let selection use it.
- Engine and checker take thresholds and geometric predicates from one place, so a concept cannot drift between them.
