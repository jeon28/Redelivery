"""GOLD (Touax) 스크래퍼.

분석 문서: REDELIVERY/GOLD/ANALYSIS.md
구현 계획: REDELIVERY/GOLD/IMPLEMENTATION_PLAN.md

자동 발급 모드:
  1. 로그인
  2. 컨테이너별로 /off-hire 진입 → City/Container 입력 → Search
  3. "Off hire" 모달 열기 → can/cannot 테이블 파싱
  4. 유효 컨테이너만 Confirm 클릭 (실 발급)
  5. /off-hire/history에서 RA####### 매칭
"""
import asyncio
import logging

from scrapers.base import BaseScraper
from config.credentials import get_credential

logger = logging.getLogger(__name__)

LOGIN_URL    = "https://www.touax-container.com/login"
OFF_HIRE_URL = "https://www.touax-container.com/off-hire"
HISTORY_URL  = "https://www.touax-container.com/off-hire/history"

REGION_MAP: dict[str, str] = {
    # 영문
    "BUSAN":     "KRPUS",
    "INCHON":    "KRINC",
    "INCHEON":   "KRINC",
    "GWANGYANG": "KRKAN",
    "KWANGYANG": "KRKWA",
    "UIWANG":    "KRUWN",
    "GUNSAN":    "KRKUV",
    "YANGSAN":   "KRYSN",
    "SEOUL":     "KRSEL",
    # 국문
    "부산": "KRPUS",
    "인천": "KRINC",
    "광양": "KRKAN",
    "의왕": "KRUWN",
    "군산": "KRKUV",
    "양산": "KRYSN",
    "서울": "KRSEL",
}


