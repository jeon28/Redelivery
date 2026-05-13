# GOLD 스크래퍼 구현 계획서

> 작성일: 2026-05-14
> 상태: 검토 대기
> 분석 근거: `GOLD/ANALYSIS.md`

---

## 1. 목표

Touax(`https://www.touax-container.com`) 사이트에 대해 **조회 + 자동 발급(Search → "Off hire" → Confirm) 통합 자동화**를 구현한다.
요청된 컨테이너 목록을 입력받아 임대사 사이트에서 off-hire 예약을 시도하고, 발급된 RA####### 또는 거부 사유를 표준 API 형식으로 반환한다.

---

## 2. 입출력 (API 계약)

### 입력 (기존 `QueryRequest` 그대로)

```json
POST /query
{
  "company": "장금상선" | "흥아라인",
  "lessor": "GOLD",
  "containers": ["GLDU9717652", ...],
  "region": "INCHON"
}
```

### 출력 (각 컨테이너별 1행 — 기존 `ContainerResult` 그대로)

| 필드 | GOLD 매핑 |
|------|----------|
| `container_no` | 입력값 (대문자 정규화) |
| `available` | Search 결과/모달 "can be off hire" 테이블에 포함 시 True |
| `depot` | Search 결과 행 또는 모달의 Depot (예: `SEUNGJIN ENTERPRISE`) |
| `booking_ref` | Confirm 직후 `/off-hire/history`에서 매칭된 `RA#######` |
| `over_caps` | N/A → `null` |
| `close_date` | history의 Period (예: `13/May/2026`) |
| `reason` | 거부 메시지 (Search 결과 셀 또는 모달 "cannot" 테이블) |

---

## 3. 파일 위치

| 파일 | 역할 |
|------|------|
| `scraper/scrapers/gold.py` (신규) | `GoldScraper(BaseScraper)` 구현 |
| `scraper/scrapers/base.py` (수정) | `get_scraper`에 `GOLD` 분기 추가 |
| `scraper/test_gold.py` (기존) | 분석/인스펙션 스크립트 (Phase 5+ 보존) |
| `scraper/test_gold_scraper.py` (신규) | 프로덕션 클래스 통합 동작 테스트 |
| `config/credentials.py` (수정 완료) | 장금 lessors에 `GOLD` 포함 — 본 작업에서 추가 변경 없음 |

---

## 4. 클래스 설계

```python
class GoldScraper(BaseScraper):
    LOGIN_URL  = "https://www.touax-container.com/login"
    OFF_HIRE   = "https://www.touax-container.com/off-hire"
    HISTORY    = "https://www.touax-container.com/off-hire/history"

    async def login(self) -> bool: ...
    async def query(self, containers: list[str], region: str) -> list[dict]: ...

    # 내부 헬퍼
    async def _dismiss_cookie_banner(self): ...
    async def _set_city(self, city_code: str): ...                # TomSelect 네이티브 select에 값 + change
    async def _search_one(self, city_code, container) -> dict:    # 단일 컨테이너 조회/발급 처리
    async def _open_off_hire_modal(self) -> bool: ...             # "Off hire" 버튼 클릭 + 모달 로딩 대기
    async def _parse_modal_cannot(self) -> dict[str,str]: ...     # {container: reason}
    async def _parse_modal_can(self)    -> dict[str,str]: ...     # {container: depot}
    async def _click_confirm(self) -> bool: ...                   # 모달 Confirm 클릭 (실 발급)
    async def _lookup_history(self, container) -> dict|None: ...  # history에서 RA#/period/depot 추출
```

---

## 5. 처리 흐름

```
login()
  ├─ POST /login (id/pw 자동 탐지)
  └─ 쿠키 배너(tarteaucitron) dismiss

query(containers, region)
  ├─ region → city_code 매핑
  ├─ 입력 컨테이너 정규화/중복 제거
  └─ for each container:                  # GOLD는 단일 입력 필드라 1건씩 처리
        ├─ goto /off-hire
        ├─ _set_city(city_code)
        ├─ container 입력
        ├─ Search 클릭
        ├─ 결과 테이블 1행 파싱
        │     - "not currently on lease" / "Please contact" 등 → invalid (reason 기록, 종료)
        │     - 정상 행 (Depot 표시) → 다음 단계
        ├─ "Off hire" 모달 열기 → 콘텐츠 로딩 대기
        ├─ _parse_modal_cannot() 와 _parse_modal_can() 호출
        │     - 무효: reason 기록, Cancel 닫기
        │     - 유효: depot 기록
        ├─ 유효 시 Confirm 클릭 (실 발급)
        ├─ 발급 확인을 위해 /off-hire/history 조회
        │     - 동일 container의 최신 RA####### 추출 (period/depot 동기)
        └─ 결과 행 갱신

return [results in input order]
```

