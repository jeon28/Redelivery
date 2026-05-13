# GESE 개발 규칙

> 임대사: SeaCo (Sea Container)
> 코드: `GESE` (장금 변형 `GESE+CROS`, 흥아 변형 `GESE+SGCN`)
> 도메인 (메모리): `seacoglobal.com`
> 루트 `../CLAUDE.md` 규칙을 먼저 따르고, 본 문서의 규칙을 추가로 적용합니다.

## 1. 기본 정보

| 항목 | 값 |
|------|-----|
| 임대사명 | SeaCo |
| 코드 | `GESE` (`+CROS`, `+SGCN` 접미사는 `_normalize_lessor`로 GESE로 통합) |
| 도메인 | `seacoglobal.com` |
| 로그인 URL | _(분석 시 기록)_ |
| 접근 방식 | 웹 자동화 (Playwright) — 과거 PLAN.md에서 "웹 미작동" 보류였으나 재시도 |

## 2. 자격증명 키 규칙

| 선사 | ID 키 | PW 키 |
|------|-------|-------|
| 장금상선 (SK) | `SK_GESE_ID` | `SK_GESE_PW` |
| 흥아라인 (HA) | `HA_GESE_ID` | `HA_GESE_PW` |

- 장금/흥아 모두 사용. 본 문서/`ANALYSIS.md`에 실 ID/PW 기재 금지.

## 3. 위치 매핑

| 항목 | 경로 |
|------|------|
| 사이트 분석 문서 | `./ANALYSIS.md` |
| 스크래퍼 구현 | `../scraper/scrapers/gese.py` |
| 공통 베이스 클래스 | `../scraper/scrapers/base.py` |
| 자격증명 환경변수 | `../scraper/.env` |

## 4. 작업 규칙

- **분석 → 합의 → 구현 → 테스트** 순. 각 단계 사이 사용자 승인.
- `+CROS`/`+SGCN` 접미사는 코드 분기 시 `_normalize_lessor`로 처리됨 (이미 base.py에 적용).
- 사이트 변경 시 `ANALYSIS.md` 먼저 갱신 후 `gese.py` 수정.
- 선사 차이점은 `ANALYSIS.md` 끝 섹션에 기록.

## 5. 분석 시 최소 캡처 항목

- 로그인 URL/폼 (캡차/2FA 유무, 슬라이더 여부)
- 반납 메뉴 진입 경로 (직접 URL 또는 메뉴 클릭)
- 입력 폼 (지역/포트/컨테이너 번호/날짜 등) + 위젯 종류
- 결과 화면 (가능/불가, 컬럼명)
- 반납번호 발급 트리거 + 단계 수
- 예약 취소 경로

## 6. 주의사항

- 과거 "웹 미작동" 메모가 있으므로 사이트 동작 여부부터 검증.
- 실 발급 위험성 사전 확인. 안전 검증 전까지 발급 버튼 클릭 금지.
- 중복 예약 방지 로직 필수.
- 계정 보호 (실 ID/PW 기재 금지).
