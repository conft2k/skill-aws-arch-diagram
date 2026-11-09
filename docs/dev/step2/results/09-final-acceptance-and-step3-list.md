# Ticket 09 results: final acceptance and the step 3 list

Final main 601099d (step 2 tickets 01–07, 10, the AZ twin follow-up and the example redraws) against the step 1 baseline main 36c7ea3.
Evidence on the development machine: `~/.cache/skill-design/improve/accept09/` (judges, corpus report, `SUMMARY.md`) and `~/.cache/skill-design/improve/t09/` (step 3 experiments).

## Done criteria

| Criterion | Result |
|---|---|
| No case worse than the step 1 baseline | 103 better / 655 same / 2 worse / 15 uncompared (new cases). The 2 worse runs are the GWLB slide spec in slide and slide-no-title, worse by canvas area only (+5.7%) after its spec padding moved arrowheads off container borders; the user accepted this exception because the picture judge rated it better and the checker cannot see arrowheads on borders yet. Check problems −18. |
| Tier-0 total lower than 36c7ea3 | 201 → 160: R-flow 82 → 46, R-rt 94 → 90, R-border 17 → 15, R-label 2 → 0, R-twin 6 → 9. The R-twin +3 is the new mirrored-AZ case reported as TWR, as intended. |
| Blocking misreadings fewer, 0 new | Codex re-judged the 15 QA reproductions and 21 examples, one reviewer per spec, in their corpus modes: flow-misreading blockers 21 → 15 (spec × mode), new blockers 0. All blockers including text size and technical ones: 38 → 34. Fixed: t1-multiregion-dr (3 → 0), t4-shared-lane (3 → 0). Remaining misreadings: t1-privatelink 2, t2-false-junction 2, t3-cache-label 2, t3-dns-trunk 2, t3-nat-route-table 2, t4-order-14steps 2, t4-three-az-writer 3 — lines through other icons, false junctions and labels nearer another line. |
| Runtime within the ticket 04 limits | Worst per-run ratio 2.78× (bench/engine2-egress slide-no-title; specs unchanged since 36c7ea3), worst run 18.1 s; summed 1.056×. |

## Step 3 list

See [`../step3-list.md`](../step3-list.md): nine heuristics, each disabled alone and run on the corpus against main 601099d. One is removable now (router `_crowded`), three after a named prerequisite, five stay.
