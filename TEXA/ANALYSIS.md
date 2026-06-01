# TEXA 사이트 분석 결과

> 임대사: Textainer (`TEXA`)
> 분석일: 2026-05-12
> 자동화 방식: **B안 (전체 자동화)**
> 출처: 루트 `PLAN.md` 섹션 10에서 분리

## 사이트 구조

| 항목 | 내용 |
|------|------|
| 로그인 URL | `https://www.textainer.com` (우상단 LOGIN 팝업) |
| 포털 URL | `https://tex.textainer.com/Customer/CustomerMenu.aspx` |
| 반납 조회 메뉴 | Others → **Request Redelivery** |

## 로그인 폼

| 필드 | 값 |
|------|-----|
| Login As | `Customer_Desktop` (Leasing Customer 선택) |
| Login Name | 계정 ID |
| Password | 계정 비밀번호 |

## Redelivery Request 입력 폼

| 필드 | 설명 |
|------|------|
| Country And City (1) | 국가 드롭다운 (예: `KOREA - KOR`) |
| Country And City (2) | 도시 드롭다운 (예: `INCHON - INC`) |
| Container ID | 컨테이너 번호 textarea (줄바꿈 구분, 최대 100개) |
| Query Mode | `Equipment Query` 라디오버튼 선택 |
| Preview 버튼 | 반납 가능 여부 조회 실행 |

## 자동화 전체 흐름 (B안)

```
1. 로그인 (www.textainer.com 팝업)
      ↓
2. Redelivery Request 페이지 이동
      ↓
3. Country/City 드롭다운 선택
   + Container ID 입력 (복수 가능)
      ↓
4. Preview 버튼 클릭
      ↓
5. 결과 파싱
   ├── "Containers cannot be redelivered" (빨간색)
   │     → Eqp Units + Reason 추출 → 반납 불가 처리
   └── "Containers can be booked" (파란색)
         → 체크박스 선택 + Book 버튼 클릭
              ↓
         6. 반납번호 발급 (예: TKE6E02)
              ↓
         7. 발급된 반납번호 링크 클릭
              ↓
         8. 상세 화면에서 추출:
            - Bk Ref (반납번호)
            - Depot Name (반납지, 예: INC05 - SEUNG JIN ENTERPRISES)
            - Over Caps (YES/NO)
            - Ant Close Date (유효기간)
```

## 결과 화면 구조

### 반납 불가

```
제목: "Containers cannot be redelivered"
컬럼: Eqp Units | Reason
예시: TEMU154935 | CONTAINERS NOT HIRED BY SINOK1
```

### 반납 가능 (Preview)

```
제목: "Containers can be booked and references will be issued immediately"
컬럼: Units | Contract | Lease | Cust Name | Eqp Type | Depot Name | Tex Ofc | Caps Left | Over Caps
예시: 1 | KORL0457 | KORL0458 | SINOKOR | 20 STD DRY FRT | INC05 - SEUNG JIN ENTERPRISES | SEL | 5 | NO
```

### 반납번호 상세 (Book 후)

```
Booking Header:
  Bk Ref: TKE6E02
  Depot Name: INC05 - SEUNG JIN ENTERPRISES
  Over Caps: NO
  Ant Close Date: 2026-MAY-31

Assigned Containers:
  Equipment ID | Eqp Type | Eqp Status | Move Status | Move Depot | Move Date
```

## ⚠️ 주의사항

- **Book 버튼 클릭 = 실제 예약 생성** → 이메일 자동 발송, Caps Left 차감
- 동일 컨테이너 중복 실행 시 중복 예약 발생 가능
- 스크래퍼에서 중복 체크 로직 필요

### 반납번호(Bk Ref) prefix 는 시기별로 변동한다

- 5월분은 `TKE…`, 6월분은 `TKF…` 처럼 **세 번째 글자가 시기에 따라 굴러간다**.
- 따라서 반납번호를 prefix 문자열(`"TKE"`)로 하드코딩 필터링하면 안 된다. 필요 시 `^TK[A-Z0-9]` 패턴으로 매칭한다.

### Book 직후 반납번호 회수 흐름 (정정)

- Book 클릭 직후 화면은 **링크 목록이 아니라** success 메시지 + 빈 폼이다:
  `New Booking - {Bk Ref} is created successfully! Email has been sent ...`
- 따라서 Book 직후 반납번호/반납지/Caps/유효기간 회수는 **동일 컨테이너로 Preview 를 한 번 더 실행**해
  `Containers are booked` 상태로 전환한 뒤 "already booked" 파서로 추출한다. (Preview 는 조회 전용이라 중복 예약 위험 없음)
- success 메시지의 `{Bk Ref}` 는 로그/교차검증용으로만 사용.

