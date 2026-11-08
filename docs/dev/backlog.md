# 개발 백로그

2026-11-07에 멈춘 지점과 남은 일입니다. 다시 시작할 때 이 문서와
[`rules-design.md`](rules-design.md)를 먼저 읽습니다.

## 지금 상태

- **회귀 corpus:** `tests/corpus/`(MANIFEST.yaml) + `tests/run_corpus.py`가 변경 판정의 기준입니다.
  - 실행: `python3 tests/run_corpus.py --rule-checker scripts/rules.py:corpus --keep <dir> --out <json> -q -j 6`
  - 결과(main 36c7ea3): 267개 항목, 760회 실행. spec 형식 오류 16건만 거부되고, 이전에 거부되던 모순 제약 케이스 4개도 이제 그려집니다.
    QA 재현 15개(`tests/corpus/qa/`)와 새 slide 예제가 포함됩니다. 태그 불일치는 0건입니다.
- **규칙 검사기 1단계:** `scripts/rules.py`는 보고 전용이라 엔진 draft를 바꾸지 않습니다.
  - 규칙: R-flow, R-rt, R-twin, R-label, R-fit, R-border
  - corpus의 `good`/`bad` 태그로 검사기 판정을 검증합니다.
- **사용자가 정한 기준:** 그림을 보고 정한 기준은 `rules-design.md` §6에 있습니다.
  - RT1 엄격: 허브의 모든 선이 연관된 RT만 허브 옆이어도 통과
  - RT2: 연관 선이 하나인 RT는 그 선에서 2S + sibling_gap 안
  - F5·L1의 직접 배치 면제와 모서리 판정
  - R-border를 tier 0으로
- **글자 크기:** 독자가 실제로 보는 크기로 판정합니다(`rules-design.md` §6).
  - slide: 16:9 슬라이드 pt 기준, 목표 10pt, 하한 8pt
  - document: 760px 본문 폭 px 기준, 목표 11px, 하한 9px
  - 목표보다 작으면 모든 글자를 같은 배율로 키워 최대 2회 다시 배치합니다(`text_scale: auto|off|<배율>`).
  - 그림이 나빠지거나 라벨·배지가 다른 선에 붙으면 원래 그림을 유지합니다.
  - 효과(corpus): slide 하한 미만 117→103, document 하한 미만 107→96.
    document 모드의 큰 그림(centralized-egress, tgw, bedrock-dx)은 원래 크기 그대로입니다.
    centralized-egress slide는 키워졌지만(5.14→6.65pt) 아직 하한 아래입니다.
- **리뷰:** 코드 리뷰는 Codex CLI(`codex exec`)가 맡고, 코드는 Claude Code가 씁니다.

## 남은 일 (순서대로)

