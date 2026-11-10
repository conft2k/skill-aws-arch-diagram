# Ticket 02: 큰 text scale에서 단계 번호를 선 위에

기준은 main `c3aa9ef`의 `~/.cache/skill-design/baseline/main-c3aa9ef.json`과 `main-c3aa9ef-drafts/`다(브랜치 시작점 2f66c6f는 그 뒤 문서 커밋만 있다). 증거와 scratch는 `~/.cache/skill-design/improve/eb/eb02/`에 있다. 독립 리뷰(Codex)와 PNG 판정은 이 문서 뒤에 따로 한다.

## 바꾼 것

1. **경고(먼저, 그림은 그대로):** `layout_route._place`가 배지를 놓은 뒤 그 piece에서 선호 쪽(가로선 위, 세로선 왼쪽)을 벗어났으면 `step badge N went below its line (y=…) — no clear spot above it: <막은 것> …; <고칠 것>`을 낸다. 막은 것은 그 piece 가운데 위 자리를 `badge_ok`와 같은 순서로 다시 재서 이름을 붙인다(`_badge_blocker`): 캔버스, 다른 연결선, 그룹 테두리, 자기 라벨(선이 짧아 나란히 못 둠 — 가이드의 예외), 아이콘, 그룹 배지, 제목·CIDR 줄(몇 px 모자라는지), 노드 라벨, 다른 배지, 다른 연결선 라벨. 고칠 것은 막은 것마다 다르다(제목이면 `pad_top`, 자기 라벨이면 piece를 늘리거나 라벨을 줄임, 그 밖은 offset·bend). 이 경고는 경로 후보 순위(`r.quality`)에 세지 않는다(`_route_warns`). 세면 경로가 바뀌어 그림이 달라진다(첫 시도에서 multi-account 문서의 edge 0·1 bend가 8px 움직였다).
   - 이 단계만 넣은 corpus(`warn.json`): 기준 대비 **better 0 / same 804 / worse 0, 바뀐 draft 0**. 경고는 111개 run에서 158개(제목·CIDR 53, 자기 라벨·다른 라벨 89, 그 밖 16).
2. **제목 아래 배지 자리(badge room, 아래 "리뷰 차단 수정"에서 그룹별로 바꿈):** `layout_const.badge_room(header_bottom)` = 제목(또는 CIDR 줄) 글자 아래 + `BADGE_CLEAR`(4, 이제 layout_const에 하나) + 배지가 선 위로 올라가는 높이(`BADGE_DY + BADGE_R`) − 아이콘 절반(24). `top_inset(..., "icon", badges=True)`가 스타일 값과 이 값(올림) 중 큰 쪽을 준다. 배율 1에서는 모든 스타일 값이 이미 이보다 크다(subnet 25.5 ≤ 28, 테스트 `test_badge_room_is_free_at_scale_one`). 솔버(`_Model.badges`)는 **spec에 step 배지가 하나라도 있을 때만** 켠다. 그룹마다가 아니라 그림 전체에 한 번이라 쌍둥이 VPC·subnet은 어느 쪽에 단계가 있든 같게 그려진다.
   - 처음에는 모든 그림에 적용했다(`eb02.json`). 그러면 배지가 없는 그림도 slide에서 1.12×부터 바뀌었고(slide subnet 28은 1.2×에서 이미 모자람), trunk/merge-v3az slide에 새 tier-0(R-flow F3)이 생겼다. 배지가 있는 그림으로 좁혀 둘 다 없앴다.
