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
import re
import traceback

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
                    logger.error(
                        "FLOR search %s error: %s\n%s",
                        cont, exc, traceback.format_exc(),
                    )
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

        # 헤더 기반 매핑은 사이트 구조 변화에 취약함 (Port:/Depot: 필터 라벨 등).
        # 값 자체의 패턴으로 컬럼 식별하는 헬퍼.
        def parse_cells(cells: list) -> dict:
            """행의 셀들에서 값 패턴으로 필드 식별."""
            out: dict = {
                "ref": "", "status": "", "contract": "",
                "order_date": "", "equip_type": "",
            }
            STATUS_WORDS = (
                "open", "closed", "close",
                "void", "voided",
                "cancelled", "canceled", "cancel",
                "pending", "active", "inactive",
                "completed", "complete",
                "rejected", "approved", "submitted",
            )
            for v in cells:
                v = (v or "").strip()
                if not v:
                    continue
                # PPR####### 또는 PPF#######
                if re.match(r"^PP[RF]\d+$", v):
                    out["ref"] = v
                # 상태값: 짧은 단어로 위 목록에 포함
                elif v.lower() in STATUS_WORDS or (
                    len(v) <= 20 and any(w == v.lower() for w in STATUS_WORDS)
                ):
                    out["status"] = v
                # DF-HNGA20008, LT-HALINE-02 등
                elif re.match(r"^[A-Z]{2,}-[A-Z]+[-\d]+[A-Z]?$", v):
                    out["contract"] = v
                # 2026-04-01 / 2026-04-30 형식
                elif re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", v):
                    out["order_date"] = v
                # 40' Dry High Cube 등
                elif re.match(r"^\d+'\s*(Dry|Reefer|Standard|HC|High)", v, re.IGNORECASE):
                    out["equip_type"] = v
            return out

        def status_of(r: list) -> str:
            return parse_cells(r).get("status", "")

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

        # 모든 행을 파싱해서 로그 (디버깅용)
        for i, r in enumerate(rows):
            pc = parse_cells(r)
            logger.info("FLOR %s row[%d] cells=%s parsed=%s",
                        container, i, r, pc)

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
        parsed = parse_cells(row)
        logger.info("FLOR %s parsed=%s", container, parsed)

        ref    = parsed.get("ref", "")
        status = parsed.get("status", "")

        # + More 클릭 → 상세 (Expiry Date, Depot Name, Open Rdlvry Qty) 추출
        details: dict = {}
        if ref:
            try:
                details = await self._expand_and_extract(ref)
                logger.info("FLOR %s details=%s", container, details)
            except Exception as exc:
                logger.warning("FLOR %s expand 실패: %s", container, exc)

        depot     = details.get("depot_name") or None
        expiry    = details.get("expiry_date") or None
        open_qty  = details.get("open_rdlvry_qty")

        try:
            over_caps = int(open_qty) if open_qty and str(open_qty).isdigit() else None
        except (ValueError, TypeError):
            over_caps = None

        # 가용 판정: Status가 Open 이면 반납 가능
        is_open = "open" in status.lower()
        available = is_open

        reason: str | None = None
        if not available:
            if "closed" in status.lower():
                reason = "이미 반납됨 (Closed)"
            elif "void" in status.lower() or "cancel" in status.lower():
                reason = "취소된 예약 (VOID)"
            else:
                reason = f"발급 상태: {status or '미상'}"

        # 유효기간 우선순위: Expiry Date > Order Date
        date = expiry or parsed.get("order_date", "")

        return {
            "container_no": container,
            "available": available,
            "depot": depot,
            "booking_ref": ref or None,
            "over_caps": over_caps,
            "close_date": date or None,
            "reason": reason,
        }

    # ------------------------------------------------------------------ #
    # + More 클릭 → 상세 추출
    # ------------------------------------------------------------------ #

    async def _expand_and_extract(self, ref: str) -> dict:
        """
        Status 테이블에서 Redelivery No=ref 행의 + More 아이콘을 클릭해 펼치고,
        Expiry Date / Depot Name / Open Rdlvry Qty 를 추출.
        """
        clicked = await self.page.evaluate(r"""(needle) => {
            const trs = Array.from(document.querySelectorAll('table tbody tr'));
            for (const tr of trs) {
                const txt = (tr.innerText || '');
                if (!txt.includes(needle)) continue;
                // Element UI 등 흔한 expand 아이콘
                const sels = [
                    '.el-table__expand-icon',
                    'i.el-icon-plus',
                    'i.el-icon-arrow-right',
                    'span.el-icon-plus',
                    '.el-table__expand-column i',
                ];
                for (const s of sels) {
                    const el = tr.querySelector(s);
                    if (el) {
                        el.scrollIntoView({ block: 'center' });
                        el.click();
                        return { ok: true, via: s };
                    }
                }
                // fallback: text "+" / ">" / "More"
                const all = tr.querySelectorAll('*');
                for (const el of all) {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (t === '+' || t === '▶' || t === '▷' || /^more$/i.test(t)) {
                        el.scrollIntoView({ block: 'center' });
                        el.click();
                        return { ok: true, via: 'text:' + t };
                    }
                }
                return { ok: false, error: 'expand icon not found' };
            }
            return { ok: false, error: 'row not found' };
        }""", ref)

        logger.info("FLOR expand result: %s", clicked)
        if not clicked.get("ok"):
            return {}

        await asyncio.sleep(2)

        return await self.page.evaluate(r"""() => {
            function valueByLabel() {
                const labels = Array.from(arguments);
                const els = Array.from(document.querySelectorAll(
                    'th, td, div, span, dt, dd, label, strong, b, p'
                ));
                for (const want of labels) {
                    for (const el of els) {
                        const text = (el.innerText || '').trim();
                        if (text === want || text === want + ':' || text === want + ' :') {
                            // 같은 행의 다음 셀 (th-td 패턴)
                            let next = el.nextElementSibling;
                            while (next && !(next.innerText || '').trim()) {
                                next = next.nextElementSibling;
                            }
                            if (next) {
                                const v = (next.innerText || '').trim();
                                if (v && v.length < 200) return v;
                            }
                        }
                    }
                }
                return null;
            }

            // Contracts 테이블에서 Open Rdlvry Qty 추출
            let openQty = null;
            for (const tbl of document.querySelectorAll('table')) {
                const headers = Array.from(tbl.querySelectorAll('thead th, thead td'))
                    .map(th => (th.innerText || '').trim());
                const idx = headers.findIndex(h => /open\s*rdlvry\s*qty/i.test(h));
                if (idx >= 0) {
                    const firstRow = tbl.querySelector('tbody tr');
                    if (firstRow) {
                        const cells = firstRow.querySelectorAll('td');
                        if (idx < cells.length) {
                            openQty = (cells[idx].innerText || '').trim();
                        }
                    }
                    break;
                }
            }

            return {
                expiry_date: valueByLabel('Expiry Date', 'EXPIRY DATE', 'Expiry'),
                depot_name: valueByLabel('Depot Name', 'DEPOT NAME', 'Depot'),
                open_rdlvry_qty: openQty,
            };
        }""")

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
