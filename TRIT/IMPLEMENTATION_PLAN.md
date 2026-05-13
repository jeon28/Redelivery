# TRIT 스크래퍼 구현 계획서

> 작성일: 2026-05-13
> 상태: 검토 대기
> 분석 근거: `TRIT/ANALYSIS.md`

---

## 1. 목표

TRIT(Triton) 사이트에 대해 **조회 + 자동 발급(Stage 1→3) 통합 자동화**를 구현한다.
요청된 컨테이너 목록을 입력받아 임대사 사이트에서 반납 예약을 시도하고, 발급된 반납번호 또는 거부 사유를 표준 API 형식으로 반환한다.

---

## 2. 입출력 (API 계약)

### 입력 (Vercel → Railway, 기존 PLAN.md §5 형식 준수)

```json
POST /query
{
  "company": "장금상선" | "흥아라인",
  "lessor": "TRIT",
  "containers": ["TCLU8769849", ...],
  "date": "2026-05-13",     // TRIT 폼에 날짜 필드 없음 → 무시
  "region": "부산"            // → country=KOREA, port=BUSAN 매핑
}
```

### 출력 (각 컨테이너별 1행)

```json
{
  "container_no": "TCLU8769849",
  "lessor": "TRIT",
  "available": true,
  "return_location": "Coolstar Co., Ltd.",   // Stage 3 결과의 Depot Name
  "return_no": "ABUSG48854",                 // Stage 2/3 후 발급된 반납번호
  "reason": null,                            // 거부 시에만 채움
  "status": "Created"                        // "Created" | "PendingCreate" | "Invalid"
}
```

거부 케이스 예:
```json
{
  "container_no": "TCLU9479119",
  "lessor": "TRIT",
  "available": false,
  "return_location": null,
  "return_no": null,
  "reason": "This unit may not be returned as it is currently on lease to [SNKX].",
  "status": "Invalid"
}
```

---

## 3. 파일 위치

| 파일 | 역할 |
|------|------|
| `scraper/scrapers/trit.py` (신규) | `TritScraper(BaseScraper)` 구현 |
| `scraper/scrapers/base.py` (기존) | 변경 없음 |
| `scraper/scrapers/__init__.py` (수정) | `get_scraper` 에 `TRIT` 분기 추가 |
| `scraper/test_trit.py` (기존) | 분석 스크립트 — 그대로 유지 |
| `scraper/test_trit_finalize.py` (기존) | 분석 스크립트 — 그대로 유지 |

> 임대사 폴더 규칙 준수: 실행 코드는 `scraper/scrapers/`, 문서는 `TRIT/`.

---

## 4. 클래스 설계

```python
class TritScraper(BaseScraper):
    LOGIN_URL  = "https://tools.tritoncontainer.com/tritoncontainer/login/auth"
    CREATE_URL = "https://tools.tritoncontainer.com/tritoncontainer/redeliverySession/create"

    async def login(self) -> bool: ...
    async def query(self, containers: list[str], region: str) -> list[dict]: ...

    # 내부 헬퍼
    async def _dismiss_cookie_banner(self): ...
    async def _select_location(self, country: str, port: str): ...
    async def _add_unit_numbers(self, containers: list[str]): ...
    async def _submit_validate(self) -> str: ...   # 반환: validate URL
    def _parse_invalid_table(self, page) -> list[dict]: ...
    def _parse_valid_table(self, page) -> list[dict]: ...
    async def _continue_redelivery(self) -> str: ...   # 반환: redelivery number (URL에서 추출)
    async def _finalize(self) -> dict: ...             # 반환: 최종 결과 행
```

---

## 5. 처리 흐름

```
login()
  └─ POST /login/auth (id/pw 자동 탐지)

query(containers, region)
  ├─ region → (country, port) 매핑
  ├─ goto /redeliverySession/create
  ├─ Cookie banner dismiss
  ├─ Select2: country / port / unitNumbers 설정
  ├─ Click "Request Redelivery" → /redeliverySession/validate
  ├─ Parse Invalid table → 거부 행 수집
  ├─ #redeliveriesTab 클릭 → 유효 단위 확인
  │
  ├─ 유효 단위 존재 시:
  │    ├─ Click "Continue Redelivery Request" → /redelivery/create/<no>
  │    ├─ URL에서 redelivery number 추출
  │    ├─ Status 확인 ("Pending Create")
  │    ├─ Click "Finalize" → /redeliverySession/finish/<id>
  │    └─ Parse 최종 결과 테이블 → 발급 행 수집
  │
  └─ 입력 컨테이너별로 결과 행 merge → list 반환
```