3. **문서:** quick_reference "Step badges"에 세로선 배지 자리(`cx = line.x − 22`, `VBADGE_DX`, 라벨은 오른쪽), 배지 자리, 경고를 적었다. diagram_guide에 "선 아래로 가면 엔진이 경고"를 덧붙였다. GLOSSARY에 **Badge room**을 넣었다.
4. **corpus:** `tests/corpus/badge/`에 세 사례를 넣었다.
   - `title-1p8-tgw-subnet`(템플릿 축소, 1.8×)
   - `title-1p9-public-subnet`(QA r07 축소, 1.9×)
   - `title-blocked-offset`: offset으로 선을 16px 올려 정말 막힌 사례. `match: "step badge 1 went below its line"`.
   - 앞의 두 사례는 기준 엔진에서 경고가 나고 이 브랜치에서 사라짐을 직접 확인했다. `tests/test_layout_route.py::BadgeSideTest`가 세 mode에서 이를 검사한다. 템플릿 badge 3이 위에 있는지, 막힌 사례의 경고가 제목과 `pad_top`을 말하는지도 본다. `pad_top: 76`이면 막힌 사례의 경고가 사라짐을 손으로 확인했다.
5. **예제:** `docs/examples/centralized-egress.svg/.png`, `nlb-mtls-reference-architecture.svg/.png`(document)를 다시 만들었다. 슬라이드와 덱은 그대로다. 나머지 예제는 다시 그려도 byte-identical이다.

## 완료 조건

- [x] 템플릿 badge 3, r07 badge 3·4가 document와 slide에서 선 위에 있다(경고 없음). 템플릿 badge 1은 가이드의 예외대로 라벨 "VPC attachment"가 위, 배지가 아래다(선 140px < 배지+라벨). 이제 그 이유가 경고로 나온다. 축소본 둘이 corpus에 있다.
  - PNG 전/후: `png-before/{tmpl,r07}.{document,slide}.png`, `png-after/…`
- [x] 정말 막힌 사례가 경고하고 corpus가 `match`로 태그한다.
- [~] **≤ ~1.6× byte-identical: 배지가 없는 그림만 그렇다.** 배지가 있는 그림은 slide에서 ~1.2×, document sg(28)에서 ~1.5×부터 배지 자리가 스타일 값보다 커진다. ticket의 "~1.68×부터"는 document subnet(32)만 본 값이었다. 기준 배율 ≤ 1.66에서 바뀐 run은 다음과 같다(모두 배지 있음).
  - three-b slide(1.52→1.69×)·slide-no-title(1.31×, 높이 850→857): 기준에서 배지 3개씩이 제목에 막혀 아래였고 지금은 slide 1개(다른 선)만 남는다.
  - nlb-mtls document(1.58×, 높이 1353→1371)·slide-no-title(1.64×): 배지는 그대로다(자기 라벨 예외). 높이만 는다.
  - rtcol document(1.59→1.97×, better)
  - 기준 1.0×로 끝났던 centralized-egress 계열 document 8개(better, 아래)
- [x] 바뀐 그림 목록과 R-fit 변화는 아래 표에 있다. R-fit이 통과에서 실패로 바뀐 run은 0이다. 가장 큰 악화는 bench/v2-1 slide 6.46 → 5.84pt다(둘 다 10pt에 한참 못 미침).
- [x] quick_reference에 `VBADGE_DX`와 경고를 적었다.
- [x] corpus vs main-c3aa9ef: **better 11 / same 749 / worse 44 / uncompared 9**(새 badge 사례 3×3), 바뀐 draft 56, **새 tier-0 identity 0**, check problem delta +0, rule violation delta 모두 +0, 태그 불일치 0, failures 0. worse 44는 모두 아래 이유 중 하나다.
- [x] 테스트: `961 passed, 1 xfailed, 2865 subtests passed`. `tests/test_examples.py centralized-egress nlb-mtls`: 4 specs all PASS(export 포함).
- [ ] Codex review, Codex PNG 판정(템플릿 전부 + 예제 5개): 리뷰어 몫.

시간: summed 1227.8s로 경고만 넣은 실행(1268.6s, 같은 기계 같은 부하)의 0.97×다. 기준 대비 1.75×는 이 기계 부하(load avg 15–19, 8 core) 때문이며 경고만 넣은 실행도 1.81×였다.

## 바뀐 run (56개, `eb02b.json`)

