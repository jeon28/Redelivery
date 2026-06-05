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
        # 로그인 실패 시 구체적 사유. base.py가 RuntimeError 메시지로 사용.
        self._login_error: str | None = None

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
                url = self.page.url
                url_low = url.lower()
                # 도메인이 맞아도 path가 로그인 마커를 포함하면 만료로 단정.
                # 예: tex.textainer.com/.../Login.aspx
                login_markers = ("login.aspx", "/login", "signin")
                is_login_page = any(m in url_low for m in login_markers)
                if "tex.textainer.com" in url_low and not is_login_page:
                    await asyncio.sleep(2)  # frameset 안정화
                    logger.info(
                        "TEXA(%s): existing session valid → skip login (%s)",
                        self.company, url,
                    )
                    return True
                logger.info(
                    "TEXA(%s): stored session expired → fresh login (%s)",
                    self.company, url,
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
        # 자격증명 사전 체크 — 빈 값이면 30초 대기 없이 즉시 실패
        if not self.cred.get("id") or not self.cred.get("pw"):
            self._login_error = f"TEXA 자격증명 미설정 ({self.company})"
            logger.error(self._login_error)
            return False

        # ① 메인 페이지 진입
        try:
            await self.page.goto(
                "https://www.textainer.com",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
        except Exception as exc:
            self._login_error = "TEXA 메인 페이지 진입 실패 (네트워크 또는 사이트 다운)"
            logger.error("%s: %s", self._login_error, exc)
            return False

        # ② 로그인 모달 열기 — JS click 으로 Foundation overlay intercept 우회
        try:
            await self.page.evaluate(
                "document.querySelector('a[data-reveal-id]').click()"
            )
            await self.page.wait_for_selector("select", state="visible", timeout=10_000)
        except Exception as exc:
            self._login_error = "TEXA 로그인 모달 열기 실패 (사이트 UI 변경 가능)"
            logger.error("%s: %s", self._login_error, exc)
            return False

        # ③ 사용자 유형 선택 (Leasing Customer = Customer_Desktop)
        try:
            await self.page.select_option("select", value="Customer_Desktop")
        except Exception as exc:
            self._login_error = "TEXA 사용자 유형 선택 실패"
            logger.error("%s: %s", self._login_error, exc)
            return False

        # ④ 자격증명 입력
        try:
            await self.page.get_by_label("Login Name").fill(self.cred["id"])
            await self.page.get_by_label("Password").fill(self.cred["pw"])
        except Exception as exc:
            self._login_error = "TEXA 로그인 양식 입력 필드 누락"
            logger.error("%s: %s", self._login_error, exc)
            return False

        # ⑤ Login 버튼 클릭
        try:
            await self.page.get_by_role("button", name="Login").click()
        except Exception as exc:
            self._login_error = "TEXA Login 버튼 클릭 실패"
            logger.error("%s: %s", self._login_error, exc)
            return False

        # ⑥ portal redirect 대기 (frameset 이므로 wait_for_url 대신 wait_for_function)
        try:
            await self.page.wait_for_function(
                "window.location.href.includes('tex.textainer.com')",
                timeout=30_000,
            )
            await asyncio.sleep(3)  # frameset frames 안정화
        except Exception as exc:
            self._login_error = (
                "TEXA 자격증명 거부됨 또는 사이트 응답 지연 (portal 진입 30초 timeout)"
            )
            logger.error("%s: %s (url=%s)", self._login_error, exc, self.page.url)
            return False

        logger.info("TEXA fresh login OK: %s", self.page.url)
        return True

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

    async def _select_region(self, frame, region_info: dict) -> None:
        """
        국가 → 도시 드롭다운을 순서대로 선택.

        국가(예: KOREA) 선택은 ASP.NET postback 을 유발해 도시 <select>[1] 옵션이
        전세계 목록(~456개)에서 해당 국가용(한국=7개)으로 재로딩된다. 고정 sleep 으로는
        느린 postback 에서 도시 선택이 stale/미갱신 상태와 겹쳐 'No option' 예외
        ('지역 선택 실패')가 간헐 발생하므로, 도시 옵션이 실제로 갱신될 때까지 대기한다.
        """
        await self._select_containing(frame, 0, region_info["country"])
        await self._wait_city_options(frame, region_info["city"])
        await self._select_containing(frame, 1, region_info["city"])
        await asyncio.sleep(1)

    async def _wait_city_options(self, frame, city: str, timeout_s: float = 15.0) -> bool:
        """
        국가 선택 postback 후 도시 <select>[1] 이 해당 국가용으로 좁혀지고(전세계 ~456개 →
        소수) 대상 도시가 나타날 때까지 폴링 대기. 준비되면 True.
        timeout 시 경고만 남기고 False — 호출부는 그대로 선택을 시도(best-effort).
        """
        steps = max(1, int(timeout_s / 0.5))
        for _ in range(steps):
            try:
                opts = await frame.locator("select").nth(1).locator("option").evaluate_all(
                    "els => els.map(e => e.textContent.trim())"
                )
                # 국가별로 좁혀졌고(<=60) 대상 도시가 존재하면 준비 완료
                if len(opts) <= 60 and any(city.upper() in o.upper() for o in opts):
                    return True
            except Exception:
                pass  # postback 중 detach 등 — 다음 루프에서 재확인
            await asyncio.sleep(0.5)
        logger.warning("도시 옵션 갱신 대기 timeout (city=%s) — 그대로 선택 시도", city)
        return False

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
                await self._select_region(form_frame, region_info)
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
            # Book(실 예약) 후, success 화면은 링크 목록이 아니라 메시지+빈 폼이므로
            # 동일 컨테이너로 재-Preview 하여 'already booked' 파서로 결과를 확정한다.
            booked_handled = False
            if "can be booked" in page_text_lower:
                preview_matched = True
                logger.info("Found: can be booked")
                await self._book_and_resolve(
                    form_frame, results, region_info, containers
                )
                booked_handled = True

            # ── Case 3: already booked ─────────────────────────────────
            # Case 2 가 실행되면 재-Preview 에서 이미 booked 테이블을 파싱했으므로
            # (그리고 form_frame 은 navigate 로 무효화됨) 중복 처리하지 않는다.
            if "are booked" in page_text_lower and not booked_handled:
                preview_matched = True
                logger.info("Found: already booked")
                stale = await self._parse_booked_table(
                    form_frame, results, region_info["city"]
                )
                # 과거 날짜 booking(오늘자 BkRefSearch 에 없음)은 Rebook 으로 갱신
                if stale:
                    await self._rebook_stale(
                        form_frame, results, region_info, containers, stale
                    )

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

    async def _parse_booked_table(
        self, frame, results: dict, city: str
    ) -> list[tuple[str, str]]:
        """
        Parse 'already booked' preview page.

        Step 1: Eqp ID table  → (eqp_id, bk_ref, depot) list
        Step 2: Booking Reference Search results table (city-filtered)
                → bk_caps[bk_ref] = Booked − Moved  AND  bk_close[bk_ref]
                Only today's bookings appear; older ones are absent.
        Step 3: Populate results.
                If bk_ref absent from step 2 → assume available=True
                ("Can be deleted" label implies returnable slot exists).

        Returns: 오늘자 BkRefSearch 에 없는(=과거 날짜) booking 행 목록
                 [(eqp_id, bk_ref)] — 호출측이 Rebook 트리거에 사용.
        """
        stale: list[tuple[str, str]] = []
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
                    stale.append((eqp_id, bk_ref))
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
        return stale

    # ------------------------------------------------------------------ #
    # Rebook flow — 과거 날짜 booking 을 R 버튼으로 갱신                   #
    # ------------------------------------------------------------------ #

    async def _rebook_stale(
        self,
        form_frame,
        results: dict,
        region_info: dict,
        containers: list[str],
        stale: list[tuple[str, str]],
    ):
        """
        'Containers are booked (Can be deleted or rebooked)' 패널에서
        오늘자 BkRefSearch 에 없는 과거 booking(만료 의심) 행을 Rebook 한다.

        ① 패널에서 해당 Eqp 행 체크 (postback 으로 R 버튼 enable)
        ② R(Rebook) 버튼 클릭 → Confirm [Yes] 가 뜨면 처리
        ③ 재-Preview → _parse_booked_table 로 새 Bk Ref/유효기간 확정
        실패 시 기존 결과(옛 Bk Ref, available=True)를 그대로 둔다.
        """
        stale_eqps = {self._norm_eqp(e) for e, _ in stale}
        logger.info("Rebook 대상(과거 booking): %s", stale)
        try:
            panel_heading = form_frame.locator("text=Containers are booked").first
            panel_table = panel_heading.locator("xpath=following::table[1]")
            if await panel_table.count() == 0:
                logger.warning("Rebook: booked 패널 테이블 미발견")
                return

            checked = 0
            rows = panel_table.locator("tr")
            row_count = await rows.count()
            for i in range(row_count):
                cells = rows.nth(i).locator("td")
                if await cells.count() < 2:
                    continue
                row_eqp = self._norm_eqp((await cells.nth(1).inner_text()).strip())
                if not any(
                    row_eqp.startswith(s) or s.startswith(row_eqp)
                    for s in stale_eqps
                ):
                    continue
                row_cb = rows.nth(i).locator("input[type='checkbox']")
                if await row_cb.count() == 0:
                    continue
                await row_cb.first.check()
                checked += 1
                logger.info("Rebook: 행 체크 Eqp=%s", row_eqp)

            if checked == 0:
                logger.warning("Rebook: 체크할 행 미발견 — 기존 결과 유지")
                return

            # 행 체크는 __doPostBack 유발 → R 버튼 enable 까지 대기
            await asyncio.sleep(3)

            if not await self._click_rebook_r(form_frame):
                logger.warning("Rebook: R 버튼 미발견 — 기존 결과 유지")
                return
            await asyncio.sleep(1)

            # 삭제(X)와 동일하게 Confirm Box 가 뜰 수 있음 — 없으면 그냥 진행
            await self._click_confirm_yes(form_frame)
            await asyncio.sleep(5)

            try:
                snippet = (await form_frame.inner_text("body"))[:300]
                logger.info("Rebook 후 화면 snippet: %s", snippet)
            except Exception:
                pass

            # 재-Preview 로 새 Bk Ref / 유효기간 / Caps 확정
            if not await self._reopen_and_parse_booked(
                results, region_info, containers
            ):
                logger.warning("Rebook 후 재-Preview 파싱 실패 — 기존 결과 유지")
        except Exception as exc:
            logger.error("Rebook 처리 오류: %s", exc)

    async def _click_rebook_r(self, frame) -> bool:
        """
        패널 우하단 R(Rebook) 버튼 클릭.

        실제 사이트 마크업: `<input type="image" title="Rebook" name="...btnRebook"
        src="../Images/buttons/Letter-R-icon.png">`. X(삭제)와 동일하게 행 체크
        전에는 disabled 이므로 enable 될 때까지 잠시 대기한 뒤 클릭한다.
        """
        candidates = [
            frame.locator("input[type='image'][title='Rebook']"),
            frame.locator("input[id$='btnRebook']"),
            frame.locator("input[name$='btnRebook']"),
            frame.locator("input[type='image'][src*='Letter-R-icon' i]"),
        ]
        for loc in candidates:
            try:
                if await loc.count() == 0:
                    continue
                btn = loc.first
                for _ in range(10):
                    if await btn.is_enabled():
                        break
                    await asyncio.sleep(0.5)
                await btn.click()
                logger.info("Rebook: R 버튼 클릭")
                return True
            except Exception as exc:
                logger.debug("R locator 시도 실패: %s", exc)
        return False

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

        await self._select_region(form_frame, region_info)

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

        # 행 체크는 __doPostBack 을 유발 → 패널이 재렌더되며 btnDelete 가 enable 된다.
        # postback 완료를 기다린 뒤(미대기 시 btnDelete 가 disabled 라 클릭 무시됨) 삭제 클릭.
        await asyncio.sleep(3)

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
        """
        패널 우하단 빨간 X(삭제) 버튼 클릭.

        실제 사이트 마크업: `<input type="image" title="Delete" name="...btnDelete"
        src="../Images/buttons/Letter-X-icon.png">`. 행 체크 전에는 disabled 이며,
        행 체크 postback 으로 패널이 재렌더되므로 stale 한 panel_table 대신 frame 단위로
        안정적인 셀렉터를 쓰고, enable 될 때까지 잠시 대기한 뒤 클릭한다.
        """
        candidates = [
            frame.locator("input[type='image'][title='Delete']"),
            frame.locator("input[id$='btnDelete']"),
            frame.locator("input[name$='btnDelete']"),
            frame.locator("input[type='image'][src*='Letter-X-icon' i]"),
            frame.locator("input[type='image'][src*='_x' i]"),
            panel_table.locator("input[type='image']"),
        ]
        for loc in candidates:
            try:
                if await loc.count() == 0:
                    continue
                btn = loc.first
                # disabled 해제(행 체크 postback 완료) 대기 — 최대 ~5초
                for _ in range(10):
                    if await btn.is_enabled():
                        break
                    await asyncio.sleep(0.5)
                await btn.click()
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

    # ------------------------------------------------------------------ #
    # Case 2 handler — Book then recover refs via re-Preview              #
    # ------------------------------------------------------------------ #

    async def _book_and_resolve(
        self, form_frame, results: dict, region_info: dict, containers: list[str]
    ):
        """
        'can be booked' 케이스 처리.

        ① 체크박스 전체 선택 → Book 클릭(실 예약 생성)
        ② success 메시지에서 발급 Bk Ref 추출 (로그/교차검증용)
        ③ 동일 컨테이너로 재-Preview → 'are booked' 상태에서 _parse_booked_table 로 결과 확정
        ④ 재-Preview 가 실패하면 옛 링크-방문 경로로 폴백
        """
        # ① 체크박스 전체 선택 후 Book
        checkboxes = form_frame.locator("input[type='checkbox']")
        cb_count = await checkboxes.count()
        for i in range(cb_count):
            cb = checkboxes.nth(i)
            if not await cb.is_checked():
                await cb.check()

        # exact=True: 과거 booking 이력이 있으면 "Rebook" 아이콘 버튼이 함께 떠서
        # 부분 일치 시 strict mode violation (2 elements) 발생
        await form_frame.get_by_role("button", name="Book", exact=True).click()
        await asyncio.sleep(5)

        # ② success 메시지에서 발급된 반납번호 추출 (Bk Ref prefix 변동 무관)
        try:
            post_text = await form_frame.inner_text("body")
        except Exception:
            post_text = ""
        issued = re.findall(
            r"New Booking\s*-\s*([A-Z0-9]+)\s+is created successfully",
            post_text,
            re.IGNORECASE,
        )
        if issued:
            logger.info("New booking(s) created: %s", issued)
        else:
            logger.warning(
                "Book 후 success 메시지 미검출 (booking 생성 여부 불명) snippet=%s",
                post_text[:300],
            )

        # ③ 동일 컨테이너로 재-Preview → 검증된 'already booked' 경로 재사용
        reparsed = await self._reopen_and_parse_booked(results, region_info, containers)

        # ④ 폴백: 재-Preview 가 실패한 경우에만 옛 링크-방문 경로 시도
        if not reparsed:
            logger.warning("재-Preview 파싱 실패 → 링크 방문 폴백 시도")
            try:
                await self._collect_and_visit_bookings(form_frame, results)
            except Exception as exc:
                logger.error("링크 방문 폴백 실패: %s", exc)

    async def _reopen_and_parse_booked(
        self, results: dict, region_info: dict, containers: list[str]
    ) -> bool:
        """
        동일 컨테이너로 Preview 재실행 → 'are booked' 패널이 노출되면
        _parse_booked_table 로 파싱하고 True 반환. (Preview 는 조회 전용 → 중복 예약 위험 없음)

        Book 직후엔 동일 Redelivery 폼이 화면에 그대로 남아있으므로(좌측 메뉴 재진입은
        해당 화면에서 'Request Redelivery' 메뉴가 없어 실패함) **현재 폼을 그대로 재사용**한다.
        폼 프레임을 못 찾을 때만 메뉴로 재진입을 시도한다.
        """
        try:
            form_frame = await self._frame_containing("Country")
            if form_frame is None:
                # 폼이 화면에 없을 때만 메뉴로 재진입
                await self._navigate_to_redelivery()
                await asyncio.sleep(3)
                form_frame = await self._frame_containing("Country")
            if form_frame is None:
                logger.error("재-Preview: 폼 프레임 미발견")
                return False

            await self._select_region(form_frame, region_info)

            await form_frame.locator("textarea").fill("\n".join(containers))
            eq_radio = form_frame.get_by_label("Equipment Query")
            if await eq_radio.count() > 0:
                await eq_radio.check()

            await form_frame.get_by_role("button", name="Preview").click()
            await asyncio.sleep(5)

            body = (await form_frame.inner_text("body")).lower()
            if "are booked" in body:
                await self._parse_booked_table(form_frame, results, region_info["city"])
                return True

            logger.warning(
                "재-Preview: 'are booked' 미노출 (snippet=%s)", body[800:1100]
            )
            return False
        except Exception as exc:
            logger.error("재-Preview 오류: %s", exc)
            return False

    async def _collect_and_visit_bookings(self, frame, results: dict):
        """
        (폴백 경로) Book 결과 화면에 반납번호 링크가 있을 경우 각 상세를 방문해 results 갱신.

        Bk Ref prefix 는 시기별로 변동(TKE→TKF…)하므로 '^TK + 영숫자' 패턴으로 매칭한다.
        """
        bk_links = frame.locator("a").filter(has_text=re.compile(r"TK[A-Z0-9]{4,}"))
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