---

## 6. Region → City 매핑

| region (입력) | city code | 도시명 |
|--------------|----------|--------|
| BUSAN / 부산 | `KRPUS` | BUSAN |
| INCHON / INCHEON / 인천 | `KRINC` | INCHEON |
| GWANGYANG / 광양 | `KRKAN` | GWANGYANG |
| KWANGYANG | `KRKWA` | KWANGYANG (별칭) |
| UIWANG / 의왕 | `KRUWN` | UIWANG |
| GUNSAN / 군산 | `KRKUV` | GUNSAN |
| YANGSAN / 양산 | `KRYSN` | YANGSAN |
| SEOUL / 서울 | `KRSEL` | SEOUL |

- 미매핑 region 입력 시 모든 컨테이너에 `reason="지원하지 않는 지역: <name>"` 반환.
- Touax 도시 옵션은 1624개 — 향후 한국 외 지역 확장 가능.

---

## 7. Date 처리

- 기존 `QueryRequest`에 `date` 필드 없음 → GOLD의 `Redelivery month` 필드는 **현재 월(MM/YYYY)** 기본값을 그대로 사용.
- 폼에 손대지 않으면 화면 기본값이 채워져 있어 추가 작업 불요.

---

## 8. 중복 발급 방지

- **사이트 자체 방어**: 이미 RA가 있는 컨테이너는 "Container not currently on lease" 등으로 거부됨. 사전 체크 불요.
- **race 보호**: 호출 측 책임 (본 범위 외).
- **단일 컨테이너 1건 처리**: 동일 입력에서 같은 컨테이너 중복 입력 시 set으로 dedup.

---

## 9. 에러 처리

| 상황 | 처리 |
|------|------|
| 로그인 실패 | `RuntimeError("GOLD 로그인 실패")` |
| 지역 매핑 실패 | 모든 입력 컨테이너에 동일 reason 행 반환 |
| Search 페이지 진입 실패 | 해당 컨테이너만 `reason="조회 실패"` |
| 결과 행 없음 | `reason="결과 없음"` |
| 모달 미로딩 (타임아웃) | `reason="모달 로딩 실패"` |
| Confirm 후 history에서 RA 못 찾음 | `available=True` 유지, `booking_ref=None`, `reason="발급은 완료된 듯하나 RA 추출 실패"` (수동 확인 권장 마커) |

---

## 10. 테스트 계획

1. **로그인 단독**: SK/HA 양 계정 로그인 성공.
2. **거부 케이스**: `GLDU7591349` (반납완료) + KRPUS → reason="Container not currently on lease" 또는 모달 reason.
3. **도시 매칭 실패**: `GLDU9717652` + KRPUS → 모달 "OFF-HIRE NOT ALLOWED. UNIDENTIFIED DEPOT" reason.
4. **유효 E2E**: **사용자 사전 승인 + 발급 후 수동 원상복귀** 사이클로 1건만.
5. **혼합**: 위 3개 컨테이너 동시 입력 → 결과 정확성 검증.

> 통합 테스트 스크립트: `scraper/test_gold_scraper.py` (`EXECUTE_BOOKING` 명시 플래그, 기본 False).

---

## 11. 작업 순서

1. **본 계획서 검토/승인** — 현재 단계
2. `scrapers/gold.py` 구현 (login + query 골격, 단일 컨테이너 처리)
3. `scrapers/base.py`의 `get_scraper`에 `GOLD` 분기 추가
4. 거부 케이스만 사용한 안전 테스트 (test_gold_scraper.py)
5. 사용자 사전 승인 후 유효 케이스 E2E (사용자가 원상복귀)
6. 결과 정리, 다음 임대사(FLOR)로 이동

---

## 12. 미결 / 후속 항목

- 다중 컨테이너 단일 폼 입력 가능성 (콤마/공백 분리) — 분석 추가 필요. 본 구현은 1건씩 처리.
- 한국 외 지역 region 매핑 — 운영 중 확장.
- 발급 후 취소(원상복귀) 자동화 — 별도 작업 (사용자 명시: "취소는 추후 개발").
- `/off-hire-ref-check` 활용한 read-only 조회 전용 모드 — 향후 옵션 추가 가능.
