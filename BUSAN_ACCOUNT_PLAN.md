# 부산 사무소 계정 추가 — 개발 계획서

> 작성일: 2026-05-15
> 상태: 검토 대기
> 트리거: 부산에서 별도 계정 + 메일 세팅 요청

---

## 목표

1. **사무소별 로그인 계정** 도입 (1차: 인천 `skrinc` / 부산 `skrpus`).
2. 로그인한 계정에 **사무소를 고정 매핑** — 헤더에 "부산 사무소" 자동 표시, 변경 불가.
3. **메일 세팅(수신자 + 발신자 표기)을 사무소별로 분리** — 같은 임대사라도 부산은 별도의 To/Cc 사용.
4. **관리자 PIN(자격증명 페이지 잠금)도 사무소별로 분리**.
5. 향후 평택·광양·울산 사무소 추가가 **환경변수 + USERS 맵에 한 줄 추가**로 끝나는 구조 보장.

### 변경하지 않는 것

- 임대사(TEXA/TRIT/GOLD/FLOR/GESE 등) 사이트 로그인 자격증명은 **사무소 구분 없이 공유**. `config/credentials.py` 구조는 그대로.
- 백엔드 스크래퍼 로직, 임대사별 폴더 구조, 결과 데이터 포맷.

---

## 1. 결정 사항 (확정)

| 항목 | 결정 |
|---|---|
| 계정 모델 | 사무소별 계정 (`skrinc`, `skrpus`, …) |
| PW 저장 | 환경변수 (`SKRINC_PW`, `SKRPUS_PW`) |
| 헤더 사무소 표시 | 로그인 사무소로 **잠금** (드롭다운 → 표시 전용 라벨) |
| 관리자 PIN | 사무소별 분리 (`ADMIN_PIN_INC`, `ADMIN_PIN_PUS`) |
| 메일 분리 범위 | To/Cc 분리 + 본문 `{office}` 자동 주입 (둘 다) |
| 부산 메일 To/Cc 주소 | 구조만 먼저 만들고, UI에서 사용자가 입력 |
| 임대사 자격증명 | 사무소 무관, 기존 공유 구조 유지 |

---

## 2. 영향 받는 파일 / 변경 요약

### 인증 계층 (frontend)

| 파일 | 변경 |
|---|---|
| `frontend/lib/users.ts` *(신규)* | `USERS` 맵 정의. `{ skrinc: { office:'인천', pw: env.SKRINC_PW }, skrpus: { office:'부산', pw: env.SKRPUS_PW } }`. 추후 사무소 추가는 여기에 한 줄. |
| `frontend/app/actions/auth.ts` | `login`: USERS 맵 조회로 변경, 세션에 `office` 포함. `unlockCredentials`: 세션 office에 따라 `ADMIN_PIN_INC` / `ADMIN_PIN_PUS` 매칭. |
| `frontend/lib/session.ts` | `createSession(userId, office)`, `verifySession()` 반환에 `office` 추가. JWT payload 확장. |

### UI 계층 (frontend)

| 파일 | 변경 |
|---|---|
| `frontend/components/HeaderOfficeSelector.tsx` | `<select>` → 표시 전용 `<span>` ("부산 사무소"). 서버에서 세션 office prop으로 전달. |
| `frontend/app/dashboard/page.tsx` | 헤더에 세션 office 전달. 기존 office prop 흐름 점검. |
| `frontend/components/SearchForm.tsx` 외 office 사용처 | localStorage / `office-change` 이벤트 의존 제거 → 세션 office 단일 소스. (변경 범위는 코딩 단계에서 grep 후 확정) |

### 메일 템플릿 (backend)

| 파일 | 변경 |
|---|---|
| `scraper/config/email_templates.py` | 구조 확장: `TEMPLATES[lessor] = { default: {...}, offices: { 부산:{to,cc,subject?,body?}, 인천:{...} } }`. `get_template(lessor, office)`은 office 오버라이드 → default 폴백. 마이그레이션 함수 추가 (기존 단일 템플릿을 `default`로 이동). |
| `scraper/routers/email_templates.py` | GET/PUT에 `office` 쿼리 파라미터 추가. office별로 부분 업데이트. |
| `frontend/components/EmailTemplateTab.tsx`, `EmailSettingTabs.tsx`, `RecipientRulesTab.tsx` | 세션 office를 받아 해당 사무소 템플릿 로드/저장. UI는 "현재 편집 중: 부산" 표시. |
| `frontend/app/dashboard/email-setting/page.tsx` | 세션 office prop 전달. |

### 환경변수

| 신규 | 용도 |
|---|---|
| `SKRINC_PW` | 인천 계정 비밀번호 (기존 `APP_USER_PW` 대체) |
| `SKRPUS_PW` | 부산 계정 비밀번호 (신규) |
| `ADMIN_PIN_INC` | 인천 사무소 자격증명 페이지 PIN |
| `ADMIN_PIN_PUS` | 부산 사무소 자격증명 페이지 PIN |

