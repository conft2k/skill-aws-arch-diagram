# Ticket 03: router LINE OVER TEXT 경고에 다시 그려 확인한 값

기준은 main `c3aa9ef`의 `~/.cache/skill-design/baseline/main-c3aa9ef.json`과 `main-c3aa9ef-drafts/`다. 작업 브랜치는 `eb03`(main `2f66c6f`에서 시작)이다. 독립 리뷰(Codex 코드 리뷰)는 이 문서 뒤에 별도로 한다.

증거: `~/.cache/skill-design/improve/eb/eb03/` 아래에 있다.

- `eb03.json`, `corpus.log`, `eb03-drafts/`: 최종 corpus
- `main-now.json`, `main-now.log`: 같은 시각에 돌린 main `2f66c6f` export(`main-src/`)
- `table.py`, `table-final.json`: 아래 표와 값 적용 검사
- `qa-r3.layout.yaml`, `qa-r1.layout.yaml`: QA 재현

## 완료 조건

- [x] DX QA stuck case가 값을 낸다. qa-after2 dx-vpn-tgw redraw 3(`rtvpc min_gap_before: 160`)의 `tgw -- enid`(`shape: VH, from_offset: 23`)가 VPC RT의 sub line `'10.0.0.0/8 → DX (VPN 백업)'` 위를 지나는 경우다(브리프의 "Dev VPC" header 사례는 템플릿 slide의 같은 edge이고, 아래 표에 있다). 출력은 다음과 같다.
  `warning: edges[7] tgw -- enid (TGW – TGW ENI (Shared services VPC)): LINE OVER TEXT '10.0.0.0/8 → DX (VPN 백업)' of VPC RT (best of the candidates); try nodes[8] rtvpc (VPC RT): dx: 11 (0 now) — drawn again, the line clears '10.0.0.0/8 → DX (VPN 백업)'`
  spec에 적용하면 경고가 사라지고 `Layout OK`가 나오며 rule 줄은 0이다. redraw 1(`tgw`, `rtvpc` 둘 다 115)에서는 두 경고가 모두 값을 낸다(`rtop dx: -9`, `cols: {id: rtvpc, min_gap_before: 171} (gap 158 now)`).
- [x] corpus에 넣었다. `qa/eb03-dx-qa-r3`는 QA 작성자의 spec 그대로이고 slide 모드만 돈다. `qa/eb03-dx-line-over-text`는 축소 재현으로 세 모드를 돈다. 축소본에서는 요청한 VH가 refuse되는 형태로 재현된다.
- [x] 경고 전부의 전후 목록: 아래 표. 값마다 적용해서 확인했다.
- [x] draft가 byte-identical이다. 기준 대비 corpus 결과는 **0 better, 804 same, 0 worse, 5 uncompared**(새 사례 2개의 5 run), **0 changed drafts**, check problem delta +0, violation delta 전부 +0.
- [x] 시간: 같은 시각에 돌린 main 대비 matching run 합계 **1.024×**(2042.6초 / 1994.6초). 첫 실행은 1.014×였다. 저장된 기준과 비교하면 2.913×인데, 다른 worktree의 corpus가 동시에 돌아 load가 약 18(8 core)이었기 때문이다. main export도 같은 부하에서 1994.6초가 나왔다(기준 701초). LOT 경고가 있는 28개 기준 run은 합계 약 +26초다.
- [x] 메시지 파싱이 없다.
  - 경고는 `layout_route.RouteWarning`(str subclass)이다. 문자열은 그대로이고, 아래 구조화 데이터를 함께 들고 있다.
    - `edge`, `line`, `refused`, `shape`
    - `hits`: `TextHit`(piece, pieces, axis, at, box, owner)의 목록. owner는 `TextOwner`(node/group, id, line/title/CIDR line, text)다. `_Ctx.text_owner`가 box id에서 주인을 찾는다.
    - `tries`: router가 찾은 piece 이동 `PieceTry`
    - `base`, `fix`
  - 값과 판정은 이 데이터에서만 나온다. 테스트 `test_line_over_text_hint_reads_structured_data_not_the_message`는 문자열을 바꾼 경고로도 같은 값이 나오는지 확인한다.
