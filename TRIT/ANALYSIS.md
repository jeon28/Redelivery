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

- **상단 알림 배너 (전체 실패 시)**: 노란 배경
  - 예: `All units failed Redelivery validation; no redeliveries will be created. Please see below for reasons.`
- **탭/섹션 구분**: 유효/무효 단위 분리
  - 무효 탭 라벨: `N Invalid Unit(s)` (예: `1 Invalid Unit`)
  - 유효 탭 라벨: _(미확인 — 유효 컨테이너 테스트 필요)_
- **무효 단위 테이블** (class=`table-all`)
  | 컬럼 | 설명 |
  |------|------|
  | `Requested Unit Number` | 입력한 컨테이너 번호 |
  | `Reason` | 거부 사유 (예: `This unit was already turned in.`) |
- **유효 단위 화면**: _(미확인 — 유효 컨테이너 테스트 필요)_
  - 추정: 가능 컨테이너 목록 + 반납지/Depot 정보 + Stage 2 확정 버튼

### 확인된 거부 사유 예시

| Reason 문구 | 분류 | 의미 |
|------------|------|------|
| `This unit was already turned in.` | 컨테이너 상태 | 이미 반납 완료된 컨테이너 |
| `There are no Triton depots active for [<Port>] at this time. Please contact your local Triton subsidiary for assistance.` | 포트(Depot 가용성) | 해당 포트에 활성 Depot 없음 — 다른 포트 시도 필요 |

> 추가 사유 문구는 실 운영 중 수집하여 매핑 테이블로 관리.
> `[<Port>]` 부분에는 선택한 포트 이름이 동적으로 들어감 (예: `[Shanghai]`).

---

## 5. 반납번호 발급 흐름

### 2단계 구조 (사용자 확인)

```
[Stage 1] Request Redelivery 버튼 클릭
        ↓ POST /redeliverySession/validate
[Validate 결과 화면]
   ├── 모두 무효: 거부 사유 표시 + 추가 액션 없음 (안전 종료)
   └── 일부/전체 유효: 유효 단위 표시 + Stage 2 확정 버튼 노출
              ↓
        [Stage 2] 최종 확정 클릭
              ↓
        반납번호 발급 (즉시 또는 Pending 지연 생성)
```

### Stage 1 (Validate) 자동화 — 확인됨

1. Country 단일선택 (`location_country`) — Select2
2. Port 단일선택 (`location_port`) — Select2
3. Unit Numbers 다중선택 (`unitNumbers`) — Select2 tag autocomplete
4. `<input type="submit" name="Request Redelivery">` 클릭
5. `/redeliverySession/validate` 페이지 결과 파싱

### Stage 2 (Confirm) — **미확인**

- 유효 컨테이너로 한 번 더 테스트 필요
- 발급된 반납번호의 위치, 컬럼명, Pending 상태 표시 방식 등 캡처 필요

---

## 6. 주의사항

- **Stage 2 = 실 발급**: Stage 2 확정 버튼 클릭 시 반납번호가 발급(또는 Pending 등록)되므로, 자동화에서는 사용자 의도가 명확할 때만 실행한다. 단순 조회는 Stage 1까지만.
- **Pending 지연 생성**: 일부 컨테이너는 즉시 발급되지 않고 Pending 상태로 지연 생성됨 → 이후 상태 폴링 또는 별도 화면 확인 필요 (구현 시 추가 분석).
- **Select2 위젯**: 모든 드롭다운이 jQuery + Select2 기반. 자동화 시 네이티브 `<select>`에 값 설정 + `jQuery(sel).trigger('change')` 패턴 사용 (UI 클릭보다 안정적).
- **Unit Numbers 입력**: textarea가 아닌 Select2 multi-select. 동적 옵션 추가 패턴:
  ```javascript
  $('#unitNumbers').append(new Option('TCLU1619873', 'TCLU1619873', true, true)).trigger('change');
  ```
- **Cookie 배너 (Cookiebot)**: 진입 시 자동 표시. 셀렉터: `#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll` 클릭으로 닫기.
- **중복 예약 방지**: 동일 컨테이너 중복 Stage 2 실행 방지 로직 필수.

---

## 7. 선사 차이점 (SK / HA)

> _(라이브 시연 진행 중 — 추가 예정)_
