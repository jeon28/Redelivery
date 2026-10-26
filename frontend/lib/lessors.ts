// ─────────────────────────────────────────────────────────────
// 임대사 카탈로그·메일 템플릿·브라우저 저장 헬퍼
// 다중 조회(SearchForm) / 통합 조회(SingleLookupForm) 공용
// ─────────────────────────────────────────────────────────────

// 임대사 카탈로그 (헌법: 프론트 하드코딩)
// 카탈로그 코드 → 베이스 코드(template key) 정규화 함수 제공
export type LessorMode = 'query' | 'email'
export type LessorEntry = {
  code: string
  mode: LessorMode
  status?: 'ready' | 'wip'
  // 웹 조회가 원활하지 않아 메일 신청도 함께 정식 경로로 안내하는 임대사
  mailFallback?: boolean
}

export const LESSOR_CATALOG: Record<string, LessorEntry[]> = {
  장금상선: [
    { code: 'TEXA',       mode: 'query', status: 'ready' },
    { code: 'TRIT+TRAM',  mode: 'query', status: 'ready' },
    { code: 'GLOD',       mode: 'query', status: 'ready', mailFallback: true },
    { code: 'FLOR+DFIC',  mode: 'query', status: 'ready' },
    { code: 'GESE+CROS',  mode: 'query', status: 'ready', mailFallback: true },
    { code: 'GCIC',       mode: 'query', status: 'wip' },
    { code: 'CAIC',       mode: 'email' },
    { code: 'BCON',       mode: 'email' },
    { code: 'CARL',       mode: 'email' },
    { code: 'BLUE',       mode: 'email' },
  ],
  흥아라인: [
    { code: 'TEXA',       mode: 'query', status: 'ready' },
    { code: 'TRIT',       mode: 'query', status: 'ready' },
    { code: 'GOLD',       mode: 'query', status: 'ready', mailFallback: true },
    { code: 'FLOR',       mode: 'query', status: 'ready' },
    { code: 'GESE+SGCN',  mode: 'query', status: 'ready', mailFallback: true },
    { code: 'BCON',       mode: 'email' },
    { code: 'CARL',       mode: 'email' },
    { code: 'BLUE',       mode: 'email' },
    { code: 'MWSC+CALT',  mode: 'email' },
    { code: 'GVCC',       mode: 'email' },
  ],
}

// 선사명 → 백엔드 판별 결과의 line 값 (반납 대장 LINE 칸)
export const COMPANY_LINE: Record<string, string> = {
  장금상선: 'SK',
  흥아라인: 'HA',
}

// 카탈로그 코드 → 템플릿 키 정규화
export function templateKey(code: string): string {
  // GLOD → GOLD (장금만 GLOD, 흥아는 GOLD)
  if (code === 'GLOD') return 'GOLD'
  // TRIT+TRAM → TRIT, FLOR+DFIC → FLOR, GESE+CROS → GESE 등
  return code.split('+')[0]
}

// 판별된 베이스 코드(TEXA, GOLD, MWSC …) → 해당 선사 카탈로그 항목
export function catalogEntryFor(
  company: string,
  baseCode: string
): LessorEntry | undefined {
  return (LESSOR_CATALOG[company] ?? []).find(
    (l) => templateKey(l.code) === baseCode
  )
}

// 임대사 베이스 코드 → 공식 홈페이지/포털 URL
const LESSOR_HOMEPAGES: Record<string, string> = {
  TEXA: 'https://www.textainer.com/contact',
  TRIT: 'https://www.tritoncontainer.com/tritoncontainer/',
  GOLD: 'http://www.touax-container.com/?option=com_indexinfo',
  FLOR: 'http://www.florens.com/',
  GESE: 'https://seaweb.seacoglobal.com/',
  GCIC: 'https://gcx.intermodalportal.com/',
  CAIC: 'https://cai.capps.com/',
  BCON: 'https://beacon.intermodalportal.com/',
  CARL: 'https://seacube.intermodalportal.com/',
  BLUE: 'https://bsiu.com/',
}

export function homepageFor(code: string): string | null {
  return LESSOR_HOMEPAGES[templateKey(code)] ?? null
}

// ─────────────────────────────────────────────────────────────
// 반납지역
// ─────────────────────────────────────────────────────────────
export const REGIONS = [
  { label: '부산', value: 'BUSAN' },
  { label: '인천', value: 'INCHON' },
  { label: '평택', value: 'PYEONGTAEK' },
  { label: '광양', value: 'GWANGYANG' },
  { label: '울산', value: 'ULSAN' },
]

// 로그인 사무소 → 반납지역 기본값 (본사 등 목록에 없으면 인천)
export function regionForOffice(office: string): string {
  return REGIONS.find((r) => r.label === office)?.value ?? 'INCHON'
}

export const CARRIER_CODES: Record<string, { code: string; alt: string }> = {
  장금상선: { code: 'SKR', alt: 'SKR' },
  흥아라인: { code: 'HAS', alt: 'HAL' },
}

// ─────────────────────────────────────────────────────────────
// 메일 템플릿
// ─────────────────────────────────────────────────────────────
export type Template = {
  name: string
  language: string
  to: string
  cc: string
  subject: string
  body: string
}
export type Templates = Record<string, Template>

