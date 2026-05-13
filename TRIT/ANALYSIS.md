# TRIT (Triton) 사이트 분석

> 분석일: 2026-05-13
> 분석 방식: 사용자 라이브 시연 기반
> 상태: 진행 중

---

## 1. 로그인

| 항목 | 값 |
|------|-----|
| 로그인 URL | `https://tools.tritoncontainer.com/tritoncontainer/login/auth` |
| 로그인 폼 | 2개 필드 (Username, Password) |
| 추가 인증 | 없음 (캡차/2FA 등 없음) |
| 도메인 베이스 | `https://tools.tritoncontainer.com/tritoncontainer/` |

### 자격증명 환경변수 키

| 선사 | ID 키 | PW 키 |
|------|-------|-------|
| 장금상선 (SK) | `SK_TRIT_ID` | `SK_TRIT_PW` |
| 흥아라인 (HA) | `HA_TRIT_ID` | `HA_TRIT_PW` |

---

## 2. 반납 조회 메뉴 진입 경로

- **메뉴 클릭 불필요 — URL 직접 진입 가능**
- 진입 URL: `https://tools.tritoncontainer.com/tritoncontainer/redeliverySession/create`
- 로그인 후 위 URL로 바로 이동하면 **반납번호 생성 화면**이 표시됨
- 자동화 흐름: 로그인 성공 → `redeliverySession/create` URL 이동 → 입력 폼 표시

---

## 3. 반납 조회 입력 폼

> Playwright 인스펙션 결과 (`TRIT/_inspect/03_create_form.json`).

### 페이지 정보

| 항목 | 값 |
|------|-----|
| 페이지 타이틀 | `Triton International - Request Redelivery` |
| 상단 메뉴 경로 | `Unit Activity → Request Redelivery` |
| 폼 ID | `validateForm` |
| 폼 action | `POST /tritoncontainer/redeliverySession/validate` |

### 폼 필드 (validateForm)

화면 기본 표시: **Location (Country, Port)** + **Unit Numbers** + 제출 버튼.
Depot / DepotType은 DOM에 존재하나 기본은 미표시 — 국가/포트 선택 후 동적으로 활성화될 가능성 (구현 시 확인 필요).

| 필드 라벨 | DOM `name` | DOM `id` | 위젯 | 옵션 수(초기) | 비고 |
|----------|-----------|----------|------|--------------|------|
| Country | `location.country` | `location_country` | Select2 단일선택 | 135 | 첫 옵션 `-Country-` |
| Port | `location.port` | `location_port` | Select2 단일선택 | 300 | 첫 옵션 `-Port-` |
| Depot | `location.depot` | `location_depot` | Select2 다중선택 + autocomplete | 0 | 국가/포트에 따라 동적 |
| Depot Type | `location.depotType` | `location_depotType` | Select2 다중선택 | 4 | `DEPO`, `WHSL`, `CONS`, `CUCY` |
| Unit Numbers | `unitNumbers` | `unitNumbers` | Select2 다중선택 + autocomplete + text-uppercase | 0 | **컨테이너 번호를 태그로 추가** |

### 제출 버튼

- 화면 라벨: **`Request Redelivery`**
- DOM: `<input type="submit" id="Request Redelivery" name="Request Redelivery" class="btn btn-submit">`
- 액션 URL: `POST /redeliverySession/validate` (validate 단계 = TEXA의 Preview에 해당, 사용자 확인)

### 자동화 시 주의사항

- **모든 드롭다운이 Select2**: 네이티브 `<select>`는 숨김 처리 (`select2-hidden-accessible`). Playwright에서 자동화 시 옵션:
  1. 네이티브 select에 값 설정 후 `change` 이벤트 dispatch
  2. Select2 UI(`.select2-selection`)를 직접 클릭하여 드롭다운 열고 옵션 선택
- **Unit Numbers는 textarea 아님**: Select2 multi-select tag input. 자동완성으로 값을 추가해야 함.
  - 추정 방식: Select2 input에 컨번호 입력 → Enter 또는 자동완성 클릭 → 태그로 추가
  - 또는 네이티브 select에 `<option>`을 동적으로 주입 후 selected 처리
- **Cookie 배너**: 진입 시 Cookiebot 배너가 나타남 — 화면 일부 가림. 필요 시 `Accept` 버튼 자동 클릭.
- **사용자 표시**: 우상단에 로그인 사용자 이름 표시 (예: `EUNMI KO`).

---

## 4. 결과 화면 (Stage 1 / Validate)

