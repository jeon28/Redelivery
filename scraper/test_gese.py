"""GESE (SeaCo) 사이트 분석 — Phase 1: 로그인 화면/대시보드 진입 캡처.

URL은 SAP UI5 기반 (`seaweb.seacoglobal.com/sap/bc/ui5_ui5/sap/zseaweb/index.html`).
로그인 방식 (Basic Auth / Form / SSO) 파악 후 후속 전략 수립.

안전 가드: 로그인 시도 안 함. 페이지 진입 + 화면 캡처 + 인증 challenge 분석.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

load_dotenv()

ENTRY_URL = (
    "https://seaweb.seacoglobal.com/sap/bc/ui5_ui5/sap/zseaweb/index.html"
    "?saml2=disabled&handleX509=false&_sap-hash=JTIzJTJGbmF2Q3VzX0Rhc2hib2FyZA#/navCus_Dashboard"
)
HEADLESS = True

# ── 입력값 ─────────────────────────────────────────────
COMPANY = "SK"
# ──────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR   = REPO_ROOT / "GESE" / "_inspect"
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
        return {
            url: location.href,
            title: document.title,
            forms: Array.from(document.querySelectorAll('form')).map(f => ({
                id: f.id, name: f.name, action: f.action, method: f.method,
            })),
            inputs: Array.from(document.querySelectorAll('input')).map(pick),
            buttons: Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], a.btn')).map(pick),
            labels: Array.from(document.querySelectorAll('label')).slice(0, 100).map(l => ({
                for: l.htmlFor || null, text: (l.innerText || '').slice(0, 200),
            })),
            iframes: Array.from(document.querySelectorAll('iframe')).map(f => ({
                src: f.src, id: f.id, name: f.name, class: f.className,
            })),
            // SAP UI5 환경 감지
            sap_present: typeof window.sap !== 'undefined',
            sap_version: (typeof window.sap !== 'undefined' && window.sap.ui)
                ? (window.sap.ui.version || (window.sap.ui.getCore && window.sap.ui.getCore().getConfiguration().getVersion().toString()))
                : null,
            body_text_preview: (document.body.innerText || '').slice(0, 3000),
        };
    }""")
    (OUT_DIR / f"{label}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


async def main():
    user = os.getenv(f"{COMPANY}_GESE_ID")
    pw   = os.getenv(f"{COMPANY}_GESE_PW")
    if user and pw:
        print(f"계정: {COMPANY} ({user[:3]}***) (참고만 — 본 단계에서 사용 안 함)")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        # 401 challenge 자동 처리 안 되도록 단순 컨텍스트로 시작
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()

        # 네트워크 응답 모니터링 (401, 302 등)
        responses = []
        def on_response(resp):
            try:
                if resp.status in (401, 302, 403):
                    responses.append({
                        "status": resp.status,
                        "url": resp.url,
                        "auth_hdr": resp.headers.get("www-authenticate"),
                    })
            except Exception:
                pass
        page.on("response", on_response)

        print(f"[1] 진입: {ENTRY_URL}")
        try:
            await page.goto(ENTRY_URL, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"  goto 예외: {e}")
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        await page.wait_for_timeout(3500)

        await page.screenshot(path=str(OUT_DIR / "01_entry.png"), full_page=True)
        d = await dump_page(page, "01_entry")
        (OUT_DIR / "01_entry.html").write_text(await page.content(), encoding="utf-8")

        print(f"  URL (이동 후): {page.url}")
        print(f"  Title: {d['title']}")
        print(f"  forms={len(d['forms'])} inputs={len(d['inputs'])} buttons={len(d['buttons'])}")
        print(f"  iframes={len(d['iframes'])}")
        print(f"  SAP UI5: present={d['sap_present']} version={d['sap_version']}")
        print(f"\n  네트워크 응답 (401/302/403):")
        for r in responses[:15]:
            print(f"    [{r['status']}] {r['url'][:120]}  WWW-Auth={r.get('auth_hdr')}")

        # 본문 미리보기
        print(f"\n  본문 텍스트 (처음 800자):")
        print(d.get("body_text_preview", "")[:800])

        # Phase 2: 로그인 시도
        if not user or not pw:
            print(f"\n[Phase2 skip] {COMPANY}_GESE_ID/PW 누락")
            await browser.close(); return

        print(f"\n[Phase2] 로그인 시도 ({COMPANY}: {user[:3]}***)")
        user_el = await page.query_selector('#USERNAME_FIELD-inner')
        pw_el = await page.query_selector('#PASSWORD_FIELD-inner')
        login_btn = await page.query_selector('#LOGIN_LINK')
        if not user_el or not pw_el or not login_btn:
            print("  로그인 필드/버튼 못 찾음")
            await browser.close(); sys.exit(2)
        await user_el.fill(user)
        await pw_el.fill(pw)
        await page.wait_for_timeout(500)
        await login_btn.click()
        try:
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        await page.wait_for_timeout(4500)  # SAP UI5 부팅 대기
        await page.screenshot(path=str(OUT_DIR / "02_after_login.png"), full_page=True)
        d2 = await dump_page(page, "02_after_login")
        (OUT_DIR / "02_after_login.html").write_text(await page.content(), encoding="utf-8")
        print(f"  URL: {page.url}")
        print(f"  Title: {d2['title']}")
        print(f"  SAP UI5: present={d2['sap_present']} version={d2['sap_version']}")
        print(f"  본문 (700자):")
        print(d2.get("body_text_preview", "")[:700])

        # Phase 3: "Online Returns" 메뉴 클릭 → 반납 화면 진입
        print(f"\n[Phase3] 'Online Returns' 메뉴 클릭")
        or_btn = page.locator("text=Online Returns").first
        if await or_btn.count() == 0:
            print("  메뉴 'Online Returns' 못 찾음")
        else:
            try:
                await or_btn.click()
                await page.wait_for_timeout(3500)
                await page.screenshot(path=str(OUT_DIR / "03_online_returns.png"), full_page=True)
                d3 = await dump_page(page, "03_online_returns")
                (OUT_DIR / "03_online_returns.html").write_text(await page.content(), encoding="utf-8")
                print(f"  URL: {page.url}")
                print(f"  본문 (800자):")
                print(d3.get("body_text_preview", "")[:800])
                # 하위 메뉴/링크/anchor 추출
                items = await page.evaluate(r"""() => {
                    const all = Array.from(document.querySelectorAll('a, [role=button], [role=link], li, span'));
                    return all.map(e => ({
                        text: (e.innerText || '').trim().slice(0, 80),
                        tag: e.tagName,
                        role: e.getAttribute('role') || null,
                    })).filter(e => e.text && e.text.length < 80)
                       .filter(e => /return|redeliver|request|outstanding|online/i.test(e.text));
                }""")
                # 중복 제거
                seen = set(); out = []
                for it in items:
                    k = it["text"]
                    if k in seen: continue
                    seen.add(k); out.append(it)
                print(f"  관련 항목:")
                for o in out[:30]:
                    print(f"    [{o['tag']}/{o['role']}] {o['text']}")
            except Exception as e:
                print(f"  Online Returns 클릭 실패: {e}")

        # Phase 4: Redelivery Request 클릭 → 신규 신청 폼
        print(f"\n[Phase4] 'Redelivery Request' 클릭")
        rr_btn = page.locator("text=Redelivery Request").first
        if await rr_btn.count() > 0:
            try:
                await rr_btn.click()
                await page.wait_for_timeout(4000)
                await page.screenshot(path=str(OUT_DIR / "04_redelivery_request.png"), full_page=True)
                d4 = await dump_page(page, "04_redelivery_request")
                (OUT_DIR / "04_redelivery_request.html").write_text(await page.content(), encoding="utf-8")
                print(f"  URL: {page.url}")
                print(f"  본문 (1000자):")
                print(d4.get("body_text_preview", "")[:1000])
            except Exception as e:
                print(f"  Redelivery Request 클릭 실패: {e}")

        # Phase 4b: Redelivery Request — City 옵션 덤프 + Add to Returns (실 컨테이너로)
        TEST_CITY = "BUSAN"   # 또는 PUSAN — 옵션 덤프로 확정
        TEST_UNITS = [
            "SEGU9586313",   # 사용자 제공 (장금, 부산)
            "CRXU9980434",   # 사용자 제공 추가 (장금, 부산)
        ]
        print(f"\n[Phase4b] City 옵션 + {TEST_UNITS} 입력 + Add to Returns")
        # 이미 Phase 4에서 Redelivery Request 페이지에 있으므로 재진입 불요
        CITY_ID = "container-com.seaco.seaweb---Cus_RedeliveryRequest--idRedeliveryRequestComboBoxCity-inner"
        SERIAL_ID = "container-com.seaco.seaweb---Cus_RedeliveryRequest--idTextAreaSerialNo-inner"

        # City 입력에 "Busan" 전체 타이핑 후 Tab으로 확정 (SAP UI5 ComboBox autocomplete)
        city_inp = page.locator(f'[id="{CITY_ID}"]').first
        await city_inp.click()
        await page.wait_for_timeout(500)
        await city_inp.fill("Busan")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "04b_city_dropdown.png"), full_page=True)

        # 옵션 덤프 (다양한 SAP UI5 popover 셀렉터)
        opts = await page.evaluate("""() => {
            const sels = [
                '.sapMComboBoxBasePicker li.sapMLIB',
                '.sapMSelectList li',
                '[role="listbox"] [role="option"]',
                '.sapMPopover li.sapMLIB',
                'ul.sapMSelectList li',
            ];
            for (const sel of sels) {
                const items = Array.from(document.querySelectorAll(sel))
                    .filter(e => e.offsetParent !== null);
                if (items.length > 0) {
                    return { selector: sel, items: items.map(e => (e.innerText || '').trim()).filter(t => t) };
                }
            }
            // fallback: any visible li
            const all = Array.from(document.querySelectorAll('li'))
                .filter(e => e.offsetParent !== null);
            return { selector: 'li(visible)', items: all.map(e => (e.innerText || '').trim()).filter(t => t && t.length < 80) };
        }""")
        print(f"  City 필터(B) 결과: selector='{opts['selector']}' / {len(opts['items'])}개")
        for o in opts['items'][:30]:
            print(f"    - {o}")

        # Busan 옵션을 정확히 매칭 (단어 단위)
        target_opt = next((o for o in opts['items']
                           if o.strip().upper() in ('BUSAN', 'PUSAN')), None)
        if not target_opt:
            # 첫번째 단어가 Busan/Pusan인 옵션
            target_opt = next((o for o in opts['items']
                               if o.strip().upper().split()[0] in ('BUSAN', 'PUSAN')), None)
        print(f"  매칭: {target_opt}")
        if not target_opt:
            print("  ❌ Busan/Pusan 옵션 없음 — 분석 종료")
            await browser.close(); return

        # 옵션 li 직접 클릭 (정확히 일치하는 텍스트)
        clicked = await page.evaluate("""(needle) => {
            const items = Array.from(document.querySelectorAll('li'))
                .filter(e => e.offsetParent !== null);
            const target = items.find(e => (e.innerText || '').trim().toUpperCase() === needle.toUpperCase());
            if (!target) return false;
            target.scrollIntoView({ block: 'center' });
            target.click();
            return true;
        }""", target_opt)
        print(f"  City 선택 클릭: {clicked} → {target_opt}")
        await page.wait_for_timeout(800)

        # Serial No. 입력
        ser_el = page.locator(f'[id="{SERIAL_ID}"]').first
        if await ser_el.count() == 0:
            print(f"  ❌ Serial No. textarea 못 찾음")
            await browser.close(); return
        await ser_el.fill("\n".join(TEST_UNITS))
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "04c_form_filled.png"), full_page=True)
        print(f"  Serial No. 입력 완료: {len(TEST_UNITS)}개 (줄바꿈)")

        # Add to Returns 클릭
        add_btn = page.locator("button").filter(has_text="Add to Returns").first
        if await add_btn.count() == 0:
            print(f"  ❌ Add to Returns 버튼 못 찾음")
            await browser.close(); return
        await add_btn.click()
        await page.wait_for_timeout(4000)
        await page.screenshot(path=str(OUT_DIR / "04d_after_add.png"), full_page=True)
        d4d = await dump_page(page, "04d_after_add")
        (OUT_DIR / "04d_after_add.html").write_text(await page.content(), encoding="utf-8")
        print(f"  Add to Returns 후 URL: {page.url}")

        # Phase 4e: Validate 클릭 (서버 검증, 발급 아님)
        print(f"\n[Phase4e] Validate 클릭 (서버 검증, Submit 안 함)")
        # sap.ui.table SelectAll: Playwright 직접 클릭이 SAP 이벤트를 더 잘 트리거
        sa = page.locator('.sapUiTableSelectAllCheckBox').first
        if await sa.count() > 0:
            try:
                await sa.click(force=True)
                print(f"  SelectAll 클릭 (Playwright)")
            except Exception as e:
                print(f"  SelectAll 클릭 실패: {e}")
        else:
            # fallback: row headers individually
            hdrs = page.locator('.sapUiTableRowHdr')
            n = await hdrs.count()
            for i in range(n):
                try:
                    await hdrs.nth(i).click(force=True)
                except Exception:
                    pass
            print(f"  Row headers 클릭: {n}개")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT_DIR / "04e_selected.png"), full_page=True)
        validate_btn = page.locator("button").filter(has_text="Validate").first
        if await validate_btn.count() == 0:
            print("  Validate 버튼 없음")
        else:
            await validate_btn.click()
            try:
                await page.wait_for_load_state("networkidle", timeout=30_000)
            except Exception:
                pass
            await page.wait_for_timeout(4000)
            await page.screenshot(path=str(OUT_DIR / "04e_after_validate.png"), full_page=True)
            d4e = await dump_page(page, "04e_after_validate")
            (OUT_DIR / "04e_after_validate.html").write_text(await page.content(), encoding="utf-8")
            # 테이블 행 데이터 추출
            rows = await page.evaluate(r"""() => Array.from(document.querySelectorAll('table tbody tr'))
                .map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim()))
                .filter(r => r.length > 0)""")
            print(f"  Validate 후 행 ({len(rows)}개):")
            for i, r in enumerate(rows[:10]):
                print(f"    ROW {i}: {r}")

        print(f"\n[Phase5] 'Redelivery View/Cancel' 클릭")
        print(f"\n[Phase5] 'Redelivery View/Cancel' 클릭")
        vc_btn = page.locator("text=Redelivery View/Cancel").first
        if await vc_btn.count() > 0:
            try:
                await vc_btn.click()
                await page.wait_for_timeout(4000)
                await page.screenshot(path=str(OUT_DIR / "05_view_cancel.png"), full_page=True)
                d5 = await dump_page(page, "05_view_cancel")
                (OUT_DIR / "05_view_cancel.html").write_text(await page.content(), encoding="utf-8")
                print(f"  URL: {page.url}")
                print(f"  본문 (1200자):")
                print(d5.get("body_text_preview", "")[:1200])
            except Exception as e:
                print(f"  Redelivery View/Cancel 클릭 실패: {e}")

        print(f"\n산출물: {OUT_DIR}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
