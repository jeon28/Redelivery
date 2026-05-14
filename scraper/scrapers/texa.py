import asyncio
import logging
import re
from urllib.parse import urljoin

from scrapers.base import BaseScraper
from config.credentials import get_credential

logger = logging.getLogger(__name__)

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

    # ------------------------------------------------------------------ #
    # Login                                                                #
    # ------------------------------------------------------------------ #

    async def login(self) -> bool:
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

            logger.info("TEXA login OK: %s", self.page.url)
            return True

        except Exception as exc:
            logger.error("TEXA login failed: %s", exc)
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

    async def query(self, containers: list[str], region: str) -> list[dict]:
        region_info = REGION_MAP.get(region, REGION_MAP["INCHON"])

        results: dict[str, dict] = {
            cno: {
                "container_no": cno,
                "available": False,
                "depot": None,
                "booking_ref": None,
                "over_caps": None,
                "close_date": None,
                "reason": "조회 실패",
            }
            for cno in containers
        }

        try:
            await self._navigate_to_redelivery()
            await asyncio.sleep(3)

            # ── Find the frame that holds the redelivery form ──────────
            form_frame = await self._frame_containing("Country")
            if form_frame is None:
                logger.error("Cannot find redelivery form frame")
                return list(results.values())
            logger.info("Form frame: %s", form_frame.url)

            # ── Fill Country dropdown ──────────────────────────────────
            await self._select_containing(form_frame, 0, region_info["country"])
            await asyncio.sleep(3)   # wait for ASP.NET postback → city options

            # ── Fill City dropdown ─────────────────────────────────────
            await self._select_containing(form_frame, 1, region_info["city"])
            await asyncio.sleep(1)

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
                            for cno in list(results.keys()):
                                if cno == eqp or cno.startswith(eqp):
                                    results[cno]["reason"] = reason
                except Exception as exc:
                    logger.error("Cannot-redeliver parse error: %s", exc)

            # ── Case 2: can be booked (new booking) ───────────────────
            if "can be booked" in page_text_lower:
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
                logger.info("Found: already booked")
                await self._parse_booked_table(form_frame, results, region_info["city"])

        except Exception as exc:
            logger.error("TEXA query error: %s", exc)

        # 불가(available=False)인데 사유가 비어 있으면 안전장치로 기본 사유 채움
        for r in results.values():
            if not r.get("available") and not r.get("reason"):
                r["reason"] = "조회 실패 (사유 미상)"

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
                        if eqp_id in results:
                            container_rows.append((eqp_id, bk_ref, depot))
                            logger.info("EqpID row: %s → %s depot=%s", eqp_id, bk_ref, depot)
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
