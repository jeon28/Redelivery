# TEXA 개발 규칙

> 임대사: Textainer
> 코드: `TEXA`
> 루트 `../CLAUDE.md` 규칙을 먼저 따르고, 본 문서의 규칙을 추가로 적용합니다.

## 1. 기본 정보

| 항목 | 값 |
|------|-----|
| 임대사명 | Textainer |
| 코드 | `TEXA` |
| 로그인 URL | `https://www.textainer.com` (우상단 LOGIN 팝업) |
| 포털 URL | `https://tex.textainer.com/Customer/CustomerMenu.aspx` |
| 접근 방식 | 웹 자동화 (Playwright) |

## 2. 자격증명 키 규칙

| 선사 | ID 키 | PW 키 |
|------|-------|-------|
| 장금상선 (SK) | `SK_TEXA_ID` | `SK_TEXA_PW` |
| 흥아라인 (HA) | `HA_TEXA_ID` | `HA_TEXA_PW` |

- 선사 분기는 `company` 파라미터(`"SK"` / `"HA"`)로 처리하며, 스크래퍼가 해당 prefix의 환경변수를 로드한다.
- 본 문서 및 `ANALYSIS.md`에 실제 ID/PW를 절대 기재하지 않는다. 키 이름만 표기한다.

## 3. 위치 매핑

| 항목 | 경로 |
|------|------|
| 사이트 분석 문서 | `./ANALYSIS.md` |
| 스크래퍼 구현 | `../scraper/scrapers/texa.py` |
| 공통 베이스 클래스 | `../scraper/scrapers/base.py` |
| 자격증명 환경변수 | `../scraper/.env` |

## 4. 작업 규칙

- **분석 → 합의 → 구현 → 테스트** 순으로 진행하며, 각 단계 사이에 사용자 승인을 받는다.
- 사이트 UI/플로우가 변경되면 **먼저 `ANALYSIS.md`를 갱신** 한 후 `texa.py`를 수정한다.
- 선사 간 차이점(도시 기본값, 화면 차이 등)은 `ANALYSIS.md` 끝의 "선사 차이점" 섹션에 기록한다.

## 5. 주의사항

- **Book 버튼 = 실 발급**: 클릭 즉시 예약 생성 + 이메일 자동 발송 + Caps Left 차감. 동일 컨테이너 중복 실행 방지 로직 필수.
- Country/City 드롭다운은 동적 옵션이므로 텍스트 매칭으로 선택한다 (예: `KOREA - KOR`, `INCHON - INC`).
- Container ID 입력은 줄바꿈 구분 textarea이며 1회 최대 100개.
