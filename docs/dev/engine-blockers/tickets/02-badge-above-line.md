# 02: Step badges above their line at large text scale

**What to build:** At any `text_scale`, a group title keeps enough room under it for a step badge that sits above a horizontal line at the icon row, with its 4px clearance, as at scale 1 (the scaled header-to-icon offset reserves title bottom + badge clearance + the badge's extra height). When a badge still ends up below its line (or on the wrong side of a vertical piece) because every spot on the preferred side is blocked, the engine prints a warning naming the step, the edge and what blocked the spot above (a title, a label, a border). The guide's existing exception (line too short for badge and label side by side) keeps working and is covered by the warning only if the badge leaves its preferred side.

**Blocked by:** None (can start immediately)

**Status:** wontfix (2026-11-10: dropped after the one fix round; see [results](../results/02-badge-above-line.md) and docs/dev/backlog.md)

- [ ] `templates/multi-account-egress.layout.yaml` badge 3 and the QA spec `~/.cache/skill-design/improve/stage5/qa-after/multi-account/arch.r07.layout.yaml` badges 3 and 4 sit above their lines in document and slide; a reduced reproduction of each is in the corpus.
- [ ] A case where above is truly blocked prints the warning; the corpus tags it.
- [ ] Drawings at `text_scale` ≤ ~1.6 are byte-identical; the changed drawings are listed with their size change, and no R-fit result gets worse by more than the listed amount.
- [ ] references/quick_reference.md says where a badge goes on a vertical piece (the engine's `VBADGE_DX` rule) and that a badge below its line is warned.
- [ ] Corpus vs main-c3aa9ef: 0 worse apart from listed intended changes; tests green; Codex review 0 blocking; Codex PNG judge on a sample of the changed drawings (all templates plus 5 examples) not worse.
