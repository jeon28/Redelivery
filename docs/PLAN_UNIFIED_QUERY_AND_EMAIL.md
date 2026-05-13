# 개발 계획서: 조회 페이지 통합 + Email Setting

> **작성일**: 2026-05-14
> **상태**: 협의 완료 — 최종 승인 대기
> **관련 헌법 조항**: 협업 규칙 1조 (협의 우선), 2조 (계획서 필수)

---

## 1. 목표

기존 분리된 두 페이지(조회 / 메일 반납)를 **조회 페이지 한 곳으로 통합**하고, 임대사별 메일 양식·수신자 규칙을 **Email Setting 페이지**에서 관리한다. 웹반납 임대사도 백업 용도로 메일 발송 옵션을 제공한다.

---

## 2. 합의된 결정 사항 (17개)

| # | 항목 | 결정 |
|---|---|---|
| 1 | 컨테이너 입력 형식 | 한 줄에 `번호 사이즈` (사이즈 생략 시 기본값) |
| 2 | 메일 모드 메인 UI | 컨테이너 입력 + 메일 보내기 버튼만 (To/Cc 안 보임) |
| 3 | 발신자 처리 | Outlook 자동 (시스템에서 사용자 식별 안 함) |
| 4 | 사무소 옵션 (6개) | 본사 / 부산 / 인천 / 평택 / 광양 / 울산 |
| 5 | 반납지역 옵션 (5개) | 부산 / 인천 / 평택 / 광양 / 울산 |
| 6 | 서명 | Outlook 자동 서명 (시스템은 본문만 생성) |
| 7 | 사무소 ↔ 반납지역 | 사무소 선택 시 반납지역 자동 동기화 + 브라우저 저장 |
| 8 | 프리셋 편집 | 가능 (PIN 보호 없음) |
| 9 | 준비중 임대사 표시 | 드롭다운에 `[준비중]` 표시 |
| 10 | 임대사 카탈로그 | 프론트 하드코딩 |
| 11 | 헤더 메뉴 | `[조회] [Email Setting] [비밀번호 관리]` |
| 12 | 본문 "발신:" 라인 | `발신: {carrier_name} {office}` (이름 제거) |
| 13 | Email Setting 구조 | 2-tab (Recipient Rules + Email Template) — skrpti 스타일 |
| 14 | Recipient Rules 매칭 | 임대사별 1세트 (선사 차원 없음) |
| 15 | 프리셋 범위 | **모든 임대사** (웹반납 포함, 약 10개) |
| 16 | Restore | 부분 복원 (현재 선택 임대사만) |
| 17 | 웹반납 임대사 UI | 두 버튼 (`🔍 조회하기` + `📧 메일로 신청`) |

---

## 3. 임대사 카탈로그

```typescript
const LESSOR_CATALOG = {
  장금상선: [
    { code: 'TEXA',       mode: 'query', status: 'ready' },
    { code: 'TRIT+TRAM',  mode: 'query', status: 'wip'   },
    { code: 'GLOD',       mode: 'query', status: 'wip'   },
    { code: 'FLOR+DFIC',  mode: 'query', status: 'wip'   },
    { code: 'GESE+CROS',  mode: 'query', status: 'wip'   },
    { code: 'GCIC',       mode: 'query', status: 'wip'   },
    { code: 'CAIC',       mode: 'email' },
    { code: 'BCON',       mode: 'email' },
    { code: 'CARL',       mode: 'email' },
    { code: 'BLUE',       mode: 'email' },
  ],
  흥아라인: [
    { code: 'TEXA',       mode: 'query', status: 'ready' },
    { code: 'TRIT',       mode: 'query', status: 'wip'   },
    { code: 'GOLD',       mode: 'query', status: 'wip'   },
    { code: 'FLOR',       mode: 'query', status: 'wip'   },
    { code: 'GESE+SGCN',  mode: 'query', status: 'wip'   },
    { code: 'BCON',       mode: 'email' },
    { code: 'CARL',       mode: 'email' },
    { code: 'BLUE',       mode: 'email' },
  ],
}
```

**Recipient Rules / Templates 단위는 임대사 코드별 1세트:**
- 고유 임대사 코드: `TEXA`, `TRIT(+TRAM)`, `GLOD/GOLD`, `FLOR(+DFIC)`, `GESE(+CROS/SGCN)`, `GCIC`, `CAIC`, `BCON`, `CARL`, `BLUE` (10개)

---

## 4. 메인 화면 (조회 페이지)

