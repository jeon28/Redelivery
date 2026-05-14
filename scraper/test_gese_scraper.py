"""GeseScraper 통합 동작 테스트.

기본 설정: 이미 ERROR 확인된 컨테이너 사용 → Validate ERROR로 결정, Submit 진행 안 됨.
실 발급(E2E)은 추후 사용자 사전 승인 + 수동 원상복귀 사이클로.

사용: cd scraper && python test_gese_scraper.py
"""
import asyncio
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# ── 테스트 설정 ──────────────────────────────────────────────────────
COMPANY    = "장금상선"
LESSOR     = "GESE"
REGION     = "BUSAN"
CONTAINERS = [
    "SEGU9586313",   # 분석 시 ERROR 확인 (Reefer/depot 부적합)
]
HEADLESS = True
# ─────────────────────────────────────────────────────────────────────


async def main():
    from scrapers.gese import GeseScraper

    scraper = GeseScraper(company=COMPANY, lessor=LESSOR)
    print(f"\n조회 시작: {COMPANY} / {LESSOR} / {REGION}")
    print(f"컨테이너: {CONTAINERS}\n")

    results = await scraper.run(CONTAINERS, REGION, headless=HEADLESS)

    print("\n=== 조회 결과 ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
