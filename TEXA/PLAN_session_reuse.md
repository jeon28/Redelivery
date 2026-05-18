# TEXA 세션 재사용 (storage_state) 계획

## 목표

매 조회마다 풀 로그인 (~8~18초) 을 반복하는 비용을 제거한다.
Playwright `storage_state` (쿠키 + localStorage) 를 회사별로 저장·복원하여
유효 세션이 있을 때 로그인 단계 전체를 건너뛴다.

FLOR (`02cd3ca`) 에서 검증된 패턴을 TEXA에 그대로 이식.

## 적용 범위

`scraper/scrapers/texa.py` **단일 파일**. `base.py`, `query.py`, 프론트엔드,
기타 임대사 무관.

## 동작 설계

### 세션 파일 위치

- 디렉토리: `TEXA_SESSION_DIR` env (기본 `/data` — Railway Volume)
- 파일명: `texa_session_SK.json` / `texa_session_HA.json` (선사별 분리)
- FLOR 와 같은 `/data` 디렉토리, prefix만 다르게.

### start() 오버라이드

`BaseScraper.start()` 는 `browser.new_page()` 를 직접 만든다.
TEXA에선 `browser.new_context(storage_state=...)` → `context.new_page()` 로
교체한다. `self.context` 를 보관해 나중에 `context.storage_state(path=...)`
호출 가능하게 함.

```python
self.context = await self.browser.new_context(
    storage_state=str(sess) if sess.exists() else None
)
self.page = await self.context.new_page()
```

### login() 분기

기존 `login()` 본체는 **로직 변경 없이** `_fresh_login()` 으로 이름만 변경.

새 `login()`:
1. 세션 파일이 있으면 portal URL (`tex.textainer.com/Customer/CustomerMenu.aspx`) 로 직접 goto.
2. `wait_for_function` 으로 `window.location.href.includes('tex.textainer.com')` 확인 (단 짧은 타임아웃, 10s).
3. URL 이 portal 도메인에 머물면 → 세션 유효, `return True`.
4. URL 이 `www.textainer.com` 또는 로그인 페이지로 튕기면 → 만료. `_fresh_login()` 호출 후 성공 시 `_save_session()`.
5. 세션 파일이 없으면 → 곧장 `_fresh_login()` + `_save_session()`.

### 세션 유효성 검증

TEXA portal 은 ASP.NET frameset. URL 만으로 인증 여부를 단정할 수 없을 가능성
이 있으니 보수적으로:
- `wait_for_function`: `tex.textainer.com` 포함 + 10초 내
- 추가로 frame 중 하나에 "Customer" 또는 "Logout" 같은 portal-only 텍스트가
  보이면 확실히 로그인 상태. 이건 비용 큰 검증이라 1단계 URL 체크만으로 충분
  하면 생략 (FLOR도 URL 체크만 함).

### _save_session()

`_fresh_login()` 성공 직후 호출. FLOR 와 동일:

```python
async def _save_session(self):
    sess = _session_file_for(self.company)
    sess.parent.mkdir(parents=True, exist_ok=True)
    await self.context.storage_state(path=str(sess))
```

## 시간 효과 예측

| 시나리오 | 현재 | 변경 후 |
|---|---|---|
| 세션 유효 | ~12s (풀 로그인) | ~2~3s (portal 직접 진입) |
| 세션 만료 | ~12s | ~12s + 2s (만료 감지 라운드트립) |
| 첫 cold start | ~12s | ~12s + 저장 (저장은 ms 단위) |

일반적 사용 (몇 시간 내 반복 조회) 에선 **10초 안팎 단축**.

## 위험 / 대응

| 위험 | 대응 |
|---|---|
| 세션 만료 후 portal URL 가 frameset 내부로 튕기지 않고 다른 도메인으로 튕길 수 있음 | URL 체크에 `tex.textainer.com` 미포함 시 fresh login 으로 폴백. 폴백 비용은 만료 감지 ~2s 만 추가. |
| storage_state 파일 동시 쓰기 | FLOR와 동일 가정 (현 트래픽 수준에서 무시). 향후 트래픽 증가 시 동시성 처리 별도. |
| ASP.NET 의 `__VIEWSTATE` 같은 폼 상태도 storage_state 에 들어가는지 | 쿠키만 들어감. `__VIEWSTATE` 는 폼 hidden 필드라 페이지 로드 시 새로 받음 → 영향 없음. |
| 봇 차단 시그널 | FLOR는 캡차 대응 목적이 컸음. TEXA는 캡차 없어 봇 차단 위험 자체가 낮음. 부가 효과로 자동화 흔적 감소는 있음. |

## 비변경

- 가시화 작업 (`PLAN_error_visibility.md`) 으로 추가된 단계별 reason 로직 그대로 유지.
- `query()` 본체, ASP.NET 고정 sleep 들 — 손대지 않음.
- 다른 임대사 (TRIT/GOLD/GESE) — 본 PR 범위 밖.

## 검증

1. 로컬: 세션 파일 없는 상태에서 1회 조회 — fresh login 발생, 세션 파일 생성 확인.
2. 로컬: 같은 회사로 즉시 재조회 — login 스킵 로그 (`existing session valid → skip login`) 확인.
3. 로컬: SK / HA 양사 각각 별도 세션 파일 생성되는지 확인 (`texa_session_SK.json`, `texa_session_HA.json`).
4. Railway 배포 후 처음엔 fresh login, 두 번째 조회부터 단축 확인.

## 작업 순서

1. 본 계획 사용자 승인
2. `texa.py` 수정 (~50줄 추가, 기존 `login` 본체 함수명만 변경)
3. 로컬 위 1·2·3 검증
4. 커밋. 메시지 예: `TEXA: 로그인 세션 재사용 (Playwright storage_state)`
