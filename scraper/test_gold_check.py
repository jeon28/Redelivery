"""GOLD history 확인 — 방금 전 Confirm 클릭으로 실제 발급되었는지 확인."""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
COMPANY = "SK"

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR   = REPO_ROOT / "GOLD" / "_inspect"


async def main():
    user = os.getenv(f"{COMPANY}_GOLD_ID")
    pw   = os.getenv(f"{COMPANY}_GOLD_PW")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        await page.goto("https://www.touax-container.com/login", wait_until="domcontentloaded")
        pw_el = (await page.query_selector_all('input[type="password"]'))[0]
        user_el = (await page.query_selector_all('input[type="text"], input[type="email"], input:not([type])'))[0]
        await user_el.fill(user); await pw_el.fill(pw); await pw_el.press("Enter")
        try: await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception: pass

        await page.goto("https://www.touax-container.com/off-hire/history", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT_DIR / "13_history_check.png"), full_page=True)
        # 페이지 본문 텍스트 출력
        body = await page.evaluate("() => document.body.innerText")
        # 표 영역만
        ra_rows = await page.evaluate(r"""() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            return rows.map(r => Array.from(r.querySelectorAll('td')).map(td => td.innerText.trim()));
        }""")
        for row in ra_rows:
            print("ROW:", row)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
