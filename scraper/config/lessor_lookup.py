"""
컨테이너 번호 → 임대사 자동 판별.

판별 순서:
  1) 반납 대장(엑셀 업로드) 에 있는 번호 → 대장의 Lessor/LINE/TPSZ 그대로
  2) 없으면 접두어(앞 4자리) 표
  3) 둘 다 없으면 미판별

- 영구 저장: /data/lease_inventory.json, /data/prefix_map.json (GCS 마운트)
- 접두어 기본값은 2026-10-26 반납 대장 집계를 사용자 검수 후 확정한 표.
- 여러 Cloud Run 인스턴스가 같은 파일을 보므로 파일 mtime 이 바뀌면 다시 읽는다.
"""
import io
import json
import logging
import os
import re
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

LEASE_INVENTORY_FILE = Path(
    os.getenv("LEASE_INVENTORY_FILE", "/data/lease_inventory.json")
)
PREFIX_MAP_FILE = Path(os.getenv("PREFIX_MAP_FILE", "/data/prefix_map.json"))

_CONTAINER_RE = re.compile(r"^[A-Z]{4}\d{7}$")
_LESSOR_RE = re.compile(r"^[A-Z]{4}$")
_TYPE_RE = re.compile(r"^\d{2}[A-Z][A-Z0-9]$")

# 대장 표기 → 시스템 베이스 코드 (프론트 templateKey 와 같은 단위)
LESSOR_ALIASES: dict[str, str] = {
    "TEXT": "TEXA",   # 대장 오타
    "MWSL": "MWSC",   # 같은 임대사 (사용자 확인 2026-10-26)
    "CALT": "MWSC",   # MWSC+CALT 메일 묶음
    "GLOD": "GOLD",   # 장금 표기
    "GLDU": "GOLD",   # 접두어를 임대사 칸에 잘못 적은 행
}

# 대장 LINE 표기 → company 키
LINE_ALIASES: dict[str, str] = {"SKR": "SK", "HAS": "HA", "HAL": "HA"}

DEFAULT_PREFIX_MAP: dict[str, str] = {
    **dict.fromkeys(["TEMU", "TGHU", "TGBU", "MAGU", "CLHU", "AXIU", "HJCU", "HCIU"], "TEXA"),
    **dict.fromkeys(["TCNU", "TCLU", "TRHU", "TCKU", "TLLU", "TRIU"], "TRIT"),
    **dict.fromkeys(["DFSU", "FCIU", "FSCU", "FBLU", "FDCU", "ESPU", "FCGU", "FJKU", "PCIU"], "FLOR"),
    **dict.fromkeys(["SEGU", "GESU"], "GESE"),
    **dict.fromkeys(["GLDU", "TGCU"], "GOLD"),
    **dict.fromkeys(["BMOU", "BEAU"], "BCON"),
    **dict.fromkeys(["WBPU", "DRYU", "GAOU", "RFCU"], "CARL"),
    **dict.fromkeys(["CAIU", "CAAU", "CAXU"], "CAIC"),
    "BSIU": "BLUE",
    "UETU": "GVCC",
    "HALU": "MWSC",
    **dict.fromkeys(["HSLU", "HSZU", "KMLU"], "HSLN"),
    **dict.fromkeys(["CICU", "JZPU", "RXTU", "STNU", "TFLU", "VPLU"], "BEST"),
}

# ISO 6346 문자값: A=10 부터, 11의 배수(11/22/33)는 건너뜀
_ISO6346_VALUES: dict[str, int] = {
    **{str(d): d for d in range(10)},
    **dict(zip(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        [v for v in range(10, 39) if v % 11 != 0],
    )),
}

_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}


def normalize_lessor(raw) -> str | None:
    s = str(raw or "").strip().upper()
    s = LESSOR_ALIASES.get(s, s)
    return s if _LESSOR_RE.match(s) else None


def check_digit_ok(container: str) -> bool:
    """ISO 6346 체크디짓 검증."""
    if not _CONTAINER_RE.match(container):
        return False
    total = sum(_ISO6346_VALUES[ch] * (2 ** i) for i, ch in enumerate(container[:10]))
    return (total % 11) % 10 == int(container[10])


# ── 파일 IO ──────────────────────────────────────────────────────

def _read_json(path: Path):
    """mtime 기반 캐시. 다른 인스턴스가 파일을 바꾸면 다음 호출에서 다시 읽는다."""
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _cache.pop(str(path), None)
        return None
    hit = _cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return None
    _cache[str(path)] = (mtime, data)
    return data


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(path)
    _cache.pop(str(path), None)


# ── 접두어 표 ────────────────────────────────────────────────────

def get_prefix_map() -> dict[str, str]:
    data = _read_json(PREFIX_MAP_FILE)
    if isinstance(data, dict) and data:
        return data
    return dict(DEFAULT_PREFIX_MAP)


