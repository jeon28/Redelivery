from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()


class QueryRequest(BaseModel):
    company: str
    lessor: str
    region: str
    containers: List[str]


class ContainerResult(BaseModel):
    container_no: str
    available: bool
    depot: Optional[str] = None
    booking_ref: Optional[str] = None
    over_caps: Optional[int] = None
    close_date: Optional[str] = None
    reason: Optional[str] = None


class QueryResponse(BaseModel):
    results: List[ContainerResult]


@router.post("/query", response_model=QueryResponse)
async def query_containers(req: QueryRequest):
    """
    Phase 1: Mock 응답 반환
    Phase 2: 실제 임대사별 스크래퍼 호출
    """
    from scrapers.base import get_scraper

    scraper = get_scraper(req.company, req.lessor)
    if scraper is None:
        # 지원하지 않는 임대사는 Mock 데이터 반환
        results = _mock_results(req.containers)
    else:
        results = await scraper.run(req.containers, req.region)

    return QueryResponse(results=results)


def _mock_results(containers: List[str]) -> List[ContainerResult]:
    results = []
    for i, no in enumerate(containers):
        if i % 2 == 0:
            results.append(ContainerResult(
                container_no=no,
                available=True,
                depot="INC05 - SEUNG JIN ENTERPRISES",
                booking_ref=f"TKE{i:04d}",
                over_caps=1,
                close_date="2026-MAY-31",
                reason=None,
            ))
        else:
            results.append(ContainerResult(
                container_no=no,
                available=False,
                depot=None,
                booking_ref=None,
                over_caps=None,
                close_date=None,
                reason="CONTAINERS NOT HIRED BY SINOK1",
            ))
    return results
