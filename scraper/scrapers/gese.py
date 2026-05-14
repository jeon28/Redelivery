"""GESE (SeaCo) 스크래퍼.

분석 문서: REDELIVERY/GESE/ANALYSIS.md
구현 계획: REDELIVERY/GESE/IMPLEMENTATION_PLAN.md

자동 발급 모드 (Add → Validate → Submit):
  1. SAP UI5 로그인
  2. /navCus_RedeliveryRequest 진입 → City + Serial No. (max 25) 입력
  3. Add to Returns → Staging List 추가
  4. SelectAll → Validate → 행별 Status(OK/ERROR) 파싱
  5. OK 행이 있으면 Submit → 발급 결과(RA) 캡처
"""
import asyncio
import calendar
import logging
import re
from datetime import date

from scrapers.base import BaseScraper
from config.credentials import get_credential

logger = logging.getLogger(__name__)

ENTRY_URL = (
    "https://seaweb.seacoglobal.com/sap/bc/ui5_ui5/sap/zseaweb/index.html"
    "?saml2=disabled&handleX509=false&_sap-hash=JTIzJTJGbmF2Q3VzX0Rhc2hib2FyZA#/navCus_Dashboard"
)
REQUEST_URL = (
    "https://seaweb.seacoglobal.com/sap/bc/ui5_ui5/sap/zseaweb/index.html"
    "?saml2=disabled&handleX509=false&sap-client=100&sap-language=EN#/navCus_RedeliveryRequest"
)

# SAP UI5 컨트롤 ID (분석에서 확보)
ID_CITY_INPUT   = "container-com.seaco.seaweb---Cus_RedeliveryRequest--idRedeliveryRequestComboBoxCity-inner"
ID_SERIAL_INPUT = "container-com.seaco.seaweb---Cus_RedeliveryRequest--idTextAreaSerialNo-inner"

# Region → GESE city (영문 그대로)
REGION_MAP: dict[str, str] = {
    "BUSAN":     "Busan",
    "INCHON":    "Inchon",
    "INCHEON":   "Inchon",
    "GWANGYANG": "Gwangyang",
    "PYEONGTAEK": "Pyeongtaek",
    "ULSAN":     "Ulsan",
    "SEOUL":     "Seoul",
    # 국문
    "부산": "Busan",
    "인천": "Inchon",
    "광양": "Gwangyang",
    "평택": "Pyeongtaek",
    "울산": "Ulsan",
    "서울": "Seoul",
}

MAX_BATCH = 25   # GESE Serial No. textarea 최대 입력

# Validate ERROR 메시지에서 기존 RA(반납번호) 추출. 좌측 0 패딩은 호출부에서 제거.
ACTIVE_RA_RE = re.compile(r"active Return Authorization\s+(\d+)", re.IGNORECASE)


