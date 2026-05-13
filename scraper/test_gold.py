"""GOLD (Touax) 사이트 구조 분석 스크립트 — Phase 1.

목적: 로그인 → 대시보드 캡처 + 메뉴 구조 + 반납 관련 링크 탐지.
안전 가드:
  - 어떤 submit/예약 버튼도 클릭하지 않음
  - 자격증명 값은 출력에 노출하지 않음

산출물: GOLD/_inspect/ 에 스크린샷 + 폼/링크 구조 JSON 저장.
사용: cd scraper && python test_gold.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

load_dotenv()

LOGIN_URL = "https://www.touax-container.com/login"
HEADLESS  = True

# ── 입력값 ─────────────────────────────────────────────
COMPANY = "SK"   # "SK" 또는 "HA"
# ──────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR   = REPO_ROOT / "GOLD" / "_inspect"
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def dump_page(page: Page, label: str) -> dict:
    """페이지의 폼/링크/메뉴/제목/본문 일부를 JSON으로 추출."""
    data = await page.evaluate("""() => {
        const pick = (el) => ({
            tag: el.tagName, type: el.type || null,
            id: el.id || null, name: el.name || null,
            class: el.className || null,
            placeholder: el.placeholder || null,
            text: (el.innerText || el.value || '').toString().slice(0, 200),
        });
        return {
            url: location.href,
            title: document.title,
            forms: Array.from(document.querySelectorAll('form')).map(f => ({
                id: f.id, name: f.name, action: f.action, method: f.method,
            })),
            labels: Array.from(document.querySelectorAll('label')).slice(0, 200).map(l => ({
                for: l.htmlFor || null, text: (l.innerText || '').slice(0, 200),
            })),
            inputs: Array.from(document.querySelectorAll('input')).map(pick),
            selects: Array.from(document.querySelectorAll('select')).map(s => ({
                ...pick(s),
                options: Array.from(s.options).map(o => ({ value: o.value, text: o.text })),
            })),
            textareas: Array.from(document.querySelectorAll('textarea')).map(pick),
            buttons: Array.from(document.querySelectorAll('button, input[type=submit], input[type=button]')).map(pick),
            // 네비게이션/메뉴/링크 — 반납 메뉴 찾기 위한 데이터
            anchors: Array.from(document.querySelectorAll('a[href]')).slice(0, 300).map(a => ({
                text: (a.innerText || '').trim().slice(0, 120),
                href: a.href,
                role: a.getAttribute('role') || null,
            })).filter(a => a.text || a.href),
            body_text_preview: (document.body.innerText || '').slice(0, 5000),
        };
    }""")
    (OUT_DIR / f"{label}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


async def auto_login(page: Page, user: str, pw: str) -> bool:
    """password 필드 탐지 → 같은 form 내 text/email/no-type input을 username으로."""
    pw_els = await page.query_selector_all('input[type="password"]')
    if not pw_els:
        print("  ERROR: password 필드 없음")
        return False
    pw_el = pw_els[0]
    user_els = await page.query_selector_all(
        'input[type="text"], input[type="email"], input:not([type])'
    )
    if not user_els:
        print("  ERROR: username 필드 없음")
        return False
    await user_els[0].fill(user)
    await pw_el.fill(pw)
    await pw_el.press("Enter")
    try:
        await page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:
        pass
    return "/login" not in page.url


async def main():
    user = os.getenv(f"{COMPANY}_GOLD_ID")
    pw   = os.getenv(f"{COMPANY}_GOLD_PW")
    if not user or not pw:
        print(f"ERROR: {COMPANY}_GOLD_ID / {COMPANY}_GOLD_PW 누락")
        sys.exit(1)
    print(f"계정: {COMPANY} GOLD ({user[:3]}***)")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()

        print("\n[1] 로그인 페이지 진입")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.screenshot(path=str(OUT_DIR / "01_login_page.png"), full_page=True)
        d = await dump_page(page, "01_login_form")
        print(f"  URL: {page.url}")
        print(f"  forms={len(d['forms'])}, inputs={len(d['inputs'])}, buttons={len(d['buttons'])}")

        print("\n[2] 로그인 시도")
        ok = await auto_login(page, user, pw)
        await page.screenshot(path=str(OUT_DIR / "02_after_login.png"), full_page=True)
        if not ok:
            print(f"  로그인 실패 — 현재 URL: {page.url}")
            await dump_page(page, "02_login_failed")
            await browser.close()
            sys.exit(2)
        print(f"  로그인 성공 — 현재 URL: {page.url}")

        print("\n[3] 진입 후 페이지 덤프 + 메뉴/링크 캡처")
        d2 = await dump_page(page, "03_landing")
        kw = ("redeliver", "return", "redelivery", "off-hire", "offhire", "release", "reservation")
        candidates = [a for a in d2["anchors"]
                      if any(k in (a.get("text") or "").lower() or k in (a.get("href") or "").lower() for k in kw)]
        print(f"  반납 관련 링크 후보 ({len(candidates)}개):")
        for a in candidates[:30]:
            print(f"    - text='{a['text']}' href={a['href']}")

        (OUT_DIR / "03_landing.html").write_text(await page.content(), encoding="utf-8")

        # Phase 2: 반납 페이지 진입 + 인스펙션 (Submit 버튼은 절대 클릭 안 함)
        for label, url in [
            ("04_off_hire",          "https://www.touax-container.com/off-hire"),
            ("05_off_hire_history",  "https://www.touax-container.com/off-hire/history"),
            ("06_off_hire_ref",      "https://www.touax-container.com/off-hire-ref-check"),
        ]:
            print(f"\n[Phase2:{label}] {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception as exc:
                print(f"  goto 예외: {exc}")
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUT_DIR / f"{label}.png"), full_page=True)
            d = await dump_page(page, label)
            (OUT_DIR / f"{label}.html").write_text(await page.content(), encoding="utf-8")
            print(f"  URL: {page.url}")
            print(f"  forms={len(d['forms'])} inputs={len(d['inputs'])} selects={len(d['selects'])} textareas={len(d['textareas'])} buttons={len(d['buttons'])}")
            for s in d['selects'][:6]:
                name = s.get('name') or s.get('id') or '?'
                print(f"    select [{name}] options={len(s.get('options', []))}")

        # Phase 3: history → 첫 RA##### 링크 클릭 (JS 트리거) → 상세 영역 캡처
        print("\n[Phase3] history → 첫 RA##### 링크 클릭")
        await page.goto("https://www.touax-container.com/off-hire/history",
                        wait_until="networkidle", timeout=30_000)
        await page.wait_for_timeout(1500)

        ra_locator = page.locator("a").filter(
            has_text=__import__("re").compile(r"^RA\d+$")
        )
        ra_count = await ra_locator.count()
        if ra_count == 0:
            print("  RA 링크 없음")
        else:
            ra_text = (await ra_locator.first.inner_text()).strip()
            print(f"  RA 링크 {ra_count}개. 첫 항목 '{ra_text}' 클릭")
            await ra_locator.first.click()
            await page.wait_for_timeout(2500)
            await page.screenshot(path=str(OUT_DIR / "07_history_detail.png"), full_page=True)
            await dump_page(page, "07_history_detail")
            (OUT_DIR / "07_history_detail.html").write_text(
                await page.content(), encoding="utf-8"
            )
            print(f"  현재 URL: {page.url}")

        # Phase 4: off-hire-ref-check 로 컨테이너 조회 (read-only 검증)
        print("\n[Phase4] off-hire-ref-check → GLDU7467425 조회")
        await page.goto("https://www.touax-container.com/off-hire-ref-check",
                        wait_until="networkidle", timeout=30_000)
        await page.wait_for_timeout(1000)
        # placeholder 'Container numbers' 가 두 번째 input
        cn_input = await page.query_selector('input[placeholder*="Container"]')
        if cn_input:
            await cn_input.fill("GLDU7467425")
            search_btn = page.locator('button[type="submit"]').filter(has_text="Search").first
            if await search_btn.count() > 0:
                await search_btn.click()
                try:
                    await page.wait_for_load_state("networkidle", timeout=20_000)
                except Exception:
                    pass
                await page.wait_for_timeout(1500)
                await page.screenshot(path=str(OUT_DIR / "08_ref_check_result.png"), full_page=True)
                await dump_page(page, "08_ref_check_result")
                (OUT_DIR / "08_ref_check_result.html").write_text(
                    await page.content(), encoding="utf-8"
                )
                print(f"  결과 URL: {page.url}")
            else:
                print("  Search 버튼 없음")
        else:
            print("  Container numbers input 없음")

        # Phase 5: /off-hire Search 테스트 (안전 검증)
        # ⚠ EXECUTE_BOOKING=True 시 "Off hire" 버튼 + 모달 Confirm까지 진행 (실 발급)
        # 의도적으로 실행할 때만 True 로 변경 (기본값 False 유지)
        EXECUTE_BOOKING  = False
        TEST_CITY_CODE   = "KRINC"
        TEST_CONTAINER_N = "GLDU9717652"   # 장금 부산 (사용자 승인, 원상복귀 예정)

        print(f"\n[Phase5] /off-hire Search 테스트 — {TEST_CITY_CODE} / {TEST_CONTAINER_N}")
        await page.goto("https://www.touax-container.com/off-hire",
                        wait_until="networkidle", timeout=30_000)
        await page.wait_for_timeout(1500)

        # City: KRBUS 선택 (TomSelect — native select에 값 + change 이벤트)
        city_result = await page.evaluate("""(target) => {
            const sel = document.getElementById('app_front_off_hire_filter_city');
            if (!sel) return { ok: false, error: 'select not found' };
            const opt = Array.from(sel.options).find(o => o.value === target || o.text.toUpperCase().includes(target));
            if (!opt) return { ok: false, error: 'option not found for ' + target };
            sel.value = opt.value;
            sel.dispatchEvent(new Event('change', { bubbles: true }));
            // TomSelect 인스턴스가 있으면 그쪽도 갱신
            if (sel.tomselect) {
                sel.tomselect.setValue(opt.value);
            }
            return { ok: true, value: opt.value, text: opt.text };
        }""", TEST_CITY_CODE)
        print(f"  City: {city_result}")

        cn = await page.query_selector('#app_front_off_hire_filter_containerNumber')
        if cn:
            await cn.fill(TEST_CONTAINER_N)

        await page.screenshot(path=str(OUT_DIR / "09_before_search.png"), full_page=True)

        # Search 클릭
        search = page.locator('form[name="app_front_off_hire_filter"] button[type="submit"]').first
        if await search.count() == 0:
            search = page.locator('button[type="submit"]').filter(has_text="Search").first
        await search.click()
        try:
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(OUT_DIR / "10_search_result.png"), full_page=True)
        await dump_page(page, "10_search_result")
        (OUT_DIR / "10_search_result.html").write_text(
            await page.content(), encoding="utf-8"
        )
        print(f"  Search 결과 URL: {page.url}")

        # Phase 6: "Off hire" 모달 열기 → 모달 캡처
        off_hire_btn = page.locator('a.modalClickoffHire').first
        if await off_hire_btn.count() == 0:
            print("\n[Phase6] 'Off hire' 버튼 없음 — 결과가 invalid이거나 페이지 구조 변경")
        else:
            print("\n[Phase6] 'Off hire' 버튼 발견 → 클릭 (모달 오픈)")
            await off_hire_btn.click()
            # 모달 콘텐츠 AJAX 로딩 완료 대기 (본문 길이 또는 form/button 등장)
            try:
                await page.wait_for_function("""() => {
                    const m = document.querySelector('.modal.show, .modal.in, .modal[style*="display: block"]');
                    if (!m) return false;
                    return (m.innerText || '').length > 80;
                }""", timeout=15_000)
            except Exception as e:
                print(f"  모달 콘텐츠 대기 타임아웃: {e}")
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUT_DIR / "11_off_hire_modal.png"), full_page=True)
            await dump_page(page, "11_off_hire_modal")
            (OUT_DIR / "11_off_hire_modal.html").write_text(
                await page.content(), encoding="utf-8"
            )

            # 모달 내 submit/확정 후보 버튼 탐지
            modal_buttons = await page.evaluate(r"""() => {
                const root = document.querySelector('.modal.show, .modal.in, .modal[style*="display: block"]') || document;
                const els = Array.from(root.querySelectorAll('button, input[type=submit], a.btn'));
                return els.map(e => ({
                    tag: e.tagName, type: e.type || null,
                    id: e.id || null, name: e.name || null,
                    class: e.className || null,
                    text: (e.innerText || e.value || '').trim().slice(0, 80),
                    visible: !!(e.offsetParent),
                })).filter(b => b.visible && b.text && !/(close|cancel|cookie|consent|accept all)/i.test(b.text));
            }""")
            print(f"  모달 내 후보 버튼 ({len(modal_buttons)}개):")
            for b in modal_buttons:
                print(f"    - tag={b['tag']} type={b['type']} text='{b['text']}' class='{(b['class'] or '')[:60]}'")

            # Phase 7: 모달 확정 클릭 (EXECUTE_BOOKING 시)
            if EXECUTE_BOOKING and modal_buttons:
                # 우선순위: type=submit > "Confirm"/"Validate"/"Off hire" 텍스트
                target = None
                for b in modal_buttons:
                    if b.get('type') == 'submit':
                        target = b; break
                if not target:
                    for b in modal_buttons:
                        if any(k in (b.get('text') or '').lower()
                               for k in ('confirm', 'validate', 'submit', 'off hire', 'off-hire', 'ok')):
                            target = b; break
                if not target:
                    target = modal_buttons[0]
                print(f"\n[Phase7] ⚠ 확정 클릭: text='{target['text']}'")
                # 동일 조건으로 다시 selector로 매칭해서 클릭
                clicked = await page.evaluate("""(t) => {
                    const root = document.querySelector('.modal.show, .modal.in, .modal[style*="display: block"]') || document;
                    const els = Array.from(root.querySelectorAll('button, input[type=submit], a.btn'));
                    const target = els.find(e => (e.innerText || e.value || '').trim().slice(0, 80) === t);
                    if (!target) return false;
                    target.click();
                    return true;
                }""", target['text'])
                if not clicked:
                    print("  ERROR: 모달 내 확정 버튼 재탐지 실패")
                else:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=60_000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(3000)
                    await page.screenshot(path=str(OUT_DIR / "12_after_confirm.png"), full_page=True)
                    await dump_page(page, "12_after_confirm")
                    (OUT_DIR / "12_after_confirm.html").write_text(
                        await page.content(), encoding="utf-8"
                    )
                    print(f"  확정 후 URL: {page.url}")

        print("\n[완료] Phase 1~7 캡처 종료.")
        print(f"산출물: {OUT_DIR}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
