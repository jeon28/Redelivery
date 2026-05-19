import asyncio
import logging
import os
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright

from scrapers.base import BaseScraper
from config.credentials import get_credential

logger = logging.getLogger(__name__)

PORTAL_URL = "https://tex.textainer.com/Customer/CustomerMenu.aspx"

# Playwright storage_state 저장 디렉토리 (쿠키 + localStorage).
# 회사별로 파일 분리, Railway Volume `/data/` 같은 영구 디스크에 두어야
# 워커 재시작 후에도 세션이 유지됨. FLOR와 같은 디렉토리, prefix만 다름.
TEXA_SESSION_DIR = Path(os.getenv("TEXA_SESSION_DIR", "/data"))


def _session_file_for(company: str) -> Path:
    suffix = {"장금상선": "SK", "흥아라인": "HA"}.get(company, "OTHER")
    return TEXA_SESSION_DIR / f"texa_session_{suffix}.json"


REGION_MAP = {
    "INCHON": {"country": "KOREA", "city": "INCHON"},
    "BUSAN":  {"country": "KOREA", "city": "PUSAN"},  # TEXA 사이트는 옛 표기 PUSAN
    "GWANGYANG": {"country": "KOREA", "city": "GWANGYANG"},
}

# TEXA depot code → 한글/영문 풀네임 매핑.
# 신규 depot 발견 시 여기에 추가하면 결과 표시가 자동으로 풀네임으로 바뀜.
DEPOT_NAMES = {
    "INC05": "INC05 - SEUNG JIN ENTERPRISES",
}


def _depot_with_name(code: str) -> str:
    """depot code에 풀네임이 매핑되어 있으면 'CODE - NAME'으로, 없으면 코드 그대로."""
    if not code:
        return code
    return DEPOT_NAMES.get(code.strip(), code.strip())