- [x] 테스트: 전체 suite green(아래).
- [x] Codex review 1차: 차단 2건. 아래 "리뷰 수정"에서 고쳤다. 다시 독립 리뷰를 받는다.

## 동작

1. router(`layout_route.draw`)는 두 경고를 `RouteWarning`으로 만든다. 하나는 "best of the candidates"이고, 다른 하나는 author shape을 거절한 `refused()`다. 거절이면 요청한 shape의 후보 polyline에서 hit을 잰다.
2. `_piece_tries`는 첫 hit의 piece를 움직이는 field의 가장 가까운 깨끗한 값을 찾는다. `_nearest_clear`를 쓰고, 양쪽 ±2도 깨끗해야 한다.
   - 끝 piece는 `from_offset` / `to_offset`이다. 끝의 면 안(±반폭)으로 한정한다.
   - 세 piece의 가운데는 `bend_x` / `bend_y`다. author 식이 있으면 그 식을 옮겨서 보여 준다.
   - 다음 경우는 이유만 남긴다: trunk, 다른 shape으로 그려진 경우, 직선, author bend 값이 이미 있는 경우.
3. `layout._lot_moves`는 위 값 다음에 text 주인의 이동을 붙이고, 가까운 것부터 정렬한다.
   - 주인 node의 `dx` / `dy`: 아이콘과 caption 전체가 piece를 비키는 양이다. 같은 spec 항목의 instance 전부에 적용한다. 선의 끝 node, xy 고정, flow stack의 y는 제외한다.
   - piece와 text(group이면 그 box의 첫 track) 사이 track의 `min_gap_before`: 지금 gap에 겹친 양을 더한다.
4. `line_over_text_tip`은 앞의 4개를 차례로 적용한다.
   - 적용 방법: loaded spec 사본에 적용하고, main()과 같은 `draw_final`로 다시 그린다. `draw_final`은 main에서 꺼낸 pipeline이다(feedback, repair, selection 포함).
   - 채택 조건: 같은 spec line의 같은 text 주인 위에 경고가 없고(거절이면 거절 자체가 없고), 이 drawing에 없던 tier-0 identity가 생기지 않을 때. 첫 번째로 맞는 것을 `try <change> (<now> now) — drawn again, …`으로 쓴다.
   - 없으면 `no value: <why>`를 쓴다. 거절이면 원래의 일반 조언이 뒤에 남는다.
5. 같은 면 out-and-back 거절은 `no value: a same-side out-and-back …` 뒤에 원래의 pad 조언을 둔다.

check_layout의 LINE OVER TEXT(spec_fix)는 바꾸지 않았다.

## 전후 표 (router LINE OVER TEXT 경고)

기준 30건의 내역은 다음과 같다.

- 값이 있던 경고는 2건이다(privatelink의 author bend `bend_y`. 다시 그려 확인한 값은 아니다).
- 나머지 28건은 값이 없었다. "(best of the candidates)"만 있는 경고가 10건, 일반 "widen the gap" 또는 out-and-back 조언만 있는 거절이 18건이다.

ticket 뒤 원래 30건은 다음과 같다.

- **다시 그려 확인한 값 5건**: 적용하니 5건 모두 경고가 사라졌다.
- **기존 router bend 값 2건**: 이번 변경으로 바뀌지 않았다. 적용하니 경고가 사라졌다.
- **`no value: <why>` 23건**: 23건 모두 이유를 단다.
- 새 corpus 사례 5 run은 모두 값을 냈고, 적용하니 5건 모두 경고가 사라졌다.

