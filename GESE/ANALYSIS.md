# GESE (SeaCo) 사이트 분석

> 분석일: 2026-05-14
> 분석 방식: Playwright 직접 조사
> 상태: 1차 분석 — Add to Returns 후 흐름 및 City 옵션은 추가 검증 필요

---

## 1. 로그인

| 항목 | 값 |
|------|-----|
| 진입 URL | `https://seaweb.seacoglobal.com/sap/bc/ui5_ui5/sap/zseaweb/index.html?saml2=disabled&handleX509=false&_sap-hash=...#/navCus_Dashboard` |
| 로그인 폼 | User + Password (SAP 폼 기반, 캡차/슬라이더 없음) |
| 폼 액션 | `POST {entry_url}` (form name=`loginForm`, id=`LOGIN_FORM`) |
| User 필드 | `input#USERNAME_FIELD-inner` (name=`sap-user`) |
| Password 필드 | `input#PASSWORD_FIELD-inner` (name=`sap-password`) |
| Submit | `button#LOGIN_LINK` (text=`Log On`) |
| 추가 인증 | 없음 (SAML/X509 모두 비활성 — URL 파라미터 `saml2=disabled&handleX509=false`) |
| 로그인 후 URL | `...index.html?...&sap-client=100&sap-language=EN#/navCus_Dashboard` |

### 자격증명 환경변수 키

| 선사 | ID 키 | PW 키 |
|------|-------|-------|
| 장금상선 (SK) | `SK_GESE_ID` | `SK_GESE_PW` |
| 흥아라인 (HA) | `HA_GESE_ID` | `HA_GESE_PW` |

### 로그인 사용자 표시

상단 우측 표시 (예: `O.H Kwon`).

---

## 2. 기술 스택

- 프레임워크: **SAP UI5 (Fiori) v1.120.15**
- 화면 라우팅: 해시 기반 (`#/navCus_XXX`)
- 백엔드: SAP NetWeaver (`/sap/bc/ui5_ui5/sap/zseaweb/`)
- 클라이언트: `sap-client=100`, 언어: EN

### 자동화 시 주의사항

- SAP UI5 컨트롤은 일반 HTML과 달리 wrapping 구조 (예: `sap.m.Input` → 내부 `input#XXX-inner`).
- **레이블 텍스트로 클릭** (Playwright `locator("text=...")`) 가 안정적.
- 페이지 전환 후 SAP UI5 부팅에 **3~5초 소요** — 명시적 wait 필요.
- 메뉴 펼침은 SAP TreeNode 구조 (role=treeitem).

---

## 3. 주요 화면 / URL 매핑

| 화면 | 해시 경로 |
|------|----------|
| 대시보드 | `#/navCus_Dashboard` |
| Redelivery Request (신규) | `#/navCus_RedeliveryRequest` |
| Redelivery View/Cancel (조회/취소) | `#/navCus_RedeliveryRequestViewCancel` |
| Depreciated Residual Value (DRV) | _(미캡처)_ |
| Customer Activity Reports | _(미캡처)_ |
| Depot Inventory | _(미캡처)_ |
| Outstanding Redelivery | _(대시보드 타일에서 진입)_ |
| Return Schedule | _(Online Returns 하위 메뉴)_ |

### 대시보드 구성

- 좌측 메뉴 (트리): DRV / Customer Activity Reports / **Online Returns** ▶ / Depot Inventory
  - Online Returns 하위: `Redelivery Request`, `Redelivery View/Cancel`
- 중앙 타일: **Outstanding Redelivery: 21** (대기 중 단위 수)
- 하단 Unit Enquiry 카드: 컨테이너 번호 textarea (max 100, line-sep) + Search / Reset
- Quick Links: Publications

---

## 4. Redelivery Request — 신규 신청 폼

URL: `#/navCus_RedeliveryRequest`

### 폼 필드

| 라벨 | 위젯 | 필수 | 비고 |
|------|------|------|------|
| Customer Name | 드롭다운 | ✅ | SK는 `Sinokor Merchant Marine Co. Ltd. (100898)` 자동 선택. 회사 코드 100898 |
| Start Date | 텍스트 (DD/MM/YYYY) |  | 기본 = 오늘 |
| Expiry Date Date | 텍스트 (DD/MM/YYYY) |  | 기본 = 월말 |
| (Switch to Next month) | 버튼 |  | Expiry +1개월 |
| City | 드롭다운 | ✅ | 옵션 미캡처 |
| Serial No. | textarea | ✅ | **최대 25개**, 줄바꿈 구분, 형식 `XXXX#######` (4letter + 7digit) |

