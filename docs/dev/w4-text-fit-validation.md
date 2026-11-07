# W4 text-fit validation

Implementation commit: `5e6a022b5dfcbf23dcf7a9aa00fbeb86cce53773` (fix3, parent main 88872ab).

`layout_const.effective_text` measures document/web text in a 760px column without
enlargement (target/floor 11/9px), and fitted slide text (10/8pt). Document text below
target is a warning and tier-2 R-fit report, never feedback/check cost.

Automatic scaling retries at most twice, each at most 1.8×, rounding each preceding
font size. Fixed numeric and `off` modes disable retries. Candidates cannot increase
check/other rule counts or move a trunk badge across a merge/fork junction. The initial
render retains five routing feedback rounds; a font retry has at most two and keeps
the preceding render if conflicts remain.

## Examples

Document actual sizes are px in a 760px column; slide actual sizes are pt. Canvas and
minimum font are SVG px. Unchanged pairs are written once.

| Example | Canvas before → after | Minimum px before → after | Actual before → after |
|---|---|---|---|
| alb | 1105×806 | 12 | 8.25px |
| bedrock-dx | 1629×1266 | 12 | 5.60px |
| centralized-egress | 1780×1224 | 12 | 5.12px |
| example | 666×653 | 12 | 12.00px |
| gwlb | 1139×769 | 12 | 8.01px |
| nfw | 1571×840 | 12 | 5.81px |
| nlb-mtls | 1143×828 → 1342×1058 | 12 → 17 | 7.98 → 9.63px |
| nlb | 888×806 → 924×844 | 12 → 13 | 10.27 → 10.69px |
| serverless-order-pipeline | 1328×1501 | 12 | 6.87px |
| tgw | 1328×594 | 12 | 6.87px |
| slides/alb | 1107×536 | 12 | 10.02pt |
| slides/gwlb | 979×540 | 12 | 10.00pt |
| slides/nfw | 1102×538 | 12 | 10.04pt |
| slides/nlb | 920×536 | 12 | 10.07pt |
| slides/tgw | 1107×470 | 12 | 10.02pt |

## Corpus

Full corpus: 706 runs, 690 drawn, 16 expected spec rejections; no failures. Baseline and
final runs both used four workers. The sandbox prohibited Python 3.15 forkserver
socket binding, so the final invocation selected `fork` and ran the same corpus CLI
with `-j 4`.

| Medium | Drawn | Below target before → after | Below floor before → after | Changed drafts |
|---|---:|---:|---:|---:|
| Document | 230 | 114 → 112 | 107 → 99 | 29 |
| Slide, titled + untitled | 460 | 174 → 174 | 117 → 105 | 54 |

All 83 changed drafts were below target before scaling. No individual run gained
check problems or violations of other rules. check_layout problems stayed 154;
SLIDE TOO SMALL stayed 174. Other rule violations stayed 189: R-rt 94, R-flow 30,
R-border 63, R-label 2.

Raw rule totals are 363 → 475 because document R-fit was previously not reported.
Applying the new criterion to both sides gives 477 → 475 total violations
(R-fit 288 → 286). Three existing good R-fit tags disagree with the new document
criterion; these remain report-only tag mismatches.

Runtime: baseline 59.58s wall / 233.09s summed; final 117.64s / 462.68s:
1.974× wall / 1.985× summed, within the 2× target.

## Verification and remaining limits

- pytest: 611 passed, 2,082 subtests passed, 62.93s
- test_examples.py: all 15 specs passed parsing, deterministic layout, standalone check,
  export and structural comparison
- 760px PNGs directly inspected: centralized-egress, tgw, nlb, plus enlarged nlb-mtls;
  no overlap or clipping seen
- centralized-egress and tgw retain their previous render to preserve trunk-badge or
  label attribution; NLB improves slightly, NLB mTLS crosses the 9px floor
- many large diagrams still need splitting or a slide spec; scaling is conservative
- skill quick_validate reports the existing description over its 1,024-character
  limit (1,111 characters); frontmatter was not changed

Artifacts:

- `/home/ec2-user/.cache/skill-design/fix3.json`
- `/home/ec2-user/.cache/skill-design/fix3-comparison.json`
- `/home/ec2-user/.cache/skill-design/fix3-drafts/`
- `/home/ec2-user/.cache/skill-design/fix3-evidence/examples.json`
- `/home/ec2-user/.cache/skill-design/fix3-evidence/centralized-egress.after.760.png`
- `/home/ec2-user/.cache/skill-design/fix3-evidence/tgw-reference-architecture.after.760.png`
- `/home/ec2-user/.cache/skill-design/fix3-evidence/nlb-reference-architecture.after.760.png`
- `/home/ec2-user/.cache/skill-design/fix3-evidence/nlb-mtls-reference-architecture.after.760.png`
- `/home/ec2-user/.cache/skill-design/fix3-evidence/{pytest,test-examples,corpus}.log`

Worktree Git metadata is read-only in this sandbox. Commits used the alternate index
`/home/ec2-user/.cache/skill-design/fix3.index` and advanced only `refs/heads/fix3`
through the writable common Git directory. The alternate index is clean. The original
read-only index still represents 88872ab and needs synchronization outside this sandbox.

## Changed source locations

| File:line | Change |
|---|---|
| scripts/layout_const.py:444 | Medium thresholds and effective size |
| scripts/layout.py:104,740,813,854,899 | Measurement, report, rendering, badge guard, retries |
| scripts/layout_text.py:41,51,78 | Checker registration, per-pass rounding, scoped metrics |
| scripts/layout_model.py:687 | Scale option and active render state |
| scripts/layout_spec.py:534 | Scale validation and YAML off handling |
| scripts/rules.py:854 | R-fit for both media |
| scripts/check_layout.py:143,1011,1466,2557 | Typography scopes and standalone registration |
| tests/test_text_scale.py:1 | Threshold, enlargement, invariance and rollback regressions |
| tests/test_rules.py:239 | Document R-fit expectation |
| tests/test_layout_main.py:1865,1899 | Retry CPU budget and summary assertion |
| tests/test_layout_spec.py:641 | Schema diagnostic |
| tests/compare_structure.py:100,113 | Enlarged font and badge recognition |
| tests/run_corpus.py:324 | Actual text metrics in JSON |
| SKILL.md:202 | Scale workflow and controls |
| references/layout_spec.md:47,442 | Option and retry behavior |
| docs/dev/rules-design.md:63 | Shared user decisions |
