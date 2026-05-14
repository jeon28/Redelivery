# FLOR (Florens) 사이트 분석

> 분석일: 2026-05-14
> 분석 방식: Playwright 직접 조사
> 상태: 1차 분석 — 신규 신청 폼 세부와 발급 흐름은 추가 검증 필요

---

## 1. 로그인

| 항목 | 값 |
|------|-----|
| 로그인 URL | `https://www.florens.com/official-pc/login#/` |
| 로그인 폼 | Florens ID + Password (2 필드) |
| 추가 보안 | **슬라이드 캡차 (단순 좌→우 드래그)** |
| 로그인 후 이동 | `https://www.florens.com/user/home#/` |
| 도메인 베이스 | `https://www.florens.com/` |

### 자격증명 환경변수 키

| 선사 | ID 키 | PW 키 |
|------|-------|-------|
| 장금상선 (SK) | `SK_FLOR_ID` | `SK_FLOR_PW` |
| 흥아라인 (HA) | `HA_FLOR_ID` | `HA_FLOR_PW` |

### 슬라이더 처리

- 단순한 좌→우 드래그 슬라이드 (퍼즐/이미지 매칭 없음)
- DOM 구조:
  - `.slider-captcha` / `.slider-container` (외곽, 312×24)
  - `.slider-track` (레일, 312×2)
  - `.slider-bar` (채워지는 fill, 0 → 288px)
  - `.slider-button-wrapper` / `.slider-button` (드래그 핸들, 24×24)
- Playwright 자동화:
  - 핸들 중심에서 시작 → 트랙 끝까지 약 288px 드래그
  - 30 step ease-out + 약간의 Y noise → 인간형 곡선
  - 검증된 동작 (실측 2026-05-14)
- 슬라이드 만으로는 로그인 안 됨 → **Sign-in 버튼 추가 클릭** 필요

### 로그인 후 사용자 표시

상단 우측에 사용자 코드 표시:
- SK: `SKRCMT`
- HA: `YEONG`

---

## 2. 주요 메뉴 / 진입 경로

로그인 후 `/user/home#/` 대시보드에 "Web Functions" 6개 그리드:
- Booking / **Redelivery** / Replacement Value / Maintenance & Repair / Management Report

| 페이지 | URL | 용도 |
|--------|-----|------|
| 사용자 홈 | `/user/home#/` | 대시보드 |
| Redelivery (Apply/Status 탭) | `/func/redelivery#/` | **반납 신청 + 이력 조회** |

> 상단 메뉴는 hover 드롭다운이므로 직접 URL 진입이 가장 확실.

### 백엔드 단서

페이지 HTML에 다음 hidden form 발견:
- `action=https://florensfm.florens.com:10043/psp/fmp8/?cmd=login&languageCd=ENG`
- `name=userid` / `name=pwd` (PeopleSoft 스타일)

→ 프론트는 Vue SPA, 백엔드는 PeopleSoft 기반 추정. 자동화에는 SPA 화면 조작으로 충분.

---

## 3. Redelivery 페이지 구조

### 탭 (2개)

| 탭 | 용도 |
|----|------|
| **Apply Redelivery** | 신규 반납 신청 (3단계 위저드) |
| **Redelivery Status** | 발급 이력/현황 조회 |

### Apply Redelivery — 3단계 위저드

```
[1] Select Depot          [2] Enter Unit Numbers          [3] Completed
 (Customer/Port/Depot)     (컨테이너 번호 입력)              (5분 내 제출)
       Next →                     Next →                Confirm Redelivery Order
```

#### Step 1 필드 (확인됨)

| 라벨 | 위젯 | 비고 |
|------|------|------|
| Customer ID | 라디오 (`SINOKOR` 등) | 계약 고객. 단일 선택 |
| Port | Element UI 드롭다운 (`el-select`) | "Please select the port according to the terms of contract" |
| Depot | Element UI 드롭다운 | "Please select" — Port 종속 추정 |

→ Vue.js + Element UI. 네이티브 `<select>` 없음. `el-input__inner` 텍스트 인풋 클릭 시 옵션 패널 열림.

#### Step 2/3

