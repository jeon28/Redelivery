"""GoldScraper 통합 동작 테스트.

기본 설정: 이미 거부되는 컨테이너만 사용 → 실 발급 없음, 거부 사유 파싱 검증.
end-to-end (실 발급) 테스트는 컨테이너 번호를 변경 + 사용자 사전 승인 + 발급 후 수동 원상복귀.

사용: cd scraper && python test_gold_scraper.py
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
LESSOR     = "GOLD"
REGION     = "INCHON"
CONTAINERS = [
    "GLDU7591349",   # 반납완료 (확인됨)
    "GLDU7467425",   # 이미 RA434352 발급 상태 (홍콩 depot)
]
HEADLESS = True
# ─────────────────────────────────────────────────────────────────────


async def main():
    from scrapers.gold import GoldScraper

    scraper = GoldScraper(company=COMPANY, lessor=LESSOR)
    print(f"\n조회 시작: {COMPANY} / {LESSOR} / {REGION}")
    print(f"컨테이너: {CONTAINERS}\n")

    results = await scraper.run(CONTAINERS, REGION, headless=HEADLESS)

    print("\n=== 조회 결과 ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