class TexaScraper(BaseScraper):
    def __init__(self, company: str, lessor: str):
        super().__init__(company, lessor)
        self.cred = get_credential(company, lessor)
        # storage_state 적용을 위해 context를 직접 보관 (base.py는 page만 보유)
        self.context = None

    # ------------------------------------------------------------------ #
    # Browser start — storage_state 복원으로 로그인 빈도 최소화                  #
    # ------------------------------------------------------------------ #

    async def start(self, headless: bool = True):
        """저장된 storage_state가 있으면 복원해 브라우저 컨텍스트를 만든다."""
        browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
        if browsers_path:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

        self._playwright = await async_playwright().start()
        # --no-sandbox / --disable-dev-shm-usage: Chromium in Docker
        self.browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        sess = _session_file_for(self.company)
        storage_arg = str(sess) if sess.exists() else None
        if storage_arg:
            logger.info("TEXA(%s): storage_state 복원 시도 %s", self.company, sess)

        self.context = await self.browser.new_context(storage_state=storage_arg)
        self.page = await self.context.new_page()

    # ------------------------------------------------------------------ #
    # Login                                                                #
    # ------------------------------------------------------------------ #

    async def login(self) -> bool:
        """
        저장된 storage_state가 있으면 portal 직접 진입으로 유효성부터 확인.
        - portal URL로 goto했을 때 tex.textainer.com 도메인에 머물면 OK.
        - 만료/누락이면 _fresh_login → _save_session.
        """
        sess = _session_file_for(self.company)
        if sess.exists():
            try:
                await self.page.goto(
                    PORTAL_URL, wait_until="domcontentloaded", timeout=20_000
                )
                # 짧은 대기 후 URL 도메인 확인
                try:
                    await self.page.wait_for_function(
                        "window.location.href.includes('tex.textainer.com')",
                        timeout=5_000,
                    )
                except Exception:
                    pass
                if "tex.textainer.com" in self.page.url:
                    await asyncio.sleep(2)  # frameset 안정화
                    logger.info(
                        "TEXA(%s): existing session valid → skip login (%s)",
                        self.company, self.page.url,
                    )
                    return True
                logger.info(
                    "TEXA(%s): stored session expired → fresh login (%s)",
                    self.company, self.page.url,
                )
            except Exception as exc:
                logger.info(
                    "TEXA(%s): session check failed → fresh login: %s",
                    self.company, exc,
                )

        ok = await self._fresh_login()
        if ok:
            await self._save_session()
        return ok

    async def _save_session(self) -> None:
        sess = _session_file_for(self.company)
        try:
            sess.parent.mkdir(parents=True, exist_ok=True)
            await self.context.storage_state(path=str(sess))
            logger.info("TEXA(%s): storage_state 저장 %s", self.company, sess)
        except Exception as exc:
            logger.warning("TEXA(%s): storage_state 저장 실패: %s", self.company, exc)

    async def _fresh_login(self) -> bool:
        try:
            await self.page.goto(
                "https://www.textainer.com",
                wait_until="domcontentloaded",
                timeout=30_000,
            )

            # Open login modal — use JS click to bypass Foundation overlay intercept
            await self.page.evaluate(
                "document.querySelector('a[data-reveal-id]').click()"
            )
            await self.page.wait_for_selector("select", state="visible", timeout=10_000)

            # Select "Leasing Customer" (value = Customer_Desktop)
            await self.page.select_option("select", value="Customer_Desktop")

            # Fill credentials
            await self.page.get_by_label("Login Name").fill(self.cred["id"])
            await self.page.get_by_label("Password").fill(self.cred["pw"])

            # Submit
            await self.page.get_by_role("button", name="Login").click()

            # Wait for redirect to TEXA portal.
            # CustomerMenu.aspx is a frameset — wait_for_url hangs waiting
            # for load state on a frameset. Use wait_for_function instead.
            await self.page.wait_for_function(
                "window.location.href.includes('tex.textainer.com')",
                timeout=30_000,
            )
            await asyncio.sleep(3)  # Give frameset frames time to settle

            logger.info("TEXA fresh login OK: %s", self.page.url)
            return True

        except Exception as exc:
            logger.error("TEXA fresh login failed: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Navigation helpers                                                   #
    # ------------------------------------------------------------------ #

    async def _frame_containing(self, text: str):
        """Return the first frame whose content contains *text*."""
        for frame in self.page.frames:
            try:
                if await frame.locator(f"text={text}").count() > 0:
                    return frame
            except Exception:
                pass
        return None

    async def _navigate_to_redelivery(self):
        """Click Others → Request Redelivery in the portal menu."""
        for _ in range(3):
            for frame in self.page.frames:
                try:
                    # Try clicking "Others" to expand sub-menu first
                    others = frame.get_by_text("Others", exact=True)
                    if await others.count() > 0:
                        await others.click()
                        await asyncio.sleep(0.5)

                    redeliv = frame.get_by_text("Request Redelivery", exact=False)
                    if await redeliv.count() > 0:
                        await redeliv.first.click()
                        await asyncio.sleep(2)
                        logger.info("Navigated to Request Redelivery")
                        return
                except Exception:
                    pass
            await asyncio.sleep(1)

        raise RuntimeError("Cannot navigate to Request Redelivery")

    # ------------------------------------------------------------------ #
    # Form-filling helpers                                                 #
    # ------------------------------------------------------------------ #

    async def _select_containing(self, frame, nth: int, text: str):
        """Select the option whose label contains *text* from the nth <select>."""
        sel = frame.locator("select").nth(nth)
        options = await sel.locator("option").all()
        for opt in options:
            opt_text = await opt.inner_text()
            if text.upper() in opt_text.upper():
                value = await opt.get_attribute("value")
                await sel.select_option(value=value)
                return
        raise RuntimeError(f"No <select>[{nth}] option containing '{text}'")

    # ------------------------------------------------------------------ #
    # Field-extraction helpers (booking detail page)                      #
    # ------------------------------------------------------------------ #

    async def _extract_field(self, frame, label: str) -> str:
        """Find *label* in any <tr> and return the text of the next <td>."""
        try:
            rows = frame.locator("tr")
            count = await rows.count()
            for i in range(count):
                row_text = await rows.nth(i).inner_text()
                if label not in row_text:
                    continue
                cells = rows.nth(i).locator("td")
                cell_count = await cells.count()
                for j in range(cell_count):
                    cell_text = (await cells.nth(j).inner_text()).strip()
                    if label in cell_text and j + 1 < cell_count:
                        value = (await cells.nth(j + 1).inner_text()).strip()
                        if value:
                            return value
        except Exception as exc:
            logger.warning("_extract_field '%s': %s", label, exc)
        return ""

    async def _extract_assigned_containers(self, frame) -> list[str]:
        """Return container IDs from the 'Assigned Containers' table."""
        containers: list[str] = []
        try:
            tables = frame.locator("table")
            table_count = await tables.count()
            # Scan from last table backwards to find the equipment table
            for t in range(table_count - 1, -1, -1):
                tbl = tables.nth(t)
                tbl_text = await tbl.inner_text()
                if "Equipment ID" in tbl_text or "Eqp" in tbl_text:
                    rows = tbl.locator("tr")
                    row_count = await rows.count()
                    for i in range(1, row_count):
                        cells = rows.nth(i).locator("td")
                        if await cells.count() >= 1:
                            eq_id = (await cells.nth(0).inner_text()).strip()
                            if len(eq_id) >= 10:          # typical container ID length
                                containers.append(eq_id)
                    break
        except Exception as exc:
            logger.warning("_extract_assigned_containers: %s", exc)
        return containers

    # ------------------------------------------------------------------ #
    # Main query                                                           #
    # ------------------------------------------------------------------ #

    async def query(self, containers: list[str], region: str, depot: str | None = None) -> list[dict]:
        # depot 인자는 향후 사용자 명시 depot용 슬롯. TEXA는 현재 미사용.
        _ = depot
        region_info = REGION_MAP.get(region, REGION_MAP["INCHON"])

        results: dict[str, dict] = {
            cno: {
                "container_no": cno,
                "available": False,
                "depot": None,
                "booking_ref": None,
                "over_caps": None,
                "close_date": None,
                "reason": None,
            }
            for cno in containers
        }

        # Preview 응답에서 세 case 중 하나라도 매칭됐는지 추적.
        # 셋 다 미매칭이면 세션 만료/사이트 변경 가능성을 사용자에게 안내.
        preview_matched = False

        try:
            try:
                await self._navigate_to_redelivery()
            except Exception as exc:
                logger.error("Navigate to Request Redelivery failed: %s", exc)
                self._fill_reason(results, "TEXA 포털 메뉴 진입 실패 (사이트 응답 지연 가능)")
                return list(results.values())
            await asyncio.sleep(3)

            # ── Find the frame that holds the redelivery form ──────────
            form_frame = await self._frame_containing("Country")
            if form_frame is None:
                logger.error("Cannot find redelivery form frame")
                self._fill_reason(results, "반납 신청 화면 로드 실패")
                return list(results.values())
            logger.info("Form frame: %s", form_frame.url)

            # ── Fill Country / City dropdowns ──────────────────────────
            try:
                await self._select_containing(form_frame, 0, region_info["country"])
                await asyncio.sleep(3)   # wait for ASP.NET postback → city options
                await self._select_containing(form_frame, 1, region_info["city"])
                await asyncio.sleep(1)
            except Exception as exc:
                logger.error("Region dropdown select failed: %s", exc)
                self._fill_reason(results, "지역 선택 실패 (사이트 UI 변경 가능)")
                return list(results.values())

            # ── Container IDs ─────────────────────────────────────────
            await form_frame.locator("textarea").fill("\n".join(containers))

            # ── Equipment Query radio ──────────────────────────────────
            eq_radio = form_frame.get_by_label("Equipment Query")
            if await eq_radio.count() > 0:
                await eq_radio.check()

            # ── Preview ───────────────────────────────────────────────
            logger.info("Clicking Preview...")
            await form_frame.get_by_role("button", name="Preview").click()
            await asyncio.sleep(5)
            page_text = await form_frame.inner_text("body")
            page_text_lower = page_text.lower()
            logger.info("Preview done. page snippet: %s", page_text[800:1200])

            list_url = form_frame.url  # baseline URL to return to after detail visits

            # ── Case 1: cannot be redelivered ─────────────────────────
            if "cannot be redelivered" in page_text_lower:
                preview_matched = True
                logger.info("Found: cannot be redelivered")
                try:
                    # Find the first <table> that follows the heading text
                    cannot_tbl = form_frame.locator(
                        "text=cannot be redelivered"
                    ).first.locator("xpath=following::table[1]")
                    rows = cannot_tbl.locator("tr")
                    row_count = await rows.count()
                    # Log header row for diagnostics
                    if row_count > 0:
                        hdr = (await rows.nth(0).inner_text()).strip()
                        logger.info("Cannot-redeliver table header: %s", hdr)
                    for i in range(1, row_count):
                        cells = rows.nth(i).locator("td")
                        n = await cells.count()
                        if n < 2:
                            continue
                        eqp_cell = (await cells.nth(0).inner_text()).strip()
                        reason   = (await cells.nth(1).inner_text()).strip()
                        # A single cell may contain multiple IDs separated by newlines.
                        # TEXA sometimes omits the check digit (10 chars), so match
                        # by exact OR by the result key starting with the extracted ID.
                        for raw in eqp_cell.splitlines():
                            eqp = self._norm_eqp(raw.strip())
                            if not eqp:
                                continue
                            logger.info("Cannot-redeliver: eqp=%s reason=%s", eqp, reason)
                            match_key = self._find_result_key(results, eqp)
                            if match_key:
                                results[match_key]["reason"] = reason
                except Exception as exc:
                    logger.error("Cannot-redeliver parse error: %s", exc)

            # ── Case 2: can be booked (new booking) ───────────────────
            if "can be booked" in page_text_lower:
                preview_matched = True
                logger.info("Found: can be booked")
                checkboxes = form_frame.locator("input[type='checkbox']")
                cb_count = await checkboxes.count()
                for i in range(cb_count):
                    cb = checkboxes.nth(i)
                    if not await cb.is_checked():
                        await cb.check()

                await form_frame.get_by_role("button", name="Book").click()
                await asyncio.sleep(5)

                await self._collect_and_visit_bookings(form_frame, results, list_url)

            # ── Case 3: already booked ─────────────────────────────────
            if "are booked" in page_text_lower:
                preview_matched = True
                logger.info("Found: already booked")
                await self._parse_booked_table(form_frame, results, region_info["city"])

            if not preview_matched:
                logger.error("Preview page matched none of the 3 known cases")
                self._fill_reason(
                    results,
                    "Preview 응답 해석 불가 (세션 만료 또는 사이트 변경 의심)",
                )

        except Exception as exc:
            logger.error("TEXA query error: %s", exc)
            self._fill_reason(results, f"TEXA 조회 오류: {type(exc).__name__}")

        # 어떤 테이블에도 등장하지 않은 컨테이너: 사이트에 정보 없음으로 단정
        for r in results.values():
            if not r.get("available") and r["reason"] is None:
                r["reason"] = "임대사 시스템에 해당 컨테이너 정보 없음"

        return list(results.values())

    # ------------------------------------------------------------------ #
    # Already-booked table parser (no navigation needed)                  #
    # ------------------------------------------------------------------ #

    async def _parse_booked_table(self, frame, results: dict, city: str):
        """
        Parse 'already booked' preview page.

        Step 1: Eqp ID table  → (eqp_id, bk_ref, depot) list
        Step 2: Booking Reference Search results table (city-filtered)
                → bk_caps[bk_ref] = Booked − Moved  AND  bk_close[bk_ref]
                Only today's bookings appear; older ones are absent.
        Step 3: Populate results.
                If bk_ref absent from step 2 → assume available=True
                ("Can be deleted" label implies returnable slot exists).
        """
        try:
            # ── Step 1: container → (bk_ref, depot) from Eqp ID table ─────────
            container_rows: list[tuple[str, str, str]] = []  # (eqp_id, bk_ref, depot)
            bk_close: dict[str, str] = {}
            try:
                eqp_id_th = frame.locator("th").filter(
                    has_text=re.compile(r"^\s*Eqp ID\s*$")
                ).first
                eqp_tbl   = eqp_id_th.locator("xpath=ancestor::table[1]")
                if await eqp_tbl.count() > 0:
                    e_rows  = eqp_tbl.locator("tr")
                    e_count = await e_rows.count()
                    for i in range(1, e_count):
                        cells = e_rows.nth(i).locator("td")
                        n = await cells.count()
                        if n < 3:
                            continue
                        bk_ref = (await cells.nth(0).inner_text()).strip()
                        eqp_id = self._norm_eqp((await cells.nth(1).inner_text()).strip())
                        depot  = (await cells.nth(4).inner_text()).strip() if n > 4 else ""
                        match_key = self._find_result_key(results, eqp_id)
                        if match_key:
                            container_rows.append((match_key, bk_ref, depot))
                            logger.info("EqpID row: %s → %s depot=%s", match_key, bk_ref, depot)
            except Exception as exc:
                logger.warning("Eqp ID table parse failed: %s", exc)

            # ── Step 2: Caps Left from Booking Reference Search results ──────────
            # The "Booking Reference Search" table shows currently-open bookings
            # with Booked/Moved counts (Caps Left = Booked − Moved).
            # Bookings older than today's default date filter won't appear here.
            # For those missing bookings, we fall back to "available by default"
            # because presence in "Containers are booked (Can be deleted)"
            # implies at least one returnable slot exists.
            bk_caps: dict[str, int] = {}  # bk_ref → Caps Left (if determinable)
            try:
                spec_th_caps = frame.locator("th").filter(
                    has_text=re.compile(r"^\s*Spec Bill\s*$")
                ).first
                bk_ref_tbl = spec_th_caps.locator("xpath=ancestor::table[1]")
                if await bk_ref_tbl.count() > 0:
                    bk_rows  = bk_ref_tbl.locator("tr")
                    bk_count = await bk_rows.count()
                    hdr_cells = bk_rows.nth(0).locator("th, td")
                    headers = [
                        (await hdr_cells.nth(i).inner_text()).strip()
                        for i in range(await hdr_cells.count())
                    ]

                    def col(kw):
                        return next((i for i, h in enumerate(headers) if kw.lower() in h.lower()), -1)
                    def col_exact(kw):
                        return next((i for i, h in enumerate(headers) if h.strip() == kw), -1)

                    i_bk     = col("Bk Ref")
                    i_city   = col("City")
                    i_booked = col_exact("Booked")
                    i_moved  = col_exact("Moved")
                    i_date   = col("Close Date")

                    for i in range(1, bk_count):
                        cells = bk_rows.nth(i).locator("td")
                        n = await cells.count()
                        if n < 5 or i_bk < 0:
                            continue
                        bk_ref   = (await cells.nth(i_bk).inner_text()).strip()
                        row_city = (await cells.nth(i_city).inner_text()).strip() if 0 <= i_city < n else ""
                        if city.upper() not in row_city.upper():
                            continue
                        try:
                            booked = int((await cells.nth(i_booked).inner_text()).strip()) if 0 <= i_booked < n else 0
                            moved  = int((await cells.nth(i_moved).inner_text()).strip())  if 0 <= i_moved  < n else 0
                        except ValueError:
                            booked, moved = 0, 0
                        caps = booked - moved
                        bk_caps[bk_ref] = caps
                        # Also collect close_date here
                        close_dt = (await cells.nth(i_date).inner_text()).strip() if 0 <= i_date < n else ""
                        bk_close[bk_ref] = close_dt
                    logger.info("Caps from BkRefSearch: %s", bk_caps)
            except Exception as exc:
                logger.warning("BkRef caps lookup failed: %s", exc)

            # ── Step 3: populate results ───────────────────────────────────────
            # over_caps = Caps Left from BkRef Search if available.
            # If not in search results (e.g. booking pre-dates today's filter),
            # "Can be deleted" label implies a returnable slot → available=True.
            for eqp_id, bk_ref, depot in container_rows:
                if bk_ref in bk_caps:
                    caps_left = bk_caps[bk_ref]
                    available = caps_left > 0
                    reason    = None if available else "당월 반납분 소진"
                else:
                    caps_left = None   # unknown — not in search results
                    available = True   # "Can be deleted" → slot exists
                    reason    = None
                close_date = bk_close.get(bk_ref, "")
                results[eqp_id].update({
                    "available":   available,
                    "depot":       _depot_with_name(depot),
                    "booking_ref": bk_ref,
                    "over_caps":   caps_left,
                    "close_date":  close_date,
                    "reason":      reason,
                })
                logger.info("Result %s → %s depot=%s caps=%s avail=%s",
                            eqp_id, bk_ref, depot, caps_left, available)

        except Exception as exc:
            logger.error("_parse_booked_table: %s", exc)

    # ------------------------------------------------------------------ #
    # Shared booking-detail visitor (for newly-created "can be booked")   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _norm_eqp(texa_id: str) -> str:
        """TEMU790765-8  →  TEMU7907658  (remove TEXA check-digit dash)."""
        return texa_id.replace("-", "")

    @staticmethod
    def _fill_reason(results: dict, reason: str) -> None:
        """reason이 아직 비어있는 항목 전체에 동일 사유 채움."""
        for r in results.values():
            if r["reason"] is None:
                r["reason"] = reason

    @staticmethod
    def _find_result_key(results: dict, eqp_id: str) -> str | None:
        """
        사용자 입력 키와 TEXA 반환 ID 사이의 체크디짓 누락을 양방향으로 흡수.
        예: 입력 'TEMU790765' / TEXA 'TEMU7907658' 둘 다 매칭.
        """
        if not eqp_id:
            return None
        if eqp_id in results:
            return eqp_id
        for k in results:
            if k.startswith(eqp_id) or eqp_id.startswith(k):
                return k
        return None

    # ------------------------------------------------------------------ #
    # Cancel flow (ANALYSIS.md "취소(Cancel) 흐름" 그대로 구현)            #
    # ------------------------------------------------------------------ #

    async def cancel(self, items: list[dict], region: str) -> list[dict]:
        region_info = REGION_MAP.get(region, REGION_MAP["INCHON"])

        # booking_ref 별 그룹핑 (입력 순서 보존을 위해 별도 order 리스트 유지)
        groups: dict[str, list[str]] = {}
        order: list[tuple[str, str]] = []
        for it in items:
            cn = it["container_no"]
            bk = it["booking_ref"]
            groups.setdefault(bk, []).append(cn)
            order.append((cn, bk))

        outcomes: dict[tuple[str, str], tuple[bool, str | None]] = {}

        for bk_ref, containers in groups.items():
            try:
                group_outcome = await self._cancel_group(region_info, bk_ref, containers)
            except Exception as exc:
                logger.error("Cancel group %s error: %s", bk_ref, exc)
                group_outcome = {cn: (False, f"오류: {exc}") for cn in containers}
            for cn in containers:
                outcomes[(cn, bk_ref)] = group_outcome.get(cn, (False, "처리 결과 미확인"))

        out: list[dict] = []
        for cn, bk in order:
            ok, reason = outcomes[(cn, bk)]
            out.append({
                "container_no": cn,
                "booking_ref": bk,
                "cancelled": ok,
                "reason": None if ok else reason,
            })
        return out

    async def _cancel_group(
        self, region_info: dict, bk_ref: str, containers: list[str]
    ) -> dict[str, tuple[bool, str | None]]:
        """단일 booking_ref 그룹을 1회 Preview → 체크 → X → Yes 로 처리."""
        await self._navigate_to_redelivery()
        await asyncio.sleep(3)

        form_frame = await self._frame_containing("Country")
        if form_frame is None:
            return {cn: (False, "폼 화면 진입 실패") for cn in containers}

        await self._select_containing(form_frame, 0, region_info["country"])
        await asyncio.sleep(3)
        await self._select_containing(form_frame, 1, region_info["city"])
        await asyncio.sleep(1)

        await form_frame.locator("textarea").fill("\n".join(containers))

        eq_radio = form_frame.get_by_label("Equipment Query")
        if await eq_radio.count() > 0:
            await eq_radio.check()

        logger.info("Cancel[%s]: Preview…", bk_ref)
        await form_frame.get_by_role("button", name="Preview").click()
        await asyncio.sleep(5)

        page_text_lower = (await form_frame.inner_text("body")).lower()
        if "can be deleted" not in page_text_lower:
            logger.warning("Cancel[%s]: 'Can be deleted' 패널 미노출", bk_ref)
            return {cn: (False, "이미 취소되었거나 예약 없음") for cn in containers}

        panel_heading = form_frame.locator("text=Containers are booked").first
        panel_table = panel_heading.locator("xpath=following::table[1]")
        if await panel_table.count() == 0:
            return {cn: (False, "취소 패널 테이블 미발견") for cn in containers}

        norm_to_orig = {self._norm_eqp(cn): cn for cn in containers}
        matched: set[str] = set()

        rows = panel_table.locator("tr")
        row_count = await rows.count()
        for i in range(row_count):
            cells = rows.nth(i).locator("td")
            if await cells.count() < 2:
                continue
            row_bk = (await cells.nth(0).inner_text()).strip()
            row_eqp = self._norm_eqp((await cells.nth(1).inner_text()).strip())
            if row_bk != bk_ref or row_eqp not in norm_to_orig:
                continue
            row_cb = rows.nth(i).locator("input[type='checkbox']")
            if await row_cb.count() == 0:
                continue
            await row_cb.first.check()
            matched.add(norm_to_orig[row_eqp])
            logger.info("Cancel[%s]: 행 체크 Eqp=%s", bk_ref, row_eqp)

        if not matched:
            return {cn: (False, "사이트에서 해당 컨테이너 행 미발견") for cn in containers}

        if not await self._click_delete_x(form_frame, panel_table):
            return {cn: (False, "삭제(X) 버튼 미발견") for cn in containers}
        await asyncio.sleep(1)

        if not await self._click_confirm_yes(form_frame):
            return {cn: (False, "확인 다이얼로그 처리 실패") for cn in containers}
        await asyncio.sleep(5)

        return await self._verify_cancel_result(
            form_frame, bk_ref, containers, matched, norm_to_orig
        )

    async def _click_delete_x(self, frame, panel_table) -> bool:
        """패널 우하단 빨간 X(삭제) 버튼 클릭. 다양한 셀렉터를 순차 시도."""
        candidates = [
            panel_table.locator("img[src*='delete' i]"),
            panel_table.locator("img[src*='cancel' i]"),
            panel_table.locator("img[src*='_x' i]"),
            panel_table.locator("input[type='image']"),
            panel_table.locator("a[onclick*='delete' i]"),
            panel_table.locator("a[onclick*='remove' i]"),
            frame.locator("img[title='Delete']"),
            frame.locator("img[alt*='Delete' i]"),
            frame.locator("input[type='image'][src*='delete' i]"),
        ]
        for loc in candidates:
            try:
                if await loc.count() > 0:
                    await loc.first.click()
                    logger.info("Cancel: X(delete) 버튼 클릭")
                    return True
            except Exception as exc:
                logger.debug("X locator 시도 실패: %s", exc)
        return False

    async def _click_confirm_yes(self, frame) -> bool:
        """in-page Confirm Box 의 [Yes] 버튼 클릭."""
        candidates = [
            frame.get_by_role("button", name="Yes"),
            frame.locator("input[type='button'][value='Yes']"),
            frame.locator("input[type='submit'][value='Yes']"),
            frame.locator("button:has-text('Yes')"),
            frame.locator("a:has-text('Yes')"),
        ]
        for loc in candidates:
            try:
                if await loc.count() > 0:
                    await loc.first.click()
                    logger.info("Cancel: Confirm [Yes] 클릭")
                    return True
            except Exception as exc:
                logger.debug("Yes locator 시도 실패: %s", exc)
        return False

    async def _verify_cancel_result(
        self,
        frame,
        bk_ref: str,
        containers: list[str],
        matched: set[str],
        norm_to_orig: dict[str, str],
    ) -> dict[str, tuple[bool, str | None]]:
        """취소 직후 화면을 재검사해 컨테이너별 성공/실패 판정."""
        body_text = (await frame.inner_text("body")).lower()
        outcome: dict[str, tuple[bool, str | None]] = {}

        if "can be booked" in body_text and "can be deleted" not in body_text:
            for cn in containers:
                outcome[cn] = (True, None) if cn in matched else (False, "사이트에서 해당 컨테이너 행 미발견")
            logger.info("Cancel[%s]: 전체 성공 (can be booked 전환)", bk_ref)
            return outcome

        if "can be deleted" in body_text:
            remaining: set[str] = set()
            try:
                heading = frame.locator("text=Containers are booked").first
                table = heading.locator("xpath=following::table[1]")
                rows = table.locator("tr")
                row_count = await rows.count()
                for i in range(row_count):
                    cells = rows.nth(i).locator("td")
                    if await cells.count() < 2:
                        continue
                    row_eqp = self._norm_eqp((await cells.nth(1).inner_text()).strip())
                    if row_eqp in norm_to_orig:
                        remaining.add(norm_to_orig[row_eqp])
            except Exception as exc:
                logger.warning("Cancel[%s]: 잔존 행 스캔 실패: %s", bk_ref, exc)

            for cn in containers:
                if cn not in matched:
                    outcome[cn] = (False, "사이트에서 해당 컨테이너 행 미발견")
                elif cn in remaining:
                    outcome[cn] = (False, "사이트에서 취소되지 않음")
                else:
                    outcome[cn] = (True, None)
            logger.info("Cancel[%s]: 부분 결과 — 잔존 %s", bk_ref, remaining)
            return outcome

        logger.warning("Cancel[%s]: 결과 화면 판정 불가", bk_ref)
        return {cn: (False, "취소 결과 확인 불가") for cn in containers}

    async def _collect_and_visit_bookings(
        self, frame, results: dict, list_url: str
    ):
        """Find all TKE booking ref links, visit each detail page, update results."""
        bk_links = frame.locator("a").filter(has_text="TKE")
        bk_count = await bk_links.count()

        # Collect ref texts only (hrefs are javascript: postbacks, unusable for goto)
        booking_refs: list[str] = []
        for i in range(bk_count):
            ref_text = (await bk_links.nth(i).inner_text()).strip()
            booking_refs.append(ref_text)

        logger.info("Booking refs to visit: %s", booking_refs)

        remaining = set(results.keys())  # stop early once all containers resolved

        for booking_ref in booking_refs:
            if not remaining:
                break
            try:
                # Re-find the link each time (postback rewrites the DOM)
                link = frame.locator("a").filter(has_text=booking_ref).first
                await link.click()
                await asyncio.sleep(3)  # wait for ASP.NET postback to render

                depot_name = await self._extract_field(frame, "Depot Name")
                over_caps  = await self._extract_field(frame, "Over Caps")
                close_date = await self._extract_field(frame, "Ant Close Date")
                assigned   = await self._extract_assigned_containers(frame)

                logger.info(
                    "Booking %s → depot=%s over_caps=%s containers=%s",
                    booking_ref, depot_name, over_caps, assigned,
                )

                for raw_cno in assigned:
                    cno = self._norm_eqp(raw_cno)
                    if cno in results:
                        results[cno].update({
                            "available": True,
                            "depot": _depot_with_name(depot_name),
                            "booking_ref": booking_ref,
                            "over_caps": over_caps,
                            "close_date": close_date,
                            "reason": None,
                        })
                        remaining.discard(cno)

                # Go back to the booking-list page via browser history
                await frame.evaluate("history.back()")
                await asyncio.sleep(2)

            except Exception as exc:
                logger.error("Booking %s detail error: %s", booking_ref, exc)
                try:
                    await frame.evaluate("history.back()")
                    await asyncio.sleep(1)
                except Exception:
                    pass
