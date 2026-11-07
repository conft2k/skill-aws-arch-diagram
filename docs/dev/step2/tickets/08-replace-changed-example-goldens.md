# 08: Replace changed example diagrams after review

**What to build:** Each example diagram that selection changed is shown side by side with its previous version and judged by a Codex reviewer: technically sound and the flow reads at least as well. Only the examples that pass get their goldens replaced. The others are reported, and the reason they changed is investigated before step 2 closes.

**Blocked by:** 07

**Status:** ready-for-agent

- [ ] A before and after image pair exists for every changed example, document and slide.
- [ ] The Codex verdict for each pair is recorded. Goldens are replaced only for passing pairs.
- [ ] The examples test passes on the replaced goldens.
