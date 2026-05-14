"""TRIT (Triton) 스크래퍼.

분석 문서: REDELIVERY/TRIT/ANALYSIS.md
구현 계획: REDELIVERY/TRIT/IMPLEMENTATION_PLAN.md

자동 발급 모드 (Stage 1 → 2 → 3):
  1. 로그인
  2. /redeliverySession/create 진입 → Country/Port/UnitNumbers 입력 → Request Redelivery
  3. Invalid 탭 파싱 (거부 컨테이너별 사유)
  4. Redelivery 탭에 유효 단위가 있으면:
     - Continue Redelivery Request → Pending Create (반납번호 발급)
     - Finalize → "Success: Created N Redelivery" → 최종 결과 테이블 파싱
"""
import asyncio
import logging
import re

from scrapers.base import BaseScraper
from scrapers._completed import detect_completed
from config.credentials import get_credential

logger = logging.getLogger(__name__)

LOGIN_URL  = "https://tools.tritoncontainer.com/tritoncontainer/login/auth"
CREATE_URL = "https://tools.tritoncontainer.com/tritoncontainer/redeliverySession/create"

REGION_MAP: dict[str, dict[str, str]] = {
    # 영문 코드 (대문자) — port 값은 Triton 사이트 드롭다운 옵션 텍스트에 부분 매칭됨.
    # Triton은 "INCHEON" (E 포함, 표준 표기) 을 쓰므로 우리 시스템 입력값 INCHON 을 INCHEON 으로 변환.
    "INCHON":     {"country": "KOREA", "port": "INCHEON"},
    "BUSAN":      {"country": "KOREA", "port": "BUSAN"},
    "GWANGYANG":  {"country": "KOREA", "port": "GWANGYANG"},
    "PYEONGTAEK": {"country": "KOREA", "port": "PYEONGTAEK"},
    "ULSAN":      {"country": "KOREA", "port": "ULSAN"},
    # 국문 동의어
    "부산": {"country": "KOREA", "port": "BUSAN"},
    "인천": {"country": "KOREA", "port": "INCHEON"},
    "광양": {"country": "KOREA", "port": "GWANGYANG"},
    "평택": {"country": "KOREA", "port": "PYEONGTAEK"},
    "울산": {"country": "KOREA", "port": "ULSAN"},
}


