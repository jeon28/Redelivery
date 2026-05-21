from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()


class StatusDetailRequest(BaseModel):
    company: str
    lessor: str
    containers: List[str]


class StatusDetailResult(BaseModel):
    container_no: str
    available: bool
    depot: Optional[str] = None
    booking_ref: Optional[str] = None
    over_caps: Optional[int] = None
    close_date: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = None
    completed_date: Optional[str] = None


class StatusDetailResponse(BaseModel):
    results: List[StatusDetailResult]


@router.post("/status-detail", response_model=StatusDetailResponse)
async def status_detail(req: StatusDetailRequest):
    from scrapers.base import get_scraper

    scraper = get_scraper(req.company, req.lessor)
    if scraper is None:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 임대사: {req.lessor}")

    try:
        results = await scraper.run_status_detail(req.containers)
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail=f"{req.lessor}는 Status 단독 조회 미지원",
        )

    return StatusDetailResponse(results=results)