1. **2단계: 엔진이 규칙 판정으로 후보를 고르기 (진행 중, 2026-11-08).**
   - spec과 티켓은 `docs/dev/step2/`에 있습니다. 01–06, 08, 10은 병합했습니다. 07(R-twin·R-label)은 [검증 결과](step2/results/07-enable-twin-and-label-rules.md)를 냈습니다(main 6e3fb7a 대비 8 better / 752 same / 0 worse). 09의 3단계 목록은 다음 세션에 합니다.
   - corpus 결과 (main 36c7ea3 → main 6e3fb7a, 티켓 10 포함):
     - R-flow 82 → 46
     - R-rt 94 → 90
     - R-border 17 → 17 (변화 없음)
     - check 문제 389 → 379
     - 36c7ea3 대비 better 92 / same 668 / worse 0, 새 tier-0 위반 identity 0
     - 시간: 그림 하나 최대 2.76×, 최악 17.2초, corpus wall 126→110초(티켓 10의 캐시)
   - 2026-11-08 밤 팀장 결정 (사용자 확인 필요):
     - **뒤 단계의 보호는 임시 보호입니다** (티켓 03).
       - 규칙별 위반 개수가 늘면 버립니다.
       - "첫 렌더링부터 어떤 규칙도 늘면 안 됨"은 실패했습니다. 127개 사례가 나빠졌습니다.
       - "모든 라운드를 verdict로 비교"는 R-flow를 30개 줄였지만, check 문제가 44개 늘고 최악 시간이 5.9배가 되어 보류했습니다. 참고 브랜치는 `t03-verdict`입니다.
     - **잘림 check를 verdict의 첫 항목(tier 0급)으로 셉니다** (티켓 04). 해당 check는 LINE OFF CANVAS, OFF CANVAS, BADGE OFF CANVAS입니다.
     - **글자 축소 한도** (티켓 06). 결과 글자가 목표(slide 10pt, document 11px)보다 작으면서 기본 그림보다 10% 넘게 작은 후보는 고르지 않습니다. Q2의 "조금 작은"을 이렇게 해석했습니다.
     - **03 리뷰의 차단 2를 Q2를 근거로 기각했지만, 인수 판정에서 이 판단이 틀렸습니다.** hybrid-dns slide에서 F3가 다른 자리로 옮겨 갔고 글자가 6.26pt에서 5.65pt로 작아졌습니다. **티켓 10에서 고쳤습니다(2026-11-08, 사용자 승인 규칙).**
       - 새 자리의 tier-0 위반은 tier-0 개수가 엄격히 줄 때만 받아들입니다.
       - 뒤 단계(후보 안의 뒤 단계 포함)에서 목표 미만 글자를 1% 넘게 더 줄이는 변경도 tier-0 개수가 엄격히 줄 때만 받아들입니다. 후보 선택 자체에는 기존 한도(목표 미만이면서 기본 그림보다 10% 넘게 작으면 거부)를 그대로 씁니다.
   - 남은 문제:
     - R-border는 후보가 줄이지 못했습니다(17 그대로).
     - 대각선 쌍을 뒤집는 것만으로는 R-rt가 거의 줄지 않습니다. rt/three-b는 뒤집을 쌍이 없습니다.
     - 선이 아이콘을 관통하는 문제(qa NAT RT, three-az-writer)에는 아직 후보 규칙이 없습니다. 이 문제는 tier-0 rule이 아니라 check이기 때문입니다.
     - overlay 제목 겹침은 그대로입니다.
     - 노트 배경이 라벨을 가리는 문제는 검출되지 않습니다(아래 절).
   - 최종 인수 재판정(Codex, main 3946906, 이전 main 36c7ea3과 비교, 보고서는 개발 머신의 `~/.cache/skill-design/accept3/`):
     - 흐름을 잘못 읽게 만드는 차단은 QA 6→4, 8→6, 예제 0→0으로 합계 14→10입니다.
     - 새 결함은 1건입니다(hybrid-dns slide, 위 글머리 참고). 티켓 10 뒤 hybrid-dns는 36c7ea3 그림(6.26pt, VGW 옆 F3)으로 돌아왔습니다. 인수 재판정은 07 뒤에 다시 합니다.
2. **3단계: 경우별 휴리스틱 제거.**
   - 대상은 `rules-design.md` §3 끝의 Removable later 목록입니다.
   - 휴리스틱 하나당 커밋 하나로 지우고, 지울 때마다 corpus 판정과 검사 건수가 같거나 좋아야 합니다.
3. **R-border B2의 잔여 경로 개선.**
   - `b2-check`에서 공통 판정을 check_layout으로 옮겨 `LINE IN HEADER`로 보고하고,
     routing 장애물·공간 요구 제약을 feedback에 연결했습니다. corpus B2는 63→6건,
     기존 check 코드와 다른 규칙 위반 수는 동일하고 새 <10pt run은 없습니다.
   - 남은 입력: `flowcol/r3-xy-30`, `twin/sub`, `twin/three`의 slide/slide-no-title.
     고정 KMS와 새 테두리 충돌, ASG overlay 멤버십의 공간 제약이 남습니다.
   - 판정·변경 draft·검증·PNG·재사용 JSON은 [`b2-check.md`](b2-check.md)에 있습니다.