class GoldScraper(BaseScraper):
    def __init__(self, company: str, lessor: str):
        super().__init__(company, lessor)
        self.cred = get_credential(company, lessor)
        self._cookie_dismissed = False

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
                logger.error("GOLD login: 입력 필드 탐지 실패")
                return False
            await user_els[0].fill(self.cred.get("id", ""))
            await pw_els[0].fill(self.cred.get("pw", ""))
            await pw_els[0].press("Enter")
            try:
                await self.page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            ok = "/login" not in self.page.url
            if ok:
                logger.info("GOLD login OK: %s", self.page.url)
            else:
                logger.error("GOLD login failed: %s", self.page.url)
            return ok
        except Exception as exc:
            logger.error("GOLD login exception: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    async def query(self, containers: list[str], region: str) -> list[dict]:
        city_code = REGION_MAP.get((region or "").upper()) or REGION_MAP.get(region or "")
        if not city_code:
            logger.error("GOLD: 지원하지 않는 region '%s'", region)
            return [self._error_row(c, f"지원하지 않는 지역: {region}") for c in containers]

        # 입력 정규화 + 중복 제거 (입력 순서 보존)
        seen: set[str] = set()
        deduped: list[str] = []
        for c in containers:
            k = (c or "").strip().upper()
            if not k or k in seen:
                continue
            seen.add(k)
            deduped.append(k)

        results: dict[str, dict] = {}
        for cont in deduped:
            try:
                results[cont] = await self._process_one(city_code, cont)
            except Exception as exc:
                logger.error("GOLD process %s error: %s", cont, exc)
                results[cont] = self._error_row(cont, "조회 실패 (예외)")

        # 안전장치
        for r in results.values():
            if not r.get("available") and not r.get("reason"):
                r["reason"] = "조회 실패 (사유 미상)"

        return [
            results.get((c or "").strip().upper()) or self._error_row(c, "결과 없음")
            for c in containers
        ]

    async def _process_one(self, city_code: str, container: str) -> dict:
        # 1) /off-hire 진입 + 쿠키 배너 dismiss
        await self.page.goto(OFF_HIRE_URL, wait_until="networkidle", timeout=30_000)
        await self._dismiss_cookie_banner_once()

        # 2) City 선택 (TomSelect)
        r = await self._set_city(city_code)
        if not r.get("ok"):
            return self._error_row(container, f"City 설정 실패: {r.get('error')}")

        # 3) Container 입력
        cn_el = await self.page.query_selector('#app_front_off_hire_filter_containerNumber')
        if not cn_el:
            return self._error_row(container, "Container 입력 필드를 찾을 수 없음")
        await cn_el.fill(container)

        # 4) Search 클릭
        search_btn = self.page.locator(
            'form[name="app_front_off_hire_filter"] button[type="submit"]'
        ).first
        if await search_btn.count() == 0:
            return self._error_row(container, "Search 버튼을 찾을 수 없음")
        await search_btn.click()
        try:
            await self.page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        await asyncio.sleep(1.0)

        # 5) "Off hire" 버튼 존재 확인 → 모달 열기
        off_btn = self.page.locator('a.modalClickoffHire').first
        if await off_btn.count() == 0:
            row_msg = await self._read_first_result_row()
            return self._error_row(container, row_msg or "검색 결과 없음")
        await off_btn.click()
        try:
            await self.page.wait_for_function(
                """() => {
                    const m = document.querySelector('.modal.show, .modal.in, .modal[style*="display: block"]');
                    if (!m) return false;
                    return (m.innerText || '').length > 80;
                }""",
                timeout=15_000,
            )
        except Exception:
            logger.warning("GOLD: 모달 콘텐츠 로딩 타임아웃")
        await asyncio.sleep(1.0)

        # 6) 모달 can/cannot 파싱
        cannot = await self._parse_modal_table("cannot be off hire")
        can = await self._parse_modal_table("can be off hire", exclude_substr="cannot")

        # 7) 결과 매핑
        if container in cannot:
            return self._error_row(container, cannot[container])

        if container not in can:
            return self._error_row(container, "모달에서 컨테이너 정보를 찾을 수 없음")

        depot_from_modal = can[container]

        # 8) Confirm 클릭 (실 발급)
        if not await self._click_modal_confirm():
            return {
                "container_no": container,
                "available": False,
                "depot": depot_from_modal,
                "booking_ref": None,
                "over_caps": None,
                "close_date": None,
                "reason": "Confirm 버튼을 찾을 수 없음 (발급 미수행)",
            }
        try:
            await self.page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        await asyncio.sleep(2.0)

        # 9) /off-hire/history 에서 RA 추출
        ra_info = await self._lookup_history(container)
        if ra_info:
            return {
                "container_no": container,
                "available": True,
                "depot": ra_info.get("depot") or depot_from_modal,
                "booking_ref": ra_info.get("ra"),
                "over_caps": None,
                "close_date": ra_info.get("period"),
                "reason": None,
            }
        return {
            "container_no": container,
            "available": True,
            "depot": depot_from_modal,
            "booking_ref": None,
            "over_caps": None,
            "close_date": None,
            "reason": "발급 완료 추정, RA 추출 실패 — 수동 확인 필요",
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _error_row(container: str, reason: str) -> dict:
        return {
            "container_no": (container or "").strip().upper(),
            "available": False,
            "depot": None,
            "booking_ref": None,
            "over_caps": None,
            "close_date": None,
            "reason": reason,
        }

    async def _dismiss_cookie_banner_once(self):
        if self._cookie_dismissed:
            return
        for sel in (
            '#tarteaucitronAllAllowed',
            '#tarteaucitronPersonalize2',
            '.tarteaucitronCTAButton.tarteaucitronAllow',
        ):
            try:
                btn = await self.page.query_selector(sel)
                if btn:
                    await btn.click(timeout=2_000)
                    await asyncio.sleep(0.3)
                    self._cookie_dismissed = True
                    return
            except Exception:
                continue

    async def _set_city(self, city_code: str) -> dict:
        return await self.page.evaluate(
            """(target) => {
                const sel = document.getElementById('app_front_off_hire_filter_city');
                if (!sel) return { ok: false, error: 'select not found' };
                const opt = Array.from(sel.options).find(o => o.value === target);
                if (!opt) return { ok: false, error: 'option not found for ' + target };
                sel.value = opt.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                if (sel.tomselect) { sel.tomselect.setValue(opt.value); }
                return { ok: true, value: opt.value, text: opt.text };
            }""",
            city_code,
        )

    async def _read_first_result_row(self) -> str | None:
        """Search 결과 테이블 첫 행의 Depot 셀(거부 메시지) 추출."""
        try:
            cells = self.page.locator("table tbody tr").first.locator("td")
            if await cells.count() < 2:
                return None
            return " ".join((await cells.nth(1).inner_text()).split())
        except Exception:
            return None

    async def _parse_modal_table(self, heading_substr: str, exclude_substr: str | None = None) -> dict[str, str]:
        """모달 내 'can be off hire' / 'cannot be off hire' 다음 테이블 파싱.
        반환: { container_upper: 다음 열 텍스트(depot 또는 reason) }"""
        result: dict[str, str] = {}
        try:
            data = await self.page.evaluate(
                """(args) => {
                    const [needle, exclude] = args;
                    const root = document.querySelector('.modal.show, .modal.in, .modal[style*="display: block"]') || document;
                    const headings = Array.from(root.querySelectorAll('div, p, h1, h2, h3, h4, h5, h6'));
                    const match = headings.find(e => {
                        const t = (e.innerText || '').toLowerCase();
                        if (!t.includes(needle.toLowerCase())) return false;
                        if (exclude && t.includes(exclude.toLowerCase())) return false;
                        return true;
                    });
                    if (!match) return [];
                    let sibling = match.nextElementSibling;
                    while (sibling && sibling.tagName !== 'TABLE') sibling = sibling.nextElementSibling;
                    if (!sibling) return [];
                    return Array.from(sibling.querySelectorAll('tbody tr'))
                        .filter(tr => tr.querySelector('td'))
                        .map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim()));
                }""",
                [heading_substr, exclude_substr],
            )
            for row in data:
                if len(row) < 2:
                    continue
                cont = row[0].strip().upper()
                value = " ".join(row[1].split())
                if cont:
                    result[cont] = value
        except Exception as exc:
            logger.warning("GOLD _parse_modal_table(%r): %s", heading_substr, exc)
        return result

    async def _click_modal_confirm(self) -> bool:
        try:
            btn = self.page.locator(
                '.modal.show a.btn_valider.confirm, .modal.in a.btn_valider.confirm'
            ).first
            if await btn.count() == 0:
                btn = self.page.locator('a.btn_valider.confirm').first
            if await btn.count() == 0:
                return False
            await btn.click()
            return True
        except Exception as exc:
            logger.warning("GOLD _click_modal_confirm: %s", exc)
            return False

    async def _lookup_history(self, container: str) -> dict | None:
        """/off-hire/history 에서 컨테이너에 매칭되는 행 추출 (최신=상단)."""
        try:
            await self.page.goto(HISTORY_URL, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(1.5)
            rows = await self.page.evaluate(
                """() => Array.from(document.querySelectorAll('table tbody tr'))
                    .filter(tr => tr.querySelector('td'))
                    .map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim()))"""
            )
            container_u = container.upper()
            # 컬럼: [RA, Period, Depot, Contract, Container]
            for row in rows:
                if len(row) >= 5 and row[4].upper() == container_u:
                    return {
                        "ra":     row[0],
                        "period": row[1],
                        "depot":  row[2],
                    }
        except Exception as exc:
            logger.warning("GOLD _lookup_history: %s", exc)
        return None
