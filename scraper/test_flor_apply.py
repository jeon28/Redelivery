"""FLOR — Apply Redelivery E2E 테스트 (실 발급 가능 케이스).

사용자 명시 승인: 발급 후 수동 원상복귀.
입력값: HA / FSCU5896157 / BUSAN

흐름:
  1. 로그인 (슬라이더 + Sign-in)
  2. /func/redelivery#/ 진입 (Apply Redelivery 기본 탭)
  3. Step 1: Customer ID 라디오 (첫 옵션) + Port (BUSAN) + Depot (첫 옵션)
  4. Step 2: 컨테이너 번호 입력
  5. Step 3: Confirm Redelivery Order → 발급
  6. 결과 화면 + Status 탭에서 PPR 번호 확인

사용: cd scraper && python test_flor_apply.py
"""
import asyncio
import json
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

load_dotenv()

LOGIN_URL    = "https://www.florens.com/official-pc/login#/"
REDELIV_URL  = "https://www.florens.com/func/redelivery#/"
HEADLESS     = True

# ── 입력값 ─────────────────────────────────────────────
COMPANY    = "HA"
TEST_UNIT  = "FSCU5896157"
TEST_PORT  = "PUSAN"   # Florens 표기 (BUSAN 아님)
TEST_DEPOT = None     # None = 드롭다운 첫 옵션 자동 선택
EXECUTE_BOOKING = True   # ⚠ True 시 Confirm Redelivery Order 클릭 (실 발급)
# ──────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR   = REPO_ROOT / "FLOR" / "_inspect"
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def slider_drag(page: Page) -> bool:
    """슬라이더 좌→우 드래그 (ease-out + 약간의 Y noise)."""
    rects = await page.evaluate("""() => {
        const btn = document.querySelector('.slider-button');
        const track = document.querySelector('.slider-track') || document.querySelector('.slider-container');
        const br = btn && btn.getBoundingClientRect();
        const tr = track && track.getBoundingClientRect();
        return {
            btn: br ? { x: br.x, y: br.y, w: br.width, h: br.height } : null,
            track: tr ? { x: tr.x, y: tr.y, w: tr.width, h: tr.height } : null,
        };
    }""")
    if not rects["btn"] or not rects["track"]:
        return False
    br, tr = rects["btn"], rects["track"]
    sx = br["x"] + br["w"] / 2
    sy = br["y"] + br["h"] / 2
    ex = tr["x"] + tr["w"] - br["w"] / 2
    await page.mouse.move(sx, sy)
    await page.mouse.down()
    for i in range(1, 31):
        progress = i / 30
        eased = 1 - (1 - progress) ** 2
        cx = sx + (ex - sx) * eased
        cy = sy + random.uniform(-1.5, 1.5)
        await page.mouse.move(cx, cy)
        await asyncio.sleep(0.03)
    await page.mouse.up()
    return True


async def login(page: Page, user: str, pw: str) -> bool:
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    try:
        await page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:
        pass
    await page.wait_for_timeout(2500)

    pw_el = await page.query_selector('input[type="password"]')
    user_el = None
    for inp in await page.query_selector_all('input'):
        t = await inp.get_attribute("type")
        if t in ("password", "hidden", "checkbox", "radio", "submit", "button"):
            continue
        user_el = inp
        break
    if not pw_el or not user_el:
        print("  로그인 필드 못 찾음")
        return False
    await user_el.fill(user)
    await pw_el.fill(pw)
    await page.wait_for_timeout(500)
    if not await slider_drag(page):
        print("  슬라이더 드래그 실패")
        return False
    await page.wait_for_timeout(1500)

    if "/login" in page.url:
        signin = page.locator("button").filter(has_text="Sign-in").first
        if await signin.count() == 0:
            signin = page.locator("button").filter(has_text="Sign In").first
        if await signin.count() > 0:
            await signin.click()
            try:
                await page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
    await page.wait_for_timeout(2500)
    return "/login" not in page.url


async def el_select_pick(page: Page, input_selector: str, option_text: str | None) -> dict:
    """Element UI el-select 헬퍼.
    input_selector: 표시용 input의 셀렉터 (placeholder 등으로 지정)
    option_text: 매칭할 옵션 텍스트 (None이면 첫 옵션 선택)
    """
    # 1) 입력 클릭 → 드롭다운 열기
    el = page.locator(input_selector).first
    if await el.count() == 0:
        return {"ok": False, "error": "input not found: " + input_selector}
    await el.click()
    await page.wait_for_timeout(800)

    # 2) 옵션 패널에서 선택
    # 보이는 패널의 li.el-select-dropdown__item 중에서 매칭
    if option_text:
        opt = page.locator('.el-select-dropdown:not([style*="display: none"]) li.el-select-dropdown__item').filter(
            has_text=option_text
        ).first
    else:
        opt = page.locator('.el-select-dropdown:not([style*="display: none"]) li.el-select-dropdown__item').first
    if await opt.count() == 0:
        # 패널 스타일 필터 없이 시도
        if option_text:
            opt = page.locator('li.el-select-dropdown__item').filter(has_text=option_text).first
        else:
            opt = page.locator('li.el-select-dropdown__item').first
    if await opt.count() == 0:
        # 옵션 후보 디버깅용 dump
        opts = await page.evaluate("""() => Array.from(document.querySelectorAll('li.el-select-dropdown__item'))
            .filter(li => li.offsetParent !== null)
            .map(li => (li.innerText || '').trim())""")
        return {"ok": False, "error": "option not found", "looked_for": option_text, "visible_opts": opts[:30]}

    selected_text = (await opt.inner_text()).strip()
    await opt.click()
    await page.wait_for_timeout(600)
    return {"ok": True, "selected": selected_text}


