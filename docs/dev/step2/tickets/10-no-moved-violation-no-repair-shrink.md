# 10: A moved tier-0 violation or further shrink below target is not an improvement

**What to build:** When the engine compares a new drawing with the one it holds, a tier-0 violation that moved to a new place counts as worse, not as equal. A repair that leaves text below target also may not shrink it further. Final acceptance (ticket 09) found qa/t3-hybrid-dns slide breaking both: the F3 junction moved from edge:4/edge:12 beside the VGW to edge:4/edge:7 in front of AZ1 Inbound ENI, and the effective text size fell from 6.26pt to 5.65pt. The new drawing was kept because one check problem went away and the tier-0 count and cost stayed the same. The rejected ticket 03 review blocker 2 named this case and qa/t1-multiregion-dr (3.66→3.50pt).

**Blocked by:** 06 (merged)

**Status:** implemented-verified — user-approved count-decrease exception; clean worse 0, R-flow 46; prepared commit/bundle fallback for read-only shared Git; see results/10-no-moved-violation-no-repair-shrink.md

Decisions (lead, 2026-11-08, user approved the fix):

- A violation's identity is its rule, code and owner set (not its coordinates). A tier-0 violation whose identity the held drawing does not have is a *new* violation.
- A new drawing that adds a new tier-0 violation replaces the held drawing only when its tier-0 count is strictly lower. This applies to every comparison that decides whether to keep a drawing: candidate selection and every later stage (feedback rounds, header, fixed-answer and text-scale steps).
- When the held drawing's effective text size is below target (slide 10pt; document 11px in a 760px column), a later stage may keep a drawing below 99% of the held text size only when its total tier-0 violation count is strictly lower. A reduction of check problems or tier-0 cost alone is insufficient (user-approved exception, 2026-11-08). This includes later stages inside candidate construction. Candidate selection keeps the existing 90% text-size limit; shrink introduced by candidate selection within this limit is allowed (lead clarification, 2026-11-08).
- The verdict order itself does not change. This is a gate in front of it.

- [x] Tests first (red) reproduce both cases through the CLI: qa/t3-hybrid-dns slide and slide-no-title, and qa/t1-multiregion-dr slide. Then green.
- [x] qa/t3-hybrid-dns slide: no tier-0 violation that the pre-step-2 drawing (main 36c7ea3) lacks, and effective text size at least 6.26pt. The same check applies to slide-no-title. qa/t1-multiregion-dr slide: any later-stage shrink beyond 1% requires a strict tier-0 count decrease; record its before/after PNG judgement.
- [x] Corpus against the main 3946906 baseline: per-rule, check, better/same/worse and runtime tables. Every changed run is listed with its reason.
- [x] Corpus against the pre-step-2 baseline (main 36c7ea3): count the runs that have a tier-0 violation identity the 36c7ea3 run lacked, and the runs below target whose text is smaller than at 36c7ea3. Both counts are listed with their cases. Remaining shrink is allowed when introduced by candidate selection within the fixed 90% limit, or by a later stage with a strict tier-0 count decrease; list the introducing stage with evidence for every remaining run. Later-stage shrink beyond the 1% tolerance without a strict tier-0 count decrease must be zero, including inside candidates.
- [x] Step-2 wins are kept: R-flow stays at or below 48, and qa/t4-shared-lane (both modes) and qa/t1-multiregion-dr document keep their passing drawings.
- [x] Runtime stays within the ticket 04 limits (at most 3× per draft, at most 30s).
- [x] `docs/dev/step2/spec.md` and `GLOSSARY.md` (Verdict or Candidate) state the gate.

User-approved final checks (2026-11-08):

- [x] Final-code whole corpus once at -j 6: worse 0 against clean 7eb2d55; any remainder has PNG and reason
- [x] R-flow ≤48; both merge-v3az titled slides have no F3; privatelink state and reason recorded
- [x] Final-code pytest and examples once each; shrink/count, shrink/cost and shrink/check tests included
- [x] Build/fix and obstacle caches and crossing optimizations retained with equivalent drawing results; canvas-area regressions removed
