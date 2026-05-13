"""TRIT (Triton) 사이트 구조 분석 스크립트.

목적:
  - 로그인 → 반납 생성 페이지 진입 → 폼 인스펙션
  - 실제 컨테이너로 Stage 1(validate) 까지만 수행 → 결과 화면 캡처
  - Stage 2(최종 확정) 버튼은 절대 클릭하지 않음

산출물: TRIT/_inspect/ 에 스크린샷 + 폼 구조 JSON 저장.
사용: cd scraper && python test_trit.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

load_dotenv()

LOGIN_URL  = "https://tools.tritoncontainer.com/tritoncontainer/login/auth"
CREATE_URL = "https://tools.tritoncontainer.com/tritoncontainer/redeliverySession/create"
HEADLESS   = True

# ── 테스트 입력값 ──────────────────────────────────────
COMPANY          = "HA"          # "SK" (장금) 또는 "HA" (흥아)
TEST_COUNTRY     = "KOREA"
TEST_PORT        = "BUSAN"
TEST_CONTAINERS  = [             # 중복 자동 제거
    "TCLU8769849",
]

# ⚠ EXECUTE_STAGE_2 = True 일 때 "Continue Redelivery Request" 클릭 = 실 예약 생성
#   취소가 별도 절차이므로 의도적으로 실행할 때만 True 로 변경할 것 (기본값 False 유지)
EXECUTE_STAGE_2  = False
# ──────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
TRIT_DIR  = REPO_ROOT / "TRIT"
OUT_DIR   = TRIT_DIR / "_inspect"
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def dump_form(page: Page, label: str) -> dict:
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
                value: s.value,
                selected_texts: Array.from(s.selectedOptions || []).map(o => o.text),
                options: Array.from(s.options).slice(0, 300).map(o => ({ value: o.value, text: o.text })),
            })),
            textareas: Array.from(document.querySelectorAll('textarea')).map(pick),
            buttons: Array.from(document.querySelectorAll('button, input[type=submit], input[type=button]')).map(pick),
            tables: Array.from(document.querySelectorAll('table')).slice(0, 10).map(t => ({
                id: t.id, class: t.className,
                headers: Array.from(t.querySelectorAll('thead th, thead td')).map(th => th.innerText.trim()),
                rows_count: t.querySelectorAll('tbody tr').length,
                rows_preview: Array.from(t.querySelectorAll('tbody tr')).slice(0, 5).map(tr =>
                    Array.from(tr.querySelectorAll('td, th')).map(td => td.innerText.trim())
                ),
            })),
            body_text_preview: document.body.innerText.slice(0, 4000),
        };
    }""")
    (OUT_DIR / f"{label}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


async def auto_login(page: Page, user: str, pw: str) -> bool:
    pw_els = await page.query_selector_all('input[type="password"]')
    if not pw_els:
        return False
    pw_el = pw_els[0]
    user_els = await page.query_selector_all(
        'input[type="text"], input[type="email"], input:not([type])'
    )
    if not user_els:
        return False
    await user_els[0].fill(user)
    await pw_el.fill(pw)
    await pw_el.press("Enter")
    try:
        await page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    return "/login/auth" not in page.url


async def dismiss_cookie_banner(page: Page):
    try:
        btn = await page.query_selector('#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll')
        if btn:
            await btn.click(timeout=3000)
            await page.wait_for_timeout(500)
            print("    ✓ 쿠키 배너 Accept 클릭")
    except Exception as e:
        print(f"    (쿠키 배너 처리 스킵: {e})")


async def select2_set_single(page: Page, select_id: str, label_substr: str) -> dict:
    """단일 Select2 선택. 옵션 text에 label_substr이 포함된 첫 옵션을 선택 (대소문자 무시)."""
    return await page.evaluate("""(args) => {
        const [sid, sub] = args;
        const sel = document.getElementById(sid);
        if (!sel) return { ok: false, error: 'select not found: ' + sid };
        const subL = sub.toLowerCase();
        const opt = Array.from(sel.options).find(o => (o.text || '').toLowerCase().includes(subL));
        if (!opt) return { ok: false, error: 'option not found', looked_for: sub, sample: Array.from(sel.options).slice(0,5).map(o=>o.text) };
        sel.value = opt.value;
        if (window.jQuery) { jQuery(sel).trigger('change'); }
        else { sel.dispatchEvent(new Event('change', { bubbles: true })); }
        return { ok: true, value: opt.value, text: opt.text };
    }""", [select_id, label_substr])


async def select2_add_tags(page: Page, select_id: str, tag_values: list[str]) -> dict:
    """Select2 multi-select에 여러 옵션을 동적으로 추가/선택 (입력 순서 유지, 중복 제거)."""
    return await page.evaluate("""(args) => {
        const [sid, vals] = args;
        const sel = document.getElementById(sid);
        if (!sel) return { ok: false, error: 'select not found: ' + sid };
        if (!window.jQuery) return { ok: false, error: 'jQuery missing' };
        const $sel = jQuery(sel);
        const seen = new Set();
        const added = [];
        for (const v of vals) {
            const key = String(v).trim().toUpperCase();
            if (!key || seen.has(key)) continue;
            seen.add(key);
            $sel.append(new Option(key, key, true, true));
            added.push(key);
        }
        $sel.trigger('change');
        return { ok: true, added, value: $sel.val() };
    }""", [select_id, tag_values])


async def main():
    user = os.getenv(f"{COMPANY}_TRIT_ID")
    pw   = os.getenv(f"{COMPANY}_TRIT_PW")
    if not user or not pw:
        print(f"ERROR: {COMPANY}_TRIT_ID / {COMPANY}_TRIT_PW 누락")
        sys.exit(1)
    print(f"계정: {COMPANY} ({user[:3]}***)")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()

        # 1) 로그인
        print("[1] 로그인 페이지 진입")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        if not await auto_login(page, user, pw):
            print(f"  로그인 실패: {page.url}")
            await browser.close()
            sys.exit(2)
        print(f"  로그인 성공: {page.url}")

        # 2) Create 페이지
        print("[2] 반납 생성 페이지 진입")
        await page.goto(CREATE_URL, wait_until="networkidle")
        await dismiss_cookie_banner(page)
        await page.screenshot(path=str(OUT_DIR / "04_create_clean.png"), full_page=True)

        # 3) Country 선택
        print(f"[3] Country='{TEST_COUNTRY}' 선택")
        r = await select2_set_single(page, "location_country", TEST_COUNTRY)
        print(f"  결과: {r}")
        if not r.get("ok"):
            await browser.close(); sys.exit(3)
        await page.wait_for_timeout(1500)  # 종속 옵션 로딩 대기

        # 4) Port 선택
        print(f"[4] Port='{TEST_PORT}' 선택")
        r = await select2_set_single(page, "location_port", TEST_PORT)
        print(f"  결과: {r}")
        if not r.get("ok"):
            await browser.close(); sys.exit(4)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "05_after_location.png"), full_page=True)
        await dump_form(page, "05_after_location")

        # 5) Unit Number 추가
        print(f"[5] Unit Numbers에 {TEST_CONTAINERS} 추가")
        r = await select2_add_tags(page, "unitNumbers", TEST_CONTAINERS)
        print(f"  결과: {r}")
        if not r.get("ok"):
            await browser.close(); sys.exit(5)
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "06_filled_form.png"), full_page=True)

        # 6) Stage 1 — Request Redelivery (validate) 클릭
        print("[6] Request Redelivery 클릭 (Stage 1 / validate)")
        btn = await page.query_selector('input[type="submit"][name="Request Redelivery"]')
        if not btn:
            print("  ERROR: Request Redelivery 버튼을 찾지 못함")
            await browser.close(); sys.exit(6)
        await btn.click()
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT_DIR / "07_validate_result.png"), full_page=True)
        await dump_form(page, "07_validate_result")
        (OUT_DIR / "07_validate_result.html").write_text(
            await page.content(), encoding="utf-8"
        )
        print(f"  결과 URL: {page.url}")

        # 7) Redelivery 탭 클릭 (있으면) — 유효 케이스 화면 캡처
        print("[7] Redelivery 탭 확인 및 클릭")
        tab = await page.query_selector("#redeliveriesTab")
        if tab:
            await tab.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUT_DIR / "08_redelivery_tab.png"), full_page=True)
            await dump_form(page, "08_redelivery_tab")
            (OUT_DIR / "08_redelivery_tab.html").write_text(
                await page.content(), encoding="utf-8"
            )
            print("  -> 08_redelivery_tab.png 저장")
        else:
            print("  #redeliveriesTab 없음 (모두 invalid이거나 페이지 구조 변경)")
            if EXECUTE_STAGE_2:
                print("  -> 유효 단위 없음. Stage 2 스킵.")
                await browser.close(); return

        # 8) Stage 2 — Continue Redelivery Request (실 예약 생성)
        if EXECUTE_STAGE_2:
            print("\n[8] ⚠ Stage 2 실행 — Continue Redelivery Request 클릭 (실 예약 생성)")
            stage2_btn = await page.query_selector('input[name="Continue Redelivery Request"]')
            if not stage2_btn:
                print("  ERROR: Stage 2 버튼을 찾지 못함")
                await browser.close(); sys.exit(7)
            await stage2_btn.click()
            try:
                await page.wait_for_load_state("networkidle", timeout=60000)
            except Exception:
                pass
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(OUT_DIR / "09_stage2_result.png"), full_page=True)
            await dump_form(page, "09_stage2_result")
            (OUT_DIR / "09_stage2_result.html").write_text(
                await page.content(), encoding="utf-8"
            )
            print(f"  Stage 2 결과 URL: {page.url}")
            print("  -> 09_stage2_result.{png,json,html} 저장")
        else:
            print("\n[완료] Stage 1 + 두 탭 캡처. EXECUTE_STAGE_2=False 이므로 Stage 2 스킵.")

        print(f"\n산출물: {OUT_DIR}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
