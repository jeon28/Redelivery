# FLOR 조회 재설계 계획서

> 작성일: 2026-05-15
> 상태: **구현 착수** — §5 오픈 이슈 확정 완료 (2026-05-15)
> 배경 자료: `./ANALYSIS.md`, `./_inspect/apply_*.png`, `../PLAN_COMPLETED_LABEL.md`

---

## 1. 문제

### 1-1. 현재 (잘못된) 동작 — `scraper/scrapers/flor.py`

1. 로그인 후 **Redelivery Status 탭**으로 진입 (라인 144-152)
2. Unit No 검색 → 결과 테이블에서 가장 우선순위 높은 PPR 행 선택 (Open > Closed > VOID)
3. 그 PPR 정보를 그대로 가능여부/반납번호/유효기간으로 반환

### 1-2. 증상

- **과거 기록을 현재 정보처럼 반환**: 예: `FSCU5891134` → `PPF50838` (Status=Closed, Order Date=2020-11-10) → 화면엔 `11/10 완료`로 표시되지만 사용자가 알고 싶은 건 "오늘 반납 가능한가"
- **거부 사유 미캡처**: Apply Redelivery Step 3에서만 노출되는 사유(over caps, depot 불수용, 사이즈 미일치, 이미 활성 PPR 등) 전혀 안 잡힘
- 결과: 사용자 의도("지금 이 컨테이너 반납 가능?")와 시스템 답변("예전에 반납된 적 있음/없음")이 불일치

### 1-3. 본질적 원인

- ANALYSIS.md §6-7 에 분석된 Apply Redelivery 흐름이 구현에 반영되지 않음
- "조회 = read-only가 안전"이라는 잘못된 가정으로 Status 탭 read-only 흐름만 구현

---

## 2. 목표

**Apply Redelivery 3-step 위저드를 1차 경로**로 사용하여 다음을 정확히 반환:

| 케이스 | available | reason / 표시 |
|--------|-----------|--------------|
| Step3 유효행 + Confirm 성공 → 신규 PPR 발급 | True | 가능, 신규 PPR + Depot |
| Step3 거부행 (over caps) | False | 불가, "잔여 캡 초과 (Depot: ...)" |
| Step3 거부행 (depot 불수용) | False | 불가, "Depot이 reefer/dry 미수용" |
| Step3 거부행 (사이즈/계약 미일치) | False | 불가, 원본 사유 |
| Step3 거부행 (이미 활성 PPR 존재) | (오픈 이슈 §5-3) | 가능 (기존 PPR 반환) OR 불가 |
| Step3 거부행 (이전 반납 완료, 가능하면) | (오픈 이슈 §5-4) | "M/D 완료" or "이미 반납됨" |

---

## 3. 새 아키텍처

### 3-1. 흐름 (의사 코드)

```
async def query(containers, region):
    1. login (현행 유지)
    2. /func/redelivery#/ 진입 → Apply Redelivery 탭 (기본 활성)

    3. Step 1: Customer ID + Port + Depot 설정
       - Customer ID: SK → "SINOKOR" / HA → "HALINE"  (ANALYSIS.md §7 표)
       - Port: region 매핑 (INCHON → "INCHON (KRINC)" 등)
       - Depot: 오픈 이슈 §5-1 — 일단 단일 default depot 가정

    4. Next 클릭 → Step 2

    5. Step 2: Unit Numbers textarea 에 \n 구분으로 일괄 입력 (최대 100개)

    6. Next 클릭 → Step 3

    7. Step 3 결과 파싱:
       - 거부 테이블 (Unit | Contract | Equip Type | Reason) → results[unit] = 불가 + reason
       - 유효 테이블 → 후보 목록 valid_units

    8. Confirm Redelivery Order 버튼 상태 확인:
       - disabled(클래스 is-disabled) → 클릭 안 함, 모든 valid_units 도 "validation only" 로 처리
       - enabled → 클릭 (실 발급) → 발급된 PPR 목록 캡처

    9. (보조) Apply 직후 페이지에서 신규 PPR 의 상세(Depot 풀네임/Expiry/Open CAP) 가
       바로 노출되면 그대로 캡처. 부족하면 Redelivery Status 탭으로 이동 → 신규 PPR
       으로 검색 → enrichment

    10. results 정렬 + 안전장치 반환
```

### 3-2. 결과 dict 스키마 (변경 없음, 의미만 명확화)

| 키 | 값 | 비고 |
|----|-----|------|
| `container_no` | str | 입력 그대로 |
| `available` | bool | **Apply Redelivery 결과 기준** (Status 탭 기준 아님) |
| `status` | "available"/"completed"/"unavailable" | (현재 옵셔널) |
| `completed_date` | "M/D" or None | (현재 옵셔널 — §5-4 결정에 따라 의미 변경 가능) |
| `depot` | Step3/PPR 상세에서 추출 | |
| `booking_ref` | 신규 발급 PPR or 기존 활성 PPR(§5-3) | |
| `over_caps` | Open CAP (보조 조회 시) | |
| `close_date` | Expiry Date (보조 조회 시) | |
| `reason` | Step3 거부 사유 원본 | |