### 제출 버튼

- **`Add to Returns`** (녹색) — 단순 "추가" 표현 → **다음 확인/제출 단계 존재 가능성** (TRIT 패턴 유사)
- `Reset` (분홍)

### 입력 양식 안내 문구

> "For **individual** containers, please enter the 4 letter prefix and 7 digit number for each container (Eg. `SEGU3000511`).
> For **multiple** containers (Max. 25), press the Enter key after each one or copy-paste the list in the entry field"

### 미확인 항목

- City 드롭다운 옵션 (한국 항구 코드 형식, 가용 도시)
- "Add to Returns" 클릭 후 다음 화면 (확인/Submit 단계 추정)
- 발급 후 RA(Return Authorization No.) 형식
- 거부 케이스 메시지

---

## 5. Redelivery View/Cancel — 조회/취소

URL: `#/navCus_RedeliveryRequestViewCancel`

### 폼 필드

| 라벨 | 위젯 | 필수 | 비고 |
|------|------|------|------|
| Return Authorization No. | 텍스트 | ✅ | 발급된 RA 번호 입력 |

### 버튼

- `Submit` (녹색) — 조회 실행
- `Reset` (분홍)

### 의미 — 다른 임대사와의 차별점

- **취소 메뉴가 임대사 측 UI에 직접 노출** (TRIT/GOLD/FLOR엔 없던 기능)
- "View/Cancel" 명시 → 조회 결과 화면에서 취소 액션 노출 추정
- 자동화에서 발급분 원상복귀가 가능할 가능성 — 다른 임대사와 달리 잠재적 cleanup 자동화 가능

### 미확인 항목

- Submit 후 결과 화면 구조
- 취소 버튼의 정확한 위치 / 동작
- 취소 가능 조건 (시간 제약, 상태별 등)

---

## 6. 데이터 형식 정리

| 항목 | 형식 | 예 |
|------|------|-----|
| 컨테이너 prefix (Seaco owned) | `SEGU`, `XXXX` (4 letters) | `SEGU3000511` |
| 컨테이너 번호 | 4 letters + 7 digits | `SEGU3000511` |
| RA (Return Authorization No.) | 미확인 | _(발급 검증 필요)_ |
| Customer ID (SK) | 6자리 숫자 | `100898` (Sinokor Merchant Marine) |
| 날짜 표기 | `DD/MM/YYYY` | `14/05/2026` (유럽 표기) |

---

## 7. 신규 발급 흐름 — 4단계 구조 (2026-05-14 실측)

```
[Step 1] Fill Form (Customer 자동 / Start/Expiry 기본값 / City 선택 / Serial No. textarea)
       ↓
[Step 2] Add to Returns 클릭
       ↓ (페이지 이동 없음, 동일 URL 유지)
[Staging List 표시] — "RedeliveryRequest - Select Units" 섹션
       ↓
[Step 3] Validate 클릭 (선택 사항)
       ↓ (서버 검증 → 빈 필드 채워짐 + Messages 컬럼에 에러 표시)
[Step 4] 행 선택 + Submit 클릭 → 실 발급 (RA 발급)
```

### Staging List 화면 (Add to Returns 직후)

**섹션 제목**: `RedeliveryRequest - Select Units`

**상단**: `Number of Rows: N` + `View Messages` 버튼

**테이블 컬럼**:
| 컬럼 | 초기값 (Add 직후) | Validate 후 |
|------|------------------|-------------|
| ✓ (checkbox) | 미선택 | 사용자가 선택 |
| Lease Type | 비어있음 | 서버 채움 |
| Lease No. | 비어있음 | 서버 채움 |
| Unit Type Description | 비어있음 | 서버 채움 (예: `40' Reefer High-Cube`) |
| City | 입력값 (예: `Busan`) | 동일 |
| Depot Name | 비어있음 | 서버 채움 |
| Serial No. | 입력 컨번호 | 동일 |
| Status | 비어있음 | 검증 결과 (행 단위) |

**하단**:
- `Validate` (파란 primary) — 서버 검증 트리거
- `Delete` (분홍, 행 선택 시 활성)
- `Email Addresses` — 자동 입력 (예: `container@sinokor.co.kr`) — 발급 후 이메일 알림 수신처
- `Submit` (녹색, 행 선택 + 검증 후 활성) — **실 발급 트리거**
- `Reset` (분홍)

### Add to Returns의 안전성

- **Add to Returns 클릭 자체는 발급 안 됨** (Staging List 추가만)
- **Submit 클릭이 실 발급** — 자동화에서 명시적 플래그 분리 필수
- Reset 또는 페이지 이탈 시 Staging List 클리어 (SPA 상태)
- "Add to Returns" 후 페이지 떠나거나 Reset 누르면 안전한 cleanup

