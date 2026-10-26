"""
컨테이너 번호 → 임대사 자동 판별 API (단건 통합조회 화면용).

세션 인증은 프론트 API 라우트에서 검사하므로 스크래퍼 측은 X-API-Key만 검증.
"""
import os
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel

from config.lessor_lookup import (
    DEFAULT_PREFIX_MAP,
    get_prefix_map,
    inventory_summary,
    lookup,
    parse_inventory_xlsx,
    save_inventory,
    save_prefix_map,
)

router = APIRouter(tags=["lookup"])

_MAX_UPLOAD = 20 * 1024 * 1024


def _check_api_key(api_key: str | None) -> None:
    expected = os.getenv("SCRAPER_API_KEY", "")
    if not expected:
        return
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


class PrefixMapBody(BaseModel):
    mapping: dict[str, str]


@router.get("/lookup")
def lookup_route(
    container: str = Query(...),
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    return lookup(container)


@router.get("/prefix-map")
def get_prefix_map_route(x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)
    return {"mapping": get_prefix_map(), "defaults": DEFAULT_PREFIX_MAP}


@router.put("/prefix-map")
def put_prefix_map_route(
    body: PrefixMapBody,
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    return {"ok": True, "mapping": save_prefix_map(body.mapping)}


@router.get("/lease-inventory/summary")
def inventory_summary_route(x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)
    return inventory_summary()


@router.post("/lease-inventory")
async def upload_inventory_route(
    request: Request,
    x_api_key: str | None = Header(default=None),
    x_filename: str | None = Header(default=None),
):
    """반납 대장 엑셀 원본 바이트(application/octet-stream)를 받아 통째로 교체."""
    _check_api_key(x_api_key)
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="파일이 비어 있습니다.")
    if len(content) > _MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (20MB 초과).")
    try:
        parsed = parse_inventory_xlsx(content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"엑셀을 읽을 수 없습니다: {exc}")
    if not parsed["units"]:
        raise HTTPException(
            status_code=400,
            detail="'Container No' 와 'Lessor' 머리행이 있는 시트를 찾지 못했습니다.",
        )
    filename = unquote(x_filename) if x_filename else None
    return {"ok": True, **save_inventory(parsed, filename)}