- Step 2: 컨테이너 번호 입력 (UI 미확인 — Next 클릭 필요)
- Step 3: **Confirm Redelivery Order** 버튼 (실 발급 추정) + "Submit within 5 minutes" 시간 제약 안내
- Back / Next 버튼으로 단계 이동

---

## 4. Redelivery Status — 이력 조회

### 검색 옵션 (라디오)

- **Redelivery No.** (기본 선택, 단일 Ref 입력)
- **Unit No.** (컨테이너 번호 입력)
- **Advanced Options** (다중 필터: Status, Depot 등)

빈 검색 시 토스트: `Please specify Redelivery Number`.

### 결과 테이블 헤더

```
Port: | Depot: | Redelivery No. | Status | Contract | Order Date | Equip Type | Order Qty | MOV Qty | BAL Qty | More
```

> `Port:` / `Depot:` 의 콜론은 필터 라벨일 수 있음 (테이블 헤더가 아닌 상단 위젯). 행 데이터 매핑은 9개 컬럼이 명확.

### 실측 예 (HA / DFSU7591613, 2026-05-14)

| 컬럼 | 값 |
|------|-----|
| Redelivery No. | **`PPR70283`** (PPR + 5자리) |
| Status | `Closed` |
| Contract | `DF-HNGA20008` |
| Order Date | `2026-04-01` |
| Equip Type | `40' Dry High Cube` |
| Order Qty | 1 |
| MOV Qty | 1 |
| BAL Qty | 0 |
| More | `+` 버튼 (상세 펼침) |

### 의미

- **반납번호 형식**: `PPR<5자리숫자>` (예: `PPR70283`). TRIT의 ABUSG/RA / GOLD의 RA와 다름.
- **Status 값**: `Closed` 확인됨. 다른 상태(Active/Pending/Cancelled 등) 추가 수집 필요.
- **Contract prefix**: `DF-HNGA<###>` (HA), `DF-SINK<###>` 예상 (SK)
- **Equip Type**: 영문 텍스트 (`40' Dry High Cube`, `20' Dry Standard`, ...)
- **Qty 흐름**: Order Qty → MOV (movement, 실 이동 수량) → BAL (잔여 수량 = Order − MOV)

---

## 5. 반납번호 / 데이터 형식 정리

