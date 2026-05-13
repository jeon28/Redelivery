"""
메일 반납 요청 양식 (템플릿) 관리.

- 임대사별 수신자/제목/본문 양식 저장
- 사용자가 프론트에서 편집 가능
- 영구 저장: Railway Volume의 /data/email_templates.json

변수:
  {carrier_name}   장금상선 | 흥아라인
  {carrier_code}   SKR | HAS
  {region}         인천 | 부산 | 광양
  {region_en}      INCHON | BUSAN | GWANGYANG
  {date}           5/14 (월/일)
  {first_container}  첫 컨테이너 번호
  {containers}     컨테이너 블록 (carrier_code + no + type 반복)
"""
import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

EMAIL_TEMPLATES_FILE = Path(
    os.getenv("EMAIL_TEMPLATES_FILE", "/data/email_templates.json")
)

# 메일 발송 대상 임대사 (모두 회신 양식은 별도, 여기는 발송 양식만)
DEFAULT_TEMPLATES: dict = {
    "CAIC": {
        "name": "CAI Korea (CAIC)",
        "language": "ko",
        "to": "hjung@capps.com; june@capps.com; sjent@sjcon.kr; sjent_cy@sjcon.kr",
        "cc": "container@sinokor.co.kr; inchon@sinokor.co.kr; owchoi@capps.com; caise@capps.com",
        "subject": "[{carrier_name}] {first_container} 요청 {date}",
        "body": (
            "수신: CAI / 정준혁 담당님\n"
            "발신: {carrier_name} 인천사무소 전성현\n"
            "\n"
            "안녕하세요.\n"
            "\n"
            "하기 컨테이너 반납 요청드리오니 확인 후 반납번호 및 반납지역 회신 부탁드립니다.\n"
            "\n"
            "{containers}\n"
            "\n"
            "반납지역 : {region}\n"
            "\n"
            "\n"
            "Best Regards,\n"
            "Sean Jeon / 전 성 현\n"
            "INCHEON OFFICE"
        ),
    },
    "BCON": {
        "name": "Beacon (BCON) — CAI Korea 대행",
        "language": "ko",
        "to": "hjung@capps.com; june@capps.com; sjent@sjcon.kr; sjent_cy@sjcon.kr",
        "cc": "container@sinokor.co.kr; inchon@sinokor.co.kr; owchoi@capps.com; caise@capps.com",
        "subject": "[{carrier_name}] {first_container} 요청 {date}",
        "body": (
            "수신: CAI / 정준혁 담당님\n"
            "발신: {carrier_name} 인천사무소 전성현\n"
            "\n"
            "안녕하세요.\n"
            "\n"
            "하기 컨테이너 반납 요청드리오니 확인 후 반납번호 및 반납지역 회신 부탁드립니다.\n"
            "\n"
            "{containers}\n"
            "\n"
            "반납지역 : {region}\n"
            "\n"
            "\n"
            "Best Regards,\n"
            "Sean Jeon / 전 성 현\n"
            "INCHEON OFFICE"
        ),
    },
    "CARL": {
        "name": "Seacube (CARL)",
        "language": "en",
        "to": "kchoi.agent@seacubecontainers.com; inccy@thelogis.com; gayun97@nate.com; mgyoon@thelogis.com",
        "cc": "container@sinokor.co.kr; inc@heungaline.com; skeung@seacubecontainers.com",
        "subject": "[{carrier_alt}] {first_container} {first_type} OFF-HIRE / - {region_en}, KOREA. {date}",
        "body": (
            "Dear All,\n"
            "\n"
            "Good day to you\n"
            "\n"
            "We have off-hire request for subjected container at {region_en}, KOREA.\n"
            "Please double check and confirm it.\n"
            "\n"
            "{containers}\n"
            "\n"
            "감사합니다\n"
            "\n"
            "\n"
            "Best Regards,\n"
            "Sean Jeon / 전 성 현\n"
            "INCHEON OFFICE"
        ),
    },
    "BLUE": {
        "name": "Blue Sky Intermodal (BLUE / BSIU)",
        "language": "en",
        "to": "lilian.qin@bsiu.com; icoral@bsiu.com; sjent_cy@sjcon.kr",
        "cc": "container@sinokor.co.kr; inchon@sinokor.co.kr; movements@bsiu.com",
        "subject": "[{carrier_alt}] {first_container} {first_type} OFF-HIRE / - {region_en}, KOREA. {date}",
        "body": (
            "Dear All,\n"
            "\n"
            "Good day to you\n"
            "\n"
            "We have off-hire request for subjected container at {region_en}, KOREA.\n"
            "Please double check and confirm it.\n"
            "\n"
            "{containers}\n"
            "\n"
            "감사합니다\n"
            "\n"
            "\n"
            "Best Regards,\n"
            "Sean Jeon / 전 성 현\n"
            "INCHEON OFFICE"
        ),
    },
}

_lock = threading.Lock()


def _load() -> dict:
    if EMAIL_TEMPLATES_FILE.exists():
        try:
            with EMAIL_TEMPLATES_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Loaded email templates from %s", EMAIL_TEMPLATES_FILE)
            # 새 임대사가 DEFAULT에 추가됐을 수 있으니 병합
            for k, v in DEFAULT_TEMPLATES.items():
                data.setdefault(k, v)
            return data
        except Exception as exc:
            logger.warning("Failed to load %s: %s — using defaults", EMAIL_TEMPLATES_FILE, exc)
    _save(DEFAULT_TEMPLATES)
    return dict(DEFAULT_TEMPLATES)


def _save(templates: dict) -> None:
    try:
        EMAIL_TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with EMAIL_TEMPLATES_FILE.open("w", encoding="utf-8") as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)
        logger.info("Saved email templates to %s", EMAIL_TEMPLATES_FILE)
    except Exception as exc:
        logger.error("Failed to save email templates: %s", exc)


TEMPLATES: dict = _load()


def get_templates() -> dict:
    return TEMPLATES


def update_template(lessor: str, fields: dict) -> dict:
    """단일 임대사 템플릿의 일부 필드 업데이트."""
    with _lock:
        if lessor not in TEMPLATES:
            TEMPLATES[lessor] = {}
        for k, v in fields.items():
            if v is not None:
                TEMPLATES[lessor][k] = v
        _save(TEMPLATES)
    return TEMPLATES[lessor]


def reset_template(lessor: str) -> dict:
    """특정 임대사 템플릿을 기본값으로 되돌림."""
    with _lock:
        if lessor in DEFAULT_TEMPLATES:
            TEMPLATES[lessor] = dict(DEFAULT_TEMPLATES[lessor])
            _save(TEMPLATES)
    return TEMPLATES.get(lessor, {})