4. **저장소 전체 Codex 재리뷰(`CODE_REVIEW-2.md`).**
   - 첫 리뷰의 R1~R7은 모두 고쳤습니다.
   - 레이아웃 엔진 바깥 부분(export, PPTX, 아이콘, spec 로더, 문서)은 지금 바로 리뷰할 수 있습니다.
5. **overlay 제목 겹침(QA T4) 다시 하기.**
   - 브랜치 `overlay-title`(a2b59a9, 병합 안 함)은 동일·포함·부분 공유 overlay의 제목 띠를 쌓습니다.
     리뷰에서 처음 지적된 2건(선언 순서로 R-twin 대응이 어긋남, 부분 공유)은 고쳤습니다.
   - 그런데 수정이 새 차단을 만들었습니다. 재현은 한 subnet에 `a1@(a,1)`, `b1@(b,1)`, `b2@(b,2)`, `c3@(c,3)`,
     ASG `[a1,b1,b2]`, TG `[b2,c3]`, SG 전체, 모두 `header: below`, row 2 `min_gap_before: 200`입니다.
     이때 비멤버 B1이 TG 안에 들어갑니다.
   - 사례별 수정이 수렴하지 않는 모양이라 2단계(규칙 판정)와 함께 다룹니다.
     멤버십 검사(비멤버가 overlay 안에 들어감)를 rules.py에 먼저 넣어야 합니다.
   - 재현 spec은 둘입니다.
     - 원래 제목 겹침(동일 멤버 `web.*`): `tests/corpus/qa/t4-overlay-headers.layout.yaml`
     - 수정본이 만든 B1 포함 회귀: 위 입력이며, 출처는 개발 머신의 `~/.cache/skill-design/s5/rv-overlay-title-r2.md`입니다. corpus에는 아직 없습니다.
6. **글자 확대 비용 줄이기.**
   - 그림 하나 기준 중앙값은 1.29배입니다. 최악은 1.5초가 12.3초로 늘었습니다(`bench/engine2-pipeline` slide).
   - 확대 후보마다 feedback 전체를 다시 돌리기 때문입니다.
   - 확대를 포기한 이유와 목표 근처의 반올림 정체(nlb 10.69px)를 로그에 남깁니다.

7. **작은 문서 정리 (리뷰 백로그).**
   - `SKILL.md`의 "slide에는 spec이 없다"는 안내를 고치고, 예제 목록에 새 slide spec을 링크합니다.
     새 slide spec은 centralized-egress, nlb-mtls, serverless-order-pipeline-1/2, bedrock-dx-reference-architecture-1/2입니다.
   - L1 안내: `label_at: right`만 쓰면 그림은 그대로이고 보고만 사라집니다. 공간 확보와 실제 위치 확인을 먼저 안내합니다.
   - 제목 포함 PPTX의 최소 글자를 자동으로 검증합니다(nlb-mtls slide는 10.03pt로 여유가 0.03pt뿐입니다).

## 2026-11-07 인수 검토·QA에서 나온 문제 (막는 문제, 아직 안 고침)

예제 15개 인수 검토(Codex A·B·C)와 처음 쓰는 사용자 역할 QA 4명(T1 네트워크, T2 앱·데이터, T3 엔터프라이즈,
T4 한계 시험, 새 spec 16개 × document·slide)에서 나온 차단 결함 가운데 이번에 고치지 못한 것입니다.
재현 spec과 PNG는 개발 머신의 `~/.cache/skill-design/qa/T*/`(minimal/, repro-*.layout.yaml)에 있습니다.
가장 작은 재현 15개는 `tests/corpus/qa/`로 옮겼습니다(071c633). 문서 예제의 slide 글자 크기 결함에는 `bad R-fit` 태그를 달았습니다(bfe8cf7).
이 사례들이 2단계(규칙 판정으로 배치 고르기)의 시험 사례입니다.

