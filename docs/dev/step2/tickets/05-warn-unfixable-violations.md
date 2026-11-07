# 05: Unfixable violations tell the author what to write

**What to build:** When no candidate within the budget removes a violation of an enabled rule, the engine still draws the best candidate. It adds a warning with the spec change that the existing spec-fix hints suggest for that owner (a shape, a track gap, a label place), so the author can finish the diagram. Corpus cases that keep such a violation stay tagged bad, with the reason written beside the tag.

**Blocked by:** 04

**Status:** implemented and validated

Evidence: [ticket 05 validation](../results/05-warn-unfixable-violations.md).

- [x] Every remaining enabled-rule violation in the summary carries a concrete spec suggestion, or says why none applies. All 360 enabled violations have warnings; the no-hint explanation is covered by a CLI test.
- [x] Applying the suggestion to at least three corpus cases removes the violation (checked by drawing them), or the warning states that it is a hint, not a guarantee. Every hint says `not a guarantee`; six corpus cases were drawn through the CLI, and three PNGs were inspected.
- [x] Remaining bad tags for R-border and R-flow each have a reason comment. All 10 have comments; parsed MANIFEST data is unchanged.
- [x] Drafts are unchanged by this ticket, which only changes messages: 0 changed drafts on the corpus. 760 same verdicts; all 744 drawn drafts are byte-identical to main 511fd73.
