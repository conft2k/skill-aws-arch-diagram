# Engine blockers from the stage 5 first-time-user QA

Status: ready-for-agent (2026-11-10; user chose "engine blockers first", badge fix "reserve the gap under titles + warn", VPN "outside the Cloud, as an exception")

## Problem Statement

The stage 5 QA (three first-time authors, before / after) still got stuck on four things the engine does or says, not on the spec format:

1. **Overlay group ends ignore the line options.** An edge to or from an overlay group (`over:`, e.g. an ECS service or an Aurora cluster drawn over per-AZ nodes) draws one straight line per AZ instance. `trunk`, `shape`, `from_offset` and `to_offset` change nothing and nothing warns, so the picture reads "AZ 1 task → writer only". This was 4 of the 7 stuck points in the CloudFront VPC origin QA.
2. **Step badges land below their line.** Above about 1.7× `text_scale` the badge's extent above the line grows faster than the room under a subnet title (icons stay 48px), so every spot above fails the 4px clearance by 0.25–2px and the badge drops below. Nothing reports it. Seen in the multi-account template (badge 3) and its QA (badges 3, 4).
3. **The router's LINE OVER TEXT warning has no value to try.** It only gets a `try:` when the author wrote a `bend_*` expression; 12 of 30 corpus router warnings say nothing, 18 more only say "widen the gap" with no number. The DX QA author cleared it by trial and error (`min_gap_before` 135 → 160 → 180).
4. **The DX templates draw the Site-to-Site VPN inside the Region.** Stage 5 moved it there as `resource/Amazon-VPC_VPN-Connection` after a picture judge called the outside placement a technical error. The user's rule is the opposite: Site-to-Site VPN is an AWS service built for an external connection, so it is drawn outside the AWS Cloud, as an exception to "regional resources go in the Region" (the tgw-reference-architecture example already does this, and `OUTSIDE_CLOUD` enforces it for `service/AWS-Site-to-Site-VPN`).

## Solution

1. A trunk whose shared end is an overlay group meets at one point on that group (its centre unless an offset says otherwise), offsets on a group end are measured from the group's centre, and a trunk onto a group whose range covers the other ends gets a bent shape (HVH/VHV) instead of being dropped. When a requested trunk or shape still cannot be drawn, the engine warns and says why.
2. Scaled text keeps the scale-1 relationship between a group title and the icons below it, with enough extra room for a badge above a line plus its clearance. When a badge still goes below (or beside) its line, the engine warns and names what blocked the spot above.
3. The router's LINE OVER TEXT warning carries structured data (edge, piece, text owner). The engine looks for the nearest clean value of the field that moves that piece (`from_offset` / `to_offset` for an end piece, `bend_x` / `bend_y` for a middle piece), and failing that a move of the text owner (column or row gap, node `dx`/`dy`). It prints a value only after a redraw confirms that warning is gone, otherwise `no value: <why>`.
4. The DX templates go back to `service/AWS-Site-to-Site-VPN` outside the AWS Cloud, and every doc that says "VPN connection in the Region" says outside the Cloud with the reason. Both templates keep passing every rule in the modes they list.

## Done criteria (outcome first)

- The QA reproductions read correctly in the picture: one shared line into the Aurora cluster (ticket 01); badges above their lines in the multi-account template and the QA r07 spec (02); the DX QA stuck case prints a verified value (03); the DX templates show the VPN outside the Cloud (04).
- Corpus against baseline main-c3aa9ef: 0 worse runs apart from the ones each ticket lists as intended, each with a reason; no new tier-0 identity.
- Codex PNG judge on each changed drawing: not worse, 0 new misread blocking. Judges are told that a Site-to-Site VPN outside the AWS Cloud is the house convention.
- Full test suite green; Codex review 0 blocking.

## Out of scope

Document R-fit margin (the 11px floor), slide note line count, `text_scale: auto` reasons, `--explain` reason order, hop/description join, draw.io export, slide auto-split. They stay in the backlog.

## Tickets

| # | Ticket | Blocked by | Time box |
|---|---|---|---|
| 01 | [Trunk and options at an overlay group end](tickets/01-overlay-group-trunk.md) | none | 3h |
| 02 | [Badges above their line at large text scale](tickets/02-badge-above-line.md) | none | 3h |
| 03 | [A verified value for the router's LINE OVER TEXT](tickets/03-line-over-text-try.md) | none | 3h |
| 04 | [Site-to-Site VPN outside the Cloud in the DX templates](tickets/04-vpn-outside-cloud.md) | none | 1.5h |

All four start at once in their own worktrees; 01 and 03 both touch `layout_route.py` (different functions), so the second to finish rebases. 02 changes drawings at large `text_scale` (multi-account template uses 1.8), so 04 rebases after 02 if both touch the templates' drafts.