- **선이 다른 노드의 아이콘·이름을 관통 (LINE OVER ICON/TEXT):**
  - 3 AZ 큰 그림에서 AZ 3 → DB 선이 AZ 2 서버를 지나갑니다(T4 large_3az). 축소본 three_az_writer_9nodes에서는
    Endpoint/Aurora reader를 관통합니다.
  - NAT trunk가 Route-Table 아이콘을 관통합니다(T3 nat-route-table).
  - DNS outbound가 inbound 아이콘을 관통합니다(T3 dns-trunk).
  - SSM trunk가 서비스 라벨을 관통합니다(T3 ssm-trunk).
  - PrivateLink S3 경로가 다른 endpoint를 관통합니다(T1 privatelink slide).
- **라벨·배지가 다른 선에 붙음 (R-flow F5):**
  - 복제 라벨이 SQL/요청 선에 더 가깝습니다(T2 repro-badge-replication, T3 cache-label).
  - DR 복제 배지가 NLB 선에 0px로 붙습니다(T1 multiregion-dr).
  - DLQ의 "5회 실패 후 이동" 라벨이 자기 선보다 다른 선에 더 가깝습니다(T4 shared_lane_5nodes).
- **접속점처럼 보이는 교차·겹침 (R-flow F1/F2/F3, LINE ON LINE):**
  - bend 옆 8–12px 교차가 있습니다(T3 원본 remote-access, hybrid-dns. 축소본에는 F3가 남지 않습니다).
  - 두 선이 같은 꺾임점을 씁니다(T2 attempts/data-lake.slide.v2. 축소본 repro-false-junction은 수직 구간 6px 겹침).
  - 241px 구간을 함께 씁니다(T4 order_14steps slide, F1).
  - DNS 제어선과 앱 선이 한 선처럼 이어집니다(T1 multiregion-dr slide).
- **규칙 위반이 있어도 `Layout OK` (해결, 42a877b):** 이제 마지막 줄에 남은 위반 수와 규칙 코드가 나옵니다.
  `SKILL.md`에는 규칙별로 spec에서 시도할 수단을 적었습니다. exit status는 그대로입니다.
- **컨테이너 포함 오류 (해결, 8533e44·207f80c):** 형제 컨테이너를 분리하는 제약을 넣었습니다.
  충돌은 거부하지 않고 완화하며, 이동량과 고정할 값을 경고로 알립니다. rules.py에 B3/B4 포함 검사를 넣었습니다.
- **overlay 제목 겹침:** 같은 멤버를 공유하는 overlay 3개의 제목이 겹칩니다(T4 overlay_headers).
  아직 남아 있습니다. 위 "남은 일" 5번을 봅니다.
- **선이 아래 AZ subnet 머리띠 관통:** T2 repro-alb-trunk-header의 slide는 797f782에서도 관통합니다.
  `LINE IN HEADER`와 `R-border B2`가 나오고 exit 1입니다. 재판정에서는 흐름이 읽혀 경미로 봤습니다.
  feedback 수리가 이 모양(AZ 템플릿 trunk 분기)을 아직 풀지 못합니다.
- **slide 글자 크기 (797f782 재판정):** 문서용 예제 spec을 `--mode slide`로 그리면 8pt 하한 아래로 남는 것이 있습니다.
  - serverless-order-pipeline 4.1pt, bedrock-dx 4.35pt, nfw 7.56pt, nlb-mtls 7.9pt, centralized-egress
  - alb(8.4pt)와 nlb(8.9pt)는 하한은 넘지만 10pt 목표에 못 미칩니다.
  - 따로 쓴 slide spec(`docs/examples/specs/slides/*`)은 모두 10pt 이상이고 통과합니다.
  - 남은 것은 자동 확대로 풀 수 있는 크기가 아니므로, spec 분할이나 slide 전용 배치가 필요합니다.
  - 2026-11-07 세션 5에서 문서 예제 4개에 slide spec을 만들었습니다(모두 10pt 이상, 규칙 위반 0).
    centralized-egress, nlb-mtls, serverless-order-pipeline(2장), bedrock-dx(2장)입니다.
    alb, nlb, nfw는 원래 slide spec이 있습니다.
  - 인수 재판정(main 797f782, 그림 20개): 차단 7건이고, 7건 모두 위 글자 크기입니다.
    범례 잘림(nlb-mtls, gwlb, tgw, bedrock-dx)은 모두 해소됐고, 이전에 통과한 그림 가운데 나빠진 것은 없습니다.
