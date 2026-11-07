# 05: Unfixable violations tell the author what to write

**What to build:** When no candidate within the budget removes a violation of an enabled rule, the engine still draws the best candidate. It adds a warning with the spec change that the existing spec-fix hints suggest for that owner (a shape, a track gap, a label place), so the author can finish the diagram. Corpus cases that keep such a violation stay tagged bad, with the reason written beside the tag.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] Every remaining enabled-rule violation in the summary carries a concrete spec suggestion, or says why none applies.
- [ ] Applying the suggestion to at least three corpus cases removes the violation (checked by drawing them), or the warning states that it is a hint, not a guarantee.
- [ ] Remaining bad tags for R-border and R-flow each have a reason comment.
- [ ] Drafts are unchanged by this ticket, which only changes messages: 0 changed drafts on the corpus.
