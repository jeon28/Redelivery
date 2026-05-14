# GESE 스크래퍼 구현 계획서

> 작성일: 2026-05-14
> 상태: 검토 대기
> 분석 근거: `GESE/ANALYSIS.md`

---

## 1. 목표

SeaCo(`https://seaweb.seacoglobal.com`) 사이트에 대해 **조회 + 자동 발급(Add → Validate → Submit) 통합 자동화**를 구현.
요청된 컨테이너 목록을 입력받아 임대사 사이트에서 RA를 발급하고, 발급된 번호 또는 거부 사유를 표준 API 형식으로 반환.

---

## 2. 입출력 (API 계약)

### 입력 (기존 `QueryRequest` 그대로)

```json
POST /query
{
  "company": "장금상선" | "흥아라인",
  "lessor": "GESE",
  "containers": ["SEGU9586313", "CRXU9980434", ...],
  "region": "BUSAN"
}
```

`lessor`는 `GESE+CROS` / `GESE+SGCN` 변형 입력 가능 — `_normalize_lessor`가 GESE로 통합 (이미 적용됨).

### 출력 (각 컨테이너별 1행 — 기존 `ContainerResult`)

| 필드 | GESE 매핑 |
|------|----------|
| `container_no` | 입력값 정규화 |
| `available` | Validate 결과 `Status="OK"` 이고 Submit 성공 시 True |
| `depot` | Validate 결과의 `Depot Name` (예: `2724 - Seyang Logistics, CO,. LTD`) |
| `booking_ref` | Submit 후 발급된 RA 번호 (형식 미확인 — 실행 시 확정) |
| `over_caps` | N/A → `null` |
| `close_date` | Form의 Expiry Date (DD/MM/YYYY) |
| `reason` | `Status="ERROR"` 행의 Messages 내용 |

---

## 3. 파일 위치

| 파일 | 역할 |
|------|------|
| `scraper/scrapers/gese.py` (신규) | `GeseScraper(BaseScraper)` 구현 |
| `scraper/scrapers/base.py` (수정) | `get_scraper` 에 `GESE` 분기 추가 (`_normalize_lessor`로 GESE+CROS/SGCN도 매핑) |
| `scraper/test_gese.py` (기존) | 분석/인스펙션 스크립트 |
| `scraper/test_gese_scraper.py` (신규) | 프로덕션 클래스 통합 동작 테스트 |

---

## 4. 클래스 설계

```python
class GeseScraper(BaseScraper):
    LOGIN_URL    = ENTRY_URL_WITH_HASH
    REQUEST_HASH = "#/navCus_RedeliveryRequest"

    async def login(self) -> bool: ...
    async def query(self, containers: list[str], region: str) -> list[dict]: ...

    # 내부 헬퍼
    async def _goto_request(self): ...
    async def _select_city(self, city: str): ...                  # ComboBox 입력 + 옵션 클릭
    async def _add_to_returns(self, units: list[str]) -> bool: ...
    async def _select_all_rows(self): ...                          # .sapUiTableSelectAllCheckBox 클릭
    async def _validate(self) -> list[dict]: ...                   # 행별 [{unit, lease_type, depot, status, message}]
    async def _submit(self) -> dict | None: ...                    # 발급 결과 캡처
    async def _reset_form(self): ...                               # Staging List 클리어
```

---

## 5. 처리 흐름

```
login()
  ├─ goto ENTRY_URL → SAP 폼 채움 → Log On
  └─ 대시보드(/navCus_Dashboard) 도달 확인

query(containers, region)
  ├─ region → city 매핑 (영문)
  ├─ 컨테이너 정규화 + 중복 제거
  ├─ goto /navCus_RedeliveryRequest
  ├─ City ComboBox에 영문 city 입력 + 옵션 클릭
  ├─ Serial No. textarea에 컨테이너 \n 입력 (max 25개 단위로 chunk)
  ├─ Add to Returns 클릭 → Staging List 생성
  ├─ SelectAll 클릭 (Playwright force) → 행 선택
  ├─ Validate 클릭 → Status / Depot / Lease Type 등 추출
  │     - Status="ERROR" 행: reason 기록 → 결과 행 채움
  │     - Status="OK" 행: 다음 단계 후보
  ├─ ERROR만 있으면: 결과 정리 후 종료
  ├─ OK 행 있음 → Submit 클릭 → 발급 결과 화면 파싱
  │     - 발급된 RA 번호 매핑 (행/컨테이너별)
  └─ 결과 list 반환 (입력 순서 보존)
```

---

## 6. Region → City 매핑

GESE는 영문 city 이름 그대로 사용 (코드 변환 불요).