- **작성 안내 부족(처음 사용자):** multi-account 작성 패턴, CloudFront VPC origin → internal ALB 예제,
  DX+VPN+TGW 2개 RT 패턴, Route 53 Resolver inbound/outbound 아이콘 검색 결과 없음, F3/F5에 `fix:` 안내 없음,
  `rule:`의 펼친 edge 번호와 YAML `edges[n]` 번호가 다름, 범례 hop이 표시 이름 대신 node ID.

## 2026-11-08 개선 계획에서 나온 백로그

[`improve/plan.md`](improve/plan.md) 진행 중 나온 것입니다. 증거는 개발 머신의 `~/.cache/skill-design/improve/`에 있습니다.

- **AZ twin: 제목 해석 대신 spec에 명시 (1순위).** 제목에서 AZ 식별자를 찾는 방식은 리뷰마다 새 제목 변형에서 틀렸습니다(3라운드, 사용자 결정으로 e6fa151에서 멈춤). 남은 사례는 다음과 같습니다.
  - 오탐: `AZ (DR Zone: A)` / `AZ (DR Zone: B)`처럼 자기 식별자가 없는 제목에서 설명 속 `Zone: A`를 식별자로 봅니다.
  - 누락: 같은 SG가 3행을 감싸고 순서가 `[web, app, worker]` / `[app, worker, web]`처럼 돌아간 순열은 TWR이 나오지 않습니다.
  - 힌트 부족: overlay에 `span.rows`를 적은 spec은 힌트대로 `rows:`만 바꾸면 로드 오류가 납니다. span도 함께 바꾸라고 안내해야 합니다.
  - 중복: 부모 상자 쌍과 AZ 쌍이 함께 보고될 수 있습니다.
  - 근본 해결 후보: AZ 식별자 필드나 twin 지정 키를 spec에 두고, 제목 해석은 그 키가 없을 때만 씁니다.
- **검사기가 못 보는 예제 결함 3가지 (corpus에 미검출 재현으로 넣음).**
  - `qa/ex-gwlb-step2-beside-ec2`: HVH 대체 경로가 EC2 옆을 지나 GWLBe ⇄ EC2 연결처럼 읽힘. 선 관통 규칙(계획 단계 4)에서 다룹니다.
  - `qa/ex-gwlb-slide-arrowhead-on-border`: 노드로 들어가는 화살촉이 컨테이너 테두리 위에 놓임. R-border에 검사를 더해야 합니다.
  - `qa/ex-bedrock-dx-caption-bend`: 엔진이 대문자 캡션 폭을 ~14px 짧게 재서 선이 캡션 2px 옆에서 꺾임. 박스 아래 라벨의 soft run이 상자 테두리부터 재져 오른쪽 열을 밀어냄.
- **gwlb slide AZ 1 step 2 화살촉이 GWLBe subnet·AZ 아래 테두리에 걸침.** 이전 그림에도 있었고, spec으로 고치면 글자가 9.4pt로 줄어 두었습니다.
- **gwlb 문서 노트 2행에서 제목 "GWLBe ⇄ GWLB"가 설명 첫 줄에 거의 닿음.** 노트 칸 간격 문제입니다.
- **문서 예제의 작은 글자:** 760px 칼럼에서 bedrock-dx 6.0px, centralized-egress 5.1px, serverless 6.9px, tgw 7.8px, nfw 8.3px(하한 9px). 글자를 키울 때 아이콘도 함께 키우는 엔진 변경, 또는 그림 분할이 필요합니다.
- **gwlb slide의 corpus worse 2건은 면적만 늘어난 것(+5.7%)으로 사용자가 예외로 받았습니다.** 화살촉-테두리 검사가 생기면 다시 판정합니다.

## 알려진 문제 (막는 문제 아님)

