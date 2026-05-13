"""TRIT — 기존 Pending 반납번호의 Stage 3 (Finalize) 실행 스크립트.

목적: 이미 발급된 Pending 반납번호 페이지로 이동 → Finalize 버튼 클릭 → 결과 캡처.
새로운 Stage 1/2를 다시 돌리지 않으므로 중복 발급 위험이 없음.

⚠ Finalize 클릭 = 최종 확정. 의도적으로 실행할 때만 사용.

사용: cd scraper && python test_trit_finalize.py
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

LOGIN_URL  = "https://tools.tritoncontainer.com/tritoncontainer/login/auth"

# ── 입력값 ─────────────────────────────────────────────
COMPANY            = "HA"          # ABUSG48854 발급 계정
REDELIVERY_NUMBER  = "ABUSG48854"  # Pending Create 상태인 번호
# ──────────────────────────────────────────────────────

TARGET_URL = f"https://tools.tritoncontainer.com/tritoncontainer/redelivery/create/{REDELIVERY_NUMBER}"

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR   = REPO_ROOT / "TRIT" / "_inspect"
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    user = os.getenv(f"{COMPANY}_TRIT_ID")
    pw   = os.getenv(f"{COMPANY}_TRIT_PW")
    if not user or not pw:
        print(f"ERROR: {COMPANY}_TRIT_ID / {COMPANY}_TRIT_PW 누락"); sys.exit(1)

    print(f"계정: {COMPANY} / 대상: {REDELIVERY_NUMBER}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()

        # 로그인
        print("[1] 로그인")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        pw_els = await page.query_selector_all('input[type="password"]')
        user_els = await page.query_selector_all(
            'input[type="text"], input[type="email"], input:not([type])'
        )
        await user_els[0].fill(user)
        await pw_els[0].fill(pw)
        await pw_els[0].press("Enter")
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        if "/login/auth" in page.url:
            print(f"  로그인 실패: {page.url}"); await browser.close(); sys.exit(2)
        print(f"  로그인 성공: {page.url}")

        # 대상 페이지 이동
        print(f"[2] Pending 페이지 진입: {TARGET_URL}")
        await page.goto(TARGET_URL, wait_until="networkidle")

        # 쿠키 배너 닫기
        try:
            btn = await page.query_selector('#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll')
            if btn:
                await btn.click(timeout=3000)
                await page.wait_for_timeout(500)
        except Exception:
            pass
        await page.screenshot(path=str(OUT_DIR / "10_before_finalize.png"), full_page=True)

        # Finalize 버튼 클릭
        print("[3] ⚠ Finalize 클릭 (Stage 3)")
        btn = await page.query_selector('#finalizeRedelivery')
        if not btn:
            print("  Finalize 버튼 없음 — 이미 finalize되었거나 상태 변경됨")
            await page.screenshot(path=str(OUT_DIR / "10_no_finalize_btn.png"), full_page=True)
            await browser.close(); sys.exit(3)
        await btn.click()
        try:
            await page.wait_for_load_state("networkidle", timeout=60000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        await page.screenshot(path=str(OUT_DIR / "11_after_finalize.png"), full_page=True)
        (OUT_DIR / "11_after_finalize.html").write_text(
            await page.content(), encoding="utf-8"
        )
        print(f"  Finalize 후 URL: {page.url}")
        print(f"  -> 11_after_finalize.{{png,html}} 저장")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
