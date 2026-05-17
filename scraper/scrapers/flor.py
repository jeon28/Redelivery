"""FLOR (Florens) 스크래퍼 — Apply Redelivery 1차 흐름.

분석 문서: REDELIVERY/FLOR/ANALYSIS.md
구현 계획: REDELIVERY/FLOR/IMPLEMENTATION_PLAN.md

조회 흐름 (Apply Redelivery 위저드 — Phase A, Confirm 미클릭):
  1. 로그인 (슬라이드 캡차 + Sign-in 버튼)
  2. /func/redelivery#/ 진입 (Apply Redelivery 탭 기본 활성)
  3. Step1: Customer ID(SINOKOR/HALINE) + Port + Depot 설정 → Next
  4. Step2: Unit Numbers textarea \n 구분 입력 → Next
  5. Step3: 거부/유효 테이블 파싱
     - 거부행 → 사유 캡처 → 불가
     - 유효행 → 가능 (PPR 번호는 Phase B에서 Confirm 클릭 후 채움)

Phase B (예정): Confirm Redelivery Order 클릭 → 신규 PPR 캡처 → Status 보조 enrichment.
Status 탭 기반 헬퍼(`_search_one`, `_expand_and_extract`)는 Phase B 보조용으로 보존.
"""
import asyncio
import logging
import os
import random
import re
import traceback
from pathlib import Path

from playwright.async_api import async_playwright

from scrapers.base import BaseScraper
from config.credentials import get_credential

logger = logging.getLogger(__name__)

LOGIN_URL    = "https://www.florens.com/official-pc/login#/"
REDELIV_URL  = "https://www.florens.com/func/redelivery#/"

# Playwright storage_state 저장 디렉토리 (쿠키 + localStorage).
# 회사별로 파일을 분리하여 SK/HA 세션 충돌 방지.
# Railway Volume `/data/` 와 같은 영구 디스크에 두어야 워커 재시작 후에도 유지됨.
FLOR_SESSION_DIR = Path(os.getenv("FLOR_SESSION_DIR", "/data"))


def _session_file_for(company: str) -> Path:
    suffix = {"장금상선": "SK", "흥아라인": "HA"}.get(company, "OTHER")
    return FLOR_SESSION_DIR / f"flor_session_{suffix}.json"


# Port → Default Depot 옵션 문자열 (사용자 명시 depot 없을 때 fallback).
# 옵션 텍스트 포맷: "(CODE) NAME (CODE)" — 코드가 앞·뒤 두 번 노출됨 (사이트 관찰).
# BUSAN/GWANGYANG 은 미설정 — 향후 사용자 드롭다운 선택 또는 매핑 추가 필요.
PORT_DEFAULT_DEPOT: dict[str, str] = {
    "INCHON": "(KRINC04) SeungJin Enterprise Co., Ltd. (KRINC04)",
}

# Company (한글) → Customer ID 라디오 텍스트 (Step1).
COMPANY_CUSTOMER_ID: dict[str, str] = {
    "장금상선": "SINOKOR",
    "흥아라인": "HALINE",
}

# Region (대문자 영문) → Port 드롭다운 옵션 텍스트 검색용 substring.
# FLOR 사이트는 부산을 "PUSAN" (옛 표기) 으로 표시 (ANALYSIS.md §7).
PORT_OPTION_SUBSTR: dict[str, str] = {
    "INCHON":    "INCHON",
    "BUSAN":     "PUSAN",
    "GWANGYANG": "GWANGYANG",
}


def _to_mmdd(iso: str | None) -> str | None:
    """'2026-05-13' → '5/13'. 비/잘못된 입력은 None. 앞자리 0 없음."""
    if not iso:
        return None
    m = re.match(r"^\d{4}-(\d{1,2})-(\d{1,2})$", iso.strip())
    if not m:
        return None
    return f"{int(m.group(1))}/{int(m.group(2))}"


