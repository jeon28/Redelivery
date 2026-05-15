# FLOR Depot(반납CY) 선택 도입 — 개발 계획서

> 작성일: 2026-05-15
> 상태: 검토 대기
> 트리거: FLOR은 다른 임대사와 달리 Depot마다 수용 가능한 컨테이너 타입/조건이 달라 사용자가 직접 골라야 한다.

---

## 1. 목표

1. **임대사 = FLOR / FLOR+DFIC 선택 시에만** 반납CY(Depot) 선택 UI가 노출되도록 변경.
2. Depot 목록은 **사전 수집된 정적 데이터**로 하드코딩 (`scraper/scrapers/flor_depots.py`).
3. 초기 목록은 FLOR 사이트에서 **1회용 수집 스크립트**로 추출 → 코드로 이식.
4. 조회 요청에 `depot` 파라미터를 추가, 백엔드 `flor.py`가 이미 받을 준비된 자리에 그대로 전달.

### 변경하지 않는 것

- FLOR 외 다른 임대사 조회 흐름 / UI.
- `flor.py`의 위저드 자동화 로직 (이미 `depot: str | None` 지원).
- 사이트 분석 문서 (`FLOR/ANALYSIS.md`) — depot 자동화는 이미 분석돼 있음.

---

## 2. 결정 사항 (확정)

| 항목 | 결정 |
|---|---|
| Depot 목록 출처 | 사전 수집 → 코드 하드코딩 |
| 초기 목록 방식 | 1회용 Playwright 스크립트로 수집 후 이식 |
| UI 노출 조건 | 임대사 == FLOR / FLOR+DFIC 일 때만 |
| UI 위젯 | **버튼 + 모달(팝업)** |
| 위치 | 임대사 드롭다운 옆 작은 버튼. 클릭 시 모달 열림 |
| Depot 미선택 처리 | 조회 버튼 비활성 + 안내 메시지 |
| 수집 회사 | 한쪽만 (스크립트는 양사 지원, 실행 시 인자로 선택). 양사 동일 가정. |
| 초기 데이터 | **빈 채로 배포** — 인천 default(`PORT_DEFAULT_DEPOT`) 1개만 가용. 사용자가 추후 수집해서 채움. |

---

## 3. 데이터 구조

### 신규 파일: `scraper/scrapers/flor_depots.py`

```python
# (company, region) → [ { code, name, label }, ... ]
# label = FLOR Element UI 드롭다운에 노출되는 실제 문자열 (스크래퍼 매칭용)
# code  = 예: "KRPUS07"  / name = "YoungJin CY"
# 매칭 우선순위: scraper는 label 기반 substring 매칭. UI는 code+name 표시.

FLOR_DEPOTS: dict[tuple[str, str], list[dict[str, str]]] = {
    ("장금상선", "BUSAN"): [
        # 1회용 수집 후 채움
    ],
    ("장금상선", "INCHON"): [...],
    ("장금상선", "GWANGYANG"): [...],
    ("장금상선", "PYEONGTAEK"): [...],
    ("장금상선", "ULSAN"): [...],
    ("흥아라인", "BUSAN"): [...],
    ("흥아라인", "INCHON"): [...],
    ("흥아라인", "GWANGYANG"): [...],
    ("흥아라인", "PYEONGTAEK"): [...],
    ("흥아라인", "ULSAN"): [...],
}


def list_depots(company: str, region: str) -> list[dict[str, str]]:
    """company × region 에 해당하는 depot 목록 반환. 없으면 빈 리스트."""
    return FLOR_DEPOTS.get((company, region), [])
```

### 노출용 API 추가: `GET /flor/depots?company=장금상선&region=BUSAN`

응답:
```json
{
  "depots": [
    { "code": "KRPUS07", "name": "YoungJin CY", "label": "(KRPUS07) YoungJin CY (KRPUS07)" },
    ...
  ]
}
```

→ 프론트는 SearchForm의 company / region 변경 시 호출, 결과를 드롭다운에 채운다.

---

## 4. 1회용 수집 스크립트

### 위치: `scraper/scripts/collect_flor_depots.py`

### 흐름

1. CLI 인자: `--company 장금상선|흥아라인 --region BUSAN|INCHON|...`
2. FLOR 로그인 (기존 `FlorScraper._login` 재사용)
3. Apply Redelivery 진입 → Customer ID 선택 → Port 선택
4. Depot 드롭다운 클릭 → 옵션 패널의 모든 `li` 텍스트 수집 (offsetParent 있는 것만)
5. 결과를 `code`, `name`, `label` 형태로 stdout JSON 출력
6. 사용자/내가 출력 JSON을 `flor_depots.py` 상수에 복붙

### 수집 시 주의

- Port 옵션 텍스트는 `"<도시> (<코드>)"` 포맷 (`PUSAN (KRPUS)`, `INCHON (KRINC)` 등).
- Depot 옵션 텍스트는 `"(<DEPOT_CODE>) <Depot 풀네임>"` 또는 `"(<코드>) <이름> (<코드>)"` (사이트 관찰).
- 회사(Customer ID)에 따라 Port·Depot 목록이 다를 수 있음 → SK / HA 양쪽 따로 수집.
- 한 region씩 수집 후 결과 누적.

