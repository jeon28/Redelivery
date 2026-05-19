# TEXA 반납 취소(Cancel) 기능 개발 계획

> 작성일: 2026-05-18 (개정 2차 — 사이트 캡처 검증 반영)
> 상태: **사이트 분석 완료(Q4 이메일만 미확정) — 최종 합의 단계, 코딩 미시작**
> 범위: TEXA 우선 구현. 타 임대사(FLOR/TRIT/GOLD/GESE)는 분석만 병행하고 별도 계획서로 분리.

---

## 0. 사용자 1차 결정 (2026-05-18)

| 항목 | 결정 |
|------|------|
| 취소 단위 | **컨테이너 1개 단위** (다중 선택 가능) |
| Move/사용 완료 컨테이너 | **취소 불가** (서버에서 사전 차단 + 사이트도 차단 가정) |
| 트리거 UI | **결과 조회 화면(ResultTable)의 행별 체크박스**로 선택 |
| 확인 팝업 | 클릭 시 `"승인번호 *** 을 취소합니다"` 확인 모달 → 확인 후 실행 |

> 위 결정은 본 문서 §3, §6, §7 에 반영됨.

---

## 1. 목표

이미 발급된 TEXA 반납 예약(Booking Reference)에 묶인 컨테이너 중 **사용자가 결과 화면에서 체크한 컨테이너**들을 사이트 자동화로 취소한다. 현재 `/query`가 발급/조회까지만 처리하므로, 잘못 잡힌 예약을 사람이 사이트에 직접 들어가 지우는 흐름을 자동화한다.

## 2. 사이트 측 동작 (캡처 검증 완료, 2026-05-18)

> 상세 흐름은 `TEXA/ANALYSIS.md` 의 "취소(Cancel) 흐름" 섹션 참고.

| 항목 | 결과 |
|------|------|
| **Q1** 취소 UI 위치 | ✅ Preview 결과의 `Containers are booked (Can be deleted)` 테이블 — 행별 체크박스 + 우하단 빨간 ✗ 버튼 |
| **Q2′** 컨테이너 단위 부분 취소 | ✅ **지원** (행마다 체크박스, 동일 Bk Ref 안에서도 부분 선택 가능) |
| **Q3** 확인 다이얼로그 | ✅ in-page **Confirm Box** ("Are you sure you want to delete the containers you selected?" / Yes·No) — HTML 모달이므로 Playwright `dialog.accept()` 아님. `Yes` 버튼 직접 클릭 |
| **Q4** 이메일 자동 발송 | ⚠️ **미확정** — 첫 실 운영 시 확인 (Book 과 동일 패턴 가정) |
| **Q5** Move 완료 컨테이너 | ✅ 취소 불가, 서버 사전 차단 |
| 취소 성공 시그널 | Yes 클릭 후 동일 컨테이너로 Preview 자동 재실행 → `Containers can be booked` 패널로 전환 |

`Q2′` 가 지원 O 로 확인되어 사용자 결정한 **"컨테이너 1개 단위"** UX 와 사이트 동작이 정합. 운영 정책 재합의 불필요.

## 3. 입력/식별 (확정)

프론트는 **컨테이너 다건**을 한 번에 요청으로 보낸다. 서버는 booking_ref 단위로 그룹핑해 사이트 자동화를 수행한다.

**요청 페이로드 (의도):**
```json
POST /cancel
{
  "company": "SK",
  "lessor": "TEXA",
  "region": "INCHON",
  "items": [
    { "container_no": "TEMU1234567", "booking_ref": "TKE6E02" },
    { "container_no": "TCNU7654321", "booking_ref": "TKE6E03" }
  ]
}
```

- 프론트는 ResultTable 의 현재 행 정보를 그대로 전달하므로 `booking_ref` 가 함께 들어온다 (서버 재조회 불필요).
- 동일 `booking_ref` 가 여러 행에 걸쳐 있으면 서버에서 자동 그룹핑.

## 4. 아키텍처 (의도)

기존 구조를 그대로 따라간다. 별도 서비스/모듈을 새로 만들지 않는다.

