"""
자격증명 조회/수정 API.

Frontend(Vercel) ↔ Scraper(Railway) 사이 인증은 X-API-Key 헤더로 수행.
SCRAPER_API_KEY 환경변수와 일치해야 함.
"""
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config.credentials import get_all_credentials, update_credentials, COMPANIES

router = APIRouter(prefix="/credentials", tags=["credentials"])


class Credential(BaseModel):
    id: str | None = None
    pw: str | None = None


class CredentialsUpdate(BaseModel):
    # {"장금상선": {"TEXA": {"id": "...", "pw": "..."}}}
    data: dict[str, dict[str, Credential]]


def _check_api_key(api_key: str | None) -> None:
    expected = os.getenv("SCRAPER_API_KEY", "")
    if not expected:
        # API 키가 설정되지 않은 환경 (로컬 dev) 는 통과
        return
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("")
def list_credentials(x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)
    return {
        "companies": COMPANIES,
        "credentials": get_all_credentials(),
    }


@router.post("")
def patch_credentials(
    body: CredentialsUpdate,
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    # Pydantic model → plain dict
    updates: dict = {}
    for company, lessors in body.data.items():
        updates[company] = {}
        for lessor, cred in lessors.items():
            updates[company][lessor] = {"id": cred.id, "pw": cred.pw}
    saved = update_credentials(updates)
    return {"ok": True, "credentials": saved}
