"""
FLOR 반납CY(Depot) 목록 조회 API.

데이터 출처: scrapers/flor_depots.py 의 정적 dict.
사이트 변경 시 collect_flor_depots.py 로 재수집 후 그 모듈 갱신.
"""
import os

from fastapi import APIRouter, Header, HTTPException, Query

from scrapers.flor_depots import list_depots

router = APIRouter(prefix="/flor", tags=["flor"])


def _check_api_key(api_key: str | None) -> None:
    expected = os.getenv("SCRAPER_API_KEY", "")
    if not expected:
        return
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/depots")
def list_flor_depots(
    company: str = Query(..., description="장금상선 | 흥아라인"),
    region: str = Query(..., description="BUSAN/INCHON/GWANGYANG/PYEONGTAEK/ULSAN"),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    return {
        "company": company,
        "region": region,
        "depots": list_depots(company, region),
    }