```
[Frontend ResultTable]
    └─ 행마다 체크박스 (booking_ref 있고 status="available" 인 행에만 노출)
        └─ 하단 "선택 항목 취소" 버튼
            ↓ 모달: "승인번호 TKE6E02 외 N건을 취소합니다. 진행할까요?" (확인/취소)
            ↓ POST /cancel { company, lessor, region, items }
[FastAPI routers/cancel.py]   ← 신규 라우터
            ↓
[scrapers/base.py]  BaseScraper.cancel(...)  (추상 메서드, 미구현 임대사는 NotImplementedError)
            ↓
[scrapers/texa.py]  TexaScraper.cancel(...)  ← 이번 작업 범위
```

**합의 포인트 (남은 디테일):**
- (D1) 라우터 신규 분리 — `routers/cancel.py` 로 분리 (선호).
- (D2) `BaseScraper.cancel` 시그니처 — `async def cancel(self, items: list[CancelItem], region: str) -> list[CancelResult]`.
- (D3) 응답 모델 — 아래 §5 참고.

## 5. 응답 모델 (의도)

```json
{
  "results": [
    {
      "container_no": "TEMU1234567",
      "booking_ref": "TKE6E02",
      "cancelled": true,
      "reason": null
    },
    {
      "container_no": "TCNU0000000",
      "booking_ref": "TKE6E03",
      "cancelled": false,
      "reason": "이미 Move 완료 — 취소 불가"
    }
  ]
}
```

- 한 건이 실패해도 다른 건은 계속 시도 (부분 성공 허용).
- `reason` 은 한국어로 사용자 화면 표시용.

## 6. TEXA 스크래퍼 구현 흐름 (확정)

```
1. login()
2. _navigate_to_redelivery()
3. items 를 (region, booking_ref) 로 그룹핑

4. 그룹별로 1회 처리:
   a. Country/City 드롭다운 선택 (region 사용)
   b. Container ID textarea 에 그룹 내 모든 container 입력
   c. Equipment Query 라디오 체크 → Preview 클릭
   d. "Containers are booked (Can be deleted)" 패널 대기
   e. 패널 테이블에서 (Bk Ref, Eqp ID) 매칭 행의 행별 체크박스 체크
      ※ Eqp ID 의 dash 차이는 _norm_eqp 로 정규화 비교
   f. 우하단 빨간 ✗ 버튼 클릭
   g. Confirm Box 의 [Yes] 버튼 클릭
      (브라우저 dialog 가 아닌 HTML 모달 — locator 로 텍스트 매칭)
   h. 페이지 갱신 대기 후 결과 파싱:
        - "can be booked" 패널이 보이면 → 그룹 전체 취소 성공
        - "are booked (Can be deleted)" 가 그대로면 → 매칭되지 않은 row 만 잔존
          → 잔존 행에 들어있는 컨테이너만 실패로 마킹
   i. 그룹 다음으로 이동 (다음 그룹은 다시 Redelivery Request 페이지로 복귀 후 a~h 반복)

5. 결과 list[dict] 반환 (item 입력 순서 보존)
```

**구현 세부:**
- 같은 booking_ref 의 다중 컨테이너는 한 번의 Preview/X 클릭으로 일괄 처리해 사이트 부하·시간 최소화.
- 서로 다른 booking_ref 그룹 사이에는 Redelivery Request 페이지로 다시 진입 (textarea 새로 채우기).
- Move 완료 컨테이너는 `/cancel` 진입 시 서버에서 이미 차단되므로, 스크래퍼는 들어온 item 만 그대로 처리.
- Confirm Box 의 Yes 버튼 셀렉터는 first run 시 DOM 캡처해 정확한 locator 확정 (텍스트 매칭 우선).

## 7. 프론트엔드 변경 (의도)

`ResultTable.tsx` 변경:

