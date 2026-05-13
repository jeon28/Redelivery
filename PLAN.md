# 반납컨테이너 조회 시스템 개발 계획서

> 작성일: 2026-05-12  
> 상태: 검토 대기

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 목적 | 반납예정 컨테이너의 임대사별 반납 가능 여부 자동 조회 |
| 사용자 | 장금상선/흥아라인 장비팀, 지방사무소 담당자 |
| 배포 구조 | **B안** — 프론트엔드(Vercel) + 스크래퍼 서버(Railway) |

---

## 2. 시스템 구조

```
[사용자 브라우저]
      ↕  HTTPS
[Vercel] — Next.js 프론트엔드 + API Routes
      ↕  내부 API 호출 (HTTPS)
[Railway] — Python FastAPI + Playwright 스크래퍼
      ↕  웹 자동화 (Playwright)
[각 임대사 웹사이트]
```

### 흐름 설명
1. 사용자가 Vercel 웹앱에서 컨테이너 번호 / 날짜 / 지역 입력
2. Vercel API Route가 Railway 스크래퍼 서버에 조회 요청 전송
3. Railway 서버가 Playwright로 해당 임대사 사이트 로그인 → 조회 → 결과 파싱
4. 결과를 Vercel로 반환 → 화면에 표시

---

## 3. 기술 스택

### 프론트엔드 (Vercel)
| 기술 | 용도 |
|------|------|
| Next.js 14 (App Router) | 웹앱 프레임워크 |
| Tailwind CSS | UI 스타일링 |
| TypeScript | 타입 안전성 |
| Vercel Environment Variables | 자격증명 및 Railway URL 관리 |

### 스크래퍼 서버 (Railway)
| 기술 | 용도 |
|------|------|
| Python 3.11 | 메인 언어 |
| FastAPI | API 서버 프레임워크 |
| Playwright | 웹 브라우저 자동화 (로그인/조회) |
| python-dotenv | 환경변수 관리 |

---

## 4. 폴더 구조

```
redlivery/
├── CLAUDE.md
├── PLAN.md
├── .gitignore
│
├── frontend/                        # Vercel 배포
│   ├── app/
│   │   ├── page.tsx                 # 메인 조회 화면
│   │   ├── layout.tsx
│   │   └── api/
│   │       └── query/
│   │           └── route.ts         # Railway 스크래퍼 호출
│   ├── components/
│   │   ├── SearchForm.tsx           # 입력 폼 (선사/임대사/컨테이너/날짜/지역)
│   │   └── ResultTable.tsx          # 조회 결과 테이블
│   ├── .env.local                   # RAILWAY_API_URL 등
│   ├── package.json
│   └── tsconfig.json
│
└── scraper/                         # Railway 배포
    ├── main.py                      # FastAPI 진입점
    ├── routers/
    │   └── query.py                 # POST /query 엔드포인트
    ├── scrapers/
    │   ├── base.py                  # 공통 Playwright 베이스 클래스
    │   ├── texa.py                  # TEXA (Textainer) — 1순위
    │   ├── trit.py                  # TRIT (Triton) — 2순위
    │   ├── gold.py                  # GOLD/GLOD (Touax) — 3순위
    │   ├── flor.py                  # FLOR (Florens) — 4순위
    │   └── gese.py                  # GESE (SeaCo) — 5순위 (보류)
    ├── mailers/
    │   └── email_handler.py         # 이메일 발송/수신 관리 (Phase 3)
    ├── config/
    │   └── credentials.py           # .env에서 자격증명 로드
    ├── .env                         # 임대사 로그인 정보
    ├── requirements.txt
    └── Dockerfile                   # Railway 배포용
```

---

## 5. API 인터페이스 (Vercel ↔ Railway)

### 요청 (Vercel → Railway)
```json
POST /query
{
  "company": "장금상선",
  "lessor": "TEXA",
  "containers": ["ABCD1234567", "EFGH8901234"],
  "date": "2026-05-12",
  "region": "부산"
}
```

### 응답 (Railway → Vercel)
```json
{
  "results": [
    {
      "container_no": "ABCD1234567",
      "lessor": "TEXA",
      "available": true,
      "return_location": "부산 신선대",
      "return_no": "RT20260512-001",
      "reason": null
    },
    {
      "container_no": "EFGH8901234",
      "lessor": "TEXA",
      "available": false,
      "return_location": null,
      "return_no": null,
      "reason": "재고 초과"
    }
  ]
}
```

---

## 6. 화면 구성

### 메인 조회 화면
```
┌─────────────────────────────────────────────┐
│  반납컨테이너 조회 시스템                      │
├─────────────────────────────────────────────┤
│  선사    [장금상선 ▼]   임대사  [TEXA ▼]      │
│  지역    [부산 ▼]       날짜    [2026-05-12]  │
│                                             │
│  컨테이너 번호                               │
│  ┌─────────────────────────────┐            │
│  │ ABCD1234567                 │            │
│  │ EFGH8901234                 │            │
│  └─────────────────────────────┘            │
│                          [조회]             │
├─────────────────────────────────────────────┤
│  컨테이너번호  │ 가능여부 │ 반납장소 │ 반납번호  │
│  ABCD1234567  │  ✅ 가능 │ 신선대   │ RT-001   │
│  EFGH8901234  │  ❌ 불가 │    -     │ 재고초과  │
└─────────────────────────────────────────────┘
```

---

## 7. 환경변수 관리

