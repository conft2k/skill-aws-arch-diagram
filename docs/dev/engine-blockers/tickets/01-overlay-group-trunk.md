# 01: Trunk and line options at an overlay group end

**What to build:** An edge whose end is an overlay group (`over:`) honours `trunk`, `shape`, `from_offset` and `to_offset`. With `trunk: true` and the shared end on the group, all instances meet at one point on the group (its centre on that side unless an offset is given) and share one stem, so the picture reads "every task → the cluster". An offset on a group end is measured from the group's centre (`to_offset: 0` is the centre). When the group's range covers the other ends' rows (or columns), a trunk gets HVH/VHV instead of collapsing to straight lines. If a requested trunk or shape still cannot be drawn, the engine prints a warning naming the edge, the group and the reason; a drawn path that collapsed to a straight line no longer reports the bent shape it was asked for.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The reproduction (`task.* -> aurora` with `trunk: true, to_offset: 0`, and the mirror `svc -> db.*` with `trunk: true, shape: HVH, from_offset: 0`) is in the corpus; both draw one shared line meeting the group at one point, in document, slide and slide-no-title.
- [ ] A case where the trunk cannot form (e.g. no room for a bend) prints the warning, and the corpus tags it.
- [ ] Single-line overlay edges already in the corpus (`lanes/*`, `bench/*pipeline` `proxy -> aurora`, `sides/ov3` `mon -> asg`) are byte-identical unless they set one of the four options.
- [ ] references/layout_spec.md (edges section) documents trunk and offsets at an overlay group end.
- [ ] Corpus vs main-c3aa9ef: 0 worse apart from listed intended changes; tests green; Codex review 0 blocking; Codex PNG judge on the changed drawings not worse.