> URL: `https://tools.tritoncontainer.com/tritoncontainer/redeliverySession/validate`
> 페이지 타이틀: `Triton International - New Redeliveries`
> 화면 헤더: `TRITON / New Redeliveries`
> 인스펙션 산출물: `TRIT/_inspect/07_validate_result.{png,json,html}`

### 화면 구조

- **상단 알림 배너**: 노란 배경, 상황별 메시지
  | 상황 | 메시지 |
  |------|--------|
  | 전체 실패 | `All units failed Redelivery validation; no redeliveries will be created. Please see below for reasons.` |
  | 일부 성공 | `N Redelivery will be created. Please review below.` + `Some of the requested unit numbers have validation errors. Redeliveries for them will not be created. Please review the errors below.` |
  | 전체 성공 | (추정) 무효 배너 없이 성공 배너만 |
- **탭 구조** (Bootstrap nav-tabs)
  | 탭 | 셀렉터 | 컨텐츠 패널 |
  |-----|--------|------------|
  | 무효 단위 | `#invalidsTab` (추정) | `#invalidsTabContent` (추정) |
  | 유효 단위 | `#redeliveriesTab` | `#redeliveriesTabContent` |
- **무효 단위 테이블** (class=`table-all`)
  | 컬럼 | 설명 |
  |------|------|
  | `Requested Unit Number` | 입력한 컨테이너 번호 |
  | `Reason` | 거부 사유 |
- **유효 단위 테이블** (id=`redeliveryTable`, DataTables 기반)
  | # | 컬럼 헤더 | data-id (DB 필드) | 예시값 |
  |---|----------|------------------|--------|
  | 0 | `Redelivery Number` | `redeliveryNumber` | `Redelivery #1` (Stage 2 전 placeholder, 실제 번호 미발급) |
  | 1 | `Depot` | `redelivery.storageLocation.id` | `BUSG` (Busan 코드 예) — `/depot/list?locationDepot=BUSG` 링크 |
  | 2 | `Customer` | `contract.customer.id` | `HNGX` (Heung-A 코드 예) |
  | 3 | `Contract` | `contract.contractCode` | `HNGX17-200000` |
  | 4 | `Equipment Type` | `equipmentType.id` | `D5` 등 컨테이너 타입 코드 |
  | 5 | `Unit Count` | `unitCount` | `1` |
- **Stage 2 form** (유효 탭 내부)
  - 셀렉터: `form#requestForm` (`name="requestForm"`)
  - 액션: `POST /tritoncontainer/redeliverySession/save/<sessionId>`
  - 숨김 필드: `SYNCHRONIZER_TOKEN` (CSRF), `SYNCHRONIZER_URI`
  - Stage 2 버튼: `<input type="submit" name="Continue Redelivery Request" id="Continue Redelivery Request" value="Continue Redelivery Request">`

### 확인된 거부 사유 예시

| Reason 문구 | 분류 | 의미 |
|------------|------|------|
| `This unit was already turned in.` | 컨테이너 상태 | 이미 반납 완료된 컨테이너 |
| `This unit may not be returned as it is currently on lease to [<Customer>].` | 리스 상태 | 다른 고객사에 리스 중 — 본 계정으로 반납 불가 (예: `[SNKX]`) |
| `There are no Triton depots active for [<Port>] at this time. Please contact your local Triton subsidiary for assistance.` | 포트(Depot 가용성) | 해당 포트에 활성 Depot 없음 — 다른 포트 시도 필요 |

> 추가 사유 문구는 실 운영 중 수집하여 매핑 테이블로 관리.
> 대괄호 안 값은 동적 (예: `[Shanghai]`, `[SNKX]`).

---

## 5. 반납번호 발급 흐름

### 3단계 구조 (실 실행 검증, 2026-05-13)

```
[Stage 1] Request Redelivery 버튼
        ↓ POST /redeliverySession/validate
[Validate 결과 화면] (/redeliverySession/validate)
   ├── 모두 무효: 거부 사유 표시 + 추가 액션 없음 (안전 종료)
   └── 일부/전체 유효: Invalid 탭 + Redelivery 탭 + Continue 버튼 노출
              ↓
        [Stage 2] Continue Redelivery Request 버튼
              ↓ POST /redeliverySession/save/<sessionId>
[Pending 발급 화면] (/redelivery/create/<redeliveryNumber>)
   - 반납번호 즉시 발급 (예: ABUSG48854)
   - Status = "Pending Create"
   - Expiration Date 자동 설정 (예: +3개월)
              ↓
        [Stage 3] Finalize 버튼
              ↓ POST /redelivery/save/<redeliveryNumber>
[최종 성공 화면] (/redeliverySession/finish/<sessionId>)
   - "Success: Created N Redelivery"
   - 발급 결과 테이블 (Redelivery#, Depot, Unit, Equipment, Contract)
```

