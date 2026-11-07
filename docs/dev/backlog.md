# 개발 백로그

2026-11-07에 멈춘 지점과 남은 일입니다. 다시 시작할 때 이 문서와
[`rules-design.md`](rules-design.md)를 먼저 읽습니다.

## 지금 상태

- **회귀 corpus:** `tests/corpus/`(MANIFEST.yaml) + `tests/run_corpus.py`가 변경 판정의 기준입니다.
  - 실행: `python3 tests/run_corpus.py --rule-checker scripts/rules.py:corpus --keep <dir> --out <json> -q -j 6`
  - 결과: 246개 항목, 706회 실행. spec 형식 오류 16건만 거부되고, 이전에 거부되던 모순 제약 케이스 4개도 이제 그려집니다.
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

1. **2단계: 엔진이 규칙 판정으로 후보를 고르기.**
   - 설계는 `rules-design.md` §3, 완료 기준은 §4 Step 2에 있습니다.
   - 아래 문제를 이 단계에서 다룹니다.
     - `rt/three-b`: RT1 위반입니다. nfw처럼 ENI 선이 RT를 감싸게 유도해야 합니다.
     - `rt/single`류의 RT 배치: 보류한 브랜치 `f-rtlone`(fe033ee)이 노린 개선입니다. Codex 판정은 조건부였습니다(gm4가 나빠지고, 긴 라벨에서 9.66pt).
     - `flowcol/r2-float-two-wide`: 폭을 줄이면 팬아웃 교차가 1개에서 2개로 늘어납니다(R-flow F3).
     - `merge-v3az`(제목 없는 슬라이드): 10pt를 지키는 대가로 선 2개가 UHVH로 그려집니다.
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
   - 재현 spec: `tests/corpus/qa/`의 T4 overlay_headers.
6. **글자 확대 비용 줄이기.**
   - 그림 하나 기준 중앙값은 1.29배입니다. 최악은 1.5초가 12.3초로 늘었습니다(`bench/engine2-pipeline` slide).
   - 확대 후보마다 feedback 전체를 다시 돌리기 때문입니다.
   - 확대를 포기한 이유와 목표 근처의 반올림 정체(nlb 10.69px)를 로그에 남깁니다.

7. **작은 문서 정리 (리뷰 백로그).**
   - `SKILL.md`의 "slide에는 spec이 없다"는 안내를 고치고, 예제 목록에 새 slide spec을 링크합니다.
     새 slide spec은 centralized-egress, nlb-mtls, serverless-order-pipeline-1/2, bedrock-dx-reference-architecture-1/2입니다.
   - L1 안내: `label_at: right`만 쓰면 그림은 그대로이고 보고만 사라집니다. 공간 확보와 실제 위치 확인을 먼저 안내합니다.
   - 컨테이너 분리 경고: 계정 사례에서 실제로 옮길 노드(`s3`)와 수정량을 바로 짚게 합니다.
   - 제목 포함 PPTX의 최소 글자를 자동으로 검증합니다(nlb-mtls slide는 10.03pt로 여유가 0.03pt뿐입니다).

## 2026-11-07 인수 검토·QA에서 나온 문제 (막는 문제, 아직 안 고침)

예제 15개 인수 검토(Codex A·B·C)와 처음 쓰는 사용자 역할 QA 4명(T1 네트워크, T2 앱·데이터, T3 엔터프라이즈,
T4 한계 시험, 새 spec 16개 × document·slide)에서 나온 차단 결함 가운데 이번에 고치지 못한 것입니다.
재현 spec과 PNG는 개발 머신의 `~/.cache/skill-design/qa/T*/`(minimal/, repro-*.layout.yaml)에 있습니다.
corpus에 옮겨 2단계(규칙 판정으로 배치 고르기)의 시험 사례로 쓰는 것이 다음 일입니다.

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
- **corpus 태그:** 문서 모드에도 R-fit 판정이 생기면서 `slide-fit/nfw-s2`, `slide-fit/nfw-t3`,
  `slides/nfw-reference-architecture`의 `good R-fit` 태그 3개가 document run과 맞지 않습니다.
  태그를 slide 모드로 한정해야 합니다.
- **corpus 범위:** `slide-fit/nfw-s2`, `slide-fit/nfw-t3`, `slides/nfw-reference-architecture`는 `good R-fit`을 slide에만
  적용하려고 `modes`를 slide로 줄였습니다. 그래서 document 모드 run 3개(R-rt, R-label 검사)가 빠졌습니다.
  `good`에 모드별 map을 지원하면 document run을 되살릴 수 있습니다.
- **범례(note):** 줄바꿈이 홉 이름(`GWLBe → EC2` 등) 가운데서 일어날 수 있습니다.
- **글자 확대 기록:** `w4-text-fit-validation.md`의 수치는 88872ab 기준입니다. 병합 후 수치는 위 "지금 상태"에 있습니다.