## 취소(Cancel) 흐름

> 분석일: 2026-05-18 (HEUNGA 계정으로 `TEMU0013087` 캡처 검증)
> 사이트 표기: `TEMU001308-7` (dash 포함 → 스크래퍼는 `_norm_eqp` 로 dash 제거 후 비교)

### 진입 방식

1. **Redelivery Request 페이지로 이동** (조회와 동일 메뉴).
2. 동일 Country/City + 취소할 Container ID 를 textarea 에 입력.
3. **Preview** 클릭.
4. 결과 영역에 **`Containers are booked (Can be deleted)`** 패널이 노출되면 취소 가능 상태.

### "Can be deleted" 테이블 구조

| 컬럼 | 설명 |
|------|------|
| Bk Ref | 발급된 반납번호 (예: `TKE6E25`) |
| Eqp ID | 컨테이너 번호 (dash 포함, 예: `TEMU001308-7`) |
| Eqp Type | 컨테이너 타입 (예: `20 STD DRY FRT`) |
| Bk Date | 발급 일자 (예: `2026-MAY-13`) |
| Depot | depot 코드 (예: `INC05`) |
| (마지막 컬럼) | **행별 체크박스** + 헤더에 select-all 체크박스 |

테이블 우하단에 **빨간 X 버튼** (삭제 실행 버튼) 1개.

> 실제 마크업 (2026-06-01 DOM 확인):
> `<input type="image" title="Delete" name="...$btnDelete" src="../Images/buttons/Letter-X-icon.png" disabled>`
> - `<img>` 가 아니라 **`<input type="image">`** 이며 src 에 `delete`/`cancel` 문자열이 없다(`Letter-X-icon.png`).
>   → 셀렉터는 `input[type=image][title=Delete]` 또는 `input[name$=btnDelete]` 로 잡는다.
> - **행 체크 전에는 `disabled`**. 행 체크는 `__doPostBack` 을 유발해 패널을 재렌더하며 이때 enable 된다.
>   → 행 체크 후 postback 완료를 대기하고(미대기 시 disabled 클릭 무시), `is_enabled()` 확인 후 클릭.
> - 행 체크 postback 으로 패널 DOM 이 교체되므로, 체크 시점에 잡아둔 `panel_table` 참조는 stale 이 된다.
>   삭제 버튼은 frame 단위 셀렉터로 다시 찾는다.

### 취소 단계

```
1. 취소할 행의 체크박스 클릭   (행이 초록색 하이라이트로 표시됨)
   ※ 같은 Bk Ref 안의 컨테이너 중 일부만 선택 가능 → 컨테이너 단위 부분 취소 지원
2. 우하단 빨간 ✗ 버튼 클릭
3. in-page Confirm Box 팝업:
      "Are you sure you want to delete the containers you selected?"
      [ Yes ]   [ No ]
   ※ JS dialog 가 아니라 HTML 모달이므로 Playwright `dialog.accept()` 불가.
     `Yes` 버튼을 locator 로 찾아 직접 클릭.
4. Yes 클릭 후 사이트가 동일 컨테이너로 Preview 를 자동 재실행:
   → "Containers can be booked and references will be issued immediately"
     (Caps Left 가 다시 늘어난 상태) 화면으로 전환되면 취소 성공.
```

### 성공/실패 판정 시그널

- **성공**: 동일 컨테이너에 대해 결과 패널이 `can be booked` 로 바뀜
  (또는 `cannot be redelivered` 로 바뀌는 경우도 있을 수 있음 — caps 정책상).
- **실패/막힘**: `Containers are booked (Can be deleted)` 가 그대로 남아있거나, Confirm Box 자체가 안 뜨면 실패로 간주.

### 주의사항

- **Move 완료 컨테이너**: `_parse_booked_table` 의 Move 컬럼이 > 0 인 컨테이너는 취소 대상에서 사전 제외해야 한다 (사용자 정책).
- **이메일 자동 발송 여부 (TBD)**: Book 과 동일하게 사이트가 취소 메일을 발송하는지 미확정. 첫 실 운영 시 확인 후 본 섹션에 기록.
- **동일 Bk Ref 다수 컨테이너 동시 취소**: 한 번의 Preview → 다수 행 체크 → 한 번의 X 클릭으로 일괄 처리 가능. 스크래퍼도 booking_ref 단위로 그룹핑해 일괄 처리.

---

## 선사 차이점

> 장금상선(SK) / 흥아라인(HA) 간 계정, 도시 기본값, UI 차이 등을 여기에 기록.

- 취소 흐름은 SK/HA 동일 (HA 계정으로 캡처 검증, SK 도 동일 UI 가정).
