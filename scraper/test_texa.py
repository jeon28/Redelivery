"""
TEXA 스크래퍼 로컬 테스트 스크립트.
사용: python test_texa.py
"""
import asyncio
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# ── 테스트 설정 ────────────────────────────────────────────────────────
COMPANY    = "장금상선"   # 또는 "흥아라인"
REGION     = "INCHON"
CONTAINERS = [
    "TEMU8208594",
    "TEMU7786751",
    "TEMU7231558",
]
HEADLESS = False     # True = 백그라운드 실행 / False = 브라우저 화면 표시
# ───────────────────────────────────────────────────────────────────────


async def main():
    from scrapers.texa import TexaScraper

    scraper = TexaScraper(company=COMPANY, lessor="TEXA")
    print(f"\n조회 시작: {COMPANY} / TEXA / {REGION}")
    print(f"컨테이너: {CONTAINERS}\n")

    results = await scraper.run(CONTAINERS, REGION, headless=HEADLESS)

    print("\n=== 조회 결과 ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