async def main():
    user = os.getenv(f"{COMPANY}_FLOR_ID")
    pw   = os.getenv(f"{COMPANY}_FLOR_PW")
    if not user or not pw:
        print(f"ERROR: {COMPANY}_FLOR_ID/PW 누락")
        sys.exit(1)
    print(f"계정: {COMPANY} ({user[:3]}***)")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()

        print("\n[1] 로그인")
        if not await login(page, user, pw):
            await page.screenshot(path=str(OUT_DIR / "login_fail.png"), full_page=True)
            print(f"  로그인 실패: {page.url}"); await browser.close(); sys.exit(2)
        print(f"  성공: {page.url}")

        print(f"\n[2] {REDELIV_URL} 진입")
        await page.goto(REDELIV_URL, wait_until="networkidle", timeout=30_000)
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(OUT_DIR / "apply_01_step1.png"), full_page=True)

        # Step 1: Customer ID 라디오 (첫 옵션) + Port + Depot
        print("\n[3] Step 1 — Customer ID / Port / Depot")
        # Customer ID 라디오 (Element UI .el-radio__original)
        radios = await page.query_selector_all('input.el-radio__original[type="radio"]')
        if radios:
            try:
                # 첫 라디오 클릭 (label 클릭이 더 안정적)
                label = await radios[0].evaluate("e => e.closest('.el-radio') ? e.closest('.el-radio').querySelector('span.el-radio__label')?.innerText : null")
                print(f"  Customer ID 라디오 첫 옵션: {label}")
                # 라디오의 부모 클릭
                await page.evaluate("""() => {
                    const r = document.querySelector('input.el-radio__original[type=radio]');
                    if (r) {
                        const wrap = r.closest('.el-radio') || r.parentElement;
                        wrap.click();
                    }
                }""")
                await page.wait_for_timeout(500)
            except Exception as e:
                print(f"  Customer ID 라디오 클릭 실패: {e}")

        # Port — 우선 전체 옵션 덤프
        port_input = page.locator(
            'input[placeholder="Please select the port according to the terms of contract"]'
        ).first
        if await port_input.count() == 0:
            print("  Port input 못 찾음"); await browser.close(); sys.exit(3)
        await port_input.click()
        await page.wait_for_timeout(800)
        all_port_opts = await page.evaluate("""() => Array.from(document.querySelectorAll('li.el-select-dropdown__item'))
            .filter(li => li.offsetParent !== null)
            .map(li => (li.innerText || '').trim())""")
        print(f"  Port 가용 옵션 ({len(all_port_opts)}개):")
        # 한국 KR 코드 또는 BUSAN/INCHEON 키워드 추출
        kr_opts = [o for o in all_port_opts if 'KR' in o.upper() or 'BUSAN' in o.upper() or 'INCH' in o.upper() or 'KOREA' in o.upper()]
        print(f"  한국 관련: {kr_opts}")
        for o in all_port_opts[:50]:
            print(f"    - {o}")
        if len(all_port_opts) > 50:
            print(f"    ... (총 {len(all_port_opts)}개 중 50개만 표시)")

        # 매칭 시도
        if not any(TEST_PORT.upper() in o.upper() for o in all_port_opts):
            print(f"\n  ❌ '{TEST_PORT}'와 일치하는 옵션 없음 — 자동 종료")
            await page.screenshot(path=str(OUT_DIR / "apply_02_no_port.png"), full_page=True)
            await browser.close(); sys.exit(99)

        # 옵션 클릭 (스크롤 먼저)
        opt = page.locator('li.el-select-dropdown__item').filter(
            has_text=TEST_PORT
        ).first
        await opt.scroll_into_view_if_needed()
        await page.wait_for_timeout(300)
        await opt.click(force=True)
        await page.wait_for_timeout(800)
        print(f"  Port 선택 완료: {TEST_PORT}")
        await page.wait_for_timeout(1000)

        # Depot (TEST_DEPOT=None이면 첫 옵션)
        r = await el_select_pick(page,
            'input[placeholder="Please select"]',
            TEST_DEPOT)
        print(f"  Depot: {r}")
        if not r.get("ok"):
            await page.screenshot(path=str(OUT_DIR / "apply_03_depot_fail.png"), full_page=True)
            await browser.close(); sys.exit(4)
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUT_DIR / "apply_04_step1_filled.png"), full_page=True)

        # Next → Step 2
        print("\n[4] Next → Step 2")
        next_btn = page.locator("button").filter(has_text="Next").first
        if await next_btn.count() == 0:
            print("  Next 버튼 없음")
            await browser.close(); sys.exit(5)
        await next_btn.click()
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(OUT_DIR / "apply_05_step2.png"), full_page=True)
        # Step 2 페이지 인스펙션 — 어떤 입력 위젯인지 파악
        step2_inputs = await page.evaluate("""() => Array.from(document.querySelectorAll('input, textarea')).map(e => ({
            tag: e.tagName, type: e.type || null,
            placeholder: e.placeholder || null,
            class: e.className || null,
        })).filter(e => e.tag === 'TEXTAREA' || (e.type && e.type !== 'hidden' && e.type !== 'radio'))""")
        print(f"  Step 2 입력 후보:")
        for inp in step2_inputs:
            print(f"    - {inp}")

        # Container number 입력 추정
        # 일단 placeholder/class로 textarea 또는 visible text input 탐색
        cont_el = await page.query_selector('textarea')
        if not cont_el:
            cont_el = await page.query_selector('input[placeholder*="container" i]')
        if not cont_el:
            # fallback: 가장 큰 텍스트 인풋
            cont_el = await page.query_selector('input.el-input__inner:not([readonly])')
        if not cont_el:
            print("  컨테이너 입력 필드 못 찾음")
            await page.screenshot(path=str(OUT_DIR / "apply_06_step2_nofield.png"), full_page=True)
            await browser.close(); sys.exit(6)

        await cont_el.fill(TEST_UNIT)
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUT_DIR / "apply_06_step2_filled.png"), full_page=True)
        print(f"  컨테이너 입력 완료: {TEST_UNIT}")

        # Next → Step 3
        print("\n[5] Next → Step 3")
        next_btn2 = page.locator("button").filter(has_text="Next").first
        if await next_btn2.count() == 0:
            print("  Next(2) 버튼 없음")
            await browser.close(); sys.exit(7)
        await next_btn2.click()
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(OUT_DIR / "apply_07_step3.png"), full_page=True)
        (OUT_DIR / "apply_07_step3.html").write_text(await page.content(), encoding="utf-8")

        # Step 3: Confirm Redelivery Order
        if EXECUTE_BOOKING:
            print("\n[6] ⚠ Confirm Redelivery Order 클릭 (실 발급)")
            confirm_btn = page.locator("button").filter(has_text="Confirm Redelivery").first
            if await confirm_btn.count() == 0:
                print("  Confirm 버튼 없음")
                await browser.close(); sys.exit(8)
            # disabled 여부 확인
            is_disabled = await confirm_btn.evaluate("e => e.classList.contains('is-disabled') || e.disabled")
            if is_disabled:
                print("  Confirm 버튼 disabled — 발급 안 함")
            else:
                await confirm_btn.click()
                await page.wait_for_timeout(3000)
                await page.screenshot(path=str(OUT_DIR / "apply_08_confirmed.png"), full_page=True)
                (OUT_DIR / "apply_08_confirmed.html").write_text(await page.content(), encoding="utf-8")
                print(f"  Confirm 후 URL: {page.url}")
        else:
            print("  EXECUTE_BOOKING=False — Confirm 스킵")

        # Status 탭에서 새 PPR 확인
        print(f"\n[7] Status 탭에서 {TEST_UNIT} 검색")
        await page.goto(REDELIV_URL, wait_until="networkidle", timeout=30_000)
        await page.wait_for_timeout(2000)
        status_tab = page.locator("text=Redelivery Status").first
        if await status_tab.count() > 0:
            await status_tab.click()
            await page.wait_for_timeout(1500)
            unit_radio = page.locator("text=Unit No.").first
            if await unit_radio.count() > 0:
                await unit_radio.click()
                await page.wait_for_timeout(500)
            unit_input = page.locator('input[placeholder="Unit Number"]').first
            if await unit_input.count() > 0:
                await unit_input.fill(TEST_UNIT)
                await page.wait_for_timeout(300)
            search_btn = page.locator("button").filter(has_text="Search").first
            await search_btn.click()
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(OUT_DIR / "apply_09_status.png"), full_page=True)
            rows = await page.evaluate(r"""() => Array.from(document.querySelectorAll('table tbody tr'))
                .map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim()))
                .filter(r => r.length > 0)""")
            print(f"  결과 행 수: {len(rows)}")
            for i, r in enumerate(rows[:5]):
                print(f"  ROW {i}: {r}")

        print(f"\n산출물: {OUT_DIR}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