def save_prefix_map(mapping: dict[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for p, l in mapping.items():
        p = str(p or "").strip().upper()
        l = normalize_lessor(l)
        if re.match(r"^[A-Z]{4}$", p) and l:
            clean[p] = l
    with _lock:
        _write_json(PREFIX_MAP_FILE, clean)
    return clean


# ── 반납 대장 ────────────────────────────────────────────────────

def _find_header(rows: list[tuple]) -> tuple[int, list[str]] | None:
    for idx, row in enumerate(rows):
        hdr = [str(h).strip() if h is not None else "" for h in row]
        if "Container No" in hdr and "Lessor" in hdr:
            return idx, hdr
    return None


def parse_inventory_xlsx(content: bytes) -> dict:
    """반납 대장 엑셀 → {units: {cn: {...}}, sheets: [{name, rows}]}.

    머리행에 'Container No' 와 'Lessor' 가 있는 시트만 읽는다.
    같은 번호가 여러 행이면 첫 열(조회일/본사 요청일)이 가장 최근인 행을 채택.
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    units: dict[str, dict] = {}
    dates: dict[str, datetime] = {}
    sheets: list[dict] = []
    for ws in wb.worksheets:
        it = ws.iter_rows(values_only=True)
        head_rows = []
        for _ in range(5):
            try:
                head_rows.append(next(it))
            except StopIteration:
                break
        found = _find_header(head_rows)
        if not found:
            continue
        hidx, hdr = found
        ci, li = hdr.index("Container No"), hdr.index("Lessor")
        lni = hdr.index("LINE") if "LINE" in hdr else None
        ti = hdr.index("TPSZ") if "TPSZ" in hdr else None
        coi = next((hdr.index(k) for k in ("Conract No", "Contract No") if k in hdr), None)

        def cell(r, i):
            return r[i] if i is not None and i < len(r) else None

        count = 0
        for r in [*head_rows[hidx + 1:], *it]:
            cn = str(cell(r, ci) or "").strip().upper()
            if not _CONTAINER_RE.match(cn):
                continue
            lessor = normalize_lessor(cell(r, li))
            if not lessor:
                continue
            d = cell(r, 0)
            d = d if isinstance(d, datetime) else datetime.min
            if cn in units and d < dates[cn]:
                continue
            tp = str(cell(r, ti) or "").strip().upper()
            units[cn] = {
                "lessor": lessor,
                "line": LINE_ALIASES.get(str(cell(r, lni) or "").strip().upper()),
                "type": tp if _TYPE_RE.match(tp) else None,
                "contract": str(cell(r, coi) or "").strip() or None,
                "sheet": ws.title.strip(),
            }
            dates[cn] = d
            count += 1
        sheets.append({"name": ws.title.strip(), "rows": count})
    wb.close()
    return {"units": units, "sheets": sheets}


def save_inventory(parsed: dict, filename: str | None) -> dict:
    data = {
        "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filename": filename,
        "sheets": parsed["sheets"],
        "units": parsed["units"],
    }
    with _lock:
        _write_json(LEASE_INVENTORY_FILE, data)
    return inventory_summary()


def _inventory() -> dict:
    data = _read_json(LEASE_INVENTORY_FILE)
    return data if isinstance(data, dict) else {}


def inventory_summary() -> dict:
    inv = _inventory()
    units = inv.get("units") or {}
    by_lessor = Counter(u["lessor"] for u in units.values())
    return {
        "uploaded_at": inv.get("uploaded_at"),
        "filename": inv.get("filename"),
        "sheets": inv.get("sheets") or [],
        "count": len(units),
        "by_lessor": dict(by_lessor.most_common()),
    }


def _prefix_candidates(prefix: str) -> list[str]:
    """대장에서 같은 접두어로 나온 임대사들 (많은 순)."""
    units = _inventory().get("units") or {}
    cnt = Counter(u["lessor"] for cn, u in units.items() if cn.startswith(prefix))
    return [l for l, _ in cnt.most_common()]


# ── 판별 ─────────────────────────────────────────────────────────

def lookup(container: str) -> dict:
    cn = re.sub(r"[\s\-]", "", str(container or "")).upper()
    out = {
        "container_no": cn,
        "valid_format": bool(_CONTAINER_RE.match(cn)),
        "check_digit_ok": check_digit_ok(cn),
        "lessor": None,
        "source": None,
        "line": None,
        "type": None,
        "contract": None,
        "candidates": [],
    }
    if not out["valid_format"]:
        return out

    unit = (_inventory().get("units") or {}).get(cn)
    if unit:
        out.update({
            "lessor": unit["lessor"],
            "source": "inventory",
            "line": unit.get("line"),
            "type": unit.get("type"),
            "contract": unit.get("contract"),
        })
    else:
        lessor = get_prefix_map().get(cn[:4])
        if lessor:
            out.update({"lessor": lessor, "source": "prefix"})

    cands = _prefix_candidates(cn[:4])
    if out["lessor"] and out["lessor"] not in cands:
        cands.insert(0, out["lessor"])
    out["candidates"] = cands if len(cands) > 1 else []
    return out
