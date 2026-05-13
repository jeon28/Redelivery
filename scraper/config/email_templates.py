"""
메일 반납 요청 양식 (템플릿) 관리.

- 임대사별 수신자/제목/본문 양식 저장
- 사용자가 프론트에서 편집 가능
- 영구 저장: Railway Volume의 /data/email_templates.json

템플릿 키는 "베이스 임대사 코드" 기준 10개:
  TEXA, TRIT, GOLD, FLOR, GESE, GCIC, CAIC, BCON, CARL, BLUE

장금/흥아의 변형 코드 (TRIT+TRAM, FLOR+DFIC, GLOD, GESE+CROS/SGCN)는
프론트에서 베이스 코드로 정규화해서 동일 템플릿을 사용한다.

변수 (template placeholders):
  {carrier_name}     장금상선 | 흥아라인
  {carrier_code}     SKR | HAS
  {carrier_alt}      SKR | HAL  (영문 메일 헤더용)
  {office}           본사 | 부산 | 인천 | 평택 | 광양 | 울산 (사무소)
  {region}           부산 | 인천 | 평택 | 광양 | 울산 (반납지역, 한글)
  {region_en}        BUSAN | INCHON | PYEONGTAEK | GWANGYANG | ULSAN (반납지역, 영문)
  {date}             5/14 (월/일)
  {first_container}  첫 컨테이너 번호
  {first_type}       첫 컨테이너 타입
  {containers}       컨테이너 블록 (carrier_code + no + type 반복)

서명(이름/연락처)은 Outlook 자동 서명에 맡기므로 본문에 포함하지 않는다.
양사 내부 메일은 항상 Cc에 포함 (container@sinokor.co.kr 등).
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

# 양사 내부 메일 공통 Cc (모든 임대사 기본값에 포함)
INTERNAL_CC = (
    "container@sinokor.co.kr; "
    "inchon@sinokor.co.kr; "
    "inc@heungaline.com"
)

# 한글 양식 본문 공통 (CAI Korea 대행: CAIC, BCON)
_BODY_KR = (
    "수신: {agent_label}\n"
    "발신: {carrier_name} {office}\n"
    "\n"
    "안녕하세요.\n"
    "\n"
    "하기 컨테이너 반납 요청드리오니 확인 후 반납번호 및 반납지역 회신 부탁드립니다.\n"
    "\n"
    "{containers}\n"
    "\n"
    "반납지역 : {region}"
)

# 영문 양식 본문 공통 (Seacube CARL, BSIU BLUE)
_BODY_EN = (
    "Dear All,\n"
    "\n"
    "Good day to you\n"
    "\n"
    "We have off-hire request for subjected container at {region_en}, KOREA.\n"
    "Please double check and confirm it.\n"
    "\n"
    "{containers}\n"
    "\n"
    "감사합니다"
)

DEFAULT_TEMPLATES: dict = {
    # ── 메일 임대사 (회신을 메일로 받는 임대사) ───────────────
    "CAIC": {
        "name": "CAI",
        "language": "ko",
        "to": "hjung@capps.com; june@capps.com; sjent@sjcon.kr; sjent_cy@sjcon.kr",
        "cc": f"{INTERNAL_CC}; owchoi@capps.com; caise@capps.com",
        "subject": "[{carrier_name}] {first_container} 요청 {date}",
        "body": _BODY_KR.replace("{agent_label}", "CAI / 정준혁 담당님"),
    },
    "BCON": {
        "name": "Beacon (CAI Korea 대행)",
        "language": "ko",
        "to": "hjung@capps.com; june@capps.com; sjent@sjcon.kr; sjent_cy@sjcon.kr",
        "cc": f"{INTERNAL_CC}; owchoi@capps.com; caise@capps.com",
        "subject": "[{carrier_name}] {first_container} 요청 {date}",
        "body": _BODY_KR.replace("{agent_label}", "CAI / 정준혁 담당님"),
    },
    "CARL": {
        "name": "Seacube",
        "language": "en",
        "to": "kchoi.agent@seacubecontainers.com; inccy@thelogis.com; gayun97@nate.com; mgyoon@thelogis.com",
        "cc": f"{INTERNAL_CC}; skeung@seacubecontainers.com",
        "subject": "[{carrier_alt}] {first_container} {first_type} OFF-HIRE / - {region_en}, KOREA. {date}",
        "body": _BODY_EN,
    },
    "BLUE": {
        "name": "Blue Sky Intermodal (BSIU)",
        "language": "en",
        "to": "lilian.qin@bsiu.com; icoral@bsiu.com; sjent_cy@sjcon.kr",
        "cc": f"{INTERNAL_CC}; movements@bsiu.com",
        "subject": "[{carrier_alt}] {first_container} {first_type} OFF-HIRE / - {region_en}, KOREA. {date}",
        "body": _BODY_EN,
    },

    # ── 웹반납 임대사 (백업/예외 케이스용 메일 양식) ────────────
    # 평소엔 웹 조회로 처리하지만 드물게 메일이 필요할 때 사용.
    # To/Cc는 일단 양사 내부 메일만 포함, 임대사 측 주소는 사용자가 추후 입력.
    "TEXA": {
        "name": "Textainer (백업)",
        "language": "en",
        "to": "",
        "cc": INTERNAL_CC,
        "subject": "[{carrier_alt}] {first_container} {first_type} OFF-HIRE / - {region_en}, KOREA. {date}",
        "body": _BODY_EN,
    },
    "TRIT": {
        "name": "Triton (백업)",
        "language": "en",
        "to": "",
        "cc": INTERNAL_CC,
        "subject": "[{carrier_alt}] {first_container} {first_type} OFF-HIRE / - {region_en}, KOREA. {date}",
        "body": _BODY_EN,
    },
    "GOLD": {
        "name": "Touax (GOLD/GLOD, 백업)",
        "language": "en",
        "to": "",
        "cc": INTERNAL_CC,
        "subject": "[{carrier_alt}] {first_container} {first_type} OFF-HIRE / - {region_en}, KOREA. {date}",
        "body": _BODY_EN,
    },
    "FLOR": {
        "name": "Florens (백업)",
        "language": "en",
        "to": "",
        "cc": INTERNAL_CC,
        "subject": "[{carrier_alt}] {first_container} {first_type} OFF-HIRE / - {region_en}, KOREA. {date}",
        "body": _BODY_EN,
    },
    "GESE": {
        "name": "Seaco (GESE) — 현재 메일 반납 중",
        "language": "en",
        "to": "",
        "cc": INTERNAL_CC,
        "subject": "[{carrier_alt}] {first_container} {first_type} OFF-HIRE / - {region_en}, KOREA. {date}",
        "body": _BODY_EN,
    },
    "GCIC": {
        "name": "GCX (GCIC, 백업)",
        "language": "en",
        "to": "",
        "cc": INTERNAL_CC,
        "subject": "[{carrier_alt}] {first_container} {first_type} OFF-HIRE / - {region_en}, KOREA. {date}",
        "body": _BODY_EN,
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
