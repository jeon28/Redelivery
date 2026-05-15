"""
메일 반납 요청 양식 (템플릿) 관리.

- 임대사별 수신자/제목/본문 양식 저장
- 사무소별(인천/부산/…) 부분 오버라이드 지원
- 사용자가 프론트에서 편집 가능
- 영구 저장: Railway Volume의 /data/email_templates.json

데이터 구조 (v2):
  TEMPLATES[lessor] = {
      "default": { name, language, to, cc, subject, body },
      "offices": {
          "인천": { to?, cc?, subject?, body?, ... },   # 부분 오버라이드
          "부산": { ... },
      }
  }

조회 시 office 인자를 주면 default + offices[office] 머지 결과를 반환.
office 인자가 없거나 매칭 없으면 default만 반환.

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
  {region_en}        BUSAN | INCHON | PYEONGTAEK | GWANGYANG | ULSAN
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

# 초기 사무소 슬롯. 신규 사무소는 update_template에서 자동 생성되므로
# 여기에 명시하지 않아도 동작하지만, 빈 슬롯을 두면 UI 탭 노출이 일관됨.
INITIAL_OFFICES = ("인천", "부산")

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

# 임대사별 default 양식. offices 슬롯은 _ensure_v2_shape에서 자동 부착.
DEFAULT_TEMPLATES_FLAT: dict = {
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


def _wrap_v2(default_template: dict) -> dict:
    """flat한 임대사 템플릿을 v2 shape (default+offices)로 감싼다."""
    return {
        "default": dict(default_template),
        "offices": {office: {} for office in INITIAL_OFFICES},
    }


DEFAULT_TEMPLATES: dict = {
    lessor: _wrap_v2(tpl) for lessor, tpl in DEFAULT_TEMPLATES_FLAT.items()
}


def _ensure_v2_shape(data: dict) -> bool:
    """
    구버전(flat) 데이터를 v2 shape으로 마이그레이션.

    구 데이터 예: {"TEXA": {"to":..., "cc":..., ...}}
    신 데이터 예: {"TEXA": {"default": {...}, "offices": {"인천":{}, "부산":{}}}}

    변경이 일어났으면 True 반환 (즉시 저장 유도).
    """
    changed = False
    for lessor, payload in list(data.items()):
        if not isinstance(payload, dict):
            continue
        is_v2 = "default" in payload and isinstance(payload.get("offices"), dict)
        if is_v2:
            # 신규 사무소 슬롯이 누락됐을 수 있으니 보강
            for office in INITIAL_OFFICES:
                payload["offices"].setdefault(office, {})
            continue
        # v1 (flat) → v2 로 승격. 기존 필드 전부 default로 이동.
        wrapped = {
            "default": dict(payload),
            "offices": {office: {} for office in INITIAL_OFFICES},
        }
        data[lessor] = wrapped
        changed = True
        logger.info("Migrated email template %s from flat → v2 shape", lessor)
    return changed


_lock = threading.Lock()


def _load() -> dict:
    if EMAIL_TEMPLATES_FILE.exists():
        try:
            with EMAIL_TEMPLATES_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Loaded email templates from %s", EMAIL_TEMPLATES_FILE)
            migrated = _ensure_v2_shape(data)
            # 새 임대사가 DEFAULT에 추가됐을 수 있으니 병합 (default만 보강)
            for lessor, defaults in DEFAULT_TEMPLATES.items():
                data.setdefault(lessor, dict(defaults))
            if migrated:
                _save(data)
            return data
        except Exception as exc:
            logger.warning("Failed to load %s: %s — using defaults", EMAIL_TEMPLATES_FILE, exc)
    _save(DEFAULT_TEMPLATES)
    return json.loads(json.dumps(DEFAULT_TEMPLATES))  # deep copy


def _save(templates: dict) -> None:
    try:
        EMAIL_TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with EMAIL_TEMPLATES_FILE.open("w", encoding="utf-8") as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)
        logger.info("Saved email templates to %s", EMAIL_TEMPLATES_FILE)
    except Exception as exc:
        logger.error("Failed to save email templates: %s", exc)


TEMPLATES: dict = _load()


def _merge(default: dict, override: dict) -> dict:
    """default 위에 override의 비어있지 않은 필드만 덮어쓴다."""
    out = dict(default)
    for k, v in (override or {}).items():
        if v is None:
            continue
        # 빈 문자열은 "기본값 그대로 쓰겠다"는 의도로 해석 → 덮어쓰지 않음
        if isinstance(v, str) and v == "":
            continue
        out[k] = v
    return out


def get_templates(office: str | None = None) -> dict:
    """
    office가 주어지면 default + offices[office] 머지된 평면 형태 반환.
    office가 없으면 v2 raw shape 그대로 반환 (관리/디버깅용).
    """
    if office is None:
        return TEMPLATES
    merged: dict = {}
    for lessor, payload in TEMPLATES.items():
        default = payload.get("default", {})
        override = payload.get("offices", {}).get(office, {})
        merged[lessor] = _merge(default, override)
    return merged


def update_template(
    lessor: str,
    fields: dict,
    office: str | None = None,
) -> dict:
    """
    임대사 템플릿 부분 업데이트.

    - office=None: default 값 자체를 수정 (관리자 영역)
    - office="부산": offices["부산"] 오버라이드 갱신
    """
    with _lock:
        if lessor not in TEMPLATES:
            # 신규 임대사가 처음 들어오는 경우 빈 v2 shape 생성
            TEMPLATES[lessor] = {"default": {}, "offices": {o: {} for o in INITIAL_OFFICES}}
        slot = TEMPLATES[lessor]
        slot.setdefault("default", {})
        slot.setdefault("offices", {})

        if office is None:
            target = slot["default"]
        else:
            slot["offices"].setdefault(office, {})
            target = slot["offices"][office]

        for k, v in fields.items():
            if v is None:
                continue
            target[k] = v
        _save(TEMPLATES)

    # 응답은 사용자가 본 상태(머지 후) 반환
    if office is None:
        return TEMPLATES[lessor]["default"]
    return _merge(
        TEMPLATES[lessor].get("default", {}),
        TEMPLATES[lessor]["offices"].get(office, {}),
    )


def reset_template(lessor: str, office: str | None = None) -> dict:
    """
    - office=None: default를 코드 기본값으로 복원 (offices 오버라이드는 보존)
    - office="부산": offices["부산"] 오버라이드만 비움 → default로 회귀
    """
    with _lock:
        if office is None:
            if lessor in DEFAULT_TEMPLATES:
                TEMPLATES.setdefault(lessor, {"offices": {}})
                TEMPLATES[lessor]["default"] = dict(DEFAULT_TEMPLATES[lessor]["default"])
                TEMPLATES[lessor].setdefault(
                    "offices", {o: {} for o in INITIAL_OFFICES}
                )
        else:
            if lessor in TEMPLATES:
                TEMPLATES[lessor].setdefault("offices", {})
                TEMPLATES[lessor]["offices"][office] = {}
        _save(TEMPLATES)

    if office is None:
        return TEMPLATES.get(lessor, {}).get("default", {})
    return _merge(
        TEMPLATES.get(lessor, {}).get("default", {}),
        TEMPLATES.get(lessor, {}).get("offices", {}).get(office, {}),
    )
