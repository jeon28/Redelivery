# GOLD (Touax) 사이트 분석

> 분석일: 2026-05-13
> 분석 방식: Playwright 직접 조사
> 상태: 진행 중 — 신규 발급 흐름 일부 미확인

---

## 1. 로그인

| 항목 | 값 |
|------|-----|
| 로그인 URL | `https://www.touax-container.com/login` |
| 로그인 폼 | 2개 필드 (Username, Password) |
| 추가 인증 | 없음 (캡차/2FA 없음) |
| 로그인 후 이동 | `https://www.touax-container.com/` (마케팅 메인) |
| 도메인 베이스 | `https://www.touax-container.com/` |

### 자격증명 환경변수 키

| 선사 | ID 키 | PW 키 |
|------|-------|-------|
| 장금상선 (SK) | `SK_GOLD_ID` | `SK_GOLD_PW` |
| 흥아라인 (HA) | `HA_GOLD_ID` | `HA_GOLD_PW` |

> 2026-05-13 이전에는 SK 쪽 키가 `SK_GLOD_*`였으나 `SK_GOLD_*`로 통일됨.

### 로그인 사용자 표시

상단 우측 영역에 로그인한 ID(이메일)가 그대로 표시됨 (예: `container@sinokor.co.kr`).
TRIT처럼 별도의 사람 이름이 아닌 **로그인 ID 그대로 표시**.

---

## 2. 주요 메뉴 / 진입 경로

로그인 후 메인 페이지(`/`)에는 별도 대시보드가 없고, **마케팅 사이트로 이동**됨.
반납 관련 기능은 다음 3개의 **직접 URL**로 접근:

| 페이지 | URL | 용도 |
|--------|-----|------|
| Off-hire 신청 | `/off-hire` | 신규 반납 신청 (Search → 결과 + "Off hire" 모달) |
| Off-hire 이력 | `/off-hire/history` | 발급된 RA####### 목록 |
| Off-hire 단건 조회 | `/off-hire-ref-check` | Ref 또는 컨테이너 번호로 단건 확인 |
| Off-hire 요약 (모달) | `/off-hire/summary?location=&redelivery=&container=` | "Off hire" 버튼 클릭 시 fetch되는 모달 콘텐츠 (Stage 2/3) |
| Total loss declaration | `/loss-declaration` | 컨테이너 분실 신고 (반납 흐름과 별개) |

상단 메뉴는 `About us / Services / Equipment / Contact us` 마케팅 메뉴만 표시되며,
반납 메뉴는 별도 보이지 않음 — URL로 직접 진입해야 함.

---

## 3. Off-hire 신청 폼 (`/off-hire`)

### 페이지 정보

| 항목 | 값 |
|------|-----|
| 페이지 타이틀 | `Off hire` |
| 폼 이름 | `app_front_off_hire_filter` |
| 폼 method | **GET** (POST 아님) |
| 폼 action | `https://www.touax-container.com/off-hire` |

### 필드 구성

| 라벨 | name | id | 위젯 | 비고 |
|------|------|-----|------|------|
| City | `app_front_off_hire_filter[city]` | `app_front_off_hire_filter_city` | **TomSelect** (네이티브 select + JS 컨트롤) | 200 옵션. 옵션 value는 5자리 코드 (예: `KRBUS`=Busan, `ARBUE`=Buenos Aires). 검색/포커스 입력은 `_city-ts-control`. |
| Redelivery | `app_front_off_hire_filter[redelivery]` | `app_front_off_hire_filter_redelivery` | 텍스트 (MM/YYYY) | 기본값 현재 월 (예: `05/2026`). **월 단위만 입력** — 일 단위 없음. |
| Container numbers | `app_front_off_hire_filter[containerNumber]` | `app_front_off_hire_filter_containerNumber` | 텍스트 (단일) | 다중 컨테이너 입력 방식은 미확인 (콤마/공백/줄바꿈 추정 — 구현 시 검증) |
| (hidden) CSRF token | `app_front_off_hire_filter[_token]` | `app_front_off_hire_filter__token` | hidden | 매 요청마다 신선 토큰 필요 |

### 제출 버튼

- 라벨: **`Search`** (`<button type="submit" class="btn btn-primary">Search</button>`)
- GET 폼이므로 클릭 시 URL 파라미터로 검색 결과 페이지 이동
- 실제 발급(예약 생성)이 이 버튼인지 결과 화면에서 별도 액션인지 **미확인** — 추가 분석 필요

### 자동화 시 주의사항

- **TomSelect 위젯**: 단순히 native `<select>`에 값 설정 후 `change` 이벤트만 dispatch 하면 됨. (TRIT의 Select2와 유사 패턴)
- **GET 폼**: 직접 URL을 조합해도 동작 가능 (단, `_token`은 페이지 로드 시 fresh 토큰 필요)
- **Cookie 배너**: tarteaucitron 라이브러리 사용 — `#tarteaucitronAllAllowed` 또는 `#tarteaucitronPersonalize2` 버튼

---

