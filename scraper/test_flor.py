"""FLOR (Florens) 사이트 분석 — Phase 1: 로그인 페이지 구조 캡처.

목적: 슬라이더 유형 파악 + 로그인 폼 구조 인스펙션.
안전 가드: 로그인 시도 안 함. 페이지 진입 + 스크린샷 + DOM 덤프만.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

load_dotenv()

LOGIN_URL = "https://www.florens.com/official-pc/login#/"
HEADLESS  = True

# ── 입력값 ─────────────────────────────────────────────
COMPANY        = "HA"           # SK 또는 HA
TEST_UNIT_NO   = "DFSU7591613"  # HA 반납완료 (사용자 제공) — Status 탭 Unit No. 검색용
# ──────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR   = REPO_ROOT / "FLOR" / "_inspect"
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def dump_page(page: Page, label: str) -> dict:
    data = await page.evaluate("""() => {
        const pick = (el) => ({
            tag: el.tagName, type: el.type || null,
            id: el.id || null, name: el.name || null,
            class: el.className || null,
            placeholder: el.placeholder || null,
            text: (el.innerText || el.value || '').toString().slice(0, 200),
        });
        // 슬라이더 후보 (드래그 가능 요소 / canvas / verify 키워드)
        const sliders = Array.from(document.querySelectorAll(
            '[class*="slid"], [class*="captcha"], [class*="verify"], [class*="puzzle"], [class*="drag"], canvas'
        )).map(e => ({
            ...pick(e),
            rect: (() => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; })(),
        }));
        // iframe 도 슬라이더가 들어가는 경우 많음
        const iframes = Array.from(document.querySelectorAll('iframe')).map(f => ({
            src: f.src, id: f.id, name: f.name, class: f.className,
        }));
        return {
            url: location.href,
            title: document.title,
            forms: Array.from(document.querySelectorAll('form')).map(f => ({
                id: f.id, name: f.name, action: f.action, method: f.method,
            })),
            labels: Array.from(document.querySelectorAll('label')).slice(0, 100).map(l => ({
                for: l.htmlFor || null, text: (l.innerText || '').slice(0, 200),
            })),
            inputs: Array.from(document.querySelectorAll('input')).map(pick),
            selects: Array.from(document.querySelectorAll('select')).map(pick),
            buttons: Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], a.btn')).map(pick),
            sliders,
            iframes,
            body_text_preview: (document.body.innerText || '').slice(0, 3000),
        };
    }""")
    (OUT_DIR / f"{label}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()

        print(f"[1] 로그인 페이지 진입: {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        # SPA 라우팅 + 슬라이더 로딩 대기
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        await page.screenshot(path=str(OUT_DIR / "01_login_page.png"), full_page=True)
        d = await dump_page(page, "01_login_form")
        (OUT_DIR / "01_login_form.html").write_text(await page.content(), encoding="utf-8")

        print(f"  URL: {page.url}")
        print(f"  Title: {d['title']}")
        print(f"  forms={len(d['forms'])} inputs={len(d['inputs'])} buttons={len(d['buttons'])}")
        print(f"  iframes={len(d['iframes'])}")
        print(f"  슬라이더 후보 ({len(d['sliders'])}개):")
        for s in d['sliders'][:10]:
            print(f"    - tag={s['tag']} class='{(s['class'] or '')[:80]}' rect={s['rect']}")
        if d['iframes']:
            print(f"  iframe 목록:")
            for f in d['iframes'][:5]:
                print(f"    - src={f['src'][:120]} class='{(f['class'] or '')[:60]}'")

        # Phase 2: 로그인 시도 (자격증명 입력 + 슬라이더 드래그)
        user = os.getenv(f"{COMPANY}_FLOR_ID")
        pw   = os.getenv(f"{COMPANY}_FLOR_PW")
        if not user or not pw:
            print(f"\n[Phase2 skip] {COMPANY}_FLOR_ID/PW 누락")
            await browser.close()
            return

        print(f"\n[Phase2] 로그인 시도 ({COMPANY}: {user[:3]}***)")
        # 입력 필드 — placeholder/label로 매칭
        # inputs 두 개: 첫 번째가 ID, 두 번째가 password (input[type=password] 우선)
        pw_el = await page.query_selector('input[type="password"]')
        # ID 입력은 같은 form 내 첫 번째 text/visible input
        user_el = None
        for inp in await page.query_selector_all('input'):
            if inp == pw_el:
                continue
            t = await inp.get_attribute("type")
            if t in ("password", "hidden", "checkbox", "radio", "submit", "button"):
                continue
            user_el = inp
            break

        if not user_el or not pw_el:
            print("  입력 필드 탐지 실패")
            await browser.close()
            return

        await user_el.fill(user)
        await pw_el.fill(pw)
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "02_credentials_filled.png"), full_page=True)

        # 슬라이더 드래그
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
        print(f"  슬라이더 영역: {rects}")
        if not rects.get("btn") or not rects.get("track"):
            print("  슬라이더 요소 못 찾음 — 드래그 스킵")
        else:
            import random
            br, tr = rects["btn"], rects["track"]
            sx = br["x"] + br["w"] / 2
            sy = br["y"] + br["h"] / 2
            ex = tr["x"] + tr["w"] - br["w"] / 2
            ey = sy
            print(f"  드래그: ({sx:.1f},{sy:.1f}) → ({ex:.1f},{ey:.1f})  거리={ex-sx:.1f}px")

            await page.mouse.move(sx, sy)
            await page.mouse.down()
            steps = 30
            for i in range(1, steps + 1):
                progress = i / steps
                # ease-out
                eased = 1 - (1 - progress) ** 2
                cx = sx + (ex - sx) * eased
                cy = sy + random.uniform(-1.5, 1.5)
                await page.mouse.move(cx, cy)
                await asyncio.sleep(0.03)
            await page.mouse.up()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUT_DIR / "03_after_slide.png"), full_page=True)

        # 로그인 자동 진행 여부 확인 — 안 됐으면 Sign-in 버튼 클릭
        await page.wait_for_timeout(2000)
        if "/login" in page.url:
            print(f"  아직 로그인 페이지 — Sign-in 버튼 시도")
            signin = page.locator("button").filter(has_text="Sign-in").first
            if await signin.count() == 0:
                signin = page.locator("button").filter(has_text="Sign In").first
            if await signin.count() > 0:
                await signin.click()
                try:
                    await page.wait_for_load_state("networkidle", timeout=20_000)
                except Exception:
                    pass
            else:
                print("  Sign-in 버튼 없음")

        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(OUT_DIR / "04_after_login.png"), full_page=True)
        await dump_page(page, "04_after_login")
        (OUT_DIR / "04_after_login.html").write_text(await page.content(), encoding="utf-8")
        print(f"  로그인 후 URL: {page.url}")

        # Phase 3: Redelivery 페이지 직접 진입 (메뉴 클릭은 hover 드롭다운으로 추정)
        print(f"\n[Phase3] /func/redelivery 직접 진입")
        await page.goto("https://www.florens.com/func/redelivery",
                        wait_until="networkidle", timeout=30_000)
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(OUT_DIR / "05_redelivery_page.png"), full_page=True)
        await dump_page(page, "05_redelivery_page")
        (OUT_DIR / "05_redelivery_page.html").write_text(await page.content(), encoding="utf-8")
        print(f"  Redelivery URL: {page.url}")

        # Phase 4: Redelivery Status 탭 클릭 → "Unit No." 라디오 → TEST_UNIT_NO 검색
        print(f"\n[Phase4] 'Redelivery Status' 탭 → Unit No. 검색 ({TEST_UNIT_NO})")
        status_tab = page.locator("text=Redelivery Status").first
        if await status_tab.count() == 0:
            print("  Redelivery Status 탭 못 찾음")
        else:
            await status_tab.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUT_DIR / "06_status_tab.png"), full_page=True)

            # "Unit No." 라디오 클릭
            unit_radio = page.locator("text=Unit No.").first
            if await unit_radio.count() > 0:
                await unit_radio.click()
                await page.wait_for_timeout(800)

            # Unit Number 입력
            unit_input = page.locator('input[placeholder="Unit Number"]').first
            if await unit_input.count() > 0:
                await unit_input.fill(TEST_UNIT_NO)
                await page.wait_for_timeout(300)

            # Search 클릭
            search_btn = page.locator("button").filter(has_text="Search").first
            if await search_btn.count() > 0:
                await search_btn.click()
                try:
                    await page.wait_for_load_state("networkidle", timeout=20_000)
                except Exception:
                    pass
                await page.wait_for_timeout(2500)
                await page.screenshot(path=str(OUT_DIR / "07_status_search.png"), full_page=True)
                await dump_page(page, "07_status_search")
                (OUT_DIR / "07_status_search.html").write_text(await page.content(), encoding="utf-8")

                # 결과 테이블 데이터 추출 시도
                rows = await page.evaluate(r"""() => {
                    const cells = (tr) => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim());
                    return Array.from(document.querySelectorAll('table tbody tr'))
                        .map(cells)
                        .filter(r => r.length > 0);
                }""")
                print(f"  결과 행 수: {len(rows)}")
                for i, r in enumerate(rows[:5]):
                    print(f"  ROW {i}: {r}")
                # 컬럼 헤더
                headers = await page.evaluate(r"""() => {
                    const ths = document.querySelectorAll('table thead th, table thead td');
                    return Array.from(ths).map(th => (th.innerText || '').trim()).filter(t => t);
                }""")
                print(f"  헤더: {headers}")

        print(f"\n산출물: {OUT_DIR}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
