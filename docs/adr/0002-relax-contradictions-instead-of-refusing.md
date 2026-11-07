# Contradictory placements are relaxed, not refused

On 2026-11-07 the user saw the four corpus cases the solve refused and decided every one of them was a diagram that should be drawn. A refusal leaves a first-time user with nothing to look at, while a drawing with a warning shows what moved. So when a spec pins placements that cannot all hold, the engine draws the nearest placement it can and warns with the value to write to keep it, instead of refusing the spec. Conflicts this covers: an `xy` that a box cannot contain, an overlay whose members sit in different containers, and sibling containers on one track.

## Consequences

- Refusal is the right answer for a spec that cannot mean anything: malformed YAML, unknown ids or bad types.
- Placement refusals that remain go against this decision and belong in the backlog. Two are known as of 2026-11-07: an overlay that would also hold a node it does not list (`reject/overlay-holds-nonmember`), and two empty sibling groups spanning one track.
- Relaxing may move or split what the user wrote, such as drawing an overlay as one box per container. The warning must therefore name every change.