## 4. Off-hire 이력 (`/off-hire/history`)

### 화면 구조

- 페이지 타이틀: `Off hire history`
- 안내: "Please find here your current open off-hire references. You can include the historical references in your list by selecting the option below before launching the research."
- **체크박스**: "Past month redeliveries completed" — 과거 완료분 포함 토글
- **Page size dropdown**: 50 (기본)
- **Export 버튼**: 결과 CSV 등 내보내기 추정

### 결과 테이블 (실 데이터 캡처, 2026-05-13 SK 계정)

| Redelivery reference | Period | Depot | Contract number | Container |
|---------------------|--------|-------|-----------------|-----------|
| RA434352 | 27/Apr/2026 | GUANG TONG JIAN YE CONTAINER SERVICES (HONGKONG) CO., LTD | 328901 | GLDU7467425 |
| RA435718 | 12/May/2026 | SHINJI-GLOBAL CY (NEW PORT) | 328901 | GLDU5698364 |

### 컬럼 의미

| 컬럼 | 자동화에서 활용 |
|------|----------------|
| Redelivery reference | **반납번호** (`RA<6자리숫자>` 형식) — `booking_ref`로 매핑 |
| Period | 반납 예정일 (`DD/Mon/YYYY` 영문 월 약어) — `close_date`로 매핑 |
| Depot | 반납지 — `depot`으로 매핑 |
| Contract number | 계약번호 (참고용) |
| Container | 컨테이너 번호 — 검색 키 |

### 링크 동작

- `RA##########` 텍스트는 `<a>` 태그이지만 `href="#"` (앵커만) — **JS로 모달/패널 토글 추정** (정확한 동작 미확인)

---

## 5. Off-hire 단건 조회 (`/off-hire-ref-check`)

### 화면 구조

- 페이지 타이틀: `Off hire reference check`
- 입력: **"Off hire reference"** 또는 **"Container numbers"** 둘 중 하나만 입력
- 제출: `Search` 버튼 (GET 폼)

### 결과 형식 (단일 문자열)

```
Unit <CONTAINER> is authorized to be off hired at depot : <DEPOT_NAME> during the period from <START_DATE> to <END_DATE> in redelivery reference <RA######>
```

#### 실측 예

> Unit `GLDU7467425` is authorized to be off hired at depot : `GUANG TONG JIAN YE CONTAINER SERVICES (HONGKONG) CO., LTD` during the period from `27/Apr/2026` to `27/May/2026` in redelivery reference `RA434352`

### 자동화 핵심 가치

- **read-only**: 발급 위험 없음 → 안전한 컨테이너 상태 조회용
- **단일 컨테이너 → 풀 정보** 추출 가능 (depot, period, ref)
- **추정 거부 케이스**: 컨테이너가 off-hire 권한 없으면 다른 메시지 반환 (미확인 — 운영 중 수집)

---

## 6. 신규 발급 흐름

> 2026-05-14 실측: `KRPUS / 05/2026 / GLDU7591349` (장금 반납완료 밴) 으로 Search 검증.

### Stage 1 — `/off-hire` Search (안전, 읽기 전용)

1. 폼 작성 (City + Redelivery 월 + Container number)
2. **Search 버튼** 클릭 — `<button type="submit" class="btn btn-primary">Search`
3. GET method → URL: `/off-hire?app_front_off_hire_filter[city]=KRPUS&[redelivery]=&[containerNumber]=GLDU7591349&_token=...`
4. 같은 페이지에 **결과 테이블이 추가로 렌더링됨** (실제 발급 없음)

### Search 결과 테이블

| 컬럼 | 유효 시 | 무효 시 (실측) |
|------|---------|----------------|
| Locations | (출고지/위치, 추정) | 빈칸 |
| Depot | 반납 가능 depot 이름 | 거부 메시지 (예: `Container not currently on lease. GLDU7591349`) |
| IATA | depot IATA 코드 | `contact us` 링크 |
| Container # | 컨테이너 번호 | 빈칸 |

확인된 거부 메시지:
- `Container not currently on lease. <UNIT>` — 이미 반납된 컨테이너

### Stage 2 — "Off hire" 버튼 (모달 오픈)

- 결과 테이블 우측 하단의 **"Off hire" 버튼** (anchor):
  ```html
  <a class="btn btn-primary modalClickoffHire"
     data-action="front#openModal"
     data-title="Off hire Summary"
     data-href="/off-hire/summary?location=<CITY>&redelivery=<MM/YYYY>&container=<UNIT>"
     href="#">Off hire</a>
  ```
- Stimulus.js 컨트롤러(`front#openModal`)가 모달을 열고 `data-href`에서 요약 콘텐츠 AJAX fetch
- 모달 콘텐츠는 비동기 로드되므로 자동화 시 **모달 본문 채워질 때까지 대기 필수**

### Stage 2 모달 (`/off-hire/summary`)

#### 모달 구조

