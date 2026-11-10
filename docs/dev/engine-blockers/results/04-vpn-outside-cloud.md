# Ticket 04: Site-to-Site VPN을 AWS Cloud 밖에 (DX 템플릿과 문서)

2026-11-10, 작성 세션(branch eb04, main 2f66c6f에서 시작). 증거: `~/.cache/skill-design/improve/eb/eb04/`.

## 규칙

사용자 결정(2026-11-10): Site-to-Site VPN은 외부 연결용 AWS 서비스이므로 AWS Cloud 박스 밖에 그린다. "regional 리소스는 Region 안" 규칙의 예외다. 작업 중 추가 지시: **Site-to-Site VPN의 배치 정책은 Direct Connect와 같다.** 그래서 두 템플릿 모두 `service/AWS-Site-to-Site-VPN`을 Direct Connect와 같은 `edge` 열(Cloud 밖)에 둔다. Direct Connect는 DX 경로에, VPN은 Internet 경로에 놓는다. 9b9ddc2의 나머지(private subnet 유지, document spec + slide 전용 쌍, "연결: / 전파:" sub-caption, Cloud > Org > Account > Region 중첩)는 그대로 두었다.

## 템플릿

- `templates/dx-vpn-tgw.layout.yaml` (document): VPN이 Cloud 밖으로 나가면서 Internet에 열이 하나(`link`) 더 필요해졌다. 그대로 두면 canvas가 1409px로 넓어져 9.7px이 되어 R-fit에 걸린다. 그래서 Direct Connect 경로를 Region 위의 별도 행(`dxp`)으로 올렸다. 이렇게 하면 DX gateway(Cloud 안, Region 위)와 On-prem RT(Region 안)가 한 열(`rtop`)을 같이 쓴다. `vpc` 열 앞의 gap을 211로 두어 VPC 박스가 TGW의 attachment 선과 겹치지 않게 했다. "VPC attachment" 라벨은 Dev VPC 선으로 옮겼다. Prod 선에 두면 DXGW 선과 그 선 사이에 끼어 F5에 걸린다. "IPsec"은 Internet → VPN 구간, "VPN attachment"는 VPN → TGW 선의 verb로 둔다.
- `templates/dx-vpn-tgw-slide.layout.yaml` (slide 전용): 열 수는 그대로다(`vpn` 열을 없애고 `link` 열을 넣었다). Internet은 `link`, VPN은 `edge`에 둔다.
- 머리 주석은 배치 이유와 실제 글자 크기를 적도록 다시 썼다. text_scale을 키우면 생기는 일에 대한 문장은 1.6/1.8로 직접 돌려 보고 고쳤다. ±23일 때 1.6에서는 R-rt RT1, 1.8에서는 shape 거부가 난다.

| spec / mode | 이전 (2f66c6f) | 이후 |
|---|---|---|
| dx-vpn-tgw document | 1142 × 872, 12.0px | 1172 × 865, **11.7px**, 경고 0 |
| dx-vpn-tgw slide | 11.0pt, shape 거부 경고 3 | **10.4pt**, 경고 0 |
| dx-vpn-tgw slide --no-title | 12.3pt, 경고 3 | **11.7pt**, 경고 0 |
| dx-vpn-tgw-slide slide | 13.5pt | **12.5pt** |
| dx-vpn-tgw-slide slide --no-title | 13.7pt | **12.5pt** |
| dx-vpn-tgw-slide document (목록에 없는 mode) | 10.4px | 9.5px |

다섯 mode 모두 `Layout OK`이고 `rule:` 줄은 없다. PNG(직접 확인함): `doc-document.png`, `doc-slide.png`, `doc-slide-notitle.png`, `slide-slide.png`, `slide-slide-notitle.png`. 확인한 내용은 세 가지다. VPN과 Direct Connect가 Cloud 밖 한 열에 있다. DX gateway는 Cloud 안, Region 밖에 있다. On-prem RT와 VPC RT는 각자 bracket 안에 있다.

## 문서

- `references/diagram_guide.md`: 아이콘 배치 문단과 "Show what a hybrid connection runs over" 문단을 VPN은 Direct Connect와 같은 배치(Cloud 밖)로 바꾸고, 두 설명을 나란히 맞췄다. "Older examples…" 문장은 지웠다. attachment 라벨 bullet에 있던 "VPN connection의 sub-caption" 대안은 "같은 종류의 다른 선"으로 바꿨다. Technical correctness에 예외를 이유와 함께 한 번 적었다(judge와 리뷰어가 인용할 곳).
- `references/layout_spec.md` `in:` 항목과 `label_at` 예시, `SKILL.md` 템플릿 표와 체크리스트, `tests/corpus/MANIFEST.yaml`의 두 `what:`.
- `GLOSSARY.md`: **Outside the Cloud** 항목을 추가했다.
- `scripts/check_layout.py` `OUTSIDE_CLOUD` 주석, `scripts/layout_spec.py` loader 오류 문구: Direct Connect와 VPN에는 "is not in AWS" 대신 "is drawn outside the AWS Cloud (an AWS service built for the external connection)"을 쓴다. Internet 문구는 그대로다(기존 테스트가 그대로 통과한다).
- `grep -rn "VPN-Connection\|VPN connection" SKILL.md references templates README* GLOSSARY.md`: 남은 것은 Technical correctness의 "Region에 VPN-Connection 노드를 따로 그리지 않는다" 한 줄뿐이다.

## 검증

- Corpus(`templates/`, baseline main-c3aa9ef): 2 better / 6 same / 3 worse, check problem +0, 모든 규칙 violation delta +0, tier-0 새 identity 없음. 바뀐 draft는 두 DX 템플릿의 5개뿐이다. worse 3건(dx-vpn-tgw document, slide 쌍 두 mode)은 마지막 tier인 canvas area만 늘었다(Internet 열 하나만큼: 995824 → 1013780, 730800 → 755440). 의도한 변경이다. dx-vpn-tgw slide 두 mode는 area가 줄어 better다.
- 전체 테스트: **957 passed, 1 xfailed, 2853 subtests passed** (176.57s, `pytest.log`). xfail은 기존 항목이다. 문서만 바꾼 GLOSSARY와 results 편집은 테스트 실행 뒤에 했다.

## 남은 일

- Codex review와 PNG judge는 독립 세션 몫이다. judge에게는 Site-to-Site VPN이 Cloud 밖에 있는 것이 house convention임을 알려야 한다.
- `docs/dev/backlog.md:194`(dx-vpn-tgw 문서 spec을 slide로 돌릴 때 나던 shape 거부 경고 3건)는 이번 배치에서 경고가 0이 되어 해소됐다. backlog 항목은 고치지 않았다.
