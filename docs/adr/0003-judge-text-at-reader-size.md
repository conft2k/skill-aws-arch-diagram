# Text size is judged at the size the reader sees

Font sizes in the draft say little about readability: a 1780px document diagram shown in a 760px page column, or a wide slide fitted to 16:9, shrinks every font. On 2026-11-07 the user decided that the smallest text is judged at its effective size, slides at 16:9 points (target 10pt, floor 8pt) and documents in a 760px column (target 11px, floor 9px), and that the engine enlarges all fonts together, at most twice and 1.8× each, when the drawing falls short, keeping the earlier drawing if enlarging makes it worse. `text_scale: off` or a fixed factor turns this off for a spec.

## Considered Options

- Judge raw font px in the draft: rejected, a large diagram passes at 12px and is unreadable on the page.
- Shrink-to-fit only, never enlarge: rejected, it cannot reach the target on wide diagrams.
- Split a diagram automatically: out of scope for the engine; the warning tells the author to split it or write a slide spec.
