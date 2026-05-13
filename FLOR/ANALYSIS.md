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
| 컨테이너 prefix (Florens owned) | `DFSU` | `DFSU7591613` |
| 반납번호 | `PPR<5자리>` | `PPR70283` |
| Contract (HA) | `DF-HNGA<5자리>` | `DF-HNGA20008` |
| Contract (SK, 추정) | `DF-SINK<5자리>` | _(미확인, SK 측에서 확인 필요)_ |
| Order Date | `YYYY-MM-DD` | `2026-04-01` |
| Equip Type | 자유 문자열 | `40' Dry High Cube` |

---

## 6. 신규 발급 흐름 (미완료 — 추가 검증 필요)

### 확인된 부분

- 3단계 위저드 페이지 구조
- Step 1 필드 라벨/위젯
- Step 3에 `Confirm Redelivery Order` 버튼 존재 (현재 disabled 상태로 캡처됨)
- "Submit within 5 minutes" 시간 제약

### 미확인 부분

- Port/Depot 드롭다운 옵션 (Element UI 클릭 후 패널 열어야 노출됨)
- Step 2 입력 UI (단일/다중 컨테이너 방식)
- Step 3 화면 (가능/불가 표시 방식, 발급 확정 트리거)
- Confirm 후 실제 반납번호 발급 응답
- 거부 케이스 메시지 형식

### 자동화 시 주의사항

- Element UI 드롭다운: 텍스트 인풋 클릭 → `.el-select-dropdown` 패널 → `li.el-select-dropdown__item` 클릭으로 선택
- SPA 라우팅: URL 변화 없이 콘텐츠 전환되는 케이스 많음. 명시적 wait 필요.
- 5분 시간 제약: Step 3 도달 후 빠르게 처리해야 함

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

## 9. 자동화 활용 전략 (제안)

| 시나리오 | 권장 경로 |
|---------|----------|
| 컨테이너 상태/Ref 확인 | Redelivery Status 탭 → Unit No. 검색 (안전, read-only) |
| Ref로 상태 확인 | Redelivery Status 탭 → Redelivery No. 검색 |
| 발급 이력 일괄 조회 | Redelivery Status 탭 → Advanced Options (안전) |
| 신규 발급 | Apply Redelivery 3단계 (Step 3 위험성 사전 검증 후) |

> 본 분석 기반 구현 계획은 `IMPLEMENTATION_PLAN.md`에 별도 정리 예정.
