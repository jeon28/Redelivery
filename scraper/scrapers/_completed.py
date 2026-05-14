"""'이미 반납 완료' 상태 감지 헬퍼.

배경: 임대사별로 "Closed/Completed/Already redelivered" 류 응답이 다른
모양으로 노출됨.

- FLOR: Status 컬럼이 'Closed'로 구조적으로 노출 → flor.py 내부에서 직접 처리.
  이 헬퍼는 사용 안 함.
- TRIT: Request Redelivery 후 Invalid 탭에 자유 텍스트 reason 으로 노출.
- GOLD: Search 결과 첫 행 메시지 또는 모달 'cannot' 테이블의 자유 텍스트.

TRIT/GOLD는 실 데이터로 reason 텍스트를 수집해야 패턴 채울 수 있음.
현 시점에는 패턴 리스트가 비어 있어 함수는 항상 False — false positive 방지.
패턴 발견 시 아래 dict에 한 줄씩 추가하면 즉시 활성화.
"""

# 임대사 코드 → '완료' 의미의 reason 텍스트 부분일치 패턴 목록 (대소문자 무시).
COMPLETED_REASON_PATTERNS: dict[str, list[str]] = {
    "TRIT": [
        # TODO: 실제 reason 수집 후 추가. 예시 후보:
        #   "already redelivered",
        #   "off-hire complete",
        #   "previously off-hired",
    ],
    "GOLD": [
        # TODO: 동일
    ],
}


def detect_completed(lessor: str, reason: str | None) -> bool:
    """reason 텍스트가 해당 임대사의 '완료' 패턴 중 하나에 부분일치하면 True."""
    if not reason:
        return False
    r = reason.lower()
    return any(p.lower() in r for p in COMPLETED_REASON_PATTERNS.get(lessor, []))