### Railway (.env)
```
# 장금상선
SK_TEXA_ID=sel6496
SK_TEXA_PW=A6496a
SK_TRIT_ID=container@sinokor.co.kr
SK_TRIT_PW=Container@649600
...

# 흥아라인
HA_TEXA_ID=HEUNGA
HA_TEXA_PW=Heunga85
HA_TRIT_ID=cmt@heungaline.com
HA_TRIT_PW=Container@649600
...
```

### Vercel (.env.local)
```
RAILWAY_API_URL=https://your-app.railway.app
RAILWAY_API_KEY=내부통신_인증키
```

---

## 8. 개발 단계

### Phase 1 — 기반 구조 (뼈대)
- [ ] Next.js 프로젝트 초기화 (frontend/)
- [ ] FastAPI 프로젝트 초기화 (scraper/)
- [ ] 기본 UI 레이아웃 구현 (입력 폼 + 결과 테이블)
- [ ] Vercel ↔ Railway API 연결 구조 구현
- [ ] Railway 배포 환경 설정 (Dockerfile)

### Phase 2 — 임대사 스크래퍼 (순차 개발)
- [ ] **TEXA** (Textainer) — 장금상선 / 흥아라인
- [ ] **TRIT** (Triton) — 장금상선 / 흥아라인
- [ ] **GOLD/GLOD** (Touax) — 장금상선 / 흥아라인
- [ ] **FLOR** (Florens) — 장금상선 / 흥아라인
- [ ] **GESE** (SeaCo) — 보류 (웹 미작동)

### Phase 3 — 이메일 방식 임대사
- [ ] BCON, CARL, CAIC, GCIC, BLUE 이메일 발송 구현
- [ ] 이메일 회신 수신 및 상태 관리 화면

### Phase 4 — 배포 및 마무리
- [ ] Vercel 프론트엔드 배포
- [ ] Railway 스크래퍼 서버 배포
- [ ] 통합 테스트

---

## 9. 확정 사항

1. **웹앱 자체 로그인**: ✅ 필요 — 직원 아이디/비밀번호로 로그인 후 사용
   - 인증 방식: Next.js + NextAuth.js (세션 기반)
   - 계정 관리: 환경변수에 직원 계정 등록 (초기), 추후 DB 연동 가능

---

## 10. TEXA (Textainer) 사이트 분석 결과

> 분석일: 2026-05-12 / 자동화 방식: **B안 (전체 자동화)**

### 사이트 구조
| 항목 | 내용 |
|------|------|
| 로그인 URL | `https://www.textainer.com` (우상단 LOGIN 팝업) |
| 포털 URL | `https://tex.textainer.com/Customer/CustomerMenu.aspx` |
| 반납 조회 메뉴 | Others → **Request Redelivery** |

### 로그인 폼
| 필드 | 값 |
|------|-----|
| Login As | `Customer_Desktop` (Leasing Customer 선택) |
| Login Name | 계정 ID |
| Password | 계정 비밀번호 |

### Redelivery Request 입력 폼
| 필드 | 설명 |
|------|------|
| Country And City (1) | 국가 드롭다운 (예: `KOREA - KOR`) |
| Country And City (2) | 도시 드롭다운 (예: `INCHON - INC`) |
| Container ID | 컨테이너 번호 textarea (줄바꿈 구분, 최대 100개) |
| Query Mode | `Equipment Query` 라디오버튼 선택 |
| Preview 버튼 | 반납 가능 여부 조회 실행 |

### 자동화 전체 흐름 (B안)

```
1. 로그인 (www.textainer.com 팝업)
      ↓
2. Redelivery Request 페이지 이동
      ↓
3. Country/City 드롭다운 선택
   + Container ID 입력 (복수 가능)
      ↓
4. Preview 버튼 클릭
      ↓
5. 결과 파싱
   ├── "Containers cannot be redelivered" (빨간색)
   │     → Eqp Units + Reason 추출 → 반납 불가 처리
   └── "Containers can be booked" (파란색)
         → 체크박스 선택 + Book 버튼 클릭
              ↓
         6. 반납번호 발급 (예: TKE6E02)
              ↓
         7. 발급된 반납번호 링크 클릭
              ↓
         8. 상세 화면에서 추출:
            - Bk Ref (반납번호)
            - Depot Name (반납지, 예: INC05 - SEUNG JIN ENTERPRISES)
            - Over Caps (YES/NO)
            - Ant Close Date (유효기간)
```

### 결과 화면 구조

#### 반납 불가
```
제목: "Containers cannot be redelivered"
컬럼: Eqp Units | Reason
예시: TEMU154935 | CONTAINERS NOT HIRED BY SINOK1
```

#### 반납 가능 (Preview)
```
제목: "Containers can be booked and references will be issued immediately"
컬럼: Units | Contract | Lease | Cust Name | Eqp Type | Depot Name | Tex Ofc | Caps Left | Over Caps
예시: 1 | KORL0457 | KORL0458 | SINOKOR | 20 STD DRY FRT | INC05 - SEUNG JIN ENTERPRISES | SEL | 5 | NO
```

#### 반납번호 상세 (Book 후)
```
Booking Header:
  Bk Ref: TKE6E02
  Depot Name: INC05 - SEUNG JIN ENTERPRISES
  Over Caps: NO
  Ant Close Date: 2026-MAY-31

Assigned Containers:
  Equipment ID | Eqp Type | Eqp Status | Move Status | Move Depot | Move Date
```

### ⚠️ 주의사항
- **Book 버튼 클릭 = 실제 예약 생성** → 이메일 자동 발송, Caps Left 차감
- 동일 컨테이너 중복 실행 시 중복 예약 발생 가능
- 스크래퍼에서 중복 체크 로직 필요