- **체크박스 컬럼 추가** — `available === true && booking_ref != null` 인 행에만 체크박스 렌더.
- **선택 카운터 + 액션 바** — "N개 선택됨 / [선택 항목 취소]" 버튼을 테이블 상단 또는 하단에 표시.
- **확인 모달** — 클릭 시:
  - 1건: `"승인번호 TKE6E02 을 취소합니다. 진행할까요?"`
  - N건(동일 ref): `"승인번호 TKE6E02 의 컨테이너 N개를 취소합니다. 진행할까요?"`
  - N건(다중 ref): `"승인번호 TKE6E02 외 M건을 취소합니다. 진행할까요?"`
- **확인 시** — `/cancel` 호출, 응답에 따라 행 상태 갱신(취소 성공 행은 회색 처리 또는 제거, 실패 행은 사유 표시).

> 주의: `frontend/AGENTS.md` 에 "This is NOT the Next.js you know" 경고. 프론트 코드 작성 전 `node_modules/next/dist/docs/` 가이드를 먼저 확인.

## 8. 안전장치

- **Move/완료 컨테이너 사전 차단** — 프론트에서 해당 행에 체크박스 자체를 비활성화 (서버에서도 한 번 더 검증).
- **확인 모달 1회 필수**.
- **취소 진행 중 버튼 disable** + 스피너 → 더블 클릭 방지.
- **백엔드 동일 booking_ref 중복 요청 락(in-memory)** — 옵션, 추후 결정.
- **취소 이메일 사전 안내** — Q4 결과에 따라 모달 문구에 "사이트에서 자동 이메일이 발송됩니다" 추가.

## 9. 테스트 계획

- 단위 테스트는 사이트 mock 없이는 어려움 → 기존 `scraper/test_texa.py` 와 동일하게 실 사이트 수동 검증.

**시나리오:**
1. 방금 Book 한 신규 예약 1건의 컨테이너 1개 취소 (정상 케이스)
2. 동일 Bk Ref 에 묶인 컨테이너 2개 중 1개만 취소 (부분 취소 가능 시)
3. 서로 다른 Bk Ref 의 컨테이너 2건 동시 취소
4. Move 완료된 컨테이너를 강제로 요청에 포함 (서버 차단 동작 확인)
5. 존재하지 않는 booking_ref (잘못된 입력 처리)
6. 동일 컨테이너 연속 2회 취소 (멱등성/에러 처리)

## 10. 작업 순서

1. ✅ 사이트 캡처 확인 → `ANALYSIS.md` "취소 흐름" 섹션 갱신 완료
2. **본 계획 최종 합의** (현재 단계)
3. `BaseScraper.cancel` 추상 메서드 + 요청/응답 모델 + `routers/cancel.py` 골격
4. `TexaScraper.cancel` 구현 (위 §6 흐름 그대로)
5. 실 사이트 수동 테스트 (테스트용 신규 Book → 즉시 취소, Q4 이메일 발송 여부도 함께 확인)
6. 프론트 체크박스/액션 바/확인 모달 + `/cancel` 연동
7. 회고/주의사항을 `TEXA/ANALYSIS.md` 또는 별도 RETROSPECTIVE 에 기록

## 11. 타 임대사 분석 (병행)

본 작업 중 타 임대사는 **분석만** 한다. 각 폴더에 `CANCEL_ANALYSIS.md` (또는 `ANALYSIS.md` 안 섹션 추가)로 사이트별 취소 UI/플로우를 별도 정리. 구현은 TEXA 완료 후 임대사 단위로 별도 계획서.

---

## 합의 요청 (마지막 남은 항목)

- **D1~D3** (라우터 분리 · `BaseScraper.cancel` 시그니처 · 응답 모델) — 위 §4·§5 안에 큰 이견 없으시면 그대로 진행.
- **Q4 (이메일 발송)** — 코딩 후 첫 실 운영 시 함께 확인. 만약 발송이 확인되면 §7 모달 문구에 "사이트에서 자동 이메일이 발송됩니다" 추가.
- **취소 사유 입력 필요 여부** — 별도 입력 받지 않고 진행 가정. 필요하면 알려주세요.
- **운영 로그 별도 기록** — 현재 로깅(`logger.info`) 수준으로 충분 가정. 별도 DB/파일 기록이 필요하면 알려주세요.

위 항목 OK 면 §10 의 3단계부터 코딩 들어가겠습니다.