### Stage 1 (Validate) 자동화 — 확인됨

1. Country 단일선택 (`location_country`) — Select2
2. Port 단일선택 (`location_port`) — Select2
3. Unit Numbers 다중선택 (`unitNumbers`) — Select2 tag autocomplete
4. `<input type="submit" name="Request Redelivery">` 클릭
5. `/redeliverySession/validate` 페이지 결과 파싱

### Stage 2 — 확인 완료 (실 실행 검증, 2026-05-13)

- **진입 조건**: validate 결과에 1개 이상의 유효 단위 존재
- **버튼**: `<input type="submit" name="Continue Redelivery Request" id="Continue Redelivery Request">` (`#redeliveriesTabContent` 내 `form#requestForm`)
- **액션**: `POST /redeliverySession/save/<sessionId>` (+ `SYNCHRONIZER_TOKEN` CSRF)
- **이동 결과 URL**: `/redelivery/create/<redeliveryNumber>`
  - 실측 예: `/redelivery/create/ABUSG48854`
  - **URL의 마지막 segment가 발급된 반납번호** — 자동화에서 핵심 파싱 포인트

### Stage 2 결과 화면 (= Pending 발급 화면)

- 페이지 타이틀: `Triton International - New Redelivery`
- 헤더: `TRITON / New Redelivery`
- 안내 텍스트: `Creating 1 of 1 Redelivery(s)`

**Redelivery Information 카드**
| 필드 | 라벨 | 추출 위치 | 실측 예 |
|------|------|----------|---------|
| 반납번호 | (URL/form action) | `/redelivery/create/<NO>` 또는 `form#createForm` action 끝 | `ABUSG48854` |
| Storage Location | `Storage Location` | `<dt>Storage Location</dt><dd>...</dd>` | `Coolstar Co., Ltd.` (Depot 이름) |
| Master Customer | `Master Customer` | `<dt>Master Customer</dt><dd>...</dd>` | (선사별 코드) |
| Status | `Status` | `<dt>Status</dt><dd>...</dd>` | `Pending Create` |
| Expiration Date | `Expiration Date` | `<dt>Expiration Date</dt><dd>...</dd>` | `11-Aug-2026 23:59` (Asia/Seoul) |
| Standard Expiration | `Standard Expiration` | `<dt>...</dt><dd>` (boolean icon) | True (체크 아이콘) |

**Limits 카드**: 컨테이너 타입별 한도(Equipment Type, Contract, On-hire Location, Off-hire Location, TM Limit, Already TM Util, Pending Redelivery Approval, Awaiting Redelivery, Requested, Total Units on Redelivery, Available, Has Special Limits)

