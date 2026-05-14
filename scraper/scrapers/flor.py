"""FLOR (Florens) 스크래퍼 — 조회 모드.

분석 문서: REDELIVERY/FLOR/ANALYSIS.md

조회 흐름 (안전 모드, 실 발급 없음):
  1. 로그인 (슬라이드 캡차 + Sign-in 버튼)
  2. /func/redelivery#/ 진입
  3. Redelivery Status 탭 선택
  4. Unit No. 라디오 선택
  5. 컨테이너별로 입력 + Search → 결과 테이블 파싱
  6. PPR 번호 / Status / Order Date / Equip Type / Qty 반환

발급(Apply)은 별도 구현 예정. 현재는 이미 발급된 PPR 조회만.
"""
import asyncio
import logging
import random

from scrapers.base import BaseScraper
from config.credentials import get_credential

logger = logging.getLogger(__name__)

LOGIN_URL    = "https://www.florens.com/official-pc/login#/"
REDELIV_URL  = "https://www.florens.com/func/redelivery#/"


class FlorScraper(BaseScraper):
    def __init__(self, company: str, lessor: str):
        super().__init__(company, lessor)
        self.cred = get_credential(company, lessor)

    # ------------------------------------------------------------------ #
    # Login (슬라이드 캡차 + Sign-in)
    # ------------------------------------------------------------------ #

    async def _slider_drag(self) -> bool:
        """슬라이더 좌→우 드래그. 30 step ease-out + Y noise."""
        rects = await self.page.evaluate("""() => {
            const btn = document.querySelector('.slider-button');
            const track = document.querySelector('.slider-track') || document.querySelector('.slider-container');
            const br = btn && btn.getBoundingClientRect();
            const tr = track && track.getBoundingClientRect();
            return {
                btn: br ? { x: br.x, y: br.y, w: br.width, h: br.height } : null,
                track: tr ? { x: tr.x, y: tr.y, w: tr.width, h: tr.height } : null,
            };
        }""")
        if not rects.get("btn") or not rects.get("track"):
            return False
        br, tr = rects["btn"], rects["track"]
        sx = br["x"] + br["w"] / 2
        sy = br["y"] + br["h"] / 2
        ex = tr["x"] + tr["w"] - br["w"] / 2
        await self.page.mouse.move(sx, sy)
        await self.page.mouse.down()
        for i in range(1, 31):
            progress = i / 30
            eased = 1 - (1 - progress) ** 2
            cx = sx + (ex - sx) * eased
            cy = sy + random.uniform(-1.5, 1.5)
            await self.page.mouse.move(cx, cy)
            await asyncio.sleep(0.03)
        await self.page.mouse.up()
        return True

    async def login(self) -> bool:
        try:
            await self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            await asyncio.sleep(2.5)

            pw_el = await self.page.query_selector('input[type="password"]')
            user_el = None
            for inp in await self.page.query_selector_all('input'):
                t = await inp.get_attribute("type")
                if t in ("password", "hidden", "checkbox", "radio", "submit", "button"):
                    continue
                user_el = inp
                break
            if not pw_el or not user_el:
                logger.error("FLOR login: 입력 필드 탐지 실패")
                return False

            await user_el.fill(self.cred.get("id", ""))
            await pw_el.fill(self.cred.get("pw", ""))
            await asyncio.sleep(0.5)

            # 슬라이드 캡차
            if not await self._slider_drag():
                logger.error("FLOR login: 슬라이더 요소 못 찾음")
                return False
            await asyncio.sleep(1.5)

            # Sign-in 버튼 (URL이 아직 /login 이면 클릭 필요)
            if "/login" in self.page.url:
                signin = self.page.locator("button").filter(has_text="Sign-in").first
                if await signin.count() == 0:
                    signin = self.page.locator("button").filter(has_text="Sign In").first
                if await signin.count() > 0:
                    await signin.click()
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=20_000)
                    except Exception:
                        pass

            # URL 전환 폴링 (최대 15초)
            for _ in range(30):
                if "/login" not in self.page.url:
                    logger.info("FLOR login OK: %s", self.page.url)
                    return True
                await asyncio.sleep(0.5)

            logger.error("FLOR login failed — still on login: %s", self.page.url)
            return False
        except Exception as exc:
            logger.error("FLOR login exception: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Query (Redelivery Status 탭)
    # ------------------------------------------------------------------ #

    async def query(self, containers: list[str], region: str) -> list[dict]:
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

        try:
            # Redelivery 페이지 진입 → Status 탭 활성화
            await self.page.goto(REDELIV_URL, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(2.0)

            status_tab = self.page.locator("text=Redelivery Status").first
            if await status_tab.count() == 0:
                logger.error("FLOR: Redelivery Status 탭 없음")
                return [self._error_row(c, "Status 탭 없음") for c in containers]
            await status_tab.click()
            await asyncio.sleep(1.5)

            # Unit No. 라디오 선택
            unit_radio = self.page.locator("text=Unit No.").first
            if await unit_radio.count() > 0:
                await unit_radio.click()
                await asyncio.sleep(0.8)

            for cont in deduped:
                try:
                    results[cont] = await self._search_one(cont)
                except Exception as exc:
                    logger.error("FLOR search %s error: %s", cont, exc)
                    results[cont] = self._error_row(cont, "조회 실패 (예외)")
        except Exception as exc:
            logger.error("FLOR query error: %s", exc)
            for c in deduped:
                results.setdefault(c, self._error_row(c, "조회 실패"))

        # 안전장치: 모든 컨테이너 결과 보장 + reason 누락 방지
        for c in deduped:
            results.setdefault(c, self._error_row(c, "조회 실패"))
        for r in results.values():
            if not r.get("available") and not r.get("reason"):
                r["reason"] = "조회 실패 (사유 미상)"

        return [
            results.get((c or "").strip().upper()) or self._error_row(c, "결과 없음")
            for c in containers
        ]

    async def _search_one(self, container: str) -> dict:
        """Status 탭에서 컨테이너 한 개 검색 후 결과 행 파싱."""
        unit_input = self.page.locator('input[placeholder="Unit Number"]').first
        if await unit_input.count() == 0:
            return self._error_row(container, "Unit Number 입력란 없음")
        await unit_input.fill(container)
        await asyncio.sleep(0.3)

        search_btn = self.page.locator("button").filter(has_text="Search").first
        if await search_btn.count() == 0:
            return self._error_row(container, "Search 버튼 없음")
        await search_btn.click()
        try:
            await self.page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        await asyncio.sleep(2.0)

        # 결과 행 추출 + 헤더로 매핑
        # 주의: FLOR Status 테이블의 thead 에는 "Port:", "Depot:" 같은 필터 라벨이
        # 함께 들어있어 col() 인덱스를 어긋나게 만든다. 콜론으로 끝나는 셀은 제외.
        data = await self.page.evaluate(r"""() => {
            const headers = Array.from(document.querySelectorAll('table thead th, table thead td'))
                .map(th => (th.innerText || '').trim())
                .filter(t => t && !t.endsWith(':'));
            const rows = Array.from(document.querySelectorAll('table tbody tr'))
                .map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim()))
                .filter(r => r.length > 0);
            return { headers, rows };
        }""")

        headers = data.get("headers") or []
        rows = data.get("rows") or []
        logger.info("FLOR %s headers=%s", container, headers)
        if rows:
            logger.info("FLOR %s first row=%s", container, rows[0])

        if not rows:
            return {
                "container_no": container,
                "available": False,
                "depot": None,
                "booking_ref": None,
                "over_caps": None,
                "close_date": None,
                "reason": "발급된 반납번호 없음 (신청 필요)",
            }

        def col(keyword: str) -> int:
            for i, h in enumerate(headers):
                if keyword.lower() in h.lower():
                    return i
            return -1

        i_ref     = col("Redelivery No")
        i_status  = col("Status")
        i_date    = col("Order Date")
        i_bal     = col("BAL")        # 잔여 수량 (over_caps 대응)
        i_mov     = col("MOV")
        i_qty     = col("Order Qty")
        i_equip   = col("Equip")      # Equip Type 컬럼 (참고용)

        def status_of(r: list) -> str:
            return r[i_status].strip() if 0 <= i_status < len(r) else ""

        def is_active(r: list) -> bool:
            return "open" in status_of(r).lower()

        def is_void(r: list) -> bool:
            return "void" in status_of(r).lower() or "cancel" in status_of(r).lower()

        # 같은 컨테이너에 PPR 기록이 여러 건일 수 있음 (Open 1 + VOID 다수).
        # 우선순위: Open(BAL>0) → Open(BAL=0/없음) → Closed → VOID(제외) → 최신.
        def row_priority(r: list) -> int:
            s = status_of(r).lower()
            if "open" in s:
                return 0
            if "closed" in s:
                return 2
            if "void" in s or "cancel" in s:
                return 99
            return 5

        candidates = sorted(rows, key=row_priority)
        active_rows = [r for r in candidates if not is_void(r)]

        if not active_rows:
            # 모든 기록이 VOID → 활성 예약 없음. 신청 가능 상태로 안내.
            return {
                "container_no": container,
                "available": False,
                "depot": None,
                "booking_ref": None,
                "over_caps": None,
                "close_date": None,
                "reason": "활성 예약 없음 (모두 VOID) — 신청 필요",
            }

        row = active_rows[0]

        def cell(i: int) -> str:
            return row[i].strip() if 0 <= i < len(row) else ""

        ref    = cell(i_ref)
        status = cell(i_status)
        date   = cell(i_date)
        bal_s  = cell(i_bal)
        # FLOR Status 테이블에는 Depot 컬럼이 없음 (필터 라벨로만 존재).
        # 상세 expand("+" 행)에서만 보이므로 기본 결과에서는 None.
        depot: str | None = None

        try:
            bal = int(bal_s) if bal_s.isdigit() else None
        except ValueError:
            bal = None

        # 가용 판정: Status가 Open이고 BAL>0 이면 반납 가능
        is_open = "open" in status.lower()
        has_balance = (bal is None) or (bal > 0)
        available = is_open and has_balance

        reason: str | None = None
        if not available:
            if "closed" in status.lower():
                reason = "이미 반납됨 (Closed)"
            elif bal == 0:
                reason = "당월 반납분 소진 (BAL=0)"
            else:
                reason = f"발급 상태: {status or '미상'}"

        return {
            "container_no": container,
            "available": available,
            "depot": depot or None,
            "booking_ref": ref or None,
            "over_caps": bal,
            "close_date": date or None,
            "reason": reason,
        }

    # ------------------------------------------------------------------ #
    # 헬퍼
    # ------------------------------------------------------------------ #

    @staticmethod
    def _error_row(container: str, reason: str) -> dict:
        return {
            "container_no": container,
            "available": False,
            "depot": None,
            "booking_ref": None,
            "over_caps": None,
            "close_date": None,
            "reason": reason,
        }