- **svg2pptx / export**
  - `stroke-width="1e-320"`인 점선은 overflow가 나고 출력이 일부만 남습니다.
  - polyline만 있는 슬라이드는 그룹 크기가 0으로 기록됩니다.
  - viewBox에 NaN이 들어가도 그대로 받습니다.
  - render_pptx 미리보기 파일이 입력 덱의 하드 링크이면 덱을 덮어씁니다.
  - 쓰는 도중 I/O가 실패하면 그 파일은 일부만 써진 채 남습니다(평범한 `open()`과 같은 동작).
- **rules.py**
  - owner map을 `collect()`의 `own`과 따로 만듭니다.
  - 0.5px 허용값이 두 곳에 정의돼 있습니다.
  - check_layout의 비공개 함수 `_head_at`을 씁니다.
  - `for:`가 없는 RT는 판정하지 않습니다.
  - 설계 문서 L2의 "once each"에 `step_each` 예외를 적어야 합니다.
  - F5의 여유 4px 경계 사례가 있습니다(engine3/latest3-pipeline).
- **overlay 분할**
  - 상자를 나눌지 미리 시험하는 계산 때문에 로드가 느려집니다(20개 분할 시 약 1.5초).
  - 나뉜 상자에서 header 경고가 두 번 나올 수 있습니다.
- **xy 완화**
  - r3-xy-30 문서 모드에서 KMS를 Cloud 위 바깥에 두어 약 94px의 빈 띠가 생깁니다.
  - 빈 트랙 규칙 때문에 `on:` 노드가 있는 슬라이드가 16px 넓어집니다.
- **거부 메시지:** 원인을 짚는 힌트가 부족합니다.
  - overlay 멤버가 VPC 안과 밖에 나뉜 경우
  - "테두리에 걸치려면 `in:`을 빼라"
- **문서:** `layout_spec.md`의 hub 설명이 동작과 다릅니다. 선이 닿지 않는 박스는 오류가 아니라 hub None입니다.
- **corpus 범위:** `slide-fit/nfw-s2`, `slide-fit/nfw-t3`, `slides/nfw-reference-architecture`는 `good R-fit`을 slide에만
  적용하려고 `modes`를 slide로 줄였습니다(071c633, 태그 불일치는 해소). 그래서 document 모드 run 3개(R-rt, R-label 검사)가 빠졌습니다.
  `good`에 모드별 map을 지원하면 document run을 되살릴 수 있습니다.
- **범례(note):** 줄바꿈이 홉 이름(`GWLBe → EC2` 등) 가운데서 일어날 수 있습니다.
- **글자 확대 기록:** `w4-text-fit-validation.md`의 수치는 88872ab 기준입니다. 병합 후 수치는 위 "지금 상태"에 있습니다.

## 뒤에 그린 불투명 배경의 라벨 가림

- 재현: `tests/corpus/rt/gw-ret.layout.yaml`, document. `edge:9:label`의 `응답`
  baseline y=671 뒤에 노트 배경이 x=16, y=668, w=1187, h=116으로 그려져 글자의 일부를 가린다.
  같은 `edge:9` 반환선의 y=680 수평 구간도 이 배경 아래에 가려진다.
- `check_layout.collect`는 이 stroke 있는 rect의 테두리만 segment로 수집한다.
  `LINE OVER TEXT`는 테두리 교차 1건을 보고하지만, 채워진 배경의 부분 가림과 paint order를
  별도 문제로 판정하지 않는다. F5/L1도 가려지기 전의 text box와 연결선 거리/방향을 사용한다.
  그래서 이 가림은 canvas clipping count에 들어가지 않는다.
- 후속 작업: 뒤에 그린 opaque fill이 앞선 라벨/배지 글자나 연결선을 일부 또는 전부 가리는 check를 추가하고
  후보 verdict에 연결한다. 이번 티켓은 검사를 바꾸지 않았다.
  `tests/test_select.py::test_gw_ret_response_label_is_not_covered_by_note_background`를 strict xfail로 보존했다.
