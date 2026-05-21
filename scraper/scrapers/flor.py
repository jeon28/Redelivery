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
        # Deploy marker — Railway 활성 commit 검증용. 이 로그가 보이면 새 코드 실행 중.
        logger.info("FLOR scraper start [marker=closed-display-v1]")
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
            # ── Phase 1: Status 탭 우선 조회 ──────────────────────────────
            # 권위 있는 Redelivery Status 탭에서 컨테이너별 현 PPR 상태를 직접 확인.
            #  Open 행 (active PPR) 또는 Closed (이미 반납됨) → 결과 채택
            #  결과 없음 / 모두 VOID → 신규 후보로 보관 → Phase 2 에서 Apply 흐름
            new_candidates: list[str] = []
            try:
                await self._navigate_to_status()
                # S1 진단 — 환경변수 gated. 1회용 진단 후 끄기.
                if os.getenv("FLOR_STATUS_DUMP") == "1":
                    try:
                        await self._dump_status_tab()
                    except Exception as exc:
                        logger.warning("FLOR Status dump 실패: %s", exc)
            except Exception as exc:
                logger.warning(
                    "FLOR Status 탭 진입 실패 — 모든 컨테이너를 Apply 흐름으로: %s", exc
                )
                new_candidates = list(deduped)
            else:
                for c in deduped:
                    try:
                        row = await self._search_one(c)
                    except Exception as exc:
                        logger.warning("FLOR %s status lookup 실패 — Apply 후보로: %s", c, exc)
                        new_candidates.append(c)
                        continue
                    if self._status_row_is_new_candidate(row):
                        new_candidates.append(c)
                        logger.info("FLOR %s: Status 결과 없음/VOID → 신규 후보", c)
                    else:
                        results[c].update({
                            "container_no": c,
                            "available": row.get("available", False),
                            "status": row.get("status"),
                            "completed_date": row.get("completed_date"),
                            "depot": row.get("depot"),
                            "booking_ref": row.get("booking_ref"),
                            "over_caps": row.get("over_caps"),
                            "close_date": row.get("close_date"),
                            "reason": row.get("reason"),
                        })
                        logger.info(
                            "FLOR %s: Status 채택 (status=%s booking_ref=%s reason=%s)",
                            c, row.get("status"), row.get("booking_ref"), row.get("reason"),
                        )

            # ── Phase 2: 신규 후보 Apply 흐름 ────────────────────────────
            if new_candidates:
                depot_str = self._resolve_depot(region, depot)
                cust_id = COMPANY_CUSTOMER_ID.get(self.company)
                if not cust_id:
                    raise RuntimeError(f"지원하지 않는 선사: {self.company}")
                port_substr = PORT_OPTION_SUBSTR.get((region or "").upper())
                if not port_substr:
                    raise RuntimeError(f"지원하지 않는 region: {region}")

                await self._navigate_to_apply()
                await self._select_customer_id(cust_id)
                await self._select_port(port_substr)
                await self._select_depot(depot_str)
                await self._step_next()
                await self._step2_fill_units(new_candidates)
                await self._step_next()
                await self._parse_step3(results, depot_str)

                # Phase B — 자동 Confirm (사용자 요청 2026-05-21).
                # Step3 parse 후 booking_ref 없이 available=True 인 unit = 신규 발급 대상.
                # _precleared 플래그가 있으면 이미 발급된 케이스 → 재발급 방지로 제외.
                new_valid = [
                    c for c in new_candidates
                    if results.get(c, {}).get("available")
                    and not results.get(c, {}).get("booking_ref")
                    and not results.get(c, {}).get("_precleared")
                ]
                if new_valid:
                    try:
                        ppr_map = await self._confirm_redelivery_order(new_valid)
                        for unit, ppr in ppr_map.items():
                            if unit in results:
                                results[unit]["booking_ref"] = ppr
                                results[unit]["depot"] = (
                                    results[unit].get("depot") or depot_str
                                )
                    except Exception as exc:
                        logger.error("FLOR Phase B Confirm 실패: %s", exc)

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

        # 내부 가드 플래그 정리 (응답에 노출 X)
        for r in results.values():
            r.pop("_precleared", None)

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

    async def _navigate_to_status(self) -> None:
        """Redelivery Status 탭으로 전환. 탭이 안 보이면 REDELIV_URL 재진입 후 재시도."""
        status_tab = self.page.locator("text=Redelivery Status").first
        if await status_tab.count() == 0:
            await self.page.goto(REDELIV_URL, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(2.0)
            status_tab = self.page.locator("text=Redelivery Status").first
        await status_tab.click(timeout=5_000)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        await asyncio.sleep(1.5)
        # Unit Number input 이 DOM 에 붙을 때까지 대기 (visible 은 _fill_unit_input 가 처리).
        try:
            await self.page.wait_for_selector(
                'input[placeholder="Unit Number"]', state="attached", timeout=10_000
            )
        except Exception as exc:
            logger.warning("FLOR Status 탭: Unit Number input attach 대기 실패: %s", exc)

    async def _dump_status_tab(self) -> None:
        """S1 진단: Status 탭 진입 직후 DOM/Vue 상태를 로그로 캡처.

        환경변수 FLOR_STATUS_DUMP=1 일 때만 호출. 1회 사용 후 비활성화 권장.
        Status 탭에서 행이 안 잡히는 원인 가설을 좁히기 위함:
          ① Vue v-model 동기화 ② 폼 collapsed ③ default filter
          ④ Search By 라디오 잘못 선택 ⑤ 렌더 race condition
        """
        logger.info("FLOR [DUMP] Status 탭 진단 시작")
        dump = await self.page.evaluate(
            r"""() => {
                const out = {};
                // 1) 활성 탭 wrapper 의 innerHTML 첫 2000자
                const tabPanes = Array.from(document.querySelectorAll(
                    '.el-tabs__content .el-tab-pane, .tab-pane, [role="tabpanel"]'
                ));
                const activePane = tabPanes.find(el => {
                    const s = getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden';
                }) || tabPanes[0];
                out.active_pane_html = activePane
                    ? activePane.innerHTML.slice(0, 2000)
                    : '(no active pane)';

                // 2) Unit Number input 의 부모 체인 가시성 (10단계)
                const input = document.querySelector('input[placeholder="Unit Number"]');
                if (input) {
                    out.input_value = input.value;
                    out.input_chain = [];
                    let el = input, depth = 0;
                    while (el && depth < 10) {
                        const s = getComputedStyle(el);
                        out.input_chain.push({
                            tag: el.tagName,
                            cls: (el.className || '').toString().slice(0, 80),
                            display: s.display,
                            visibility: s.visibility,
                            opacity: s.opacity,
                            w: el.offsetWidth,
                            h: el.offsetHeight,
                        });
                        el = el.parentElement;
                        depth++;
                    }
                    // Vue 인스턴스 value 비교 (Vue 2 / Vue 3 둘 다 시도)
                    const v2 = input.__vue__;
                    const v3 = input.__vueParentComponent;
                    out.vue_value = null;
                    try {
                        if (v2 && 'value' in v2) out.vue_value = v2.value;
                        else if (v3 && v3.proxy && 'value' in v3.proxy)
                            out.vue_value = v3.proxy.value;
                    } catch (e) { out.vue_value = '(err: ' + e.message + ')'; }
                } else {
                    out.input_value = '(input not found)';
                }

                // 3) "Advanced Options" / "Search By" 류 라벨 검색
                const allText = (document.body.innerText || '').slice(0, 50000);
                out.has_advanced = /advanced\s*options?/i.test(allText);
                out.has_search_by = /search\s*by/i.test(allText);
                out.has_unit_no_label = /unit\s*(no\.?|number)/i.test(allText);
                out.has_redelivery_no_label = /redelivery\s*(no\.?|number)/i.test(allText);

                // 4) 라디오/탭 후보 (Unit No 선택 여부)
                const radios = Array.from(document.querySelectorAll(
                    'label.el-radio, label.el-radio-button, .el-tabs__item, [role="radio"], [role="tab"]'
                )).map(el => ({
                    text: (el.innerText || '').trim().slice(0, 50),
                    cls: (el.className || '').toString().slice(0, 80),
                    checked: el.classList.contains('is-checked')
                          || el.classList.contains('is-active')
                          || el.getAttribute('aria-selected') === 'true',
                }));
                out.radios = radios.slice(0, 20);

                // 5) 현재 보이는 결과 테이블 행 수
                const tbodyRows = Array.from(document.querySelectorAll('table tbody tr'));
                out.visible_rows = tbodyRows.length;
                out.first_row_cells = tbodyRows[0]
                    ? Array.from(tbodyRows[0].querySelectorAll('td')).map(td => (td.innerText || '').trim())
                    : null;

                // 6) collapse / panel 후보 — 펼침 가능 wrapper
                const panels = Array.from(document.querySelectorAll(
                    '.el-collapse-item, .panel, [aria-expanded]'
                )).map(el => ({
                    cls: (el.className || '').toString().slice(0, 80),
                    expanded: el.getAttribute('aria-expanded'),
                    is_active: el.classList.contains('is-active'),
                    text: (el.innerText || '').trim().slice(0, 60),
                })).slice(0, 10);
                out.panels = panels;

                return out;
            }"""
        )

        # 큰 덩어리는 잘라서 로그 (Railway 한 줄 제한 회피)
        logger.info("FLOR [DUMP] input_value=%r vue_value=%r", dump.get("input_value"), dump.get("vue_value"))
        logger.info("FLOR [DUMP] visible_rows=%s first_row=%s",
                    dump.get("visible_rows"), dump.get("first_row_cells"))
        logger.info("FLOR [DUMP] has_advanced=%s has_search_by=%s has_unit_no_label=%s has_redelivery_no_label=%s",
                    dump.get("has_advanced"), dump.get("has_search_by"),
                    dump.get("has_unit_no_label"), dump.get("has_redelivery_no_label"))
        for i, link in enumerate(dump.get("input_chain") or []):
            logger.info("FLOR [DUMP] input_chain[%d]=%s", i, link)
        for i, r in enumerate(dump.get("radios") or []):
            logger.info("FLOR [DUMP] radio[%d]=%s", i, r)
        for i, p in enumerate(dump.get("panels") or []):
            logger.info("FLOR [DUMP] panel[%d]=%s", i, p)
        pane = dump.get("active_pane_html") or ""
        # 2000자를 500자씩 4줄로 분할
        for i in range(0, len(pane), 500):
            logger.info("FLOR [DUMP] pane_html[%d:%d]=%s", i, i + 500, pane[i:i + 500])
        logger.info("FLOR [DUMP] Status 탭 진단 끝")

    async def _select_customer_id(self, cust_id: str) -> None:
        """Step1 Customer ID 라디오.

        Element UI radio는 `<label class="el-radio">…<span class="el-radio__label">TEXT</span></label>`
        구조. `<span>` 자체는 텍스트가 보여도 visibility 판정으로 Playwright click 이 timeout 됨.
        또한 사용자에 따라 옵션이 1개라 이미 선택돼 있는 케이스가 많음 (HA → HALINE 단독).
        → JS evaluate 로 (1) is-checked 확인 → 이미면 skip, (2) 아니면 label 클릭.
        """
        result = await self.page.evaluate(
            r"""(target) => {
                const targetU = target.toUpperCase();
                // 1) Element UI radio
                const labels = Array.from(document.querySelectorAll('label.el-radio, label.el-radio-button'));
                for (const lbl of labels) {
                    const text = (lbl.innerText || '').trim().toUpperCase();
                    if (text === targetU || text.includes(targetU)) {
                        const checked = lbl.classList.contains('is-checked')
                            || lbl.classList.contains('is-active');
                        if (!checked) lbl.click();
                        return { ok: true, already: checked, text };
                    }
                }
                // 2) Fallback: 일반 button/role=radio 텍스트 매칭
                const all = Array.from(document.querySelectorAll('button, [role="radio"], label'));
                for (const el of all) {
                    if (el.offsetParent === null) continue;
                    const text = (el.innerText || '').trim().toUpperCase();
                    if (text === targetU) {
                        el.click();
                        return { ok: true, already: false, text, via: 'fallback' };
                    }
                }
                return { ok: false };
            }""",
            cust_id,
        )
        if not result.get("ok"):
            raise RuntimeError(f"Customer ID '{cust_id}' 옵션 없음")
        logger.info(
            "FLOR customer_id %r → %s (already=%s)",
            cust_id, result.get("text"), result.get("already"),
        )
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

    async def status_detail(self, containers: list[str]) -> list[dict]:
        """Status 탭 단독 조회 (사용자 요청 2026-05-21).

        체크박스 선택된 precleared 행 등에 대해 Status 탭 search 만 별도 호출.
        결과 schema 는 query() 와 동일.

        주의: Status 탭 search 자체에 알려진 rows=0 버그가 있어 S2 패치 적용 전엔
        대부분 빈 결과("발급된 반납번호 없음 (신청 필요)") 반환 가능.
        """
        out: list[dict] = []
        deduped: list[str] = []
        seen: set[str] = set()
        for c in containers:
            k = (c or "").strip().upper()
            if not k or k in seen:
                continue
            seen.add(k)
            deduped.append(k)

        try:
            await self._navigate_to_status()
        except Exception as exc:
            logger.error("FLOR status_detail navigate 실패: %s", exc)
            return [self._error_row(c, f"Status 탭 진입 실패: {exc}") for c in deduped]

        for c in deduped:
            try:
                row = await self._search_one(c)
                available = bool(row.get("available"))
                out.append({
                    "container_no": c,
                    "available": available,
                    "depot": row.get("depot"),
                    "booking_ref": row.get("booking_ref"),
                    "over_caps": row.get("over_caps"),
                    "close_date": row.get("close_date"),
                    "reason": row.get("reason"),
                    "status": "available" if available else "unavailable",
                    "completed_date": None,
                })
            except Exception as exc:
                logger.warning("FLOR status_detail %s 실패: %s", c, exc)
                out.append(self._error_row(c, f"Status 조회 실패: {exc}"))
        return out

    async def _confirm_redelivery_order(self, valid_units: list[str]) -> dict[str, str]:
        """Step3 의 Confirm Redelivery Order 클릭 → 신규 PPR 발급.

        사용자 명시 요청에 따라 Step3 valid 가 있으면 자동 발급.
        memory `project_flor_flow`: Confirm 클릭 = 즉시 실 발급 (PPR<5자리> Open).

        안전장치:
          - 버튼 not found → 스킵 (로그)
          - is-disabled / disabled → 스킵 (로그)
          - valid_units 비어있으면 호출자가 미리 skip

        Returns:
          {unit: ppr_number} — 매핑 못 한 unit 은 빠짐.
        """
        if not valid_units:
            return {}

        # 1) Confirm 버튼 찾기 (텍스트 여러 변형 시도)
        btn = self.page.locator("button").filter(
            has_text="Confirm Redelivery Order"
        ).first
        if await btn.count() == 0:
            btn = self.page.locator("button").filter(has_text="Confirm").first
        if await btn.count() == 0:
            logger.warning("FLOR Confirm 버튼 미발견 — 발급 스킵")
            return {}

        # 2) disabled 체크 (Element UI: is-disabled 클래스 / 표준 disabled 속성)
        disabled = await btn.evaluate(
            "el => el.classList.contains('is-disabled') || el.disabled"
        )
        if disabled:
            logger.warning("FLOR Confirm 버튼 disabled — 발급 스킵 (사전 검증 실패 추정)")
            return {}

        # 3) 클릭 전 페이지 상태 스냅샷 (발급 전 PPR 셋트)
        text_before = await self.page.evaluate(
            "() => document.body.innerText || ''"
        )
        pprs_before = set(re.findall(r"PP[RF]\d+", text_before))

        # 4) 클릭
        logger.info(
            "FLOR Confirm Redelivery Order 클릭 (대상 %d units: %s)",
            len(valid_units), valid_units,
        )
        try:
            await btn.click(timeout=10_000)
        except Exception as exc:
            logger.error("FLOR Confirm 클릭 실패: %s", exc)
            return {}

        # 발급 후 화면 변화 대기 — 새 PPR 텍스트 등장 또는 네트워크 안정
        try:
            await self.page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        await asyncio.sleep(3.0)

        # 컴펌 다이얼로그 자동 닫기 (있으면)
        try:
            ok_btn = self.page.locator("button").filter(
                has_text=re.compile(r"^(OK|Confirm|Yes|확인)$", re.IGNORECASE)
            ).first
            if await ok_btn.count() > 0 and await ok_btn.is_visible():
                await ok_btn.click(timeout=3_000)
                await asyncio.sleep(2.0)
        except Exception:
            pass

        # 5) 응답 페이지에서 신규 PPR 추출
        text_after = await self.page.evaluate(
            "() => document.body.innerText || ''"
        )
        all_pprs_after = re.findall(r"PP[RF]\d+", text_after)
        # 중복 제거 + 순서 보존
        seen: set[str] = set()
        ordered_after: list[str] = []
        for p in all_pprs_after:
            if p not in seen:
                seen.add(p)
                ordered_after.append(p)
        new_pprs = [p for p in ordered_after if p not in pprs_before]

        logger.info(
            "FLOR Confirm 후 PPR 발견: 이전=%d 이후=%d 신규=%s",
            len(pprs_before), len(ordered_after), new_pprs,
        )

        # 6) unit → PPR 매핑
        # 페이지 텍스트에서 unit 번호 근처의 PPR 우선 시도 → 못 찾으면 순서 매핑.
        mapping: dict[str, str] = {}
        for unit in valid_units:
            idx = text_after.find(unit)
            if idx < 0:
                continue
            window = text_after[max(0, idx - 200): idx + 400]
            m = re.search(r"PP[RF]\d+", window)
            if m and m.group(0) in new_pprs:
                mapping[unit] = m.group(0)

        unmapped = [u for u in valid_units if u not in mapping]
        remaining_pprs = [p for p in new_pprs if p not in mapping.values()]
        if unmapped and remaining_pprs:
            # 잔여 PPR 을 unmapped 순서대로 1:1 할당 (best effort)
            for unit, ppr in zip(unmapped, remaining_pprs):
                mapping[unit] = ppr

        if unmapped and not remaining_pprs and new_pprs:
            # 신규 PPR 한 개를 여러 unit 이 공유하는 케이스 (같은 PPR 묶음)
            fallback = new_pprs[0]
            for unit in unmapped:
                mapping[unit] = fallback
                logger.info("FLOR %s: 잔여 PPR 없음 → 공유 PPR %s 할당", unit, fallback)

        if not mapping:
            # 매핑 실패 시 향후 분석 위해 화면 텍스트 일부 dump
            logger.warning(
                "FLOR Confirm 후 unit↔PPR 매핑 실패. text_after 앞 500자: %s",
                text_after[:500],
            )

        for unit, ppr in mapping.items():
            logger.info("FLOR %s: 신규 PPR 발급 → %s", unit, ppr)
        return mapping

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
        # Unit Detail (precleared) 영역은 Step 3 진입 후 가변 지연으로 그려질 수
        # 있어 _step_next 의 sleep(1.5) 만으로 부족한 경우가 있음. 페이지에
        # "Redelivery number:" 텍스트가 나타날 때까지 최대 4초 대기.
        # 끝까지 안 보이면 precleared 행이 없는 정상 케이스로 간주 → 통과.
        try:
            await self.page.wait_for_function(
                "() => (document.body.innerText || '').includes('Redelivery number:')",
                timeout=4_000,
            )
            logger.info("FLOR Step3: precleared 'Redelivery number:' 텍스트 감지됨")
        except Exception:
            logger.info("FLOR Step3: precleared 텍스트 없음 (4s timeout) — 신규 케이스로 진행")

        data = await self.page.evaluate(
            r"""() => {
                const out = { invalid: [], valid: [], dump: [], matched_split: [] };
                const REJECT_KEYWORDS = [
                    'incapable', 'cannot', 'over caps', 'over_caps',
                    'already', 'reject', 'invalid', 'previously', 'precleared'
                ];
                const UNIT_RE = /^[A-Z]{4}\d{6,7}$/;
                const PRECLEARED_RE = /already\s+precleared|Redelivery\s+number:\s*PP[RF]\d+/i;

                function isReasonCell(c, unit) {
                    if (!c || c === unit) return false;
                    if (UNIT_RE.test(c)) return false;
                    if (PRECLEARED_RE.test(c)) return true;
                    const cl = c.toLowerCase();
                    if (c.length >= 40) return true;
                    return REJECT_KEYWORDS.some(k => cl.includes(k));
                }

                // 모든 테이블의 모든 행을 한 스트림으로 수집 (순서 보존).
                const allRows = [];
                for (const tbl of document.querySelectorAll('table')) {
                    const rows = Array.from(tbl.querySelectorAll('tbody tr'));
                    for (const tr of rows) {
                        const cells = Array.from(tr.querySelectorAll('td'))
                            .map(td => (td.innerText || '').trim());
                        if (cells.length === 0) continue;
                        allRows.push(cells);
                    }
                }

                // 각 행 분류: same(unit+reason 같은 행) / unit-only / reason-only
                const sameRows = [];      // {unit, reason, cells, idx}
                const unitOnlyRows = [];  // {unit, cells, idx}
                const reasonOnlyRows = [];// {reason, cells, idx}

                for (let i = 0; i < allRows.length; i++) {
                    const cells = allRows[i];
                    out.dump.push(cells);
                    const unit = cells.find(c => UNIT_RE.test(c)) || '';
                    const reason = cells.find(c => isReasonCell(c, unit));
                    if (unit && reason) {
                        sameRows.push({ unit, reason, cells, idx: i });
                    } else if (unit) {
                        unitOnlyRows.push({ unit, cells, idx: i });
                    } else if (reason) {
                        reasonOnlyRows.push({ reason, cells, idx: i });
                    }
                }

                // 1차: 같은 행에 unit+reason 있는 행 → invalid
                for (const r of sameRows) {
                    out.invalid.push({ unit: r.unit, reason: r.reason, cells: r.cells });
                }

                // 2차: 다중 컨테이너 split 매칭 — Greedy nearest-neighbor (1:1).
                // 각 reason 을 미사용 unit-only 행 중 row index 가 가장 가까운 것과 매칭.
                // 같은 unit 이 두 reason 과 매칭되지 않도록 used set 사용.
                const usedUnits = new Set();
                for (const reasonRow of reasonOnlyRows) {
                    let best = null;
                    let bestDist = Infinity;
                    for (const unitRow of unitOnlyRows) {
                        if (usedUnits.has(unitRow.idx)) continue;
                        const dist = Math.abs(unitRow.idx - reasonRow.idx);
                        if (dist < bestDist) {
                            bestDist = dist;
                            best = unitRow;
                        }
                    }
                    if (!best) continue;
                    usedUnits.add(best.idx);
                    out.invalid.push({
                        unit: best.unit,
                        reason: reasonRow.reason,
                        cells: best.cells,
                    });
                    out.matched_split.push({
                        unit: best.unit,
                        reason: reasonRow.reason,
                        dist: bestDist,
                    });
                }

                // 3차: 매칭 안 된 unit-only 행 → valid (신규 발급 후보)
                for (const unitRow of unitOnlyRows) {
                    if (usedUnits.has(unitRow.idx)) continue;
                    out.valid.push({ unit: unitRow.unit, cells: unitRow.cells });
                }

                return out;
            }"""
        )

        invalid = data.get("invalid") or []
        valid = data.get("valid") or []
        matched_split = data.get("matched_split") or []
        logger.info(
            "FLOR Step3 parsed: invalid=%d valid=%d split_matched=%d (depot=%s)",
            len(invalid), len(valid), len(matched_split), depot_str,
        )
        for ms in matched_split:
            logger.info("FLOR Step3 split-match: unit=%s reason=%s",
                        ms.get("unit"), (ms.get("reason") or "")[:120])
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

    @staticmethod
    def _status_row_is_new_candidate(row: dict) -> bool:
        """Status 탭 search 결과가 '신규 후보' 인지 판정.

        - booking_ref 있음 (active Open PPR) → False (Status 결과 채택)
        - reason 에 '이미 반납됨' (Closed) → False (Status 결과 채택)
        - 그 외 (결과 없음 / 모두 VOID / 알 수 없음) → True (Apply 흐름으로 검증 필요)
        """
        if row.get("booking_ref"):
            return False
        reason = row.get("reason") or ""
        if "이미 반납됨" in reason:
            return False
        return True

    def _classify_reject(self, unit: str, reason: str) -> dict:
        """거부 reason 텍스트를 분류 (§5-3 / §5-4 / 일반).

        §5-3 이미 활성 PPR: reason 에 PPR 번호 + active/already/open 키워드 → 가능 처리
        §5-4 이전 완료    : reason 에 closed/previously + 날짜 → completed 처리
        그 외             : 일반 불가
        """
        r_lower = reason.lower()

        # §5-3: 이미 발급된 케이스 (precleared 포함).
        # 2026-05-21 사용자 요청 — PPR/Depot 추출 안 함. INFO 풀텍스트를 reason 에
        # 그대로 보존해 UI "조회 결과" 컬럼에 노출. _precleared 플래그로 Phase B
        # 자동 재발급 가드.
        ppr_match = re.search(r"PP[RF]\d+", reason)
        active_kw = any(k in r_lower for k in (
            "already", "active", "open redelivery", "existing redelivery", "precleared"
        ))
        if ppr_match and active_kw:
            logger.info(
                "FLOR %s: §5-3 precleared 감지 — PPR/Depot 추출 X, 풀텍스트 보존. ppr=%s",
                unit, ppr_match.group(0),
            )
            return {
                "available": True,
                "status": "available",
                "completed_date": None,
                "booking_ref": None,    # 추출 안 함 — 풀텍스트 reason 에 포함됨
                "depot": None,
                "over_caps": None,
                "close_date": None,
                "reason": reason,       # 풀텍스트 그대로
                "_precleared": True,    # Phase B 재발급 방지 가드
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

    async def _fill_unit_input(self, container: str) -> bool:
        """Unit Number 입력란에 값 주입.

        Playwright fill 의 visibility 판정이 Element UI 의 wrapping 으로 실패하는
        케이스(`element is not visible`)가 관찰됨. 다음 순서로 시도:
          1) scroll_into_view + 짧은 timeout fill
          2) 실패 시 JS 직접 value setter + input/change 이벤트 dispatch
             (Vue v-model 동기화용 — 호환성 위해 native setter 사용)
        """
        sel = 'input[placeholder="Unit Number"]'
        loc = self.page.locator(sel).first
        if await loc.count() == 0:
            return False
        try:
            await loc.scroll_into_view_if_needed(timeout=3_000)
        except Exception:
            pass
        try:
            await loc.fill(container, timeout=5_000)
            return True
        except Exception as exc:
            logger.info("FLOR Unit input visible-fill 실패 → JS fallback: %s", exc)

        ok = await self.page.evaluate(
            r"""(args) => {
                const el = document.querySelector(args.sel);
                if (!el) return false;
                el.focus();
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(el, args.val);
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }""",
            {"sel": sel, "val": container},
        )
        return bool(ok)

    async def _search_one(self, container: str) -> dict:
        """Status 탭에서 컨테이너 한 개 검색 후 결과 행 파싱."""
        if not await self._fill_unit_input(container):
            return self._error_row(container, "Unit Number 입력란 없음")
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

        depot_full = details.get("depot_name") or None
        expiry     = details.get("expiry_date") or None
        open_cap   = details.get("open_cap")  # Contracts 테이블의 Open CAP (잔여 캡)
        off_hire   = details.get("off_hire_date") or None

        # depot 표시는 코드만: "(KRINC04) SeungJin ..." → "KRINC04"
        depot: str | None = None
        if depot_full:
            m = re.search(r"\(([A-Z0-9]+)\)", depot_full)
            depot = m.group(1) if m else depot_full

        try:
            over_caps = int(open_cap) if open_cap and str(open_cap).isdigit() else None
        except (ValueError, TypeError):
            over_caps = None

        # 가용 판정 / 상태 분기
        is_open = "open" in status.lower()
        is_closed = "closed" in status.lower()
        is_void = "void" in status.lower() or "cancel" in status.lower()
        available = is_open
        status_val = "available" if is_open else ("completed" if is_closed else "unavailable")

        reason: str | None = None
        if not available:
            if is_closed:
                # 사용자 요청 2026-05-21: 반납완료 행의 조회 결과는
                # "OFF HIRE DATE YYYY-MM-DD" 포맷으로 통일.
                reason = (
                    f"OFF HIRE DATE {off_hire}" if off_hire
                    else "이미 반납됨 (Closed)"
                )
            elif is_void:
                reason = "취소된 예약 (VOID)"
            else:
                reason = f"발급 상태: {status or '미상'}"

        # 유효기간 우선순위: Expiry Date > Order Date
        date = expiry or parsed.get("order_date", "")

        return {
            "container_no": container,
            "available": available,
            "status": status_val,
            "completed_date": _to_mmdd(off_hire) if is_closed and off_hire else None,
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

            // per-unit 서브테이블에서 Off Hire Date 추출
            // 컬럼: #, Unit Number, Equip. Type, Move Date, Off Hire Date, Actions
            let offHireDate = null;
            for (const tbl of document.querySelectorAll('table')) {
                const headers = Array.from(tbl.querySelectorAll('thead th, thead td'))
                    .map(th => (th.innerText || '').trim());
                const idx = headers.findIndex(h => /^off\s*hire\s*date$/i.test(h));
                if (idx >= 0) {
                    const firstRow = tbl.querySelector('tbody tr');
                    if (firstRow) {
                        const cells = firstRow.querySelectorAll('td');
                        if (idx < cells.length) {
                            offHireDate = (cells[idx].innerText || '').trim();
                        }
                    }
                    break;
                }
            }

            return {
                expiry_date: valueByLabel('Expiry Date', 'EXPIRY DATE', 'Expiry'),
                depot_name: valueByLabel('Depot Name', 'DEPOT NAME', 'Depot'),
                open_cap: openCap,
                off_hire_date: offHireDate,
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