---

## 4. 구현 단계

각 단계는 **승인 후 다음으로 진행**.

### Phase A — 골격 (Apply Redelivery 위저드 자동화)

A1. `_navigate_to_apply()` — 탭 이동 헬퍼
A2. `_select_customer_id(company)` — SINOKOR / HALINE 라디오
A3. `_select_port(region)` — Element UI 드롭다운, JS evaluate
A4. `_select_depot(port, depot_pref)` — Element UI 드롭다운 (오픈 이슈 §5-1 정책 적용)
A5. `_step2_fill_units(containers)` — textarea \n 구분 입력
A6. `_step_next()` / `_step_back()` — Next/Back 클릭
A7. `_parse_step3(results)` — 거부/유효 테이블 분리 파싱

### Phase B — 발급 + 상세 캡처

B1. `_confirm_disabled()` — `classList.contains('is-disabled')` 체크
B2. `_click_confirm()` — 활성 시만 클릭, dialog/post-confirm 대기
B3. `_capture_issued_refs()` — 발급된 PPR(다중 가능) 캡처
B4. `_enrich_via_status(ref_list, results)` — 보조 Status 조회 (Depot 풀네임, Expiry, Open CAP)

### Phase C — 안전 가드

C1. 5분 룰: Step 3 도달 후 시간 추적 (자동화에선 즉시 처리이므로 사실상 무방하지만 로그)
C2. 중복 컨테이너 입력 제거
C3. Apply 실패 시 fallback — 로그인 OK 인데 페이지 진입 실패 등
C4. (선택) Status 보조 조회 실패해도 1차 결과는 보존

### Phase D — 폐기/정리

D1. 현 `_search_one`, `_expand_and_extract` 는 Status 보조 조회 용도로 축소
D2. `query()` 안전장치 루프의 reason fallback 메시지를 새 흐름에 맞춰 갱신
D3. `PLAN_COMPLETED_LABEL.md` 갱신 — completed 데이터 출처 변경 명시

---

## 5. 확정 사항 (2026-05-15)

### 5-1. Depot 선택 정책 — **Port별 default 하드코딩 + 향후 사용자 선택 확장성**

#### 2단 구조

1. **사용자 명시 (확장 슬롯)**: 프론트엔드 `SearchForm` → `/api/query` → FastAPI 요청 본문에 `depot` 필드를 추가할 자리 마련 (Optional[str], 기본 None). 사용자가 명시한 depot 옵션 문자열이 있으면 그대로 사용.
   - 현 PR 에서는 프론트엔드 UI 추가 안 함. 백엔드/스크래퍼 시그니처만 확장 슬롯 미리 만들어 둠.
   - 향후 PR 에서 BUSAN/GWANGYANG 사용 시 드롭다운 UI 붙이면 바로 연결됨.

2. **Default fallback**: 사용자 명시 없으면 `PORT_DEFAULT_DEPOT` dict 에서 Port → Depot 매핑 조회.

#### 코드 구조 (예시)

```python
# scrapers/flor.py
PORT_DEFAULT_DEPOT: dict[str, str] = {
    "INCHON": "(KRINC04) SeungJin Enterprise Co., Ltd. (KRINC04)",
    # BUSAN / GWANGYANG: 미설정. 사용자 명시 depot 없으면 에러.
}

def _resolve_depot(region: str, user_depot: str | None) -> str:
    if user_depot:
        return user_depot
    default = PORT_DEFAULT_DEPOT.get(region.upper())
    if not default:
        raise RuntimeError(f"{region} default depot 미설정 — depot 명시 필요")
    return default
```

옵션 텍스트 포맷은 `(CODE) NAME (CODE)` (코드가 앞·뒤 두 번 나옴 — apply_07_step3.html 에서 `(KRINC08) The Logis New Port CY (KRINC08)` 패턴 확인). 선택 시 `(<CODE>)` 부분일치로 매칭 (풀네임 변경에 강건).

| Port | Default Depot | 비고 |
|------|--------------|------|
| `INCHON` | `(KRINC04) SeungJin Enterprise Co., Ltd. (KRINC04)` | 사용자 지정 (2026-05-15) |
| `BUSAN` (PUSAN) | (없음 — 명시 필요) | 향후 사용자 드롭다운에서 선택 |
| `GWANGYANG` | (없음 — 명시 필요) | 동일 |

#### API 시그니처 확장 (이번 PR 에서 미리 적용)

- `FlorScraper.query(containers, region, depot=None)` — depot 인자 추가
- `BaseScraper.run(containers, region, depot=None, headless=True)` — base 도 확장
- `routers/query.py` `QueryRequest` 에 `depot: Optional[str] = None` 추가
- `frontend/components/SearchForm.tsx` request body에 `depot` 자리 추가 (UI는 없지만 향후 확장 대비)

다른 임대사(TRIT/GOLD/TEXA/GESE) 시그니처도 같이 `depot=None` 받게 확장하되 사용은 안 함 (FLOR만 우선 활용).

### 5-2. Confirm 클릭 = 실 발급 — **항상 발급**

