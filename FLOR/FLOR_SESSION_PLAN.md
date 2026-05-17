# FLOR 로그인 세션 재사용 — 개발 계획서

> 작성일: 2026-05-15
> 트리거: Florens가 양사 계정을 계정 잠금 (봇으로 의심된 잦은 로그인). 월요일 PW 재발급 예정.
> 목표: 로그인·슬라이더 캡차 시도 빈도를 극적으로 줄여 재발 차단.

---

## 목표

- 매 조회마다 신규 로그인 + 캡차 통과 → **세션이 유효한 동안 로그인 단계 건너뜀**.
- 슬라이더 캡차는 세션 만료 시점 1회만 통과.
- FLOR 외 임대사 변경 없음. 검증 후 다른 임대사로 확장.

## 결정 사항

| 항목 | 값 |
|---|---|
| 방식 | Playwright `storage_state` 파일 (쿠키 + localStorage) |
| 저장 경로 | `FLOR_SESSION_FILE` env var, 기본 `/data/flor_session.json` (Railway Volume) |
| 만료 감지 | redeliv 페이지 진입 시 URL이 `/login` 으로 튕기면 신규 로그인 |
| 저장 타이밍 | 신규 로그인 성공 직후 1회 |
| 적용 범위 | **FLOR만** (검증 후 base.py로 추출해 다른 임대사 확장) |

## 변경 파일

| 파일 | 변경 |
|---|---|
| `scraper/scrapers/flor.py` | `start()` override (storage_state 복원), `login()` 흐름 분기 (세션 체크 → 유효하면 스킵, 무효면 `_fresh_login` → `_save_session`), `close()` override 불필요 (browser.close 시 context 같이 닫힘) |

## 동작 시나리오 (월요일 새 PW 적용 후)

1. 첫 FLOR 조회 → `/data/flor_session.json` 없음 → 슬라이더 + Sign-in → 로그인 성공 → 세션 파일 저장.
2. 두 번째~N번째 조회 → 세션 파일 복원 → `/func/redelivery#/` 바로 진입 가능 → 로그인·캡차 스킵.
3. 세션 만료 (수 시간~수일 후) → `/login` redirect 감지 → 신규 로그인 → 세션 파일 갱신.

## 위험·보완

- 세션 파일에는 인증 쿠키가 들어 있으므로 Railway Volume 외 다른 곳에 노출 금지.
- Florens가 IP·UA 바인딩하면 다른 환경에서 복원 시 실패 → 그 경우 신규 로그인으로 자동 회귀 (코드가 분기 처리).
- 두 회사(SK/HA)는 자격증명이 다르므로 **세션 파일도 회사별로 분리**: `/data/flor_session_{SK|HA}.json`.

## 작업 순서

1. 본 계획서 검토·승인.
2. `flor.py` 수정 + 회사별 세션 파일 경로 분기.
3. 로컬 import 검증 (실 로그인은 월요일까지 불가).
4. 커밋 + push. Vercel·Railway 자동 재배포.
5. 월요일 PW 갱신 후 첫 FLOR 조회 → 세션 파일 생성 확인 → 두 번째 조회에서 캡차 미발생 확인.