---

## 6. 지역 매핑 (region → country, port)

`config/regions.py` (또는 `trit.py` 내 상수)에 매핑 테이블 둠.

| region (입력) | country | port |
|--------------|---------|------|
| 부산 | KOREA | BUSAN |
| 인천 | KOREA | INCHON |
| 광양 | KOREA | KWANGYANG (확인 필요) |
| 평택 | KOREA | PYEONGTAEK (확인 필요) |
| 울산 | KOREA | ULSAN (확인 필요) |

- 미매핑 region 입력 시 `ValueError` 발생 → API가 400 응답.
- 한국 외 지역(예: 상해)은 추후 확장.

---

## 7. 중복 발급 방지

- **1차 방어**: Triton 사이트 자체가 이미 발급된/리스 중 컨테이너는 validate 단계에서 거부 (사유 표시). 별도 사전 체크 불요.
- **2차 방어**: 동일 요청 중복 호출 방지 — 스크래퍼는 stateless이므로 호출 측(API Route)에서 짧은 시간 내 동일 (container, lessor) 요청 락 또는 캐시 필요. **본 작업 범위 외**, 향후 별도 합의.

---

## 8. 에러 처리

| 상황 | 처리 |
|------|------|
| 로그인 실패 | `RuntimeError("TRIT 로그인 실패")` (base 패턴 따름) |
| 지역 매핑 실패 | `ValueError("지원하지 않는 지역: <name>")` |
| validate 페이지 미도달 | 결과 행에 `status="Error"`, `reason="validate 단계 실패"` |
| Stage 2/3 중 오류 | 해당 컨테이너만 `status="Error"`, 발급된 다른 컨테이너 결과는 보존 |
| Select2/jQuery 미로드 | `RuntimeError("페이지 구조 변경 의심 — 분석 재실행 필요")` |
| 타임아웃 | `wait_for_load_state` 타임아웃 시 부분 결과라도 반환 시도 |

---

## 9. 테스트 계획

1. **로그인 단독 테스트**: SK/HA 양 계정 로그인 성공 확인.
2. **거부 케이스만 입력**: 이미 turn-in된 컨테이너 등 → invalid 결과만 반환되는지.
3. **혼합 케이스**: 일부 유효 + 일부 무효 → 양쪽 모두 결과에 포함되는지.
4. **전 단계 통합 테스트**: 실제 반납할 컨테이너 1건으로 end-to-end. **사용자 사전 승인 후 1회만**.
5. **결과 검증 후 발급분 수동 취소** (테스트 단계 동안).

> 통합 테스트는 `scraper/test_trit_full.py` 신규 작성 (또는 기존 `test_trit.py` 의 EXECUTE 플래그 활용).

---

## 10. 작업 순서

1. `IMPLEMENTATION_PLAN.md` 검토/승인 — **현재 단계**
2. `scrapers/trit.py` 구현 (login + query 골격)
3. 거부 케이스 단독 테스트 (Stage 1만 발동되는 입력으로)
4. 유효 케이스 end-to-end 테스트 (사용자 사전 승인 + 발급분 수동 취소)
5. `scrapers/__init__.py` (`get_scraper`)에 TRIT 분기 추가
6. `routers/query.py` 가 자동으로 TRIT 라우팅 확인
7. 결과 정리, ANALYSIS.md 업데이트, 다음 임대사로 이동

---

## 11. 미결 / 후속 항목

- 한국 항구 외 region 매핑은 추후 확장.
- "Pending Create" 상태에서 Finalize 직후 즉시 "Created"가 되는지 확인됨 (2026-05-13). "Pending 지연 생성" 케이스는 운영 중 수집 후 별도 처리 로직 검토.
- 발급된 반납번호의 후속 조회/취소 자동화는 본 범위 외 (`/redeliveryFind/index` 추가 분석 필요 시 별도 작업).