### 실제 수집은 어떻게?

- 사용자 환경에서 직접 실행 (Playwright + 실 계정 필요).
- 내가 스크립트만 작성, 사용자가 실행 후 결과 JSON을 chat으로 전달 → 내가 `flor_depots.py`에 이식.
- 또는 사용자가 시간 여유 있을 때 region 5개 × 회사 2개 = 10회 실행.

---

## 5. 프론트 UI 변경

### `frontend/components/SearchForm.tsx` + `frontend/components/DepotPickerModal.tsx` (신규)

추가될 영역 (조건부 노출):

```
선사 ▼ 흥아라인  임대사 ▼ FLOR  [🏭 반납CY: 미선택]  반납지역 ▼ 부산
                                  ↑ 클릭 시 모달 (라디오 + 취소/확인)
컨테이너 (수량 동시 조회 가능)
[textarea]
```

### 로직

- `lessor` state가 `FLOR` 또는 `FLOR+DFIC`로 정규화되면 (templateKey 사용) 버튼 표시
- 버튼 클릭 시 모달 컴포넌트 마운트. 모달 안에서 `/api/flor/depots?company=&region=` 호출.
- `depot` state: 선택된 depot의 **label 문자열** 저장 (백엔드 `_select_depot`이 label 기반 매칭)
- 미선택 상태에서 🔍 조회 버튼 disabled + 버튼 라벨에 "미선택" 표시 (빨간 톤)
- 선택 후 버튼 라벨에 `(KRPUS07) YoungJin CY` 표시
- (company, region) 변경 시 depot state 자동 초기화 (잘못된 조합 방지)
- 다른 임대사 선택 시 버튼 자체를 숨김

### 조회 요청 바디

```ts
{
  company,
  lessor,
  region,
  containers,
  depot,   // FLOR 외 임대사는 undefined → 백엔드에서 무시
}
```

---

## 6. 백엔드 변경

### `scraper/routers/query.py`

요청 바디 모델에 `depot: str | None = None` 추가. FLOR 외 임대사 라우팅에는 `depot` 미전달 (또는 무시).

### `scraper/scrapers/flor.py`

이미 `query(..., depot: str | None = None)` 시그니처 보유. `_resolve_depot`이 사용자 명시 우선, fallback PORT_DEFAULT_DEPOT. **변경 없음**.

### `scraper/routers/flor_depots.py` *(신규)*

```python
@router.get("/flor/depots")
def list_flor_depots(company: str, region: str, x_api_key: str | None = Header(None)):
    _check_api_key(x_api_key)
    return {"depots": list_depots(company, region)}
```

### `frontend/app/api/flor/depots/route.ts` *(신규 프록시)*

기존 `/api/query` 프록시와 동일 패턴. 세션 인증 + X-API-Key 헤더 + 쿼리 패스스루.

---

## 7. 작업 순서

1. 본 계획서 검토·승인.
2. **1회용 수집 스크립트** `scraper/scripts/collect_flor_depots.py` 작성.
3. 사용자가 region 5개 × 회사 2개 수집 실행 → JSON 결과 전달.
4. `scraper/scrapers/flor_depots.py` 생성 + 수집 결과 이식.
5. 백엔드: `GET /flor/depots` 라우터 + 쿼리 모델에 `depot` 추가.
6. 프론트: `/api/flor/depots` 프록시 + SearchForm에 조건부 Depot 드롭다운 + 조회 요청 바디 확장.
7. 로컬 타입체크/import 검증.
8. 커밋 + push.

수집은 사용자 환경에서 한 번 진행해야 하므로 **2~3단계는 별도 라운드**로 분리됨. 그 이전(스크립트 작성)과 그 이후(이식·UI·API)는 한 라운드에 묶을 수 있음.

---

## 8. 알아야 할 것 / 운영 인계

- 수집은 **실 계정으로 사이트에 로그인하는 작업**이라 환경변수(`SK_FLOR_ID/PW`, `HA_FLOR_ID/PW`)가 로컬에 세팅돼 있어야 함.
- Florens가 신규 depot을 추가하면 코드 갱신 필요 → `flor_depots.py` 한 곳만 수정하면 됨. 변경 빈도 낮을 것으로 추정 (depot 변경은 드묾).
- depot이 reefer 미수용 등 제약이 있으면 Step 3에서 거부됨 — 이미 `flor.py`의 거부 사유 파싱 로직이 처리 중. UI에 depot 선택지를 보여줄 때 "수용 가능 타입" 같은 메타 정보까지 표시할지는 후속 작업.
- 미선택 상태에서 조회 시도하면 백엔드가 fallback (INCHON만 가능)되어 부산/광양은 실패함. 프론트에서 미선택을 막아 사용자 혼선 차단.

### 본 계획서가 다루지 않는 것

- depot별 수용 가능 타입(reefer/dry) 메타데이터 UI 노출 — 사이트가 거부 사유로 알려주므로 1차 범위 외.
- 수집 자동화의 스케줄링 — 변경 빈도가 낮아 수동 갱신으로 충분.
- FLOR 외 임대사의 depot 선택 — 본 문서는 FLOR 전용.