### 4.1 레이아웃

```
┌─────────────────────────────────────────────────┐
│ 선사: [장금상선 ▼]                              │
│ 임대사: [TEXA ▼]    (메일 임대사는 [임대사명] (메일))  │
│ 사무소: [인천 ▼]                                │
│ 반납지역: [인천 ▼]   ← 사무소 따라 자동 동기화   │
├─────────────────────────────────────────────────┤
│ 컨테이너 (한 줄에 번호 사이즈)                  │
│  ABCD1234567 45GP                                │
│  EFGH8901234 22GP                                │
│  IJKL5678901                ← 사이즈 생략 시 45GP │
├─────────────────────────────────────────────────┤
│ [🔍 조회하기]  [📧 메일로 신청]   ← 웹반납 임대사 │
│ 또는                                              │
│ [📧 메일 보내기]                  ← 메일 임대사   │
└─────────────────────────────────────────────────┘
```

### 4.2 동작

- **선사 변경** → 해당 선사 임대사 목록으로 드롭다운 갱신
- **임대사 변경** → 모드(query/email)에 따라 버튼 영역 변경
- **사무소 변경** → 반납지역 자동 동기화 (본사 제외)
- **준비중 임대사 선택** → 버튼 비활성화 + "준비중" 안내
- **🔍 조회하기** → 기존 `/api/query` 호출, 결과 테이블
- **📧 메일 보내기 / 메일로 신청** → mailto: 링크 생성 → Outlook 자동 실행

### 4.3 mailto 본문 (Outlook이 열렸을 때)

```
수신: {임대사 첫 번째 To 한 명}
발신: 장금상선 인천사무소

안녕하세요.

하기 컨테이너 반납 요청드리오니 확인 후 반납번호 및 반납지역 회신 부탁드립니다.

SKR
ABCD1234567
45GP

SKR
EFGH8901234
22GP

반납지역: 인천
```

(서명은 Outlook 자동 처리)

---

## 5. Email Setting 페이지

### 5.1 레이아웃

```
┌────────────────────────────────────────────────────┐
│ Email Setting                                       │
│ Manage Outlook email rules and templates            │
│                                                     │
│ ┌─[ Recipient Rules ]─[ Email Template ]──────────┐│
│ │                                                  ││
│ │  ... (탭에 따라 다른 영역) ...                  ││
│ │                                                  ││
│ │                  [↺ Restore]  [💾 Save Changes] ││
│ └──────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────┘
```

### 5.2 Email Template 탭

```
┌─[CAIC]─[BCON]─[CARL]─[BLUE]─[TEXA]─[TRIT]─...─┐  ← 임대사 탭
│                                                  │
│  Available placeholders:                         │
│    {carrier_name}, {carrier_code}, {office},     │
│    {region}, {region_en}, {date},                │
│    {first_container}, {first_type}, {containers} │
│                                                  │
│  Subject Line:                                   │
│  ┌────────────────────────────────────────────┐│
│  │ [{carrier_name}] {first_container} 요청 {date} ││
│  └────────────────────────────────────────────┘│
│                                                  │
│  Email Body:                                     │
│  ┌────────────────────────────────────────────┐│
│  │ 수신: CAI / 정준혁 담당님                  ││
│  │ 발신: {carrier_name} {office}              ││
│  │ ...                                          ││
│  │ {containers}                                 ││
│  │ ...                                          ││
│  └────────────────────────────────────────────┘│
│                                                  │
│       [↺ Restore]            [💾 Save Changes]  │
└──────────────────────────────────────────────────┘
```

### 5.3 Recipient Rules 탭

```
Define who receives emails per lessor.

┌────────┬──────┬───────────────────────────────────┬──────┐
│ Lessor │ Type │ Email Address                     │ Edit │
├────────┼──────┼───────────────────────────────────┼──────┤
│ CAIC   │ To   │ hjung@capps.com; ...               │ ✏️ ✕ │
│ CAIC   │ Cc   │ container@sinokor.co.kr; ...       │ ✏️ ✕ │
│ BCON   │ To   │ ...                                │ ✏️ ✕ │
│ BCON   │ Cc   │ ...                                │ ✏️ ✕ │
│ CARL   │ To   │ ...                                │ ✏️ ✕ │
│ CARL   │ Cc   │ ...                                │ ✏️ ✕ │
│ BLUE   │ To   │ ...                                │ ✏️ ✕ │
│ BLUE   │ Cc   │ ...                                │ ✏️ ✕ │
│ TEXA   │ To   │ (백업용)                            │ ✏️ ✕ │
│ TEXA   │ Cc   │ ...                                │ ✏️ ✕ │
│ ... 다른 임대사들도 ...                              │      │
└────────┴──────┴───────────────────────────────────┴──────┘

       [↺ Restore]            [💾 Save Changes]
```

