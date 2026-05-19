from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()


class CancelItem(BaseModel):
    container_no: str
    booking_ref: str


class CancelRequest(BaseModel):
    company: str
    lessor: str
    region: str
    items: List[CancelItem]


class CancelResult(BaseModel):
    container_no: str
    booking_ref: str
    cancelled: bool
    reason: Optional[str] = None


class CancelResponse(BaseModel):
    results: List[CancelResult]


@router.post("/cancel", response_model=CancelResponse)
async def cancel_containers(req: CancelRequest):
    from scrapers.base import get_scraper

    scraper = get_scraper(req.company, req.lessor)
    if scraper is None:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 임대사: {req.lessor}")

    items_dicts = [it.model_dump() for it in req.items]
    try:
        results = await scraper.run_cancel(items_dicts, req.region)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail=f"{req.lessor}는 취소 미지원")

    return CancelResponse(results=results)