class FlorScraper(BaseScraper):
    def __init__(self, company: str, lessor: str):
        super().__init__(company, lessor)
        self.cred = get_credential(company, lessor)
        # storage_state 적용을 위해 context를 직접 보관 (base.py 는 page 만 보유)
        self.context = None

    # ------------------------------------------------------------------ #
    # Browser start — storage_state 복원으로 로그인·캡차 빈도 최소화
    # ------------------------------------------------------------------ #

    async def start(self, headless: bool = True):
        """저장된 storage_state 가 있으면 복원해 브라우저 컨텍스트를 만든다."""
        browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
        if browsers_path:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        sess = _session_file_for(self.company)
        storage_arg = None
        if sess.exists():
            try:
                storage_arg = str(sess)
                logger.info("FLOR(%s): storage_state 복원 시도 %s", self.company, sess)
            except Exception as exc:
                logger.warning("FLOR(%s): storage_state 복원 실패: %s", self.company, exc)
                storage_arg = None

        self.context = await self.browser.new_context(storage_state=storage_arg)
        self.page = await self.context.new_page()

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
        """
        저장된 storage_state 가 있으면 세션 유효성부터 확인.
        - redeliv 페이지로 곧장 진입 시 URL 이 `/login` 으로 튕기지 않으면 OK.
        - 만료/누락이면 신규 로그인 → 성공 시 storage_state 저장.
        """
        sess = _session_file_for(self.company)
        if sess.exists():
            try:
                await self.page.goto(
                    REDELIV_URL, wait_until="domcontentloaded", timeout=20_000
                )
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                await asyncio.sleep(1.0)
                if "/login" not in self.page.url:
                    logger.info(
                        "FLOR(%s): existing session valid → skip login (%s)",
                        self.company, self.page.url,
                    )
                    return True
                logger.info(
                    "FLOR(%s): stored session expired → fresh login (%s)",
                    self.company, self.page.url,
                )
            except Exception as exc:
                logger.info(
                    "FLOR(%s): session check failed → fresh login: %s",
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
            logger.info("FLOR(%s): storage_state 저장 %s", self.company, sess)
        except Exception as exc:
            logger.warning("FLOR(%s): storage_state 저장 실패: %s", self.company, exc)

    async def _fresh_login(self) -> bool:
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
    # Query (Apply Redelivery 위저드 — Phase A: Confirm 미클릭)
    # ------------------------------------------------------------------ #

    async def query(
        self,
        containers: list[str],
        region: str,
        depot: str | None = None,
    ) -> list[dict]:
        # 입력 정규화 + 중복 제거 (입력 순서 보존)
        seen: set[str] = set()
        deduped: list[str] = []
        for c in containers:
            k = (c or "").strip().upper()
            if not k or k in seen:
                continue
            seen.add(k)
            deduped.append(k)

        # 기본 결과: 모두 "조회 실패"로 시작 → 단계별 갱신
        results: dict[str, dict] = {c: self._error_row(c, "조회 실패") for c in deduped}

        try:
            # 1. Depot 결정 (사용자 명시 > Port 별 default fallback)
            depot_str = self._resolve_depot(region, depot)

            # 2. Customer ID + Port substring 결정
            cust_id = COMPANY_CUSTOMER_ID.get(self.company)
            if not cust_id:
                raise RuntimeError(f"지원하지 않는 선사: {self.company}")
            port_substr = PORT_OPTION_SUBSTR.get((region or "").upper())
            if not port_substr:
                raise RuntimeError(f"지원하지 않는 region: {region}")

            # 3. Redelivery 페이지 진입 (Apply 탭 기본 활성)
            await self._navigate_to_apply()

            # 4. Step 1: Customer ID / Port / Depot
            await self._select_customer_id(cust_id)
            await self._select_port(port_substr)
            await self._select_depot(depot_str)

            # 5. Next → Step 2
            await self._step_next()

            # 6. Step 2: Unit Numbers 일괄 입력
            await self._step2_fill_units(deduped)

            # 7. Next → Step 3 (사전 검증)
            await self._step_next()

            # 8. Step 3 파싱 (거부/유효 분리)
            await self._parse_step3(results, depot_str)

            # Phase B (예정): Confirm Redelivery Order 클릭 → PPR 캡처 + Status enrichment

        except Exception as exc:
            logger.error("FLOR query error: %s\n%s", exc, traceback.format_exc())

        # 안전장치 + 3상태 status 일괄 도출
        for c in deduped:
            results.setdefault(c, self._error_row(c, "조회 실패"))
        for r in results.values():
            if r.get("status") == "completed":
                continue
            if r.get("available"):
                r["status"] = "available"
                r.setdefault("completed_date", None)
            else:
                r["status"] = "unavailable"
                r.setdefault("completed_date", None)
                if not r.get("reason"):
                    r["reason"] = "조회 실패 (사유 미상)"

        return [
            results.get((c or "").strip().upper()) or self._error_row(c, "결과 없음")
            for c in containers
        ]

    # ------------------------------------------------------------------ #
    # Apply Redelivery 위저드 헬퍼 (Phase A)
    # ------------------------------------------------------------------ #

    def _resolve_depot(self, region: str, depot_param: str | None) -> str:
        """사용자 명시 depot 우선, 없으면 PORT_DEFAULT_DEPOT fallback."""
        if depot_param and depot_param.strip():
            return depot_param.strip()
        key = (region or "").upper()
        default = PORT_DEFAULT_DEPOT.get(key)
        if not default:
            raise RuntimeError(
                f"{region}: default depot 미설정 — depot 명시 필요 (BUSAN/GWANGYANG 등)"
            )
        return default

    async def _navigate_to_apply(self) -> None:
        """Redelivery 페이지 진입. Apply Redelivery 탭이 기본 활성이지만 안전을 위해 클릭."""
        await self.page.goto(REDELIV_URL, wait_until="networkidle", timeout=30_000)
        await asyncio.sleep(2.0)
        apply_tab = self.page.locator("text=Apply Redelivery").first
        if await apply_tab.count() > 0:
            try:
                await apply_tab.click(timeout=3_000)
                await asyncio.sleep(0.8)
            except Exception:
                pass  # 이미 활성이면 클릭 실패해도 무방

    async def _select_customer_id(self, cust_id: str) -> None:
        """Step1 Customer ID 라디오 클릭 (SINOKOR / HALINE)."""
        radio = self.page.locator(f"text={cust_id}").first
        if await radio.count() == 0:
            raise RuntimeError(f"Customer ID '{cust_id}' 옵션 없음")
        await radio.click()
        await asyncio.sleep(0.5)

    async def _select_port(self, port_substr: str) -> None:
        """Step1 Port Element UI 드롭다운 — 첫 번째 el-select 위젯."""
        await self._click_el_select(0)
        await self._pick_el_option_substr(port_substr)

    async def _select_depot(self, depot_str: str) -> None:
        """Step1 Depot Element UI 드롭다운 — 두 번째 el-select 위젯.
        depot_str 에서 '(CODE)' 추출하여 옵션 텍스트 부분일치."""
        m = re.search(r"\(([^)]+)\)", depot_str)
        if not m:
            raise RuntimeError(f"depot 문자열에 (CODE) 패턴 없음: {depot_str}")
        code_token = f"({m.group(1)})"
        await self._click_el_select(1)
        await self._pick_el_option_substr(code_token)

    async def _click_el_select(self, nth: int) -> None:
        """nth 번째 el-select 입력을 클릭하여 옵션 패널을 연다."""
        sel = self.page.locator(".el-select").nth(nth)
        if await sel.count() == 0:
            raise RuntimeError(f"el-select[{nth}] 없음")
        # 내부 input 클릭이 더 안정적
        inner = sel.locator(".el-input__inner").first
        if await inner.count() > 0:
            await inner.click()
        else:
            await sel.click()
        await asyncio.sleep(0.6)

    async def _pick_el_option_substr(self, substr: str) -> None:
        """현재 열려있는 옵션 패널에서 substring 매칭하는 li 를 JS evaluate 로 클릭."""
        result = await self.page.evaluate(
            r"""(sub) => {
                const items = Array.from(
                    document.querySelectorAll('.el-select-dropdown__item')
                ).filter(el => el.offsetParent !== null);
                const subU = sub.toUpperCase();
                const target = items.find(
                    el => (el.innerText || '').toUpperCase().includes(subU)
                );
                if (!target) return { ok: false, visible: items.length };
                target.scrollIntoView({ block: 'center' });
                target.click();
                return { ok: true, text: target.innerText };
            }""",
            substr,
        )
        if not result.get("ok"):
            raise RuntimeError(
                f"드롭다운 옵션 '{substr}' 없음 (visible {result.get('visible')}개)"
            )
        logger.info("FLOR option picked: %r → %r", substr, result.get("text"))
        await asyncio.sleep(0.8)

    async def _step_next(self) -> None:
        """Next 버튼 클릭."""
        btn = self.page.locator("button").filter(has_text="Next").first
        if await btn.count() == 0:
            raise RuntimeError("Next 버튼 없음")
        await btn.click()
        try:
            await self.page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        await asyncio.sleep(1.5)

    async def _step2_fill_units(self, containers: list[str]) -> None:
        """Step2 textarea 에 컨테이너 번호 \\n 구분으로 일괄 입력."""
        ta = self.page.locator("textarea.el-textarea__inner").first
        if await ta.count() == 0:
            raise RuntimeError("Unit Numbers textarea 없음")
        await ta.fill("\n".join(containers))
        await asyncio.sleep(0.5)

    async def _parse_step3(self, results: dict, depot_str: str) -> None:
        """Step3 사전 검증 결과 파싱.

        FLOR Step3 화면엔 두 종류 테이블이 있을 수 있음:
          - 거부 행: Unit Number / Contract / Equip Type / Reason
          - 유효 행: Unit Number / Contract / Equip Type / Qty 등

        구조 식별 휴리스틱:
          - 행 셀 중 reason-스러운 긴 문장(>=40자) 또는 키워드(incapable/cannot/over/already 등)
            가 있으면 거부 행으로 분류.
          - 그 외 컨테이너 패턴(`[A-Z]{4}\\d{6,7}`) 가진 행은 유효 행.
        """
        data = await self.page.evaluate(
            r"""() => {
                const out = { invalid: [], valid: [], dump: [] };
                const REJECT_KEYWORDS = [
                    'incapable', 'cannot', 'over caps', 'over_caps',
                    'already', 'reject', 'invalid', 'previously'
                ];
                for (const tbl of document.querySelectorAll('table')) {
                    const rows = Array.from(tbl.querySelectorAll('tbody tr'));
                    for (const tr of rows) {
                        const cells = Array.from(tr.querySelectorAll('td'))
                            .map(td => (td.innerText || '').trim());
                        if (cells.length === 0) continue;
                        out.dump.push(cells);
                        const unit = cells.find(c => /^[A-Z]{4}\d{6,7}$/.test(c)) || '';
                        if (!unit) continue;
                        // 거부 사유 후보: 긴 문장 또는 키워드 포함
                        const reasonCell = cells.find(c => {
                            if (c === unit) return false;
                            const cl = c.toLowerCase();
                            if (c.length >= 40) return true;
                            return REJECT_KEYWORDS.some(k => cl.includes(k));
                        });
                        if (reasonCell) {
                            out.invalid.push({ unit, reason: reasonCell, cells });
                        } else {
                            out.valid.push({ unit, cells });
                        }
                    }
                }
                return out;
            }"""
        )

        invalid = data.get("invalid") or []
        valid = data.get("valid") or []
        logger.info(
            "FLOR Step3 parsed: invalid=%d valid=%d (depot=%s)",
            len(invalid), len(valid), depot_str,
        )
        for row in (data.get("dump") or [])[:10]:
            logger.info("FLOR Step3 row: %s", row)

        # 거부행 처리: §5-3 (이미 활성 PPR), §5-4 (이전 완료) 패턴은 1차 reason 텍스트에서 탐지
        for r in invalid:
            unit = (r.get("unit") or "").upper()
            reason = r.get("reason") or ""
            if unit not in results:
                continue
            results[unit].update(
                self._classify_reject(unit, reason)
            )

        # 유효행 처리: 가능 (Phase B 에서 Confirm 후 PPR 채움)
        for r in valid:
            unit = (r.get("unit") or "").upper()
            if unit not in results:
                continue
            results[unit].update({
                "available": True,
                "status": "available",
                "completed_date": None,
                "depot": depot_str,
                "booking_ref": None,   # Phase B 에서 채움
                "over_caps": None,
                "close_date": None,
                "reason": None,
            })

    def _classify_reject(self, unit: str, reason: str) -> dict:
        """거부 reason 텍스트를 분류 (§5-3 / §5-4 / 일반).

        §5-3 이미 활성 PPR: reason 에 PPR 번호 + active/already/open 키워드 → 가능 처리
        §5-4 이전 완료    : reason 에 closed/previously + 날짜 → completed 처리
        그 외             : 일반 불가
        """
        r_lower = reason.lower()

        # §5-3: 활성 PPR 추출
        ppr_match = re.search(r"PP[RF]\d+", reason)
        active_kw = any(k in r_lower for k in (
            "already", "active", "open redelivery", "existing redelivery"
        ))
        if ppr_match and active_kw:
            logger.info("FLOR %s: §5-3 활성 PPR 감지 → %s", unit, ppr_match.group(0))
            return {
                "available": True,
                "status": "available",
                "completed_date": None,
                "booking_ref": ppr_match.group(0),
                "reason": None,
                # depot/over_caps/close_date 은 Phase B Status enrichment 에서 채움
            }

        # §5-4: 이전 완료 (날짜 패턴 검출)
        date_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", reason)
        completed_kw = any(k in r_lower for k in (
            "previously", "closed", "already redelivered", "이미 반납"
        ))
        if completed_kw and date_match:
            mmdd = _to_mmdd(date_match.group(1))
            logger.info("FLOR %s: §5-4 이전 완료 감지 → %s", unit, mmdd)
            return {
                "available": False,
                "status": "completed",
                "completed_date": mmdd,
                "reason": "이미 반납됨 (Closed)",
            }

        # 일반 불가
        return {
            "available": False,
            "status": "unavailable",
            "completed_date": None,
            "reason": reason or "거부 (사유 미상)",
        }

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

        # 모든 기록이 VOID/Cancelled → 이전 예약은 취소됨, 새로 신청 가능.
        # 사용자 시각: 컨테이너는 반납 가능한 상태 (재신청만 하면 됨) → 가능.
        if not active_rows:
            return {
                "container_no": container,
                "available": True,
                "depot": None,
                "booking_ref": None,
                "over_caps": None,
                "close_date": None,
                "reason": "재신청 가능 (이전 예약 모두 VOID)",
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

        depot    = details.get("depot_name") or None
        expiry   = details.get("expiry_date") or None
        open_cap = details.get("open_cap")  # Contracts 테이블의 Open CAP (잔여 캡)

        try:
            over_caps = int(open_cap) if open_cap and str(open_cap).isdigit() else None
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

            // Contracts 테이블에서 Open CAP 추출 (잔여 캡)
            // 주의: "Open CAP"과 "Open Rdlvry Qty" 두 컬럼이 있으니 구분 필요.
            let openCap = null;
            for (const tbl of document.querySelectorAll('table')) {
                const headers = Array.from(tbl.querySelectorAll('thead th, thead td'))
                    .map(th => (th.innerText || '').trim());
                const idx = headers.findIndex(h => /^open\s*cap$/i.test(h));
                if (idx >= 0) {
                    const firstRow = tbl.querySelector('tbody tr');
                    if (firstRow) {
                        const cells = firstRow.querySelectorAll('td');
                        if (idx < cells.length) {
                            openCap = (cells[idx].innerText || '').trim();
                        }
                    }
                    break;
                }
            }

            return {
                expiry_date: valueByLabel('Expiry Date', 'EXPIRY DATE', 'Expiry'),
                depot_name: valueByLabel('Depot Name', 'DEPOT NAME', 'Depot'),
                open_cap: openCap,
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
            "status": "unavailable",
            "completed_date": None,
            "depot": None,
            "booking_ref": None,
            "over_caps": None,
            "close_date": None,
            "reason": reason,
        }
