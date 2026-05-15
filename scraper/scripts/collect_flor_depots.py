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
    await asyncio.sleep(2.5)

    await scraper._navigate_to_apply()

    # Customer ID 클릭 — 사이트가 옵션 1개일 때 .el-radio 대신 단일 <button> 으로
    # 노출하는 케이스 (예: 장금=SINOKOR). 버튼·라디오 둘 다 후보로 잡고 visible
    # 한 것만 클릭. 매칭이 없으면 이미 활성된 상태로 가정하고 진행.
    try:
        await scraper.page.wait_for_selector(
            ".el-radio, button", state="visible", timeout=15_000
        )
    except Exception:
        logger.warning("region=%s: 폼 요소 가시화 대기 실패, 진행 시도", region)

    picked = await scraper.page.evaluate(
        r"""(id) => {
            const target = id.toUpperCase();
            const all = Array.from(
                document.querySelectorAll('.el-radio, button')
            );
            const visible = all.filter(el => el.offsetParent !== null);
            // exact match 우선, 없으면 includes
            let hit = visible.find(el =>
                (el.innerText || '').toUpperCase().trim() === target
            );
            if (!hit) {
                hit = visible.find(el =>
                    (el.innerText || '').toUpperCase().includes(target)
                );
            }
            if (!hit) {
                return { ok: false, visible: visible.length };
            }
            hit.scrollIntoView({ block: 'center' });
            hit.click();
            return { ok: true, text: hit.innerText.trim(), tag: hit.tagName };
        }""",
        cust_id,
    )
    if picked.get("ok"):
        logger.info(
            "region=%s: customer id %s clicked → %r",
            region, picked.get("tag"), picked.get("text"),
        )
    else:
        # 단일 옵션이 자동 활성된 케이스로 추정 — 클릭 없이 진행
        logger.info(
            "region=%s: customer id 매칭 없음, 이미 활성된 것으로 가정 (visible %d개)",
            region, picked.get("visible"),
        )
    await asyncio.sleep(0.8)

    # production _click_el_select 는 hidden el-select 까지 인덱싱해서 0번이 잘못된
    # 위젯을 가리킬 수 있음. 스크립트에서는 visible 한 el-select 만 카운팅해서
    # 0=Port, 1=Depot 로 사용한다. 또한 옵션 패널 가시화까지 명시적으로 대기.

    async def _open_visible_select(idx: int) -> None:
        opened = await scraper.page.evaluate(
            r"""(idx) => {
                const all = Array.from(document.querySelectorAll('.el-select'));
                const visible = all.filter(el => el.offsetParent !== null);
                if (idx >= visible.length) {
                    return { ok: false, count: visible.length };
                }
                const sel = visible[idx];
                const inner = sel.querySelector('.el-input__inner') || sel;
                inner.scrollIntoView({ block: 'center' });
                inner.click();
                return { ok: true, count: visible.length };
            }""",
            idx,
        )
        if not opened.get("ok"):
            raise RuntimeError(
                f"visible el-select[{idx}] 없음 (visible {opened.get('count')}개)"
            )
        # 옵션 패널이 떠야 다음 옵션 매칭/추출이 가능
        try:
            await scraper.page.wait_for_selector(
                ".el-select-dropdown__item", state="visible", timeout=5000
            )
        except Exception:
            # 한 번 더 클릭해서 재시도
            await scraper.page.evaluate(
                r"""(idx) => {
                    const visible = Array.from(
                        document.querySelectorAll('.el-select')
                    ).filter(el => el.offsetParent !== null);
                    const sel = visible[idx];
                    if (sel) {
                        const inner = sel.querySelector('.el-input__inner') || sel;
                        inner.click();
                    }
                }""",
                idx,
            )
            await scraper.page.wait_for_selector(
                ".el-select-dropdown__item", state="visible", timeout=5000
            )
        await asyncio.sleep(0.5)

    async def _pick_option_substr(substr: str) -> str:
        result = await scraper.page.evaluate(
            r"""(sub) => {
                const items = Array.from(
                    document.querySelectorAll('.el-select-dropdown__item')
                ).filter(el => el.offsetParent !== null);
                const u = sub.toUpperCase();
                const hit = items.find(
                    el => (el.innerText || '').toUpperCase().includes(u)
                );
                if (!hit) return { ok: false, visible: items.length };
                hit.scrollIntoView({ block: 'center' });
                hit.click();
                return { ok: true, text: hit.innerText.trim() };
            }""",
            substr,
        )
        if not result.get("ok"):
            raise RuntimeError(
                f"드롭다운 옵션 '{substr}' 없음 (visible {result.get('visible')}개)"
            )
        return result.get("text", "")

    # Port 선택
    await _open_visible_select(0)
    port_text = await _pick_option_substr(port_substr)
    logger.info("region=%s: port picked → %r", region, port_text)
    await asyncio.sleep(0.8)

    # Depot 드롭다운 열기 (Port 종속 — Port 선택 후에야 활성)
    await _open_visible_select(1)

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
                # 실패 시점 스크린샷 + HTML 덤프 (디버깅용)
                try:
                    shot = Path(f"debug_flor_{region}.png")
                    await scraper.page.screenshot(path=str(shot), full_page=True)
                    html_path = Path(f"debug_flor_{region}.html")
                    html_path.write_text(
                        await scraper.page.content(), encoding="utf-8"
                    )
                    logger.info(
                        "디버그 산출물: %s / %s (URL: %s)",
                        shot, html_path, scraper.page.url,
                    )
                except Exception as dump_exc:
                    logger.warning("디버그 산출물 캡처 실패: %s", dump_exc)
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