| region (입력) | GESE City |
|--------------|-----------|
| BUSAN / 부산 | `Busan` |
| INCHON / INCHEON / 인천 | `Inchon` (또는 `Incheon` — 분석 시 확인) |
| GWANGYANG / 광양 | `Gwangyang` (확인 필요) |
| (한국 외) | 운영 중 확장 |

미매핑 시 모든 컨테이너에 `reason="지원하지 않는 지역: <name>"`.

---

## 7. 다중 컨테이너 배치 처리

- Serial No. textarea의 **최대 25개** 제약.
- 입력이 25개 초과 시 25개씩 chunk:
  - 각 chunk에 대해 Add to Returns → SelectAll → Validate → Submit
  - 각 batch 결과를 누적
- 또는 1회 호출 = 1 batch (25개 이하)만 지원 — MVP는 단일 batch로 시작, 25개 초과 시 입력 끝부분 무시 후 reason 마커.

본 구현: **MVP는 max 25개 가정** (운영 중 더 큰 입력 발생 시 chunk 로직 추가).

---

## 8. 발급 결과 (RA 번호) 추출

- Submit 후 결과 화면의 RA 번호 형식과 위치 미확인 (실 실행 시 확정).
- 추정: 결과 테이블 또는 success message에 RA 표시.
- 폴백: Submit 후 `Redelivery View/Cancel`에서 컨테이너로 역조회하여 RA 추출 (View/Cancel은 RA 번호 입력만 받으므로 이건 불가) — 대안: `Customer Activity Reports` 또는 Outstanding Redelivery 타일 클릭으로 최신 발급 조회.
- 가장 확실한 방법: Submit 결과 화면 파싱 + 실패 시 `available=True, booking_ref=None, reason="발급 완료 추정, RA 추출 실패"` 마커.

---

## 9. 에러 처리

| 상황 | 처리 |
|------|------|
| 로그인 실패 | `RuntimeError("GESE 로그인 실패")` |
| 지역 매핑 실패 | 모든 입력에 동일 reason 행 |
| Request 페이지 진입 실패 | 결과 행에 `reason="페이지 진입 실패"` |
| City 옵션 매칭 실패 | 결과 행에 `reason="해당 지역 옵션 없음"` |
| Add to Returns 무반응 | `reason="Add to Returns 실패"` |
| Validate 후 행 못 찾음 | `reason="Validate 결과 미수신"` |
| Status=ERROR | `available=False, reason=<Messages 내용>` |
| Submit 후 RA 못 찾음 | `available=True, booking_ref=None, reason="발급 완료 추정, RA 추출 실패"` |

---

## 10. 테스트 계획

1. **로그인 단독**: SK 계정으로 대시보드 도달.
2. **거부 케이스**: SEGU9586313(이미 ERROR 확인됨) + Busan → `available=False`, reason 포함.
3. **혼합**: SEGU9586313 (ERROR) + CRXU9980434 (OK) → 한 행은 reason 한 행은 발급 진행.
4. **유효 E2E**: **사용자 사전 승인 + 발급 후 수동/자동 원상복귀** (GESE는 View/Cancel 메뉴가 있어 후속 자동 cleanup 가능성).

> 통합 테스트 스크립트: `scraper/test_gese_scraper.py` (`EXECUTE_BOOKING` 플래그 기본 False).

---

## 11. 작업 순서

1. **본 계획서 검토/승인** — 현재 단계
2. `scrapers/gese.py` 구현 (login + query 골격, max 25 단일 batch)
3. `scrapers/base.py`의 `get_scraper`에 `GESE` 분기 추가 (`_normalize_lessor` 이미 적용)
4. 거부 케이스만 사용한 안전 테스트
5. 사용자 사전 승인 후 유효 케이스 E2E (RA 형식 확정)
6. 결과 정리, ANALYSIS.md에 Submit 결과 화면 정보 보강

---

## 12. 미결 / 후속 항목

- **RA 번호 형식**: 실 발급 후 확정 (TRIT의 ABUSG, GOLD의 RA, FLOR의 PPR과 다를 가능성).
- **다른 한국 항구 매핑** (Inchon, Gwangyang 등): City 드롭다운 옵션 운영 중 수집.
- **25개 초과 chunk 처리**: 운영 중 필요해지면 추가.
- **취소(원상복귀) 자동화**: `Redelivery View/Cancel` 활용 별도 작업 — 본 범위 외.
- **흥아라인(`GESE+SGCN`) 동작 검증**: SK와 동일 구조이지만 Customer Name 텍스트 등 차이 운영 중 보완.
- **Status 값 확장**: `OK`/`ERROR` 외 다른 값 운영 중 수집.
