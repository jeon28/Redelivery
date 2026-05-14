# GESE — Validate ERROR 시 기 발급 RA 표시 + close_date 채움

> 작성일: 2026-05-14
> 1차 수정 완료 (2026-05-14): import / ACTIVE_RA_RE / ERROR 분기 / close_date finalize / _error_row 기본값
> **2차 수정 필요**: Validate ERROR 행의 메시지는 셀이 아닌 **팝업**에 존재 — 팝업 파싱 로직 추가
> 대상 파일: `scraper/scrapers/gese.py`

## 0. 1차 수정 후 발견된 문제

실제 사이트 검증 결과 (CRXU9980434 + Busan):

- 화면: 불가 / 반납지 OK / 반납번호 "-" / 유효기간 "-" / 사유 "Validate ERROR"
- 원인 분석:
  - Validate 후 Staging Table의 ERROR 행은 Messages 컬럼에 **"Messages" 라는 링크 텍스트**만 존재
  - 실제 메시지(`Container CRXU9980434 is on an active Return Authorization 0007440124`)는 **"View Messages" 버튼 클릭 시 열리는 팝업** 안에만 있음
  - 현재 `_parse_staging_table`은 "Messages" 라는 단어를 명시적으로 스킵(line 352) → `message=""` → 정규식 무매칭 → `booking_ref=None`, reason 폴백
  - 유효기간이 "-" 인 것은 backend Python 프로그램 미재시작 추정 (1차 수정 코드 미반영)

## 1. 2차 수정 목표

Validate 결과에 ERROR 행이 하나라도 있으면 **"View Messages" 팝업을 열어 모든 메시지를 캡처**, 컨테이너 번호로 매칭하여 각 ERROR 행에 실제 메시지를 채운다. 이후 기존 RA 추출 정규식 로직은 그대로 동작.

## 2. 변경 사항

### 2.1 새 헬퍼 `_capture_error_messages()` 추가

```python
async def _capture_error_messages(self) -> dict[str, str]:
    """View Messages 팝업을 열어 각 컨테이너 번호 → 메시지 텍스트 매핑을 반환.
    팝업이 없거나 비어있으면 빈 dict 반환."""
    vm_btn = self.page.locator("button").filter(has_text="View Messages").first
    if await vm_btn.count() == 0:
        return {}
    try:
        await vm_btn.click()
        await asyncio.sleep(1.2)
        # 팝업 / 다이얼로그 내 모든 텍스트 노드 수집
        texts: list[str] = await self.page.evaluate(
            r"""() => {
                const sel = '.sapMPopover, .sapMDialog, [role="dialog"], [role="tooltip"]';
                const visible = Array.from(document.querySelectorAll(sel))
                    .filter(e => e.offsetParent !== null);
                const out = new Set();
                for (const p of visible) {
                    const items = p.querySelectorAll('li, .sapMLIB, .sapMSLI, .sapMText');
                    for (const it of items) {
                        const t = (it.innerText || '').trim();
                        if (t.length > 5) out.add(t);
                    }
                    // 폴백: 컨테이너에서 직접 텍스트
                    const root = (p.innerText || '').trim();
                    if (root.length > 5) out.add(root);
                }
                return Array.from(out);
            }"""
        )
        container_re = re.compile(r"\b([A-Z]{4}\d{7})\b")
        msg_map: dict[str, str] = {}
        for t in texts:
            m = container_re.search(t)
            if not m:
                continue
            unit = m.group(1)
            # 같은 컨테이너에 대해 더 긴 메시지를 우선 (정보량 많음)
            if unit not in msg_map or len(t) > len(msg_map[unit]):
                msg_map[unit] = t
        return msg_map
    except Exception as exc:
        logger.warning("GESE _capture_error_messages: %s", exc)
        return {}
    finally:
        # 팝업 닫기 — Escape 또는 외부 클릭
        try:
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.4)
        except Exception:
            pass
```

### 2.2 `query()` 호출 흐름 수정 (현 `gese.py:184-187` 부근)

`_parse_staging_table()` 직후, ERROR 행이 있으면 메시지 캡처 후 머지:

```python
rows = await self._parse_staging_table()
has_error = any((r.get("status") or "").strip().upper() == "ERROR" for r in rows)
if has_error:
    msg_map = await self._capture_error_messages()
    for r in rows:
        if (r.get("status") or "").strip().upper() == "ERROR":
            unit = (r.get("unit") or "").strip().upper()
            popup_msg = msg_map.get(unit)
            if popup_msg and not r.get("message"):
                r["message"] = popup_msg
logger.info("GESE Validate 결과 %d행: %s", ...)
```

이후 기존 ERROR 분기 (`ACTIVE_RA_RE.search(msg)`) 가 정상 동작.

## 3. 비변경 항목

- 1차 수정으로 추가된 `ACTIVE_RA_RE`, ERROR 분기, finalize close_date 로직 — 그대로 유지.
- `_parse_staging_table` 의 기존 셀 기반 파싱 — 그대로. 팝업은 보조 소스.

## 4. 테스트 시나리오 (수동, 재시작 후)

| 입력 | 기대 |
|------|------|
| CRXU9980434 + Busan (기 발급 RA `0007440124`) | available=False, booking_ref="7440124", close_date="2026-05-31", reason=None |
| SEGU9586313 + Busan (Reefer 거부 — 다른 ERROR) | available=False, booking_ref=None, close_date="2026-05-31", reason=팝업 메시지 (e.g. Reefer 거부 사유) |
| 정상 신규 컨테이너 + Busan | available=True, booking_ref=Submit RA, close_date="2026-05-31" |

## 5. 리스크 / 미확정

- 팝업 셀렉터 (`.sapMPopover, .sapMDialog`) 가 실제 SAP UI5 v1.120 의 View Messages 다이얼로그 마크업과 일치할지 미확인. 빈 결과 시 reason 은 기존대로 "Validate ERROR" 폴백.
- 팝업이 메시지를 텍스트로 노출하지 않고 가상 스크롤로 일부만 렌더하는 경우 — 현재 행 수(최대 25)에서는 가능성 낮음. 필요 시 한 번 더 캡처 분석 후 재수정.
- 팝업 닫기 동작이 사이트 상태를 망가뜨리지 않는지 확인 필요 (Escape가 일반적).