- 제목: `Off hire Summary`
- 헤더 문구: `Here you can find the recapitulative data of your off hire`
- **요약 테이블 1**: City 코드 (예: `KRINC`), `Redelivery month` (예: `05/2026`)
- **분류 테이블** (컨테이너별 가능 여부):
  - 유효: `The following containers **can** be off hire` — 컬럼 `Container | Depot`
  - 무효: `The following containers **cannot** be off hire` — 컬럼 `Container | Reason`
  - 혼합 시 두 테이블 모두 노출
- 버튼:
  - **Cancel** (모든 케이스)
  - **Confirm** (유효 단위가 1개 이상일 때만 노출) — 이 버튼이 **실 발급 트리거**

#### Confirm 버튼 (실 발급)

```html
<a data-action="front#updateModal"
   data-title="Off hire confirmation"
   data-href="/off-hire/confirm?location=<CITY>&redelivery=<MM/YYYY>&container=<UNIT>&depot_nmat[0]=<DEPOT_CODE>@<UNIT>"
   class="ms-2 btn btn-primary btn_valider confirm">Confirm</a>
```

- 클릭 시 **`/off-hire/confirm?...`** 호출 = **즉시 실 발급** (RA######## 생성)
- `depot_nmat[0]` 파라미터: `<DEPOT_CODE>@<UNIT>` 형식 (예: `KRINCSJEA@GLDU9717652`)
  - `KRINCSJEA` = INCHEON / SEUNGJIN ENTERPRISE 의 depot 코드
- 응답은 모달 콘텐츠 갱신 (`front#updateModal`) — 발급 확인 화면

### 확인된 거부 메시지 (Stage 2 모달)

| Reason 문구 | 분류 | 의미 |
|------------|------|------|
| `OFF-HIRE NOT ALLOWED. UNIDENTIFIED DEPOT. PLEASE CONTACT OUR CUSTOMER SERVICE: LEASING.CUSTOMERSERVICE@TOUAX.COM` | 도시 매칭 실패 | 선택 도시에 Touax depot 매핑 없음 — 다른 도시(예: KRPUS→KRINC) 시도 |

### 실 발급 검증 (2026-05-14)

- 입력: `KRINC` + `05/2026` + `GLDU9717652` (장금 SK 계정)
- 결과: **`RA435880` 발급** (Depot=`SEUNGJIN ENTERPRISE`, Contract=`328901`)
- `/off-hire/history` 에서 새 행 즉시 표시 (Pending 단계 없이 바로 발급)
- 사용자가 수동 원상복귀 (취소 경로 자동화는 미파악)

---

## 7. 반납번호 / 데이터 형식 정리

| 항목 | 형식 | 예 |
|------|------|-----|
| 컨테이너 prefix (Touax owned) | `GLDU` | `GLDU7467425` |
| 반납번호 | `RA<숫자6자리>` | `RA434352`, `RA435718` |
| 도시 코드 (TomSelect value) | 국가코드(2) + 도시코드(3) | `KRBUS`(부산), `KRINC`(인천 추정), `ARBUE`(부에노스아이레스) |
| 반납 예정월 | `MM/YYYY` | `05/2026` |
| Period (이력 페이지) | `DD/Mon/YYYY` | `27/Apr/2026` |
| Depot 이름 | 전체 회사명 문자열 | `SHINJI-GLOBAL CY (NEW PORT)` |

---

## 8. 주의사항

- **Search 버튼의 안전성 미확인**: GET 방식이고 "Search"라는 라벨이지만, 결과 화면에서 자동 발급이 일어나는지 검증 필요. 안전 검증 전까지 자동화에서 호출 금지.
- **CSRF 토큰**: 매 요청마다 새 토큰 필요 — Playwright에서는 페이지 로드 후 form 내부 hidden value 사용.
- **취소 경로**: 발견 미수 — 향후 분석 필요 (Touax는 이메일 컨택 방식일 가능성).
- **다중 컨테이너 입력**: 단일 텍스트 input이라 다중 입력 분리자 미확인 — 구현 시 1건씩 호출하는 게 안전.

---

## 9. 선사 차이점 (SK / HA)

- 분석 시 **SK 계정**으로 확인됨. HA 계정은 별도 확인 미수.
- 양사 모두 동일 사이트(`touax-container.com`)에 별도 계정으로 로그인하는 구조이며 화면 구조는 동일 추정.
- 로그인 후 상단 우측에 표시되는 이메일이 다를 뿐, 화면/필드 구성은 같을 것으로 예상.

---

## 10. 자동화 활용 전략 (제안)

분석 결과를 보면 GOLD은 TRIT보다 **단순한 read-only 조회 경로**가 있습니다.

| 시나리오 | 권장 경로 |
|---------|----------|
| 컨테이너 상태/Ref 확인만 필요 | `/off-hire-ref-check` (단건, 안전) |
| 발급 이력 일괄 조회 | `/off-hire/history` (안전) |
| 신규 발급 필요 | `/off-hire` (안전성 검증 후) |

> 본 분석 기반 구현 계획은 별도 문서(`IMPLEMENTATION_PLAN.md`)에 정리 예정.
