# 반납완료 표기 변경 계획

> 작성일: 2026-05-14 (구현 기준으로 갱신)
> 합의: Order Date · `M/D 완료` · FLOR 완전 구현 + TRIT/GOLD 스캐폴드
> 상태: 구현 완료

---

## 1. 목표

이미 반납이 완료된 컨테이너 조회 시, 결과 테이블의 **가능여부 컬럼만** `❌ 불가` 대신 `M/D 완료`로 표기. 다른 시각 요소(행 배경색, 카운터, "불가 사유" 컬럼 등)는 변경하지 않음.

스크린샷 예시: `DFSU7595959` / FLOR / Closed / Order Date=`2026-05-13` → 가능여부 셀에 `5/13 완료` (빨강 텍스트, 이모지 없음).

## 2. 적용 범위

| 임대사 | 이번 PR | 비고 |
|--------|--------|------|
| FLOR | ✅ 완전 구현 (날짜 포함) | Redelivery Status 탭에 Status/Order Date 구조적으로 노출 |
| TRIT | ✅ 스캐폴드만 (감지 훅 + 빈 패턴 + TODO) | Invalid 탭 reason 패턴 + 날짜 추출은 별도 분석 필요 |
| GOLD | ✅ 스캐폴드만 (감지 훅 + 빈 패턴 + TODO) | cannot 모달 / search 첫 행 reason 패턴 분석 필요 |
| TEXA | ❌ 보류 | 별도 사이트 분석 후 후속 PR |
| GESE | ❌ 보류 | 웹 미작동 |

## 3. API 계약 변경

### `QueryResult` 인터페이스 (스크래퍼 응답 + 프론트엔드 타입)

기존 필드는 그대로 유지. 추가 필드 두 개. 하위호환 보존.

| 필드 | 타입 | 의미 |
|------|------|------|
| `status` | `"available" \| "completed" \| "unavailable" \| null` | 3상태. `null`/`undefined`이면 프론트가 `available` 불리언에서 추론 |
| `completed_date` | `string \| null` | `M/D` 형식(앞자리 0 없음). FLOR만 채움. TRIT/GOLD는 현재 `null` |

완료(`completed`) 행도 `available: false`로 둠 → 카운터가 자동으로 "불가"에 합산됨. `reason`도 비우지 않음 → "불가 사유" 컬럼에 원본 사유 그대로 노출.

## 4. 스크래퍼 변경

### 4-1. FLOR (`scraper/scrapers/flor.py`)

신규 헬퍼:

```python
def _to_mmdd(iso: str | None) -> str | None:
    """'2026-05-13' → '5/13'. 비/잘못된 입력은 None. 앞자리 0 없음."""
    m = re.match(r"^\d{4}-(\d{1,2})-(\d{1,2})$", (iso or "").strip())
    if not m:
        return None
    return f"{int(m.group(1))}/{int(m.group(2))}"
```

`_search_one` 안에서 Status 판정을 3상태로 분기:

```python
s = status.lower()
is_open   = "open" in s
is_closed = "closed" in s
available = is_open

if is_open:
    result_status = "available"
elif is_closed:
    # 이미 반납 완료 — Order Date를 'M/D'로 노출
    result_status = "completed"
    completed_date = _to_mmdd(parsed.get("order_date", ""))
    reason = "이미 반납됨 (Closed)"   # 사유 컬럼에 그대로 노출
else:
    result_status = "unavailable"
    if "void" in s or "cancel" in s:
        reason = "취소된 예약 (VOID)"
    else:
        reason = f"발급 상태: {status or '미상'}"
```

반환 dict + `_error_row` + 다른 return 경로(no rows, VOID-only)에 `status` / `completed_date` 키 추가. `query()` 안전장치 루프가 completed 행의 reason을 덮어쓰지 않도록 가드 추가 (실제론 reason이 채워져 있어 문제 없지만 명시적으로).

### 4-2. TRIT (`scraper/scrapers/trit.py`) / GOLD (`scraper/scrapers/gold.py`) — 스캐폴드

공통 헬퍼 `scraper/scrapers/_completed.py`:

```python
COMPLETED_REASON_PATTERNS: dict[str, list[str]] = {
    "TRIT": [
        # TODO: 실제 reason 텍스트 수집 후 추가
    ],
    "GOLD": [
        # TODO: 동일
    ],
}

def detect_completed(lessor: str, reason: str | None) -> bool:
    if not reason:
        return False
    r = reason.lower()
    return any(p.lower() in r for p in COMPLETED_REASON_PATTERNS.get(lessor, []))
```

각 스크래퍼의 결과 마무리 루프에서 3상태 status 일괄 도출 (update() 호출들이 status 키를 갱신하지 않으므로 최종 available + reason 기준으로 도출):

```python
for r in results.values():
    if r.get("available"):
        r["status"] = "available"
        r["completed_date"] = None
    elif detect_completed("TRIT", r.get("reason") or ""):
        r["status"] = "completed"
        r["completed_date"] = None  # 날짜 추출은 후속 작업
        # reason은 원본 유지
    else:
        r["status"] = "unavailable"
        r["completed_date"] = None
        if not r.get("reason"):
            r["reason"] = "조회 실패 (사유 미상)"
```

