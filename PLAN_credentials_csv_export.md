# 비밀번호 관리 페이지 — CSV 다운로드 추가 계획

## 목표

`/dashboard/credentials` 페이지에 **CSV 다운로드 링크** 추가.
현재 시스템이 관리하는 자격증명을 한 번에 백업/공유할 수 있는 표 형식 export.

## 대상 범위 (사용자 합의 기준)

- 시스템에 저장된 자격증명만 export.
- 현재 `scraper/config/credentials.py:26-35` 기준 = SK·HA × `[TEXA, TRIT, GOLD, FLOR, GESE]` = **10행**.
- 메일 임대사(BCON/CARL/CAIC/BLUE/GCIC/MWSC+CALT 등)는 시스템 관리 대상 아님 → CSV에 미포함.
- 향후 메일 임대사도 관리하려면 `COMPANIES` dict 확장이 선행 필요 (별도 작업).

## CSV 사양

### 컬럼

`선사, 임대사, 아이디, 비밀번호, 홈페이지`

### 데이터 예시 (실제 값 아님, 형식 예시)

```
선사,임대사,아이디,비밀번호,홈페이지
장금상선,TEXA,***ID***,***PW***,https://www.textainer.com/contact
장금상선,TRIT,...,...,https://www.tritoncontainer.com/tritoncontainer/
...
흥아라인,GESE,...,...,https://seaweb.seacoglobal.com/
```

### 인코딩

- **UTF-8 with BOM** (`﻿` 선두 1바이트). Excel에서 한글 깨짐 방지.
- 비밀번호에 `,` `"` `\n` 가 있을 수 있으니 RFC 4180 따라 `"` 로 감싸고 내부 `"` 는 `""` 로 이스케이프.

### 파일명

`credentials_YYYY-MM-DD.csv` (다운로드 시점 날짜).

### 홈페이지 URL 출처

`SearchForm.tsx:54-65` 의 `LESSOR_HOMEPAGES` 와 동일 매핑.
중복 부담 작아 export 라우트에 inline 으로 다시 정의 (현 시점 5개 query 임대사뿐).

## 구현 위치

### 1) 새 라우트: `frontend/app/api/credentials/export/route.ts`

- HTTP GET
- 기존 `frontend/app/api/credentials/route.ts:4-13` 의 `authed(req)` 동일 적용
  (세션 쿠키 + `credentials_unlock` 쿠키 둘 다 필수)
- `${RAILWAY_API_URL}/credentials` 로 현재 자격증명 fetch → CSV 직렬화 → 응답
- 응답 헤더:
  - `Content-Type: text/csv; charset=utf-8`
  - `Content-Disposition: attachment; filename="credentials_YYYY-MM-DD.csv"`
  - `Cache-Control: no-store`

### 2) 컴포넌트 수정: `frontend/components/CredentialsManager.tsx`

- 헤더 또는 상단 우측에 작은 다운로드 링크 1개:
  - `<a href="/api/credentials/export" download className="text-sm ...">📥 CSV 다운로드</a>`
- 기존 UI/로직은 손대지 않음.

## 비변경

- `scraper/` 백엔드 — 변경 없음. 기존 `/credentials` GET 그대로 사용.
- 다른 라우트/페이지 — 무관.
- 비밀번호 관리 잠금 흐름 — 그대로. 다운로드도 PIN 잠금 해제 상태에서만 가능.

## 보안 고려

- 인증: 로그인 세션 + PIN 잠금 해제 2중 (기존 `/api/credentials` GET 과 동일).
- 비밀번호 평문 노출 — 사용자 명시 요청. 파일 보관/공유 시 주의 필요 (운영 책임).
- 다운로드 로그: 이번 PR 범위 밖. 별도 검토.
- 캐시: 응답에 `no-store` 명시. 브라우저/프록시 캐시 방지.

## 검증

1. PIN 잠금 안 푼 상태에서 `/api/credentials/export` 직접 호출 → 401.
2. PIN 잠금 푼 상태에서 페이지의 CSV 링크 클릭 → 다운로드 발생.
3. 다운로드 파일 Excel 로 열기 → 한글 깨짐 없음, 5컬럼 10행 표시.
4. 비밀번호에 `,` 또는 `"` 가 포함된 경우 인코딩 정상 확인 (임의 값 한번 변경해서 테스트).

## 작업 순서

1. 본 계획 사용자 승인
2. `frontend/app/api/credentials/export/route.ts` 신규
3. `frontend/components/CredentialsManager.tsx` 링크 추가
4. 로컬에서 위 검증 1·2·3 실행
5. 커밋. 메시지 예: `비밀번호 관리: CSV 다운로드 추가`