class TritScraper(BaseScraper):
    def __init__(self, company: str, lessor: str):
        super().__init__(company, lessor)
        self.cred = get_credential(company, lessor)

    # ------------------------------------------------------------------ #
    # Login                                                               #
    # ------------------------------------------------------------------ #

    async def login(self) -> bool:
        try:
            await self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
            pw_els = await self.page.query_selector_all('input[type="password"]')
            user_els = await self.page.query_selector_all(
                'input[type="text"], input[type="email"], input:not([type])'
            )
            if not pw_els or not user_els:
                logger.error("TRIT login: 입력 필드 탐지 실패")
                return False
            await user_els[0].fill(self.cred.get("id", ""))
            await pw_els[0].fill(self.cred.get("pw", ""))
            await pw_els[0].press("Enter")
            try:
                await self.page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            ok = "/login/auth" not in self.page.url
            if ok:
                logger.info("TRIT login OK: %s", self.page.url)
            else:
                logger.error("TRIT login failed — still on login page: %s", self.page.url)
            return ok
        except Exception as exc:
            logger.error("TRIT login exception: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    async def query(self, containers: list[str], region: str) -> list[dict]:
        region_info = REGION_MAP.get((region or "").upper()) or REGION_MAP.get(region or "")
        if not region_info:
            logger.error("TRIT: 지원하지 않는 region '%s'", region)
            return [self._error_row(c, f"지원하지 않는 지역: {region}") for c in containers]

        # 입력 정규화 (대문자 + 공백 제거 + 중복 제거, 입력 순서 보존)
        seen: set[str] = set()
        deduped: list[str] = []
        for c in containers:
            k = (c or "").strip().upper()
            if not k or k in seen:
                continue
            seen.add(k)
            deduped.append(k)

        # 초기 결과 (모두 "조회 실패"로 시작 → 단계별 갱신)
        results: dict[str, dict] = {
            c: self._error_row(c, "조회 실패") for c in deduped
        }

        try:
            # 1) 반납 생성 페이지 진입
            await self.page.goto(CREATE_URL, wait_until="networkidle", timeout=30_000)
            await self._dismiss_cookie_banner()

            # 2) Country / Port / UnitNumbers 입력
            r = await self._select2_set("location_country", region_info["country"])
            if not r.get("ok"):
                raise RuntimeError(f"Country 선택 실패: {r}")
            await asyncio.sleep(1.5)

            r = await self._select2_set("location_port", region_info["port"])
            if not r.get("ok"):
                raise RuntimeError(f"Port 선택 실패: {r}")
            await asyncio.sleep(1.0)

            r = await self._select2_tags("unitNumbers", deduped)
            if not r.get("ok"):
                raise RuntimeError(f"Unit Numbers 입력 실패: {r}")

            # 3) Request Redelivery 클릭 → validate
            btn = await self.page.query_selector('input[type="submit"][name="Request Redelivery"]')
            if not btn:
                raise RuntimeError("Request Redelivery 버튼을 찾을 수 없음")
            await btn.click()
            try:
                await self.page.wait_for_load_state("networkidle", timeout=30_000)
            except Exception:
                pass
            await asyncio.sleep(2)

            # 4) Invalid 탭 파싱
            await self._parse_invalid_tab(results)

            # 5) Redelivery 탭이 있으면 Stage 2/3 진행
            redel_tab = await self.page.query_selector("#redeliveriesTab")
            if redel_tab:
                await redel_tab.click()
                await asyncio.sleep(1.5)

                # Stage 2: Continue Redelivery Request
                cont_btn = await self.page.query_selector(
                    'input[type="submit"][name="Continue Redelivery Request"]'
                )
                if not cont_btn:
                    logger.warning("TRIT: Continue Redelivery Request 버튼 없음 — Stage 2 스킵")
                else:
                    await cont_btn.click()
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=60_000)
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                    pending_no = self._extract_redelivery_no_from_url()
                    pending_info = await self._parse_pending_page()
                    logger.info("TRIT Stage 2 → pending=%s units=%s", pending_no, list(pending_info))

                    # Stage 3: Finalize
                    fin_btn = await self.page.query_selector('#finalizeRedelivery')
                    if fin_btn:
                        await fin_btn.click()
                        try:
                            await self.page.wait_for_load_state("networkidle", timeout=60_000)
                        except Exception:
                            pass
                        await asyncio.sleep(2)
                        await self._parse_finish_table(results)
                    else:
                        # Finalize 버튼 없음 → Pending 정보로 결과 채움 (반납번호는 발급된 상태)
                        logger.warning("TRIT: Finalize 버튼 없음 — Pending 결과로 반영")
                        for unit, info in pending_info.items():
                            if unit in results:
                                results[unit].update({
                                    "available": True,
                                    "depot": info.get("depot"),
                                    "booking_ref": pending_no,
                                    "close_date": info.get("expiration"),
                                    "reason": None,
                                })
            else:
                logger.info("TRIT: Redelivery 탭 없음 — 전체 invalid")

        except Exception as exc:
            logger.error("TRIT query error: %s", exc)

        # 안전장치 + 3상태 status 도출
        # (_parse_invalid_tab / Stage2 / _parse_finish_table 의 update() 호출이
        #  status 키를 갱신하지 않으므로 최종 available + reason 기준으로 일괄 도출)
        for r in results.values():
            if r.get("available"):
                r["status"] = "available"
                r["completed_date"] = None
            elif detect_completed("TRIT", r.get("reason") or ""):
                r["status"] = "completed"
                r["completed_date"] = None  # 날짜 추출은 후속 작업
                # reason은 원본 그대로 유지 (사유 컬럼에 노출)
            else:
                r["status"] = "unavailable"
                r["completed_date"] = None
                if not r.get("reason"):
                    r["reason"] = "조회 실패 (사유 미상)"

        # 입력 순서대로 반환 (중복 입력은 같은 결과를 가리킴)
        return [
            results.get((c or "").strip().upper()) or self._error_row(c, "결과 없음")
            for c in containers
        ]

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _error_row(container: str, reason: str) -> dict:
        return {
            "container_no": (container or "").strip().upper(),
            "available": False,
            "status": "unavailable",
            "completed_date": None,
            "depot": None,
            "booking_ref": None,
            "over_caps": None,
            "close_date": None,
            "reason": reason,
        }

    async def _dismiss_cookie_banner(self):
        try:
            btn = await self.page.query_selector(
                '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll'
            )
            if btn:
                await btn.click(timeout=3_000)
                await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _select2_set(self, select_id: str, label_substr: str) -> dict:
        return await self.page.evaluate(
            """(args) => {
                const [sid, sub] = args;
                const sel = document.getElementById(sid);
                if (!sel) return { ok: false, error: 'select not found: ' + sid };
                const subL = sub.toLowerCase();
                const opt = Array.from(sel.options).find(o => (o.text || '').toLowerCase().includes(subL));
                if (!opt) return { ok: false, error: 'option not found', looked_for: sub };
                sel.value = opt.value;
                if (window.jQuery) { jQuery(sel).trigger('change'); }
                else { sel.dispatchEvent(new Event('change', { bubbles: true })); }
                return { ok: true, value: opt.value, text: opt.text };
            }""",
            [select_id, label_substr],
        )

    async def _select2_tags(self, select_id: str, values: list[str]) -> dict:
        return await self.page.evaluate(
            """(args) => {
                const [sid, vals] = args;
                const sel = document.getElementById(sid);
                if (!sel) return { ok: false, error: 'select not found: ' + sid };
                if (!window.jQuery) return { ok: false, error: 'jQuery missing' };
                const $sel = jQuery(sel);
                const seen = new Set();
                const added = [];
                for (const v of vals) {
                    const k = String(v).trim().toUpperCase();
                    if (!k || seen.has(k)) continue;
                    seen.add(k);
                    $sel.append(new Option(k, k, true, true));
                    added.push(k);
                }
                $sel.trigger('change');
                return { ok: true, added };
            }""",
            [select_id, values],
        )

    async def _parse_invalid_tab(self, results: dict):
        """validate 페이지의 'table-all' 첫 테이블에서 거부 컨테이너 정보 수집."""
        try:
            tbl = self.page.locator("table.table-all").first
            if await tbl.count() == 0:
                return
            rows = tbl.locator("tbody tr")
            n = await rows.count()
            for i in range(n):
                cells = rows.nth(i).locator("td")
                if await cells.count() < 2:
                    continue
                unit = (await cells.nth(0).inner_text()).strip().upper()
                reason = " ".join((await cells.nth(1).inner_text()).split())
                if unit in results:
                    results[unit].update({"available": False, "reason": reason})
                    logger.info("TRIT invalid: %s → %s", unit, reason)
        except Exception as exc:
            logger.warning("TRIT _parse_invalid_tab: %s", exc)

    def _extract_redelivery_no_from_url(self) -> str | None:
        m = re.search(r'/redelivery/create/([^/?#]+)', self.page.url)
        return m.group(1) if m else None

    async def _parse_pending_page(self) -> dict[str, dict]:
        """Pending Create 페이지의 Units 테이블 → unit→{depot,expiration} 매핑."""
        info: dict[str, dict] = {}
        try:
            depot      = await self._dt_value("Storage Location")
            expiration = await self._dt_value("Expiration Date")
            anchors = self.page.locator('a[href*="/unitStatus/show/"]')
            n = await anchors.count()
            for i in range(n):
                unit = (await anchors.nth(i).inner_text()).strip().upper()
                if unit and unit not in info:
                    info[unit] = {"depot": depot, "expiration": expiration}
        except Exception as exc:
            logger.warning("TRIT _parse_pending_page: %s", exc)
        return info

    async def _dt_value(self, label: str) -> str:
        try:
            dt = self.page.locator(f'dt:has-text("{label}")').first
            if await dt.count() == 0:
                return ""
            dd = dt.locator('xpath=following-sibling::dd[1]')
            return " ".join((await dd.inner_text()).split())
        except Exception:
            return ""

    async def _parse_finish_table(self, results: dict):
        """Stage 3 'Success: Created N Redelivery' 페이지의 결과 테이블 파싱.
        컬럼: Redelivery Number | Depot Name | Unit Number | Equipment Name | Contract"""
        try:
            tbl = self.page.locator("table").filter(
                has=self.page.locator('th:has-text("Redelivery Number")')
            ).first
            if await tbl.count() == 0:
                logger.warning("TRIT finish: 결과 테이블을 찾지 못함")
                return
            rows = tbl.locator("tbody tr")
            n = await rows.count()
            for i in range(n):
                cells = rows.nth(i).locator("td")
                cnt = await cells.count()
                if cnt < 3:
                    continue
                redel = (await cells.nth(0).inner_text()).strip()
                depot = (await cells.nth(1).inner_text()).strip()
                unit  = (await cells.nth(2).inner_text()).strip().upper()
                if unit in results:
                    results[unit].update({
                        "available": True,
                        "depot": depot,
                        "booking_ref": redel,
                        "reason": None,
                    })
                    logger.info("TRIT finish: %s → %s @ %s", unit, redel, depot)
        except Exception as exc:
            logger.warning("TRIT _parse_finish_table: %s", exc)