class GeseScraper(BaseScraper):
    def __init__(self, company: str, lessor: str):
        super().__init__(company, lessor)
        self.cred = get_credential(company, lessor)

    # ------------------------------------------------------------------ #
    # Login                                                               #
    # ------------------------------------------------------------------ #

    async def login(self) -> bool:
        try:
            await self.page.goto(ENTRY_URL, wait_until="domcontentloaded", timeout=30_000)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            await asyncio.sleep(2.5)

            user_el  = await self.page.query_selector('#USERNAME_FIELD-inner')
            pw_el    = await self.page.query_selector('#PASSWORD_FIELD-inner')
            login_btn = await self.page.query_selector('#LOGIN_LINK')
            if not user_el or not pw_el or not login_btn:
                logger.error("GESE login: 입력 필드 탐지 실패")
                return False

            await user_el.fill(self.cred.get("id", ""))
            await pw_el.fill(self.cred.get("pw", ""))
            await asyncio.sleep(0.3)
            await login_btn.click()
            try:
                await self.page.wait_for_load_state("networkidle", timeout=30_000)
            except Exception:
                pass
            await asyncio.sleep(4.0)  # SAP UI5 부팅 대기

            ok = "/navCus_Dashboard" in self.page.url or "navCus_" in self.page.url
            if ok:
                logger.info("GESE login OK: %s", self.page.url)
            else:
                logger.error("GESE login failed — URL: %s", self.page.url)
            return ok
        except Exception as exc:
            logger.error("GESE login exception: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    async def query(self, containers: list[str], region: str) -> list[dict]:
        city = REGION_MAP.get((region or "").upper()) or REGION_MAP.get(region or "")
        if not city:
            logger.error("GESE: 지원하지 않는 region '%s'", region)
            return [self._error_row(c, f"지원하지 않는 지역: {region}") for c in containers]

        # 정규화 + 중복 제거 (입력 순서 보존)
        seen: set[str] = set()
        deduped: list[str] = []
        for c in containers:
            k = (c or "").strip().upper()
            if not k or k in seen:
                continue
            seen.add(k)
            deduped.append(k)

        if len(deduped) > MAX_BATCH:
            logger.warning("GESE: 입력 %d개가 최대 %d 초과 — 처음 %d개만 처리",
                           len(deduped), MAX_BATCH, MAX_BATCH)
            overflow = deduped[MAX_BATCH:]
            deduped = deduped[:MAX_BATCH]
        else:
            overflow = []

        results: dict[str, dict] = {c: self._error_row(c, "조회 실패") for c in deduped}
        for c in overflow:
            results[c] = self._error_row(c, f"한 회 요청 최대 {MAX_BATCH}개 초과 — 미처리")

        try:
            # 1) Request 페이지 진입
            await self.page.goto(REQUEST_URL, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(3.0)

            # 2) City 선택
            if not await self._select_city(city):
                for c in deduped:
                    results[c]["reason"] = f"City '{city}' 선택 실패"
                return self._to_list(containers, results)

            # 3) Serial No. 입력
            ser_el = await self.page.query_selector(f'[id="{ID_SERIAL_INPUT}"]')
            if not ser_el:
                for c in deduped:
                    results[c]["reason"] = "Serial No. textarea 못 찾음"
                return self._to_list(containers, results)
            await ser_el.fill("\n".join(deduped))
            await asyncio.sleep(0.5)

            # 4) Add to Returns 클릭
            add_btn = self.page.locator("button").filter(has_text="Add to Returns").first
            if await add_btn.count() == 0:
                for c in deduped:
                    results[c]["reason"] = "Add to Returns 버튼 못 찾음"
                return self._to_list(containers, results)
            await add_btn.click()
            await asyncio.sleep(4.0)

            # 5) SelectAll → Validate
            sa = self.page.locator('.sapUiTableSelectAllCheckBox').first
            if await sa.count() == 0:
                logger.warning("GESE: SelectAll 없음 — Staging List 미생성 추정")
                return self._to_list(containers, results)
            await sa.click(force=True)
            await asyncio.sleep(1.5)

            validate_btn = self.page.locator("button").filter(has_text="Validate").first
            if await validate_btn.count() == 0 or await validate_btn.evaluate(
                "e => e.classList.contains('sapMBtnDisabled')"
            ):
                logger.warning("GESE: Validate 버튼 disabled 또는 없음")
                return self._to_list(containers, results)
            await validate_btn.click()
            try:
                await self.page.wait_for_load_state("networkidle", timeout=30_000)
            except Exception:
                pass
            await asyncio.sleep(3.5)

            # 6) Validate 결과 파싱
            rows = await self._parse_staging_table()
            # ERROR 행이 있으면 View Messages 팝업에서 실제 메시지 캡처 후 머지
            if any((r.get("status") or "").strip().upper() == "ERROR" for r in rows):
                msg_map = await self._capture_error_messages()
                for r in rows:
                    if (r.get("status") or "").strip().upper() != "ERROR":
                        continue
                    unit = (r.get("unit") or "").strip().upper()
                    popup_msg = msg_map.get(unit)
                    if popup_msg and not r.get("message"):
                        r["message"] = popup_msg
            logger.info("GESE Validate 결과 %d행: %s",
                        len(rows), [(r.get("unit"), r.get("status")) for r in rows])
            for r in rows:
                unit = (r.get("unit") or "").strip().upper()
                if unit not in results:
                    continue
                status = (r.get("status") or "").strip().upper()
                if status == "ERROR":
                    msg = r.get("message") or ""
                    m = ACTIVE_RA_RE.search(msg)
                    ra = m.group(1).lstrip("0") if m else None
                    # 기 발급 RA가 있으면 사이트가 ERROR로 표시해도 사용자 관점에서는
                    # 반납 가능(기존 RA로 반납 진행). RA 추출 실패한 진짜 거부만 불가.
                    results[unit].update({
                        "available": bool(ra),
                        "depot": r.get("depot"),
                        "booking_ref": ra,
                        "reason": None if ra else (msg or "Validate ERROR"),
                    })
                elif status == "OK":
                    results[unit].update({
                        "available": True,
                        "depot": r.get("depot"),
                        "reason": None,
                    })

            # 7) row.status == "OK" 인 행만 Submit. (ERROR+기 발급 RA는 available=True
            # 라도 새 Submit 대상이 아니므로 row status 기준으로 게이트.)
            ok_units = [
                (r2.get("unit") or "").strip().upper()
                for r2 in rows
                if (r2.get("status") or "").strip().upper() == "OK"
            ]
            ok_units = [u for u in ok_units if u in results]
            if not ok_units:
                logger.info("GESE: OK 행 없음 — Submit 스킵")
                return self._to_list(containers, results)

            submit_btn = self.page.locator("button").filter(has_text="Submit").first
            if await submit_btn.count() == 0 or await submit_btn.evaluate(
                "e => e.classList.contains('sapMBtnDisabled')"
            ):
                logger.warning("GESE: Submit disabled — 발급 미수행")
                for u in ok_units:
                    results[u]["reason"] = "Submit 비활성 (전제조건 미충족)"
                    results[u]["available"] = False
                return self._to_list(containers, results)
            await submit_btn.click()
            try:
                await self.page.wait_for_load_state("networkidle", timeout=60_000)
            except Exception:
                pass
            await asyncio.sleep(4.0)

            # 8) Submit 결과에서 RA 번호 추출 시도 (형식 미확정 — 다중 패턴)
            ra_map = await self._extract_ra_after_submit(ok_units)
            for u in ok_units:
                ra = ra_map.get(u)
                if ra:
                    results[u]["booking_ref"] = ra
                else:
                    results[u]["reason"] = "발급 완료 추정, RA 추출 실패 — 수동 확인 필요"

        except Exception as exc:
            logger.error("GESE query error: %s", exc)

        # 안전장치 + close_date 일괄 세팅 (요청월 말일)
        close_date_str = self._current_month_end_str()
        for r in results.values():
            if not r.get("available") and not r.get("reason") and not r.get("booking_ref"):
                r["reason"] = "조회 실패 (사유 미상)"
            r["close_date"] = close_date_str

        return self._to_list(containers, results)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _current_month_end_str() -> str:
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        return f"{today.year:04d}-{today.month:02d}-{last_day:02d}"

    @staticmethod
    def _error_row(container: str, reason: str) -> dict:
        return {
            "container_no": (container or "").strip().upper(),
            "available": False,
            "depot": None,
            "booking_ref": None,
            "over_caps": None,
            "close_date": GeseScraper._current_month_end_str(),
            "reason": reason,
        }

    @staticmethod
    def _to_list(containers: list[str], results: dict) -> list[dict]:
        return [
            results.get((c or "").strip().upper()) or GeseScraper._error_row(c, "결과 없음")
            for c in containers
        ]

    async def _select_city(self, city: str) -> bool:
        """SAP UI5 ComboBox에 city 입력 + 정확 일치 옵션 클릭."""
        try:
            city_inp = self.page.locator(f'[id="{ID_CITY_INPUT}"]').first
            if await city_inp.count() == 0:
                return False
            await city_inp.click()
            await asyncio.sleep(0.4)
            await city_inp.fill(city)
            await asyncio.sleep(1.5)

            # 옵션 정확 일치 클릭 (popover li)
            clicked = await self.page.evaluate(
                """(needle) => {
                    const items = Array.from(document.querySelectorAll('li'))
                        .filter(e => e.offsetParent !== null);
                    const target = items.find(e => (e.innerText || '').trim().toUpperCase() === needle.toUpperCase());
                    if (!target) return false;
                    target.scrollIntoView({ block: 'center' });
                    target.click();
                    return true;
                }""",
                city,
            )
            await asyncio.sleep(0.6)
            return bool(clicked)
        except Exception as exc:
            logger.warning("GESE _select_city(%r): %s", city, exc)
            return False

    async def _capture_error_messages(self) -> dict[str, str]:
        """View Messages 팝업을 열어 컨테이너 번호 → 메시지 텍스트 매핑을 반환.
        Validate 후 ERROR 행의 실제 사유는 셀이 아닌 팝업에 있음. 팝업이 없거나
        텍스트를 못 잡으면 빈 dict 반환."""
        vm_btn = self.page.locator("button").filter(has_text="View Messages").first
        if await vm_btn.count() == 0:
            return {}
        try:
            await vm_btn.click()
            await asyncio.sleep(1.2)
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
                # 같은 컨테이너에 대해 더 긴 메시지 우선 (정보량 많음)
                if unit not in msg_map or len(t) > len(msg_map[unit]):
                    msg_map[unit] = t
            logger.info("GESE View Messages 캡처: %d개 매핑", len(msg_map))
            return msg_map
        except Exception as exc:
            logger.warning("GESE _capture_error_messages: %s", exc)
            return {}
        finally:
            try:
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(0.4)
            except Exception:
                pass

    async def _parse_staging_table(self) -> list[dict]:
        """Validate 후 Staging Table 행 데이터 추출."""
        rows = await self.page.evaluate(
            r"""() => Array.from(document.querySelectorAll('table tbody tr'))
                .map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim()))
                .filter(r => r.length > 0 && r.some(c => c))"""
        )
        out: list[dict] = []
        # 컬럼 순서 (분석 기준): Lease Type | Lease No. | Unit Type Description | City | Depot Name | Serial No. | Status | Messages | (extra)
        for row in rows:
            if not row or len(row) < 7:
                continue
            # 컨테이너 번호가 들어 있는 셀 인덱스 추정 (4 letters + 7 digits)
            unit_idx = next(
                (i for i, c in enumerate(row) if re.fullmatch(r"[A-Z]{4}\d{7}", c.strip().upper())),
                -1,
            )
            if unit_idx < 0:
                continue
            unit   = row[unit_idx].strip().upper()
            # 일반 컬럼 매핑 (헤더 텍스트가 행에 포함된 경우 스킵)
            if unit in ("LEASE TYPE", "SERIAL NO."):
                continue
            try:
                lease_type   = row[0] if unit_idx >= 1 else ""
                lease_no     = row[1] if unit_idx >= 2 else ""
                unit_type    = row[2] if unit_idx >= 3 else ""
                city         = row[3] if unit_idx >= 4 else ""
                depot_name   = row[4] if unit_idx >= 5 else ""
                status       = row[unit_idx + 1] if unit_idx + 1 < len(row) else ""
                # Messages 셀(존재 시)에서 사유 추출
                message      = ""
                for c in row[unit_idx + 2:]:
                    c = (c or "").strip()
                    if c and c.lower() != "messages":
                        message = c
                        break
            except IndexError:
                lease_type = lease_no = unit_type = city = depot_name = status = message = ""

            out.append({
                "unit": unit,
                "lease_type": lease_type,
                "lease_no": lease_no,
                "unit_type": unit_type,
                "city": city,
                "depot": depot_name,
                "status": status,
                "message": message,
            })
        return out

    async def _extract_ra_after_submit(self, ok_units: list[str]) -> dict[str, str | None]:
        """Submit 후 결과 화면에서 컨테이너별 RA 번호 추출.
        형식 미확정 — 페이지 전체 텍스트에서 'RA' 또는 영숫자 패턴 탐색."""
        ra_map: dict[str, str | None] = {u: None for u in ok_units}
        try:
            # 결과 테이블 행 추출 시도
            rows = await self.page.evaluate(
                r"""() => Array.from(document.querySelectorAll('table tbody tr'))
                    .map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim()))
                    .filter(r => r.length > 0)"""
            )
            container_re = re.compile(r"^[A-Z]{4}\d{7}$")
            ra_candidate_re = re.compile(r"^[A-Z]{1,3}\d{4,8}$|^[A-Z]+-\d+$")
            for row in rows:
                # 컨테이너 셀과 RA 후보 셀이 같은 행에 있을 수 있음
                unit = next((c.strip().upper() for c in row if container_re.fullmatch(c.strip().upper())), None)
                if not unit or unit not in ra_map:
                    continue
                ra = next((c.strip() for c in row if ra_candidate_re.fullmatch(c.strip())), None)
                if ra:
                    ra_map[unit] = ra
        except Exception as exc:
            logger.warning("GESE _extract_ra_after_submit: %s", exc)
        return ra_map
