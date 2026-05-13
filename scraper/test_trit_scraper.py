"""TritScraper 통합 동작 테스트.

기본 설정: 이미 invalid 임이 확인된 컨테이너만 사용 → Stage 2/3 발동 없이
스크래퍼의 전체 흐름 (로그인, 폼 입력, validate 결과 파싱)을 검증.

end-to-end (실 발급) 테스트는 사용자 사전 승인 후 컨테이너 번호를 변경하여 사용.

사용: cd scraper && python test_trit_scraper.py
"""
import asyncio
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# ── 테스트 설정 ──────────────────────────────────────────────────────
COMPANY    = "흥아라인"
LESSOR     = "TRIT"
REGION     = "BUSAN"
CONTAINERS = [
    "TCLU1619873",   # 이미 turn-in (확인됨)
    "TCLU9479119",   # SNKX 리스 중 (확인됨)
]
HEADLESS = True
# ─────────────────────────────────────────────────────────────────────


async def main():
    from scrapers.trit import TritScraper

    scraper = TritScraper(company=COMPANY, lessor=LESSOR)
    print(f"\n조회 시작: {COMPANY} / {LESSOR} / {REGION}")
    print(f"컨테이너: {CONTAINERS}\n")

    results = await scraper.run(CONTAINERS, REGION, headless=HEADLESS)

    print("\n=== 조회 결과 ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
