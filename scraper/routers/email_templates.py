"""
메일 발송 양식(템플릿) 조회/수정 API.

세션 인증 + Unlock 쿠키는 프론트 API 라우트에서 검사하므로,
스크래퍼 측은 X-API-Key만 검증.
"""
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config.email_templates import (
    get_templates,
    update_template,
    reset_template,
)

router = APIRouter(prefix="/email-templates", tags=["email-templates"])


class TemplatePatch(BaseModel):
    name: str | None = None
    language: str | None = None
    to: str | None = None
    cc: str | None = None
    subject: str | None = None
    body: str | None = None


def _check_api_key(api_key: str | None) -> None:
    expected = os.getenv("SCRAPER_API_KEY", "")
    if not expected:
        return
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("")
def list_templates(x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)
    return {"templates": get_templates()}


@router.patch("/{lessor}")
def patch_template(
    lessor: str,
    body: TemplatePatch,
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    updated = update_template(lessor, body.model_dump(exclude_unset=True))
    return {"ok": True, "lessor": lessor, "template": updated}


@router.post("/{lessor}/reset")
def reset_template_route(
    lessor: str,
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    restored = reset_template(lessor)
    return {"ok": True, "lessor": lessor, "template": restored}
