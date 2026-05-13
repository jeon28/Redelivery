# 전산팀 협조 요청: Microsoft 365 메일 발송 권한

> **작성자**: 컨테이너관리팀 / 전성현 (sh.jeon@sinokor.co.kr)
> **작성일**: 2026-05-14
> **시스템**: 반납컨테이너 조회 시스템 (사내 자체 개발)
> **요청 처리 기한**: 가능한 빠른 시일 내

---

## 1. 요청 개요

사내에서 개발 중인 **반납컨테이너 조회 시스템**에서, 컨테이너 임대사(BCON / CARL / CAIC / BLUE 등) 에 보내는 **반납 요청 메일을 자동 발송**하는 기능이 필요합니다. 이를 위해 **Microsoft 365 (Azure AD) 앱 등록 및 메일 발송 권한**을 요청드립니다.

### 한 줄 요약

> *"우리 시스템에서 사용자(예: sh.jeon@sinokor.co.kr) 본인 계정으로 자동으로 외부 임대사에 메일을 보낼 수 있게 해주세요."*

---

## 2. 배경

### 현재 업무 흐름 (수작업)

1. 컨테이너관리팀이 임대사별로 반납 요청 메일을 직접 작성·발송
2. 임대사가 회신 (반납번호 / 반납지 / 유효기간 포함)
3. 회신 내용을 수기로 정리해서 사용

### 문제점

- 한 건당 메일 작성 시간 약 2~3분
- 임대사별 양식이 달라 실수 발생 (수신자/참조 누락, 본문 오타)
- 일일 수십 건 발생 → 시간 소모 큼

### 시스템 도입 후 (목표)

1. 사용자가 컨테이너 번호와 반납지를 입력
2. **시스템이 임대사별 양식에 맞춰 자동 메일 생성**
3. 사용자 본인의 M365 계정으로 자동 발송
4. 회신 PDF/메일을 시스템에 업로드 → 자동 파싱 → DB 저장

이 중 **③ 자동 발송 부분**에 본 요청 사항이 필요합니다.

---

## 3. 기술적 요청 사항

### 요청 내역

**Azure AD (Microsoft Entra ID) 에 애플리케이션 등록 후, 아래 권한을 위임(delegated) 권한으로 부여**

| 항목 | 값 |
|---|---|
| 권한 종류 | Delegated permissions (위임된 권한) |
| API | Microsoft Graph |
| 필요 권한 | `Mail.Send` |
| 사용자 동의 | 사용자별 (관리자 동의 가능 시 더 좋음) |

### 인증 방식

**OAuth 2.0 Authorization Code Flow with PKCE**

- 사용자가 시스템에서 "MS 계정 연결" 클릭
- Microsoft 로그인 페이지로 이동 → 권한 동의
- Access Token + Refresh Token 발급
- 시스템이 토큰만 보관 (비밀번호는 절대 저장하지 않음)
- Refresh Token으로 자동 갱신 (수일~수개월간 재로그인 불필요)

### 구체적 설정 요청 사항

Azure Portal → **App registrations** → **New registration** 화면에서:

```
Name:                  Sinokor 반납컨테이너 시스템 (또는 임의)
Supported account types: Accounts in this organizational directory only
                        (Single tenant - sinokor.co.kr)
Redirect URI (Web):    https://redelivery.sinokor.co.kr/auth/microsoft/callback
                        (또는 Vercel URL: redelivery-xxx.vercel.app/auth/...)
```

**API permissions** 탭에서:

```
Microsoft Graph → Delegated permissions → Mail.Send
Microsoft Graph → Delegated permissions → User.Read (기본 포함)
Microsoft Graph → Delegated permissions → offline_access (Refresh Token 발급용)
```

**Certificates & secrets** 탭에서:

```
New client secret → 만료기간 24개월 (또는 정책에 따라)
→ 발급된 Client Secret 값을 사내 안전한 채널로 전달
```

### 발급받아야 할 정보

전산팀이 발급 후 컨테이너관리팀(전성현)에게 다음을 전달:

1. **Application (client) ID** — Azure Portal에 표시되는 UUID
2. **Directory (tenant) ID** — Azure Portal에 표시되는 UUID
3. **Client Secret** — 한 번만 표시됨, 안전한 채널로 전달 필요