**Units 카드** (id=`redeliveryUnits`, DataTables):
| 컬럼 | DB 필드 | 예 |
|------|---------|-----|
| Contract | `redeliveryUnits[i].contract` | `HNGX17-200000` |
| Equipment Type | `redeliveryUnits[i].equipmentType` | `D5` (= 40' High Cube Dry Van) |
| Unit Number | `redeliveryUnits[i].unitNumber` | `TCLU8769849` |
| Lease Out Date | `redeliveryUnits[i].leaseOutDate` | (예: `30-Jun-2019`) |
| Lease Out Location | `redeliveryUnits[i].leaseOutLocation` | (예: `SHEU`) |
| (내부 ID) | `redeliveryUnits[i].id` | `1580428104653` |

**Contact Information 카드**: `Customer Email`, `Customer Comments` (선택 입력)

**Stage 3 버튼**: `<input type="submit" id="finalizeRedelivery" name="Finalize" value="Finalize">`

### Stage 3 (Finalize) — 확인 완료 (실 실행 검증, 2026-05-13)

- **버튼**: `<input type="submit" id="finalizeRedelivery" name="Finalize" value="Finalize">`
- **액션**: `POST /redelivery/save/<redeliveryNumber>` + `SYNCHRONIZER_TOKEN` (CSRF)
- **이동 결과 URL**: `/redeliverySession/finish/<sessionId>` (sessionId는 새로운 내부 ID)
  - 실측 예: `/redeliverySession/finish/1580428121297`

### Stage 3 결과 화면 (= 최종 성공 화면)

- 페이지 타이틀: `Triton International - Redelivery Session Finish` (추정)
- 헤더: `TRITON / Success: Created N Redelivery`
  - 실측: `Success: Created 1 Redelivery`
- 안내: `The below units were attached to new redeliveries.` (밝은 파란 배너)
- **최종 결과 테이블** — 자동화 파싱 핵심:
  | 컬럼 | 추출 위치 | 실측 예 |
  |------|----------|---------|
  | Redelivery Number | 1열 (링크 텍스트) | `ABUSG48854` |
  | Depot Name | 2열 | `Coolstar Co., Ltd.` |
  | Unit Number | 3열 (링크 텍스트) | `TCLU8769849` |
  | Equipment Name | 4열 | `40' High Cube Dry Van` |
  | Contract | 5열 | `HNGX17-200000` |
- Stage 3 이후에는 시스템상 Redelivery가 정식 등록된 상태로 추정 (이메일 발송, 한도 차감 등 후속 효과 발생 가능).

### 관련 조회 메뉴 (Unit Activity 드롭다운)

| 메뉴 | URL | 용도 |
|------|-----|------|
| Request Redelivery | `/redeliverySession/create` | 신규 반납 요청 (본 분석 대상) |
| Redelivery View/Modify | `/redeliveryFind/index` | 발급된 반납번호 조회/수정 |
| Redelivery Activity for Customer | `/redeliveryActivity/customer` | 고객별 반납 활동 내역 |
| Redelivery Detail for Customer | `/redeliveryDetail/customer` | 고객별 반납 상세 |
| Redelivery Outstanding for Customer | `/redeliveryOutstanding/customer` | 고객별 미완료 반납 |
| Redelivery Limits | `/redeliveryLimit/list` | 반납 한도 조회 |
| Release Search/Reports | `/release/list` | 출고/리포트 |

Pending 상태 추적 및 발급 이력 조회는 위 메뉴 추가 분석 시 가능.

---

## 6. 주의사항

- **Stage 2 = Pending 발급 (실 예약 시작)**: `Continue Redelivery Request` 클릭 시 반납번호가 즉시 발급되며 상태는 `Pending Create` (예: `ABUSG48854`). 이 시점부터 시스템상 예약 존재.
- **Stage 3 = 최종 확정**: `Finalize` 클릭 시 정식 등록 완료 (`Success: Created N Redelivery`). 한도 차감, 이메일 발송 등 후속 효과 발생 가능.
- **테스트로 생성된 예약은 반드시 취소**: 본 분석에서 생성된 `ABUSG48854` (HA / BUSG / TCLU8769849 / 2026-05-13) 는 사용자가 사이트에서 수동 취소함. 자동화 테스트 시 동일 원칙 적용.
- **취소 경로**: _(사용자 시연으로 추가 기록 예정)_
- **Pending 지연 생성**: 일부 컨테이너는 즉시 확정되지 않고 Pending 단계에서 지연되는 케이스가 있음 (사용자 사전 언급). 정확한 발생 조건과 상태 코드는 운영 중 수집.
- **Select2 위젯**: 모든 드롭다운이 jQuery + Select2 기반. 자동화 시 네이티브 `<select>`에 값 설정 + `jQuery(sel).trigger('change')` 패턴 사용 (UI 클릭보다 안정적).
- **Unit Numbers 입력**: textarea가 아닌 Select2 multi-select. 동적 옵션 추가 패턴:
  ```javascript
  $('#unitNumbers').append(new Option('TCLU1619873', 'TCLU1619873', true, true)).trigger('change');
  ```
- **Cookie 배너 (Cookiebot)**: 진입 시 자동 표시. 셀렉터: `#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll` 클릭으로 닫기.
- **중복 예약 방지**: 동일 컨테이너 중복 Stage 2 실행 방지 로직 필수.

---

## 7. 선사 차이점 (SK / HA)

| 항목 | SK (장금상선) | HA (흥아라인) |
|------|--------------|--------------|
| 환경변수 키 | `SK_TRIT_ID`, `SK_TRIT_PW` | `HA_TRIT_ID`, `HA_TRIT_PW` |
| 로그인 사용자명 (우상단) | `EUNMI KO` (확인) | `CMP CMP` (확인) |
| Customer 코드 (테이블) | 미확인 — 향후 캡처 | `HNGX` (Heung-A) |
| Contract 코드 prefix | 미확인 | `HNGX17-...` |

- 로그인 후의 폼 구조, validate 결과 컬럼은 **양사 동일**.
- 차이는 노출되는 데이터(Customer/Contract/허용 컨테이너 풀)뿐 — 자동화 로직 분기는 자격증명 prefix(`SK_*` / `HA_*`)만으로 충분.