"적용"은 출력된 값을 spec YAML에 쓰고 같은 모드로 다시 돌리는 것이다(`table.py`). 판정은 그 edge의 LINE OVER TEXT나 refusing 경고가 남았는지로 했다.

| 사례 | 모드 | edge | 전 | 후 | 적용 |
|---|---|---|---|---|---|
| nfw-reference-architecture | slide, slide-no-title | edges[1] | 거절, widen the gap | `nodes[4] rtsp (Spoke RT): dy: -17 (0 now)` | 경고 사라짐 ×2 |
| xy/refuse | document, slide, slide-no-title | edges[0] | 거절, no bend_y … widen | `nodes[1] m (M): dx: 31 (0 now)` | 경고 사라짐 ×3 |
| qa/t1-privatelink | slide, slide-no-title | edges[11] | author bend `bend_y: row.main+76` | 같음 (router 값, 이번에 다시 그리지 않음) | 경고 사라짐 ×2 (원래 있던 rule 줄 1) |
| templates/dx-vpn-tgw | slide, slide-no-title | edges[7] | 거절, widen the gap | no value: 면 안(±24)의 from_offset이 없음, Dev VPC header 앞에 넓힐 column이 없음 (VPC box가 TGW column 아래까지 옴) | — |
| rt/single, rt/nd-single, rt/rtcol, slide-fit/nfw-t4 | document | TGW 선 | 거절, widen the gap | no value: 면 안의 from_offset이 없음, caption 'TGW'가 이 선의 끝 node의 것 | — |
| twin/sub | slide, slide-no-title | edges[1] | best of | no value: 면 안의 to_offset이 없음, ASG header 앞에 넓힐 column이 없음 | — |
| qa/t4-three-az-writer | slide, slide-no-title (×2씩) | edges[0] | best of | no value: 면 안의 to_offset이 없음. `cols: db`를 넓혀 다시 그려도 '10.60.22.0/24' 위 / header 앞에 column 없음 | — |
| lanes/g | document | edges[20] | best of | no value: trunk 선, AZ 2 header 앞에 column 없음 | — |
| qa/t2-alb-trunk-header | slide, slide-no-title | edges[2] | best of | no value: trunk 선, `cols: app`를 넓혀 다시 그려도 'App subnet' 위 | — |
| qa/t3-dns-trunk | slide, slide-no-title | edges[0] | best of | no value: trunk 선. inbound dx(instance 전부가 함께 움직임)와 column으로 다시 그려도 그대로 | — |
| qa/t3-ssm-trunk | document | edges[2] | best of | no value: trunk 선, caption이 선의 끝 node의 것, `cols: service`도 그대로 | — |
| qa/t3-hybrid-dns | slide, slide-no-title | edges[8] | 거절, pad_top 조언 | no value: 같은 면 out-and-back, 이어서 pad_top 조언 | — |
| xy/oab2 | document, slide, slide-no-title | edges[1] | 거절, canvas 아래 조언 | no value: 같은 면 out-and-back, 이어서 원래 조언 | — |
| qa/eb03-dx-qa-r3 (새) | slide, slide-no-title | edges[7] | — | `nodes[8] rtvpc (VPC RT): dx: 11 (0 now)` | 경고 사라짐 ×2 |
| qa/eb03-dx-line-over-text (새) | 세 모드 | edges[1] | — | `nodes[1] rtvpc (VPC RT): dx: 11 (0 now)` | 경고 사라짐 ×3 |

trunk 선의 piece 이동도 시험해 봤다(trunk 제외를 끄고 4개 사례). 깨끗한 값이 하나도 없어서 제외를 되돌렸다.

## 남은 것 (백로그 후보)