매 조회마다 Apply Step3 → Confirm Redelivery Order 즉시 클릭 → 실 PPR 발급. 사용자 의도 = "조회=신청".

- Confirm 버튼이 `is-disabled` 상태면 클릭 안 함 (모든 단위가 invalid). 결과는 거부 사유만 반환.
- 중복 발급 방지는 FLOR 자체 검증에 의존 (이미 활성 PPR 있으면 §5-3 경로로 처리됨).

### 5-3. 이미 활성 PPR 이 있는 컨테이너 — **거부 reason에서 PPR 추출 → 가능 처리**

Apply Step3 에서 "already has open redelivery PPRxxxxx" 류 메시지로 거부될 것으로 예상 (실 동작 1차 케이스로 검증 필요). 패턴 매치 후 기존 PPR을 추출:

- reason에 `PPR\d+` 패턴 발견 + 키워드 ("already", "open redelivery", "active" 등) → `available=True`, `booking_ref=<추출된 PPR>`, `reason=None`
- 매치 안되면 일반 거부 케이스로 폴백 → `available=False`, `reason=<원본>`

추가 보강: 기존 PPR을 Status 탭에서 검색하여 Depot/Expiry/CAP 채움 (보조 단계).

### 5-4. 이전 반납 완료 표기 — **Apply reason 파싱 + Status 보조 결합**

새 흐름은 두 단계 폴백:

1. **1차** — Apply Step3 거부 reason에서 "previously redelivered" / "closed" 패턴 + 날짜(YYYY-MM-DD 또는 mm/dd) 검출 시도. 검출되면 `status=completed`, `completed_date=M/D`, `reason="이미 반납됨 (Closed)"`.
2. **2차 폴백** — 1차 매치 실패해도 Apply가 단순 거부했을 가능성. 거부된 컨테이너를 Status 탭에서 재조회 → 가장 최근 Closed 행의 Order Date를 가져와 `completed_date` 채움.
3. 둘 다 실패 → 일반 거부로 처리.

→ §5-3과 마찬가지로 실 동작 확인 필요. 1차 구현은 가능한 패턴(broad regex)으로 보수적으로 시도하고, 실 데이터로 패턴 정련.

---

## 6. 영향 받는 파일

| 파일 | 변경 |
|------|------|
| `scraper/scrapers/flor.py` | **대규모 재작성**: `query()` 전면 교체. Status 탭은 보조 함수로 강등. `PORT_DEFAULT_DEPOT` 매핑 추가. `query()` 시그니처에 `depot` 인자 추가 |
| `scraper/scrapers/base.py` | `BaseScraper.run()` 시그니처에 `depot=None` 추가 |
| `scraper/scrapers/{texa,trit,gold,gese}.py` | `query()` 시그니처에 `depot=None` 받게 확장 (현재는 무시) |
| `scraper/routers/query.py` | `QueryRequest` 에 `depot: Optional[str] = None` 추가 |
| `frontend/app/api/query/route.ts` | 변경 없음 (request 본문 단순 패스스루) |
| `frontend/components/SearchForm.tsx` | request body에 `depot` 필드 자리 추가 (UI는 미추가, 향후 확장 슬롯) |
| `frontend/components/ResultTable.tsx` | 변경 없음 (response 스키마 동일) |
| `FLOR/ANALYSIS.md` | §9-10 갱신 (완료) |
| `FLOR/IMPLEMENTATION_PLAN.md` | 본 문서 (생성) |
| `PLAN_COMPLETED_LABEL.md` | §5-4 새 흐름에 맞춰 갱신 (데이터 출처 명시) |

---

## 7. 검증 계획

각 케이스마다 실 컨테이너로 E2E 1회씩:

1. 새 컨테이너 / 정상 발급 → 가능 + 신규 PPR
2. 동일 depot 에 over caps 상태 → 불가 + "over caps"
3. Reefer 컨테이너를 dry-only depot에 시도 → 불가 + "incapable"
4. 이미 활성 PPR 있는 컨테이너 → §5-3 결정에 따른 동작 확인
5. 이전에 closed 된 컨테이너 → §5-4 결정에 따른 동작 확인

각 케이스의 응답 JSON 과 화면 캡처를 `_inspect/` 에 보존하여 회귀 검증 기준으로 사용.

---

## 8. 비범위

- Status 탭 단독 조회 모드 (이력 조회 UI) — 별도 기능, 후속 작업
- Apply 실패 시 자동 재시도(retry) — 후속 작업
- 발급/조회 모드 분리 (§5-2 (c)) — 결정 시 별도 PR
- 다른 임대사(TRIT/GOLD/TEXA)의 동일 패턴 점검 — 본 PR 완료 후 검토

---

## 9. 다음 액션

1. **사용자**: §5 (4개 오픈 이슈) 결정 및 회신
2. (Optional) §5-3, §5-4 확인을 위한 실 컨테이너 테스트 캡처
3. Phase A1~A7 구현 → Phase B → Phase C → Phase D
4. 단계마다 dev/Railway 배포 후 사용자 검증
