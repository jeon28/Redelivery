# Phase 1 — 기반 구조 상세 계획서

> 작성일: 2026-05-12  
> 상태: 검토 대기

---

## 목표

실제 스크래핑 없이 **뼈대 구조**를 완성한다.  
Phase 1이 끝나면 로그인 → 조회 폼 → 결과 테이블 화면이 동작하고,  
Vercel ↔ Railway 통신이 연결된 상태가 된다.

---

## 1. 폴더 구조

```
redlivery/
├── CLAUDE.md
├── PLAN.md
├── PHASE1_PLAN.md
├── .gitignore
│
├── frontend/                        # Vercel 배포 (Next.js)
│   ├── app/
│   │   ├── layout.tsx               # 루트 레이아웃
│   │   ├── page.tsx                 # 로그인 안된 경우 로그인 페이지로 리다이렉트
│   │   ├── login/
│   │   │   └── page.tsx             # 로그인 화면
│   │   ├── dashboard/
│   │   │   └── page.tsx             # 메인 조회 화면 (로그인 필요)
│   │   └── api/
│   │       ├── auth/
│   │       │   └── [...nextauth]/
│   │       │       └── route.ts     # NextAuth 인증 핸들러
│   │       └── query/
│   │           └── route.ts         # Railway 스크래퍼 호출 API
│   ├── components/
│   │   ├── LoginForm.tsx            # 로그인 폼
│   │   ├── SearchForm.tsx           # 조회 입력 폼
│   │   └── ResultTable.tsx          # 조회 결과 테이블
│   ├── lib/
│   │   └── auth.ts                  # NextAuth 설정
│   ├── .env.local                   # 환경변수 (NEXTAUTH_SECRET, RAILWAY_API_URL 등)
│   ├── package.json
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
└── scraper/                         # Railway 배포 (Python)
    ├── main.py                      # FastAPI 진입점
    ├── routers/
    │   └── query.py                 # POST /query 엔드포인트 (Mock 응답)
    ├── scrapers/
    │   └── base.py                  # 공통 Playwright 베이스 클래스 (뼈대)
    ├── config/
    │   └── credentials.py           # .env에서 자격증명 로드
    ├── .env                         # 임대사 로그인 정보
    ├── requirements.txt
    └── Dockerfile
```

---

## 2. 기술 스택

### Frontend (Vercel)
| 패키지 | 버전 | 용도 |
|--------|------|------|
| Next.js | 14 (App Router) | 프레임워크 |
| NextAuth.js | v5 | 직원 로그인 인증 |
| Tailwind CSS | 3 | UI 스타일링 |
| TypeScript | 5 | 타입 안전성 |

### Scraper (Railway)
| 패키지 | 버전 | 용도 |
|--------|------|------|
| Python | 3.11 | 런타임 |
| FastAPI | 최신 | API 서버 |
| uvicorn | 최신 | ASGI 서버 |
| playwright | 최신 | 브라우저 자동화 (Phase 2부터 실제 사용) |
| python-dotenv | 최신 | 환경변수 |

---

## 3. 화면 흐름

```
[접속]
  └─> 로그인 화면
        └─> 아이디/비밀번호 입력
              └─> 인증 성공
                    └─> 대시보드 (메인 조회 화면)
                          ├─> 선사 선택 (장금상선 / 흥아라인)
                          ├─> 임대사 선택 (TEXA / TRIT / ...)
                          ├─> 지역 선택 (인천 / 부산 / ...)
                          ├─> 컨테이너 번호 입력 (여러 개)
                          └─> [조회] 버튼
                                └─> 결과 테이블 표시
```

---

## 4. 화면 상세

### 4-1. 로그인 화면
```
┌─────────────────────────────┐
│     반납컨테이너 조회 시스템  │
│                             │
│  아이디  [________________] │
│  비밀번호 [________________] │
│                             │
│           [로그인]           │
└─────────────────────────────┘
```

### 4-2. 메인 조회 화면
```
┌──────────────────────────────────────────────────┐
│  반납컨테이너 조회 시스템           [로그아웃]     │
├──────────────────────────────────────────────────┤
│  선사   [장금상선 ▼]    임대사  [TEXA ▼]          │
│  지역   [인천 ▼]        날짜    [2026-05-12]       │
│                                                  │
│  컨테이너 번호 (줄바꿈으로 여러 개 입력)           │
│  ┌────────────────────────────────────┐          │
│  │ ABCD1234567                        │          │
│  │ EFGH8901234                        │          │
│  └────────────────────────────────────┘          │
│                              [조회하기]           │
├──────────────────────────────────────────────────┤
│ 컨테이너번호  │가능여부│반납지          │반납번호  │Over Caps│
│ ABCD1234567  │✅ 가능 │신선대          │TKE6E02  │NO      │
│ EFGH8901234  │❌ 불가 │-              │NOT HIRED │-       │
└──────────────────────────────────────────────────┘
```