export type MailContainer = { container_no: string; container_type: string }

type TemplateContext = {
  carrier_name: string
  carrier_code: string
  carrier_alt: string
  office: string
  region: string
  region_en: string
  date: string
  containers: MailContainer[]
}

export function renderTemplate(
  tpl: Template,
  ctx: TemplateContext
): { subject: string; body: string } {
  // 한 줄 포맷: "선사코드 컨테이너번호 사이즈"
  // 예: SKR ABCD1234567 45GP
  const containerBlock = ctx.containers
    .filter((c) => c.container_no.trim())
    .map(
      (c) =>
        `${ctx.carrier_code} ${c.container_no.trim()} ${
          c.container_type.trim() || '45GP'
        }`
    )
    .join('\n')

  const first = ctx.containers[0] ?? { container_no: '', container_type: '' }

  const vars: Record<string, string> = {
    carrier_name: ctx.carrier_name,
    carrier_code: ctx.carrier_code,
    carrier_alt: ctx.carrier_alt,
    office: `${ctx.office}사무소`,
    region: ctx.region,
    region_en: ctx.region_en,
    date: ctx.date,
    first_container: first.container_no,
    first_type: first.container_type || '45GP',
    containers: containerBlock,
  }

  const replace = (s: string) =>
    s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? `{${k}}`)

  return { subject: replace(tpl.subject), body: replace(tpl.body) }
}

// 메일 제목용 날짜 (예: 10/26)
export function todayMMDD(): string {
  const today = new Date()
  return `${today.getMonth() + 1}/${String(today.getDate()).padStart(2, '0')}`
}

/** 템플릿 + 수신자 규칙 → mailto: 링크. 템플릿/컨테이너가 없으면 ''. */
export function buildMailto(
  tpl: Template | undefined,
  ctx: TemplateContext,
  isMobile: boolean
): string {
  if (!tpl || !tpl.subject || !tpl.body || ctx.containers.length === 0) return ''
  const { subject, body } = renderTemplate(tpl, ctx)
  // 저장된 To/CC 는 ';' 안내지만 ',' 로 입력된 케이스도 있어 양쪽 모두 분리.
  // 출력은 데스크톱 ';' (Outlook 데스크톱이 ','를 단일 주소의 일부로 해석해
  // 한 줄로 합치는 문제 회피), 모바일 ',' (모바일 Outlook 은 반대).
  const sep = isMobile ? ',' : ';'
  const splitAddrs = (s: string) =>
    s.split(/[,;]/).map((x) => x.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean)
  const to = splitAddrs(tpl.to).join(sep)
  const cc = splitAddrs(tpl.cc).join(sep)
  // mailto: 는 RFC 6068 에 따라 application/x-www-form-urlencoded 가 아닌
  // 표준 percent-encoding 을 사용해야 한다. URLSearchParams 는 공백을 '+' 로
  // 인코딩하여 Outlook 등에서 '+' 가 그대로 표시되는 문제가 있으므로
  // encodeURIComponent 로 직접 인코딩.
  const parts: string[] = []
  if (cc) parts.push(`cc=${encodeURIComponent(cc)}`)
  parts.push(`subject=${encodeURIComponent(subject)}`)
  parts.push(`body=${encodeURIComponent(body)}`)
  return `mailto:${to}?${parts.join('&')}`
}

// 모바일 Outlook(iOS/Android)은 RFC 6068 대로 ',' 만 구분자로 인식하고 ';' 를
// 주소 일부로 취급해 한 줄로 합쳐 오류가 난다. SSR hydration 불일치를 피하려고
// 호출자가 마운트 후에 판별한다.
export function detectMobile(): boolean {
  return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)
}

// ─────────────────────────────────────────────────────────────
// localStorage 헬퍼 (선사·반납지역 마지막 값 저장. 사무소는 세션 고정)
// ─────────────────────────────────────────────────────────────
const LS_KEY = 'redelivery_ui_state_v1'

export function loadUIState(): { company?: string; region?: string } {
  if (typeof window === 'undefined') return {}
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) ?? '{}')
  } catch {
    return {}
  }
}

export function saveUIState(state: Record<string, string>) {
  if (typeof window === 'undefined') return
  try {
    const prev = loadUIState()
    localStorage.setItem(LS_KEY, JSON.stringify({ ...prev, ...state }))
  } catch {}
}

// FLOR 반납CY 마지막 선택 기억 — (선사, 임대사, region) 별로 저장.
// 사용자가 매번 같은 depot 을 다시 고르는 비효율 제거. 변경하려면 모달 클릭.
const LS_DEPOT_KEY = 'redelivery_flor_depot_history_v1'

export function loadDepotHistory(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  try {
    return JSON.parse(localStorage.getItem(LS_DEPOT_KEY) ?? '{}')
  } catch {
    return {}
  }
}

export function saveDepotHistory(key: string, label: string) {
  if (typeof window === 'undefined') return
  if (!label) return
  try {
    const prev = loadDepotHistory()
    localStorage.setItem(LS_DEPOT_KEY, JSON.stringify({ ...prev, [key]: label }))
  } catch {}
}

export function depotHistoryKey(company: string, lessor: string, region: string): string {
  return `${company}|${lessor}|${region}`
}