| 항목 | 형식 | 예 |
|------|------|-----|
| 컨테이너 prefix (Florens owned) | `DFSU`, `FSCU` | `DFSU7591613`, `FSCU5896157` |
| 반납번호 (현재 활성) | `PPR<5자리>` | `PPR70283` |
| 반납번호 (과거 closed) | `PPF<5자리>` | `PPF50839` (2020년 발급) — 시리즈가 시기별로 다를 가능성 |
| Contract (HA, 신규) | `LT-HALINE-<번호>` | `LT-HALINE-02` |
| Contract (HA, 과거 형식) | `DF-HNGA<5자리>` | `DF-HNGA20008` (2026 시점에도 잔재) |
| Contract (SK, 추정) | `LT-SINKO-<번호>` 또는 `DF-SINK<5자리>` | _(미확인)_ |
| Port 코드 | UN/LOCODE 5자리 | `KRPUS`(부산), `KRINC`(인천), `KRSEL`(서울) |
| Depot 코드 | Port코드 + 2자리 | `KRPUS07` (YoungJin CY) |
| Equip Type 코드 | 3자리 | `R4H` (40' Reefer High-Cube) |
| Equip Type 풀네임 | 자유 문자열 | `40' Dry High Cube`, `40' Reefer High-Cube` |
| Order Date | `YYYY-MM-DD` | `2026-04-01` |

---

## 6. 신규 발급 흐름 — 실 발급 검증 완료 (2026-05-14)

### 실 발급 E2E 결과

| 단계 | 입력/동작 | 결과 |
|------|----------|------|
| 입력 | HA / `DFSU7526412` / Port=INCHON / Depot=(KRINC08) The Logis New Port CY | — |
| Step 1~3 자동화 | 폼 입력 → Next → Next → Confirm Redelivery Order | 성공 |
| 발급된 반납번호 | **`PPR77147`** | — |
| Status | `Open` (즉시 활성, Pending 단계 없음) | — |
| Contract | `DF-HNGA20008A` | — |
| Order Date | `2026-05-14` | 발급 당일 |
| Equip Type | `40' Dry High Cube` | — |
| Qty | Order=1, MOV=0, BAL=1 | 이동 전 |

→ **Florens는 Confirm 클릭 시 즉시 발급 + `Open` 상태로 활성**. TRIT의 Pending Create 단계 없음.

---

## 7. 신규 발급 흐름 — 거부 케이스 실측 (2026-05-14)

### 확인된 흐름

1. `/func/redelivery#/` 진입 (Apply Redelivery 탭 기본 활성)
2. **Step 1** — Customer ID 라디오 선택 + Port + Depot
3. **Next** → **Step 2**
4. **Step 2** — Unit Numbers textarea 입력 (줄바꿈 구분, 최대 100개)
5. **Next** → **Step 3**
6. Step 3 — Florens 자체 사전 검증으로 거부 가능 행 표시
   - 모두 무효 시 **`Confirm Redelivery Order` 버튼이 disabled** (안전)
   - 유효 행 있을 시 버튼 활성 → 클릭 시 실 발급

### Step 1 — Customer ID 라디오

| 선사 | Customer ID 값 |
|------|---------------|
| 장금상선 (SK) | `SINOKOR` |
| 흥아라인 (HA) | `HALINE` |

### Step 1 — Port 드롭다운 (HA 계약 기준, 총 168개)

한국 항구 3개 가용:
- `INCHON (KRINC)`
- **`PUSAN (KRPUS)`** ← 부산은 "PUSAN" 표기 (BUSAN 아님)
- `SEOUL (KRSEL)`

옵션 텍스트 포맷: `<도시명> (<5자리코드>)`. 코드는 5글자 (국가2 + 도시3).

### Step 1 — Depot 드롭다운

Port 선택 후 동적 활성. 옵션 텍스트 포맷: `(<DEPOT_CODE>) <Depot 풀네임>` (예: `(KRPUS07) YoungJin CY`).
**Depot마다 반납 가능 컨테이너 타입 제한**:
- Reefer 미수용 depot 존재 (예: YoungJin CY)
- Dry 전용 depot, 양쪽 모두 수용 depot 등 다양

### Step 2 — Unit Numbers textarea

```html
<textarea placeholder="A maximum of 100 redelivery can be applied at a time, please use separate by the specified symbol (only support enter)." class="el-textarea__inner">
```

- 다중 입력 가능 (줄바꿈 구분, 최대 100개)
- TRIT/GOLD와 달리 single text input이 아니어서 일괄 처리 가능

### Step 3 — 사전 검증 결과 화면

**거부 행 컬럼** (관찰):
| # | 컬럼 (추정) | 예 |
|---|------------|-----|
| 1 | Unit Number | `FSCU5896157` |
| 2 | Contract | `LT-HALINE-02` |
| 3 | Equip Type 코드 | `R4H` (= 40' Reefer High-Cube) |
| 4 | 거부 사유 | `This Depot ((KRPUS07) YoungJin CY), is incapable of accepting reefer turn-in, please enter another location or unit number.` |

**유효 행** (미캡처): 추정 컬럼은 Status 탭과 유사 — Unit / Contract / Equip Type / Order Qty 등.

### Step 3 — Confirm Redelivery Order 버튼 (실 발급)

- 클래스: `el-button el-button--primary` (활성) / `... is-disabled` (비활성)
- **모든 단위가 invalid이면 disabled 상태로 노출** → 클릭 무의미, 안전 가드
- 유효 단위 있을 시 활성. 클릭 = `PPR<5자리>` 즉시 발급 추정 (TRIT의 Pending 단계 없음)

### 확인된 거부 사유 예시

| 거부 사유 | 의미 |
|----------|------|
| `This Depot ((<DEPOT_CODE>) <NAME>), is incapable of accepting reefer turn-in, please enter another location or unit number.` | Depot이 reefer 미수용 — 다른 depot/unit 입력 필요 |

> 추가 사유는 실 운영 중 수집.

### 자동화 시 주의사항

- **Element UI 드롭다운**: Playwright의 `click()` / `scroll_into_view_if_needed()` 가 가시성 판정으로 실패할 수 있음. **JS `evaluate`로 `target.scrollIntoView() + target.click()` 직접 호출**이 안정적.
- **드롭다운 옵션 다수**: 168개 → 스크롤 가능 영역. 화면 보이는 li만 매칭하려면 `offsetParent !== null` 필터.
- **다중 컨테이너 입력**: textarea에 `\n` 구분으로 일괄 입력. TRIT/GOLD보다 효율적.
- **Confirm disabled 체크**: 클릭 전에 `classList.contains('is-disabled')` 확인 → false-positive 방지.
- **5분 시간 제약**: Step 3 도달 후 빠르게 처리 (자동화에서는 사실상 즉시 처리이므로 문제 없음).

---

## 7. 주의사항

- **슬라이더 캡차**: 단순형이지만 향후 Florens가 강화할 가능성 — 변경 시 즉시 분석 갱신.
- **Sign-in 버튼**: 슬라이더 통과만으로는 로그인 진행 안 됨. 별도 클릭 필수.
- **PeopleSoft 백엔드**: Florens Fleet Manager 본체는 별도 시스템(`florensfm.florens.com:10043`). 일부 기능이 그쪽으로 리다이렉트될 가능성.
- **시간 제약**: Step 3 5분 룰 — 자동화에서 단계 사이 sleep 과도하게 두지 말 것.
- **계정 보호**: 본 문서 및 ANALYSIS.md에 실 ID/PW 기재 금지.

---

## 8. 선사 차이점 (SK / HA)

| 항목 | SK (장금상선) | HA (흥아라인) |
|------|--------------|--------------|
| 환경변수 키 | `SK_FLOR_ID`, `SK_FLOR_PW` | `HA_FLOR_ID`, `HA_FLOR_PW` |
| 로그인 후 사용자 표시 | `SKRCMT` | `YEONG` |
| Customer ID (Step 1) | `SINOKOR` | _(미확인 — 추정 `HEUNGA` 또는 유사)_ |
| Contract prefix | `DF-SINK<###>` (추정) | `DF-HNGA<###>` (확인됨) |

> 화면 구조는 동일. 차이는 자격증명과 데이터 prefix뿐.

---

## 9. 자동화 활용 전략 (확정)

> **중요**: 본 시스템의 "조회" 의도는 **"오늘 이 컨테이너를 반납할 수 있는가?"** 이다. 따라서 **Apply Redelivery가 1차 경로**이고, Status 탭은 **신규 발급된 PPR의 상세 보강용**(또는 거부 케이스의 과거 이력 확인용)으로만 사용한다.

| 시나리오 | 권장 경로 | 1차/보조 |
|---------|----------|---------|
| **반납 가능 여부 / 가용 캡 / 거부 사유 확인 (메인 조회)** | **Apply Redelivery 3단계** | **1차** |
| 신규 발급 후 PPR 상세(Depot, Expiry 등) 보강 | Redelivery Status 탭 → Unit/Ref 검색 | 보조 (Apply 완료 후) |
| 거부된 컨테이너의 과거 이력(이전 PPR/완료 등) 확인 | Redelivery Status 탭 → Unit No. 검색 | 보조 (필요 시) |

### ⚠️ 1차 구현(2026-05-14)의 설계 오류

초기 구현(`scraper/scrapers/flor.py`)은 **Status 탭을 1차 조회 경로**로 사용했음. 이는 잘못된 설계이며 다음 증상을 유발:

- 수 년 전 closed PPR(예: `PPF50838` 2020-11-10) 을 현재 가용 정보처럼 반환
- Apply Redelivery 단계에서만 노출되는 거부 사유(over caps, depot 불수용 등) 미캡처
- 사용자가 "지금 이 컨테이너 반납 가능?"이라고 묻는데 시스템은 "예전에 반납된 적 있음"으로 답하는 의미 차이 발생

→ 재설계 진행: `IMPLEMENTATION_PLAN.md` 참조.

---

## 10. 후속 작업

- `IMPLEMENTATION_PLAN.md` (Apply Redelivery 1차 재설계) — 작성 중
- 거부 사유 카탈로그 (over caps, depot 불수용, 이미 활성 PPR, 이전 반납 완료 등) — 실 데이터 수집 후 보강