---

## 5. API 명세

### POST `/api/query` (Vercel → Railway)

**요청**
```json
{
  "company": "장금상선",
  "lessor": "TEXA",
  "region": "INCHON",
  "containers": ["ABCD1234567", "EFGH8901234"]
}
```

**응답 — 성공**
```json
{
  "results": [
    {
      "container_no": "ABCD1234567",
      "available": true,
      "depot": "INC05 - SEUNG JIN ENTERPRISES",
      "booking_ref": "TKE6E02",
      "over_caps": "NO",
      "close_date": "2026-MAY-31",
      "reason": null
    },
    {
      "container_no": "EFGH8901234",
      "available": false,
      "depot": null,
      "booking_ref": null,
      "over_caps": null,
      "close_date": null,
      "reason": "CONTAINERS NOT HIRED BY SINOK1"
    }
  ]
}
```

**응답 — 오류**
```json
{
  "error": "login_failed",
  "message": "TEXA 로그인 실패. 비밀번호를 확인하세요."
}
```

---

## 6. 인증 방식 (NextAuth)

- **방식**: Credentials Provider (아이디/비밀번호)
- **계정 구조**: 장금상선/흥아라인 통합 — 로그인 후 화면에서 선사 선택
- **계정 저장**: Vercel 환경변수에 등록
  ```
  ADMIN_ID=redlivery
  ADMIN_PW=xxxx
  ```
- **세션**: JWT 방식 (DB 불필요)
- **보호**: `/dashboard` 이하 모든 페이지는 로그인 필수

---

## 7. 지역 코드 매핑

| 화면 표시 | TEXA 코드 |
|-----------|-----------|
| 인천 | KOREA - KOR / INCHON - INC |
| 부산 | KOREA - KOR / PUSAN - PUS |
| 광양 | KOREA - KOR / GWANGYANG - GWA |

※ 다른 임대사 추가 시 해당 임대사 코드 별도 매핑

---

## 8. Phase 1 작업 목록

### Frontend
- [ ] Next.js 14 프로젝트 초기화
- [ ] Tailwind CSS 설정
- [ ] NextAuth.js 로그인 구현 (Credentials Provider)
- [ ] 로그인 화면 UI
- [ ] 메인 조회 화면 UI (SearchForm + ResultTable)
- [ ] `/api/query` → Railway 호출 API Route 구현
- [ ] 로딩 상태 처리 (조회 중 스피너)
- [ ] 에러 처리 (로그인 실패, 조회 실패 등)

### Scraper (Railway)
- [ ] FastAPI 프로젝트 초기화
- [ ] `POST /query` 엔드포인트 구현 (Phase 1에서는 Mock 데이터 반환)
- [ ] `base.py` Playwright 베이스 클래스 뼈대 작성
- [ ] `credentials.py` 환경변수 로드 구조
- [ ] `Dockerfile` 작성 (Python + Playwright 환경)
- [ ] Railway 배포 및 URL 확인

### 연동
- [ ] Vercel에서 Railway API 호출 테스트
- [ ] NEXTAUTH_SECRET, RAILWAY_API_URL 환경변수 설정
- [ ] Vercel 배포 테스트

---

## 9. Phase 1 완료 기준

아래 시나리오가 실제로 동작하면 Phase 1 완료:

1. 브라우저에서 Vercel URL 접속 → 로그인 화면 표시
2. 직원 아이디/비밀번호 입력 → 대시보드 이동
3. 선사/임대사/지역/컨테이너 입력 후 [조회] 클릭
4. Railway Mock 응답이 화면 결과 테이블에 표시
5. 로그아웃 클릭 → 로그인 화면으로 이동

---

## 10. 확정 사항

1. **계정**: 통합 단일 계정 (선사 구분 없이 로그인 후 화면에서 선택)
2. **지역**: 인천만 우선 적용, 추후 확장
3. **초기 계정 ID/PW**: 코딩 시작 전 알려주세요
