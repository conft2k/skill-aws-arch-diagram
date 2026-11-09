# 01: Report a line over a node's icon or name as a tier-0 R-flow violation

**What to build:** The rule checker reports a new R-flow code whenever a connector passes over a node's icon body or its name block (name and sub caption lines). The violation is tier 0 and owned by (edge, crossed node). The edge's own end nodes are exempt only for the segment that reaches the icon at the attach point; running over an own end node's name, or across its icon body beyond the attach point, is reported. Group titles, CIDR lines, other edges' labels and step badges are not counted (other rules own them). Edges with `points` or `bend_*` are reported with a `try:` value and not rerouted. Selection uses its existing moves only (next routing alternative of the owning edge). The corpus run measures how far crossings drop with these moves alone.

**Blocked by:** None (can start immediately)

**Status:** done (2026-11-09). Evidence: [ticket 01 results](../results/01-report-line-over-node.md). Crossings are reported at tier 0 but not yet removed (30 → 30); removal is ticket 02.

- [x] The new code is in the rule checker, tier 0, with owners (edge, node), display names in the message, and a `try:` hint; GLOSSARY and rules-design describe it and the own-end exemption.
- [x] Corpus tags: dns-trunk slide, nat-route-table slide, three-az-writer, privatelink slide and ssm-trunk slide are `bad` for the new code; each has a good pair without the crossing; one case where a line only touches its own end icon at the attach point is `good`.
- [x] Corpus against the main baseline: 0 worse cases and 0 new tier-0 identities, apart from the new code reporting crossings that already existed (listed per case as intended). Drafts with no crossing are byte-identical.
- [x] Runtime within 3× and 30 s.
- [x] A results doc lists, per bad-tagged case, the crossing count before and after selection, and which crossings remain and why (no clean alternative, trunk, hand placement).
- [x] Codex review: 0 blocking.