`_error_row`에도 `status="unavailable"`, `completed_date=None` 추가.

패턴 리스트가 비어 있어 행동 변화는 없음 (false positive 방지). 패턴 발견되는 즉시 한 줄 추가로 활성화.

### 4-3. TEXA — 변경 없음

`status` 필드를 채우지 않음 → 프론트는 `available`로 fallback.

## 5. 프론트엔드 변경 (`frontend/components/ResultTable.tsx`)

### 5-1. 타입 확장

```ts
export type QueryStatus = 'available' | 'completed' | 'unavailable'

export interface QueryResult {
  container_no: string
  available: boolean
  status?: QueryStatus | null      // 추가
  completed_date?: string | null   // 추가 ('M/D')
  depot: string | null
  booking_ref: string | null
  over_caps: number | null
  close_date: string | null
  reason: string | null
}
```

### 5-2. 상태 추론 헬퍼

```ts
function effectiveStatus(r: QueryResult): QueryStatus {
  if (r.status === 'available' || r.status === 'completed' || r.status === 'unavailable') {
    return r.status
  }
  return r.available ? 'available' : 'unavailable'
}
```

### 5-3. 렌더링 — 가능여부 셀만 분기

- `available` → `✅ 가능` (text-green-700) — 기존과 동일
- `completed` → `{completed_date} 완료` (text-red-600, **이모지 없음**). `completed_date`가 `null`이면 `완료`만.
- `unavailable` → `❌ 불가` (text-red-600) — 기존과 동일

**변경하지 않는 것** (의도):
- 행 배경색: 기존 `available ? bg-green-50 : bg-red-50` 로직 그대로. 완료 행도 `bg-red-50`.
- 상단 카운터: 기존 2분할 `가능 X · 불가 Y` 그대로. 완료 행도 `unavailable.count`에 포함.
- "불가 사유" 컬럼: 기존 `r.reason ?? '-'` 그대로. 완료 행도 "이미 반납됨 (Closed)" 등 사유 표시.

## 6. 영향 받는 파일 (실제)

| 파일 | 변경 종류 |
|------|----------|
| `scraper/scrapers/_completed.py` | 신규 — 공통 헬퍼 + 빈 패턴 dict |
| `scraper/scrapers/flor.py` | `_to_mmdd` 헬퍼 추가, `_search_one` 3상태 분기, 모든 return 경로에 `status`/`completed_date` 키, 안전장치 가드 |
| `scraper/scrapers/trit.py` | `detect_completed` import, 마무리 루프 3상태 도출, `_error_row` 보완 |
| `scraper/scrapers/gold.py` | 동일 |
| `scraper/routers/query.py` | **Pydantic `ContainerResult` 모델에 `status` (Literal) + `completed_date` 필드 추가.** 이게 누락되면 FastAPI가 `response_model=QueryResponse` 직렬화 시 새 필드를 drop함 (1차 구현 시 누락되어 프론트가 계속 "불가"로 보였던 원인). |
| `frontend/components/ResultTable.tsx` | `QueryStatus` 타입, `effectiveStatus` 헬퍼, 가능여부 셀 3분기 |
| `PLAN_COMPLETED_LABEL.md` | 본 문서 (구현 기준 갱신) |

## 7. 작업 순서 (실제로 진행한 흐름)

1. 계획 작성 + 검토 / 승인 받음
2. `_completed.py` (공통 헬퍼) 추가
3. `flor.py` `_to_mmdd` + 3상태 분기 구현
4. `trit.py`, `gold.py` 마무리 훅 추가
5. `ResultTable.tsx` 타입 + 가능여부 셀 분기
6. 1차 검토 후 범위 축소 (카운터/배경/사유 컬럼은 손대지 않음, 포맷 `MM/DD` → `M/D`)
7. (사용자 측) dev server 또는 실 컨테이너로 시각 확인

## 8. 비범위

- TRIT/GOLD의 reason 패턴 수집 / 추가 → 별도 분석 PR
- TEXA "완료" 케이스 → 별도 분석 PR
- 완료 상태 카운터 분리 / 시각 강조 → 합의에 따라 미적용
- "불가 사유" 컬럼명 변경 → 별도 작업

## 9. 위험 / 주의

- **하위호환**: `status` 필드는 optional. 백엔드가 안 보내도 프론트가 `available`로 fallback하므로 배포 순서 무관.
- **카운터 의미 유지**: 완료 행도 `available=false`로 두어 기존 "불가 N개" 카운터에 포함됨 — 외부 도구/스냅샷 비교에 영향 없음.
- **TRIT/GOLD 스캐폴드 비활성**: 패턴 리스트가 비어 있어 실제론 아무 행도 `completed`로 잡히지 않음 (실 데이터 분석 전엔 false positive 방지).
- **검증 미수행**: 본 환경에 Python 인터프리터 / frontend node_modules 가 없어 컴파일·타입 체크 미실행. 사용자 측에서 `python scrapers/_completed.py` 임포트 가능 여부, `npm install && npm run dev` 후 시각 확인 권장.