---

## 4. 권한이 사용되는 범위

### 시스템이 할 수 있는 것

- 로그인한 사용자의 **이름으로** 메일 발송
- 발송된 메일은 사용자의 **"보낸 편지함"에 정상 표시**
- 외부 수신자에게도 발송 가능

### 시스템이 할 수 없는 것 (`Mail.Send`만 부여 시)

- ❌ 메일함 읽기 (별도 `Mail.Read` 권한 필요)
- ❌ 메일 삭제
- ❌ 사용자 동의 없이 임의 발송 (반드시 OAuth 로그인 거쳐야 함)
- ❌ 다른 사용자의 메일 발송

---

## 5. 보안 고려사항

| 항목 | 내용 |
|---|---|
| 비밀번호 저장 | **하지 않음** (OAuth 토큰만 저장) |
| MFA 호환 | ✅ 완전 지원 |
| 토큰 저장 위치 | 시스템 DB (암호화) |
| 토큰 만료 시 | 사용자가 재로그인 |
| 권한 회수 | 사용자 또는 관리자가 언제든 회수 가능 (myapps.microsoft.com 또는 Azure Portal) |
| 외부 노출 | 시스템 코드는 사내 git에만 보관, Azure 인증 정보는 환경변수로 분리 |

---

## 6. 사용 예시 (구현 후)

1. 사용자가 시스템 로그인 (현재 자체 ID/PW 인증)
2. 설정 메뉴 → **"MS 계정 연결"** 클릭
3. Microsoft 로그인 화면 → `sh.jeon@sinokor.co.kr` 로 로그인
4. 권한 동의 화면:
   > "**반납컨테이너 시스템** 이 다음 권한을 요청합니다:
   > - 귀하의 이름으로 메일을 보내기 (`Mail.Send`)"
5. 동의 → 시스템으로 리다이렉트, 연결 완료
6. 이후: "메일 반납 등록" → 컨테이너 번호 입력 → **"발송"** 버튼 클릭 → 자동 발송 완료

---

## 7. 대안 (전산팀 협조가 불가능한 경우)

### 대안 A: SMTP AUTH 활성화

- M365 테넌트에서 사용자 계정에 대해 SMTP AUTH 허용
- 사용자가 자신의 비밀번호 또는 앱 비밀번호를 시스템에 등록
- **단점**: 비밀번호를 시스템에 저장해야 함 (보안↓), M365 기본값은 차단

### 대안 B: 사용자 로컬에서 Outlook으로 발송

- 시스템은 메일 양식만 생성 (`mailto:` 링크)
- 사용자 PC의 Outlook 자동 실행 → 본문 자동 입력 → 사용자가 검토 후 직접 발송
- **단점**: 매번 사용자가 한 번 더 클릭해야 함, 첨부파일 자동 추가 불가

위 대안들은 보안성 또는 자동화 정도에서 본 요청(방법 1)보다 떨어집니다.

---

## 8. 일정 협의

| 단계 | 담당 | 예상 소요 |
|---|---|---|
| Azure AD 앱 등록 | 전산팀 | 1~2일 |
| Client ID / Secret 전달 | 전산팀 → 컨테이너관리팀 | 동일 |
| 시스템 연동 코드 작성 | 컨테이너관리팀 | 2~3일 |
| 사내 테스트 | 컨테이너관리팀 | 1~2일 |
| **합계** | | **약 1주일** |

---

## 9. 참고 자료

- [Microsoft Graph: Send mail](https://learn.microsoft.com/en-us/graph/api/user-sendmail)
- [Microsoft Identity Platform: OAuth 2.0 Auth Code Flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Mail.Send Delegated Permission 상세](https://learn.microsoft.com/en-us/graph/permissions-reference#mail-permissions)

---

## 10. 문의

본 요청 관련 문의:

- **전성현** (컨테이너관리팀, 인천사무소)
- E-Mail: sh.jeon@sinokor.co.kr
- Tel: +82-32-885-0578
- Mobile: +82-10-2255-2288

전산팀에서 추가 정보가 필요하시면 위 연락처로 부탁드립니다.