- trunk 선, 그리고 선의 끝 node가 caption의 주인인 경우는 이 기계장치로 값이 나오지 않는다. 남은 수단은 shape, side, label 위치다. 이것을 제안하는 별도 hint가 필요하다.
- group header가 piece보다 앞(TGW column 아래)에서 시작하는 경우(dx 템플릿, twin/sub, three-az)는 넓힐 column이 없다. box 폭이나 pad 쪽 후보를 더 만들 수 있다.
- 기존 author bend 값(`bend_try`)은 아직 다시 그려 확인하지 않는다(적용해 보면 corpus의 2건은 경고가 사라진다).
- runtime은 부하가 없는 머신에서 저장된 기준과 다시 재야 한다.

## 테스트

`uv run -q --no-project --with pyyaml --with python-pptx --with cairosvg --with pytest --with pytest-xdist python -m pytest -q -n 8 tests`: **964 passed, 1 xfailed, 2853 subtests passed**. 새 테스트는 `tests/test_unfixable_warnings.py`에 있다.

- QA 두 사례: 값을 적용하면 경고와 rule 줄이 사라진다.
- 힌트가 draft를 바꾸지 않는다.
- 구조화 데이터만 읽는다.
- no value 이유 3종(끝 node의 caption, out-and-back, trunk).

## 리뷰 수정 (Codex 1차 차단 2건)

브랜치를 main `3411f8a`(eb01: overlay group trunk) 위로 rebase했다. 충돌은 없었다.

1. **숫자 bend 후보가 `cannot be drawn`으로 떨어졌다.** `_piece_tries`가 author 식이 없는 `bend_x` / `bend_y` 값을 float로 넣었다. spec의 bend field는 `Expr`를 기대하므로 다시 그리는 중에 `AttributeError`가 났다. 이제 `Expr("num", offset=v)`로 넣는다(`scripts/layout_route.py` `_piece_tries`). 리뷰어의 5-node `middle` spec은 이제 `try bend_x: 129 (none; the router's 271 now) — drawn again, the requested HVH is drawn`을 낸다. 이 값을 YAML에 적용하면 경고가 사라지고 `Layout OK`가 나온다.
2. **후보의 rule check가 실패해도 값을 냈다.** `RuleGuard.check`는 실패하면 `None`을 돌려준다. 그런데 `after or ()`가 이것을 위반 0건으로 읽었다. 이제 rule 결과가 없는 후보는 채택하지 않는다. 대신 `<change>: its rule check failed (<error>)`를 이유로 남기고, 결국 `no value: …`가 된다(`scripts/layout.py` `line_over_text_tip`).

새 테스트(`tests/test_unfixable_warnings.py`) 2개는 수정 전에 실패하고 수정 후에 통과한다.

- `test_numeric_bend_value_is_drawn_again_and_clears_the_warning`: `middle` spec에 값이 나오고, 적용하면 `Layout OK`다.
- `test_line_over_text_value_is_not_offered_when_its_rule_check_fails`: `qa/eb03-dx-qa-r3` slide에서 후보 redraw의 `rules.check`만 실패시키면, `drawn again` 없이 `no value`와 `its rule check failed`가 나온다.

`tests/corpus/MANIFEST.yaml`에 주석을 달았다. `qa/eb03-dx-qa-r3`는 역사적 QA 재현이고, Region 안 VPN 배치는 따라 할 템플릿이 아니다(2026-11-10부터 Site-to-Site VPN은 Direct Connect처럼 AWS Cloud 밖에 둔다).

corpus 기준(main-c3aa9ef) 대비 결과(`fix.json`, `fix.log`, `fix-drafts/`):

- **0 better, 804 same, 0 worse, 17 uncompared, 0 changed drafts**, check problem delta +0, violation delta 전부 +0, summed runtime 1.101×
- uncompared 17개: eb03 새 사례 5 run, eb01 새 사례 4개의 12 run
- rebase 전 draft(`eb03-drafts/`, 793개)와는 모두 byte-identical이다. eb01 새 사례 12개 draft는 main `3411f8a`에서 그린 것과 byte-identical이다.

전체 테스트: **971 passed, 1 xfailed, 2853 subtests passed**.