| 묶음 | 수 | 이유 |
|---|---|---|
| 그림이 크게만 됨(면적·R-fit만 변화) | 14 | 같은 배율에서 아이콘이 제목 아래로 내려가 높이가 는다. 예: multi-account document 1252→1254, slide-no-title 982→1000. multi-account slide는 노트가 lines에서 왼쪽 pane으로 옮겨 1340×982 → 1676×915(R-fit 계속 통과). 면적만으로 verdict가 worse로 나온다. |
| tier-0 비용만 증가 | 3 | engine1/v2-2/v2-3-egress document. 위반은 같고(R-rt·R-flow 같은 identity), 길이에 비례하는 비용이 그림이 커진 만큼 는다(476.5→501.75 등). |
| auto text scale이 다른 단계에 멈춤 | 28 | 대부분 2.5–3.0×에서 0.04–0.09만 오른다. 높이가 늘어 pt는 0.1–0.4 떨어진다. 이 그림들은 모두 기준에서도 R-fit 실패다. 크게 달라진 것은 두 개다. latest3-egress slide-no-title(1.78→2.70×, 비용 297→516, R-fit은 좋아짐)과 v2-1 slide(3.01→1.80×, 6.46→5.84pt, 3.0× 시도가 선택 gate를 넘지 못함, 더 파지 않음)다. |
| better | 11 | 기준에서 1.0×로 끝났던 centralized-egress 계열 document(keep/eng/ce/ce-tgw/ce-a/ce-ab/centralized-egress, nfw-slide, hub)는 이제 확대가 받아들여져 5.1 → 6.8px가 된다(예제 centralized-egress 포함). 그 밖에 rtcol document, v2-1 slide-no-title. |

배지가 선 밖으로 간 경고(새 badge 사례 제외): 158 → 108개. 제목·CIDR 줄 때문에 간 것은 **53 → 0**이다. 남은 108은 자기 라벨이나 다른 라벨(91)과 다른 선·테두리·digit(17)이다.

## 리뷰 차단 수정 (2026-11-10, 1회)

Codex 리뷰(`~/.cache/skill-design/improve/eb/eb02/rv/review.out.md`)의 차단 4건과 PNG 판정의 qa-r07 slide worse를 고쳤다. main `3411f8a` 위로 rebase했다(충돌은 `tests/corpus/MANIFEST.yaml` 하나, 양쪽 항목을 모두 남김).

### 바꾼 것

1. **배지 자리를 그룹마다:** 그림 전체 플래그(`_Model.badges`)를 없앴다. `layout_route`의 배지 경고가 `BadgeWarning`(str)이 되고, 가로선 위 자리를 그룹 제목·CIDR 줄이 막았으면 `room`에 그 그룹 id를 단다. `layout._build`는 먼저 그대로 그리고, 그런 그룹이 있으면 `Decisions.badge_room`에 넣어 다시 그린다(최대 3회, 제목에 막힌 배지가 줄 때만 채택). 솔버 `_Model._room`은 그 그룹의 twin(`twin_sets`의 같은 자리 상자)과 같은 template의 다른 instance까지 넓힌다. 제목이 배지를 막지 않은 그림은 이전과 byte-identical이다.
2. **배율 단계(`render_readable`, 배지 자리가 있을 때만):**
   - trunk 배지 분기 검사가 단계를 거절하면 단계를 (step−1)×0.97, ×0.9로 줄여 한 번씩 더 해 본다(v2-1 slide: 3.08× 거절 → 3.04× 채택).
   - 배지 자리가 이미 있는 그림에서 다음 단계로 갈 때는 기본 경로에서도 전체 verdict로 비교한다. tier-0 cost는 배율로 나눠(길이 비용이 배율과 함께 늘므로) 비교한다(latest3 slide-no-title: 1.78→2.80× 단계 거절).
