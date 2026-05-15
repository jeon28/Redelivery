"""
FLOR Apply Redelivery — Port × Depot 정적 데이터.

데이터 출처: 사이트에서 1회용 수집 스크립트(`scraper/scripts/collect_flor_depots.py`)로
한 회사(SK 또는 HA)로 로그인 후 Port → Depot 드롭다운 옵션을 추출한 결과.
SK / HA 계약별 Port·Depot 차이는 사실상 동일하다고 가정 → company 키를 두 회사 공통으로 채움.

label은 FLOR 사이트의 Element UI 드롭다운에 실제 노출되는 문자열.
scraper(`flor.py`)의 `_select_depot`이 `(CODE)` 패턴으로 substring 매칭하므로 label 안에 코드가 들어 있기만 하면 됨.
"""

from __future__ import annotations


# (company, region) → [ { code, name, label }, ... ]
# label: Element UI 옵션 텍스트. 일반 포맷: "(KRPUS07) YoungJin CY (KRPUS07)"
# region 값은 SearchForm의 REGIONS value(UN/LOCODE 영문 도시): BUSAN/INCHON/GWANGYANG/PYEONGTAEK/ULSAN
# 인천은 기존 `PORT_DEFAULT_DEPOT` 1개를 시드값으로 두어 fallback 호환.
FLOR_DEPOTS: dict[tuple[str, str], list[dict[str, str]]] = {
    ("장금상선", "BUSAN"):     [],
    ("장금상선", "INCHON"):    [
        {
            "code": "KRINC04",
            "name": "SeungJin Enterprise Co., Ltd.",
            "label": "(KRINC04) SeungJin Enterprise Co., Ltd. (KRINC04)",
        },
    ],
    ("장금상선", "GWANGYANG"): [],
    ("장금상선", "PYEONGTAEK"): [],
    ("장금상선", "ULSAN"):     [],
    ("흥아라인", "BUSAN"):     [],
    ("흥아라인", "INCHON"):    [
        {
            "code": "KRINC04",
            "name": "SeungJin Enterprise Co., Ltd.",
            "label": "(KRINC04) SeungJin Enterprise Co., Ltd. (KRINC04)",
        },
    ],
    ("흥아라인", "GWANGYANG"): [],
    ("흥아라인", "PYEONGTAEK"): [],
    ("흥아라인", "ULSAN"):     [],
}


def list_depots(company: str, region: str) -> list[dict[str, str]]:
    """company × region 에 해당하는 depot 목록 반환. 없으면 빈 리스트."""
    return list(FLOR_DEPOTS.get((company, region), []))
