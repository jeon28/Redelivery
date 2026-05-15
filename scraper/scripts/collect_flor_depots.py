"""
FLOR Depot 1회용 수집 스크립트.

FLOR 사이트의 Apply Redelivery Step1 에서 Port × Depot 옵션을 추출해
`scraper/scrapers/flor_depots.py` 의 정적 dict 에 이식하기 위한 JSON 을 출력한다.

실행 (scraper 디렉토리에서):

  python -m scripts.collect_flor_depots --company 흥아라인
  python -m scripts.collect_flor_depots --company 흥아라인 --regions BUSAN,INCHON
  python -m scripts.collect_flor_depots --company 흥아라인 --no-headless --output depots.json

요구 사항:
- `.env` 에 해당 회사의 FLOR 자격증명이 설정되어 있어야 함
  (SK_FLOR_ID/PW 또는 HA_FLOR_ID/PW)
- Playwright 브라우저 설치

결과 포맷 (JSON):
  {
    "장금상선": {
      "BUSAN": [{"code":"KRPUS07","name":"YoungJin CY","label":"..."}],
      "INCHON": [...],
      ...
    }
  }
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

# scripts/ 에서 scrapers/ import 가능하도록 path 보정
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.flor import (
    FlorScraper,
    COMPANY_CUSTOMER_ID,
    PORT_OPTION_SUBSTR,
    REDELIV_URL,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("collect_flor_depots")


ALL_REGIONS = ["BUSAN", "INCHON", "GWANGYANG", "PYEONGTAEK", "ULSAN"]


async def _collect_region_depots(
    scraper: FlorScraper, region: str
) -> list[dict[str, str]]:
    """
    한 region 의 Depot 옵션을 수집한다.

    1) Redelivery 페이지 재진입 (Apply 탭 활성)
    2) Customer ID 라디오 + Port 선택
    3) Depot 드롭다운 열기 → 모든 li 텍스트 수집
    """
    port_substr = PORT_OPTION_SUBSTR.get(region)
    if not port_substr:
        logger.warning("region '%s' 의 Port substring 매핑 없음 → 스킵", region)
        return []

    cust_id = COMPANY_CUSTOMER_ID.get(scraper.company)
    if not cust_id:
        raise RuntimeError(f"지원하지 않는 선사: {scraper.company}")

    # 페이지 상태 리셋
    await scraper.page.goto(REDELIV_URL, wait_until="networkidle", timeout=30_000)
    await asyncio.sleep(2.0)

    await scraper._navigate_to_apply()
    await scraper._select_customer_id(cust_id)
    await scraper._select_port(port_substr)

    # Depot 드롭다운 열기 (Port 다음 두 번째 el-select)
    await scraper._click_el_select(1)

    options = await scraper.page.evaluate(
        r"""() => {
            const items = Array.from(
                document.querySelectorAll('.el-select-dropdown__item')
            ).filter(el => el.offsetParent !== null);
            return items.map(el => (el.innerText || '').trim());
        }"""
    )

    depots: list[dict[str, str]] = []
    for raw_label in options:
        if not raw_label:
            continue
        # 옵션 텍스트 포맷 관찰: "(KRPUS07) YoungJin CY (KRPUS07)"
        m = re.search(r"\(([A-Z]{5}\d{2,3})\)\s*(.+?)(?:\s*\([A-Z]{5}\d{2,3}\)\s*)?$", raw_label)
        if m:
            code = m.group(1)
            name = m.group(2).strip()
        else:
            # 패턴 매칭 실패해도 label 만 저장 (수동 정리 가능)
            code_m = re.search(r"\(([^)]+)\)", raw_label)
            code = code_m.group(1) if code_m else ""
            name = raw_label
        depots.append({"code": code, "name": name, "label": raw_label})

    logger.info("region=%s: %d depots", region, len(depots))
    return depots


async def collect(
    company: str,
    regions: list[str],
    headless: bool,
) -> dict:
    scraper = FlorScraper(company, "FLOR")
    await scraper.start(headless=headless)
    try:
        ok = await scraper.login()
        if not ok:
            raise RuntimeError("FLOR 로그인 실패")
        out: dict[str, list[dict[str, str]]] = {}
        for region in regions:
            try:
                out[region] = await _collect_region_depots(scraper, region)
            except Exception as exc:
                logger.error("region=%s 수집 실패: %s", region, exc)
                out[region] = []
        return {company: out}
    finally:
        await scraper.close()


def main():
    parser = argparse.ArgumentParser(description="FLOR Depot 1회용 수집기")
    parser.add_argument(
        "--company",
        choices=["장금상선", "흥아라인"],
        default="흥아라인",
        help="수집에 사용할 회사 계정 (양사 depot 동일 가정이면 한쪽만)",
    )
    parser.add_argument(
        "--regions",
        default=",".join(ALL_REGIONS),
        help="콤마 구분 region 목록 (기본: 5개 전부)",
    )
    parser.add_argument(
        "--output", "-o",
        default="-",
        help="결과 JSON 저장 경로. '-' 이면 stdout",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="브라우저 창 표시 (디버깅용)",
    )
    args = parser.parse_args()

    regions = [r.strip().upper() for r in args.regions.split(",") if r.strip()]
    invalid = [r for r in regions if r not in ALL_REGIONS]
    if invalid:
        parser.error(f"지원하지 않는 region: {invalid} (가능: {ALL_REGIONS})")

    result = asyncio.run(collect(args.company, regions, headless=not args.no_headless))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
        logger.info("결과 저장: %s", args.output)


if __name__ == "__main__":
    main()