3. **F6 channel 폭을 정수로(배지 자리가 있을 때만):** `channel_widenings`가 365.53처럼 소수 폭을 주면 그 뒤 상자가 격자에서 벗어나, 테두리에서 12px인 bend가 11.47px로 재져 LINE HUGS BORDER가 된다. qa-r07 slide에서 위 NAT의 IGW 출구선이 UHVH로 되돌아간 원인이 이것이었다. 배지 자리가 있는 그림에서만 올림한다(모든 그림에 적용하면 v-fork·t3-ssm-trunk처럼 배지와 무관한 그림이 1px씩 바뀐다, 백로그).
4. **경고가 숫자의 막힘도 이름으로:** `_badge_blocker`가 원이 비었을 때 숫자 글자 상자의 `_common` 검사(캔버스, 테두리 8px, 선, 아이콘, 다른 배지, 글자)를 같은 순서로 다시 재고, 테두리는 어느 그룹의 어느 변인지 말한다. ex-gwlb-step2-beside-ec2 slide·slide-no-title: `the bottom border of Availability Zone 1 (3px inside the digit's 8px clearance from a border)`. 리뷰는 "위쪽 테두리"라고 했지만 좌표로는 아래쪽이다(appaz.1 rect y 68–212, 선 y=236, 위 자리의 숫자 상자 위끝 217 → 테두리와 5px).
5. **테스트:** `BadgeSideTest.test_digit_blocker_names_the_border`(위 경고 문구), `BadgeRoomPerGroupTest`(쌍둥이 VPC 중 A에만 단계: 자리는 A의 두 subnet에 정해지고 B의 두 subnet까지 넓어지며 아이콘 inset이 둘 다 같음; 배율 1이면 자리 없음, `Decisions()`와 byte-identical).
6. **예제:** `docs/examples/centralized-egress.*`, `nlb-mtls-reference-architecture.*`를 main판으로 되돌렸다(다시 그려도 기준과 같다). `tests/test_examples.py` 21 spec 모두 PASS.

### 차단별 결과

| 차단 | 결과 | 근거 |
|---|---|---|
| 1 v2-1 slide 배율 | 고침(배율), 글자는 일부만 | 3.08× 후보가 분기 검사에 막히면 3.04×로 다시 해 채택. 6.46 → **6.16pt**(전 5.84). tier-0 같음(RT1×2, 2.0). 남은 0.3pt는 배지 자리로 높이가 2576→2704 는 몫이다. corpus verdict는 아직 worse(text shortfall). |
| 2 latest3 slide-no-title | 고침(verdict) | 1.78× 뒤 단계를 verdict로 막아 기본이 1.78×(cost 317.82)에 남고, 선택 단계가 note pane 후보(1.0×)를 고른다. tier-0 cost **297.24 → 181.33**, verdict better. 글자는 6.49 → 6.14pt(10pt 목표에 둘 다 못 미침). |
| 3 gwlb 경고 | 고침 | 위 표 4. 테스트로 고정. |
| 4 nlb-mtls document | 고침 | 기준과 byte-identical(제목이 배지를 막지 않음, 배지는 자기 라벨 예외로 아래). 바뀐 draft 44개는 모두 어떤 빌드에서 제목·CIDR 줄이 배지를 막아 자리를 쓴 그림이다(자리가 없으면 새 코드 경로가 하나도 켜지지 않는다). 그런 그림은 낮은 배율(slide ~1.2×부터)에서도 바뀐다. |
| qa-r07 slide judge | 고침 | NAT → IGW가 다시 HVH로 오른쪽으로 나간다(UHVH 경고 없음). 배지 2·3·4가 선 위이고, main에 남던 F6(Prod 선이 TGW RT 라벨 위)도 없다(1 problem, main 4 problems). |

### corpus (`fix.json`, main-c3aa9ef 대비)

**better 12 / same 765 / worse 27 / uncompared 21**(새 badge 3×3 + main의 새 qa 4×3), 바뀐 draft 44, failures 0, 태그 불일치 0, check problem delta +0, rule violation delta 모두 +0. 시간 summed 1.09×.

worse 27은 모두 배지 자리가 그림을 키운 몫이다.