### 검증된 동작 (2026-05-14)

- 입력: SK / Busan / `SEGU9586313` + `CRXU9980434` (사용자 제공)
- Add to Returns → 2개 행 Staging List에 추가, City=Busan, Serial No. 정상 표시
- SelectAll 체크박스 클릭 → 행 선택 → Validate 버튼 활성화
- Validate 클릭 → 서버 검증 → 모든 필드 채워짐:

| 컬럼 | SEGU9586313 (예) | CRXU9980434 (예) |
|------|-------------------|-------------------|
| Lease Type | `Fixed` | `Variable` |
| Lease No. | `1002305` | `140638` |
| Unit Type Description | `40'HCRF Carr 69NT40-561 Primeline (MGSS)` | `40' High Cube Standard` |
| City | `Busan` | `Busan` |
| Depot Name | `2724 - Seyang Logistics, CO,. LTD` | `1973 - New Continental Logistics Co Ltd` |
| Serial No. | `SEGU9586313` | `CRXU9980434` |
| **Status** | **`ERROR`** (Reefer 처리 거부) | **`OK`** (Dry, 발급 가능) |
| Messages | (View Messages 링크) | — |

- Submit 안 눌렀으므로 발급 안 됨 (안전)

### Validate 후 Status 값 (확인된 것)

| Status | 의미 |
|--------|------|
| `OK` | 발급 가능 — Submit 시 RA 발급됨 |
| `ERROR` | 발급 불가 — Messages 링크에서 상세 사유 확인 |

### Depot Name 형식

`<코드> - <Depot 풀네임>` (예: `2724 - Seyang Logistics, CO,. LTD`)

### Lease Type 값

| 값 | 의미 |
|----|------|
| `Fixed` | 고정 계약 (반납 기간 고정) |
| `Variable` | 변동 계약 |

### 행 선택 (자동화 핵심 주의사항)

**Validate / Delete / Submit 버튼은 행이 선택된 상태에서만 활성화됨.**
- sap.ui.table 구조이므로 `.sapUiTableSelectAllCheckBox` 클릭으로 전체 선택
- Playwright `force=True` 클릭이 SAP UI5 이벤트를 더 안정적으로 트리거 (`page.evaluate` JS click은 SAP 이벤트 미발화 케이스 있음)

---

## 8. 주의사항

- **사이트 동작 정상** — PLAN.md의 "웹 미작동" 메모는 과거 시점 기준이며 현재는 정상 동작 확인 (2026-05-14).
- **SAP UI5 부팅 시간**: 페이지 전환 후 약 3~5초 대기 필요.
- **세션 만료**: 장시간 비활성 시 자동 로그아웃 가능 (SAP 일반 동작).
- **취소 메뉴 존재**: View/Cancel 기능을 활용해 자동 cleanup 자동화 검토 가능 — 다른 임대사보다 안전성 높음.
- **계정 보호**: 본 문서나 ANALYSIS.md에 실제 ID/PW 기재 금지.

---

## 9. 선사 차이점 (SK / HA)

| 항목 | SK (장금상선) | HA (흥아라인) |
|------|--------------|--------------|
| 환경변수 키 | `SK_GESE_ID`, `SK_GESE_PW` | `HA_GESE_ID`, `HA_GESE_PW` |
| 로그인 사용자명 (우상단) | `O.H Kwon` (확인) | _(미확인)_ |
| Customer Name | `Sinokor Merchant Marine Co. Ltd. (100898)` (확인) | _(추정: Heung-A Line Co. Ltd. 또는 유사)_ |
| 사용 변형 코드 | `GESE+CROS` | `GESE+SGCN` |

> 화면 구조는 동일 추정. `+CROS`/`+SGCN` 접미사는 base.py `_normalize_lessor`로 GESE로 통합 처리.

---

## 10. 자동화 활용 전략 (제안)

| 시나리오 | 권장 경로 |
|---------|----------|
| 컨테이너 상태 조회 | 대시보드의 Unit Enquiry 또는 Outstanding Redelivery 타일 |
| 발급 이력 조회 | Customer Activity Reports (추가 분석 필요) |
| 신규 발급 | Redelivery Request → Add to Returns → (Submit/Confirm) |
| 발급 취소 | Redelivery View/Cancel — **자동화 가능성 있음** (검증 필요) |

> 본 분석 기반 구현 계획은 `IMPLEMENTATION_PLAN.md`에 별도 정리 예정.
