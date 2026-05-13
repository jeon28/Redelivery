"""
자격증명 관리 모듈.

저장 우선순위:
1. CREDENTIALS_FILE (기본: /data/credentials.json) — Railway Volume에 영구 저장
2. 환경변수 (.env) — 초기값 / 폴백

런타임에 자격증명이 변경되면 파일에 즉시 저장되고 메모리에도 반영됨.
"""
import json
import logging
import os
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Railway Volume 마운트 경로. 로컬 개발 시에는 scraper 디렉토리에 저장.
CREDENTIALS_FILE = Path(os.getenv("CREDENTIALS_FILE", "/data/credentials.json"))

# 지원하는 회사 → 임대사 목록 (env var prefix 매핑 포함)
COMPANIES = {
    "장금상선": {
        "prefix": "SK",
        "lessors": ["TEXA", "TRIT", "GOLD", "FLOR", "GESE"],
    },
    "흥아라인": {
        "prefix": "HA",
        "lessors": ["TEXA", "TRIT", "GOLD", "FLOR", "GESE"],
    },
}

_lock = threading.Lock()


def _from_env() -> dict:
    """환경변수에서 모든 자격증명을 dict로 구성."""
    creds: dict = {}
    for company, cfg in COMPANIES.items():
        creds[company] = {}
        for lessor in cfg["lessors"]:
            key_id = f"{cfg['prefix']}_{lessor}_ID"
            key_pw = f"{cfg['prefix']}_{lessor}_PW"
            creds[company][lessor] = {
                "id": os.getenv(key_id, ""),
                "pw": os.getenv(key_pw, ""),
            }
    return creds


def _load() -> dict:
    """파일에서 자격증명 로드. 파일 없으면 환경변수 기반으로 생성 후 저장."""
    if CREDENTIALS_FILE.exists():
        try:
            with CREDENTIALS_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Loaded credentials from %s", CREDENTIALS_FILE)
            # 새 회사/임대사가 .env에 추가됐을 수 있으므로 병합
            env_creds = _from_env()
            for company, lessors in env_creds.items():
                data.setdefault(company, {})
                for lessor, kv in lessors.items():
                    data[company].setdefault(lessor, kv)
            return data
        except Exception as exc:
            logger.warning("Failed to load %s: %s — falling back to .env", CREDENTIALS_FILE, exc)
    creds = _from_env()
    _save(creds)
    return creds


def _save(creds: dict) -> None:
    """자격증명을 파일에 저장. 경로가 없으면 생성."""
    try:
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CREDENTIALS_FILE.open("w", encoding="utf-8") as f:
            json.dump(creds, f, ensure_ascii=False, indent=2)
        logger.info("Saved credentials to %s", CREDENTIALS_FILE)
    except Exception as exc:
        logger.error("Failed to save credentials to %s: %s", CREDENTIALS_FILE, exc)


# 모듈 로드 시 한 번 로드
CREDENTIALS: dict = _load()


def get_credential(company: str, lessor: str) -> dict[str, str]:
    """특정 회사/임대사의 자격증명 반환."""
    return CREDENTIALS.get(company, {}).get(lessor, {})


def get_all_credentials() -> dict:
    """전체 자격증명 반환 (UI 표시용)."""
    return CREDENTIALS


def update_credentials(updates: dict) -> dict:
    """
    자격증명 일괄 업데이트.

    updates 포맷:
    {
        "장금상선": {
            "TEXA": {"id": "newid", "pw": "newpw"},
            ...
        },
        ...
    }

    None 또는 누락된 필드는 기존 값 유지.
    """
    with _lock:
        for company, lessors in updates.items():
            if company not in CREDENTIALS:
                CREDENTIALS[company] = {}
            for lessor, kv in lessors.items():
                cur = CREDENTIALS[company].get(lessor, {"id": "", "pw": ""})
                new_id = kv.get("id") if kv.get("id") is not None else cur.get("id", "")
                new_pw = kv.get("pw") if kv.get("pw") is not None else cur.get("pw", "")
                CREDENTIALS[company][lessor] = {"id": new_id, "pw": new_pw}
        _save(CREDENTIALS)
    return CREDENTIALS