- **높이만 늘어 글자가 작아짐(24):** 위반·shape miss 같고 높이 +2–150px, pt −0.02–0.3. engine2 slide, latest2 slide·snt, v2-1 slide, keep-egress·eng-egress slide·snt, nfw-t4 document, ce-right document·slide·snt, ce-tgw·ce·ce-a·ce-ab slide·snt, three-b slide·snt, 예제 centralized-egress slide·snt.
- **같은 위반의 거리 비용 증가(3):** engine1-egress slide(454.09→464.09)·slide-no-title(381.94→394.94), v2-3-egress slide(585.15→660.18, RT4 거리; pt 6.51→6.13). 아이콘이 내려가 RT와 대상 사이가 는다.

better 12 중 7은 tier-0 cost가 줄어 better지만 **글자는 작아졌다**(배율 단계 verdict 비교로 덜 키움): engine1 document 5.77→5.52, v2-2 document 5.82→5.39, v2-3 document 5.76→5.26, v2-3 slide-no-title 7.03→6.57, latest3 slide 6.51→5.88, latest3 slide-no-title 6.49→6.14, nd-single document 8.49→7.83(R-rt 129→71.72). 모두 기준에서도 R-fit 실패다. 나머지 5(latest2 document, v2-1 slide-no-title, nfw-slide·hub·rtcol document)는 글자가 커졌다.

PNG 판정용 쌍: `~/.cache/skill-design/improve/eb/eb02/judge2/{before,after}/` 46쌍(배지가 있는 바뀐 draft 44 + corpus 밖 qa-r07 document·slide; before는 기준 draft, qa-r07의 before는 main `d54fdbd` 엔진).

테스트: `969 passed, 1 xfailed, 2867 subtests passed`.

## 남은 것 / 백로그 후보

- (위 수정에서 처리) 배지 자리를 그룹마다 준다.
- F6 channel 폭 올림을 모든 그림에 적용(지금은 배지 자리가 있는 그림만).
- 배율 단계에서 길이 비용이 배율보다 빨리 느는지 보는 비교를 배지 자리 없는 그림에도 쓸지(지금은 기준 정책대로 받아들임).
- 템플릿 badge 1(라벨 예외)은 경고가 나온다. 템플릿을 경고 없이 만들려면 그 선을 늘려야 한다(이 ticket 범위 밖).

## 결정: 버림 (2026-11-10)

수정 기회 1회를 쓴 뒤에도 막힘이 2건 남아, 사용자가 "버리고 백로그로"를 골랐다. 브랜치 eb02(마지막 커밋 `cd0cfea`, main `921f8f6` 위)는 지웠다. 증거는 `~/.cache/skill-design/improve/eb/eb02/`에 남아 있다(`rv/review2.out.md`, `rv/judge2-{0..3}.out.md`, `judge2/{before,after}/`).

- **Codex 재리뷰 막힘 1건:** 나중 배율 단계를 배율로 나눈 tier-0 비용으로 비교하면서, 7개 그림의 최소 글자가 작아졌다. 예: `bench/v2-2-egress` document 7.40→6.58px, `bench/engine1-egress` document 7.53→6.77px. corpus verdict로는 better로 나왔다. 첫 리뷰의 막힘 2(`bench/latest3-egress` slide-no-title tier-0 비용 297→516)를 고치려다 생긴 일이다. 글자 크기와 tier-0 비용이 서로 반대로 움직인다.
- **Codex 그림 재판정(46쌍):** better 30 / same 14 / worse 2. 새 오독은 `rt/hub` document 1건이다. VPC B→Hub 선이 VPC A의 subnet 안을 지나가 B→A→Hub로 읽힌다. 나머지 worse 1건은 `bench/engine1-egress` document의 글자 축소다.
- **해결된 것:** 그룹별 배지 자리와 twin 확장, 낮은 배율의 byte 동일성, 숫자를 막은 테두리 이름(`gwlb`), `qa-r07` slide의 NAT 우회 오독, `v2-1` slide 배율 복구.