총 약 20행 (10 임대사 × 2 타입).

---

## 6. 백엔드 데이터 구조

### 6.1 `/data/email_templates.json` (Railway Volume)

```json
{
  "CAIC": {
    "name": "CAI Korea (CAIC)",
    "language": "ko",
    "to": "hjung@capps.com; june@capps.com; sjent@sjcon.kr; sjent_cy@sjcon.kr",
    "cc": "container@sinokor.co.kr; inchon@sinokor.co.kr; owchoi@capps.com; caise@capps.com",
    "subject": "[{carrier_name}] {first_container} 요청 {date}",
    "body": "수신: CAI / 정준혁 담당님\n발신: {carrier_name} {office}\n\n..."
  },
  "BCON": { ... },
  "CARL": { ... },
  "BLUE": { ... },
  "TEXA": { ... },
  "TRIT": { ... },
  "GOLD": { ... },
  "FLOR": { ... },
  "GESE": { ... },
  "GCIC": { ... }
}
```

### 6.2 백엔드 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/email-templates` | 전체 조회 |
| PATCH | `/email-templates/{lessor}` | 단일 임대사 업데이트 |
| POST | `/email-templates/{lessor}/reset` | 단일 임대사 초기값 복원 |

(이미 구현된 엔드포인트 그대로 사용, 임대사 목록만 확장)

---

## 7. 작업 범위 (변경 파일)

### 신규
- `frontend/components/EmailSettingPage.tsx` — 2-tab UI 컨테이너
- `frontend/components/EmailTemplateTab.tsx` — Email Template 탭 (임대사 탭 + 편집기)
- `frontend/components/RecipientRulesTab.tsx` — Recipient Rules 탭 (표)
- `frontend/app/dashboard/email-setting/page.tsx` — 새 페이지

### 크게 변경
- `frontend/components/SearchForm.tsx` — 통합 폼 (조회 + 메일 모드 분기, 두 버튼)
- `scraper/config/email_templates.py` — 모든 임대사 (10개) 기본값 추가, 사무소 변수 반영

### 작은 변경
- `frontend/app/dashboard/page.tsx` — 메뉴: 메일 반납 제거, Email Setting 추가
- `frontend/app/dashboard/credentials/page.tsx` — 메뉴 업데이트
- `frontend/app/dashboard/credentials/unlock/page.tsx` — 메뉴 업데이트

### 삭제
- `frontend/app/dashboard/email-request/` — 폴더 전체 삭제
- `frontend/components/EmailRequestForm.tsx` — 파일 삭제

### 그대로 유지
- `scraper/routers/email_templates.py` — GET/PATCH/reset 모두 사용
- `frontend/app/api/email-templates/route.ts` — GET 프록시
- `frontend/app/api/email-templates/[lessor]/route.ts` — PATCH 프록시
- 비밀번호 관리 페이지/로직

---

## 8. 작업 순서

1. **이 계획서 최종 승인** ← 현재
2. 백엔드 기본 템플릿 확장 (10개 임대사)
3. 백엔드 reset 엔드포인트 점검 (이미 있음)
4. 프론트: SearchForm 재작성 (통합 UI)
5. 프론트: EmailSettingPage 페이지 + 2 탭 컴포넌트
6. 프론트: 메뉴 정리
7. 사용하지 않는 파일/폴더 삭제
8. 로컬 빌드 / 동작 확인
9. 커밋 / Vercel·Railway 자동 배포
10. 테스트

예상 소요: 3~4시간 작업.

---

## 9. 추가 고려 사항 (구현 단계에서 다룰 것)

- **Email Setting 페이지 미저장 변경사항 경고** — 다른 페이지로 이동 시 "저장하지 않은 변경사항이 있습니다" 알림
- **Recipient Rules 행 편집 방식** — 인라인 vs 모달 (구현하면서 결정)
- **준비중 임대사의 Email 발송** — 조회 불가지만 메일은 가능하게 (옵션 B의 [📧 메일로 신청] 동일)

---

## 10. 최종 승인 요청

위 계획대로 진행해도 될까요?

- ✅ 동의 → "진행" 회신 → 코딩 시작
- 🔄 수정 사항 있으면 알려주세요
