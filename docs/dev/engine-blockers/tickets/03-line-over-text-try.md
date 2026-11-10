# 03: A verified value to try for the router's LINE OVER TEXT

**What to build:** The router's LINE OVER TEXT warning (and the shape-refusal warnings that cite it) carries structured data: the edge, the piece index and the text owner (node label / sub line, group title / CIDR line). From that data, not from message text, the engine proposes a value: first the field that moves the hitting piece (`from_offset` / `to_offset` for an end piece, `bend_x` / `bend_y` for a middle piece) at its nearest clean value; failing that, a move of the text owner (the column's or row's `min_gap_before`, or the node's `dx` / `dy`). Each proposal is applied to a copy of the loaded spec and redrawn; it is printed as `try: <field>: <value> (<now>)` only if that warning (same edge, same text owner) is gone and no new tier-0 violation appears, otherwise `no value: <why>`. The check_layout connector case keeps its current hint unless the same machinery applies cheaply.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The DX QA stuck case (`tgw -- enid`, `shape: VH, from_offset: 23` hitting the "Dev VPC" header; reproduce from `~/.cache/skill-design/improve/stage5/qa-after*/dx*/`) prints a value, and applying it clears the warning; reduced reproduction in the corpus.
- [ ] Across the corpus, list router LINE OVER TEXT warnings before / after: how many get a verified value, how many `no value` and why; every printed value is checked by applying it.
- [ ] Drafts are byte-identical (hints only change messages); runtime within 1.5× of main-c3aa9ef summed.
- [ ] No message parsing: values come from the structured data (as the F4/F5/F6 hints do since b50655b).
- [ ] Tests green; Codex review 0 blocking.