| 제거 예정 | 비고 |
|---|---|
| `APP_USER_ID`, `APP_USER_PW` | USERS 맵으로 대체. 배포 후 1주일 fallback 유지 후 제거. |
| `ADMIN_PIN` | 사무소별 PIN으로 대체. 동일하게 fallback. |

---

## 3. 데이터 마이그레이션

### `email_templates.json` (Railway Volume)

기존:
```json
{ "TEXA": { "to": "...", "cc": "...", "subject": "...", "body": "..." } }
```

신규:
```json
{
  "TEXA": {
    "default": { "to": "...", "cc": "...", "subject": "...", "body": "..." },
    "offices": {
      "인천": {},
      "부산": {}
    }
  }
}
```

- `_load()`에 자동 마이그레이션 추가 (구버전 감지 → `default`로 이동, `offices` 빈 객체 초기화).
- 기존 값은 모두 `default`에 보존 → 마이그레이션 직후에도 인천/부산 둘 다 기본값으로 동작.
- 사용자가 부산용 To/Cc를 UI에서 채우는 순간 `offices.부산`에 저장되며, 미입력 항목은 `default` 폴백.

### `credentials.json`

- **변경 없음.** 사무소 차원 추가 없이 회사×임대사 구조 그대로 유지.

---

## 4. 작업 순서

1. 본 계획서 검토 / 승인.
2. **백엔드**: `email_templates.py` 구조 확장 + 마이그레이션 함수 + 라우터에 office 파라미터.
3. **프론트 인증**: `users.ts` 신규, `auth.ts` / `session.ts` 수정.
4. **프론트 UI**: `HeaderOfficeSelector` 잠금 + office 소스를 세션으로 통일.
5. **프론트 메일 세팅**: 세션 office에 따라 해당 사무소 템플릿 편집.
6. **자격증명 페이지 PIN 분기**: `unlockCredentials` 수정.
7. **로컬 테스트**: 두 계정 로그인 → 사무소 표기 / 메일 분리 / PIN 분리.
8. **배포 전 환경변수 추가**: Railway · Vercel 양쪽.
9. **운영 인계**: 부산 사용자에게 ID/PW 전달, 부산 메일 To/Cc는 UI에서 직접 입력.

---

## 5. 알아야 할 것 / 운영 인계 사항

### 사용자(부산)에게 받아야 할 정보

- [ ] 부산 계정 **비밀번호** 값 (기획자 또는 운영자가 정해서 전달)
- [ ] 부산 사무소 **자격증명 페이지 PIN** 값
- [ ] (배포 후 UI에서 입력) 임대사별 부산 사무소용 **To/Cc 이메일 주소** — TEXA/TRIT/GOLD/FLOR/GESE/GCIC/CAIC/BCON/CARL/BLUE 10개

### 배포 시 추가 환경변수 (Vercel)

```
SKRINC_PW=<인천 계정 PW>
SKRPUS_PW=<부산 계정 PW>
ADMIN_PIN_INC=<인천 PIN>
ADMIN_PIN_PUS=<부산 PIN>
```

→ Railway 백엔드는 환경변수 변경 없음 (메일 템플릿은 볼륨 JSON에 저장).

### 기존 사용자(인천) 영향

- 기존 로그인 ID/PW 그대로 사용 불가 → 새 ID는 **`skrinc`**. 운영 인계 시점에 안내 필요.
- 헤더 사무소 드롭다운이 사라지고 "인천 사무소" 고정 표기로 바뀜. 메일 본문 `{office}` 값은 동일하게 "인천"으로 채워지므로 발송 결과는 차이 없음.

### 향후 사무소 추가 시

평택·광양·울산 추가는:
1. `users.ts`에 `skrptk: { office:'평택', pw: env.SKRPTK_PW }` 한 줄 추가
2. 환경변수 `SKRPTK_PW`, `ADMIN_PIN_PTK` 추가
3. 메일 템플릿 UI는 자동으로 해당 사무소 탭이 노출됨 (offices 키를 enum이 아닌 동적 키로 처리)

→ **코드 변경은 사실상 한 줄**.

### 위험 / 주의

- `email_templates.json` 마이그레이션은 **백업 후 진행** (Railway Volume에서 `cp email_templates.json email_templates.json.bak`).
- 기존 `APP_USER_ID/PW`, `ADMIN_PIN` 환경변수는 fallback 기간(약 1주) 후 제거. 잊고 두면 의미 없는 비밀이 환경변수에 남음.
- 세션 JWT 페이로드 구조 변경 → 배포 시점에 **기존 세션은 모두 무효화**되어 재로그인 필요.

---

## 6. 본 계획서가 다루지 않는 것

- 다중 사용자 UI (계정 추가/삭제 화면) — 사무소 단위 1계정으로 충분.
- 사용자별 비밀번호 변경 흐름 — 환경변수로 운영, 변경은 배포로.
- 부산 메일의 실제 수신자 주소 — 배포 후 UI에서 입력.
