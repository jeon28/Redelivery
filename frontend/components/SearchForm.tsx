'use client'
import { useEffect, useMemo, useState } from 'react'
import ResultTable, { type QueryResult } from './ResultTable'

// ─────────────────────────────────────────────────────────────
// 임대사 카탈로그 (헌법: 프론트 하드코딩)
// 카탈로그 코드 → 베이스 코드(template key) 정규화 함수 제공
// ─────────────────────────────────────────────────────────────
type LessorMode = 'query' | 'email'
type LessorEntry = { code: string; mode: LessorMode; status?: 'ready' | 'wip' }

const LESSOR_CATALOG: Record<string, LessorEntry[]> = {
  장금상선: [
    { code: 'TEXA',       mode: 'query', status: 'ready' },
    { code: 'TRIT+TRAM',  mode: 'query', status: 'wip' },
    { code: 'GLOD',       mode: 'query', status: 'wip' },
    { code: 'FLOR+DFIC',  mode: 'query', status: 'wip' },
    { code: 'GESE+CROS',  mode: 'query', status: 'wip' },
    { code: 'GCIC',       mode: 'query', status: 'wip' },
    { code: 'CAIC',       mode: 'email' },
    { code: 'BCON',       mode: 'email' },
    { code: 'CARL',       mode: 'email' },
    { code: 'BLUE',       mode: 'email' },
  ],
  흥아라인: [
    { code: 'TEXA',       mode: 'query', status: 'ready' },
    { code: 'TRIT',       mode: 'query', status: 'wip' },
    { code: 'GOLD',       mode: 'query', status: 'wip' },
    { code: 'FLOR',       mode: 'query', status: 'wip' },
    { code: 'GESE+SGCN',  mode: 'query', status: 'wip' },
    { code: 'BCON',       mode: 'email' },
    { code: 'CARL',       mode: 'email' },
    { code: 'BLUE',       mode: 'email' },
  ],
}

// 카탈로그 코드 → 템플릿 키 정규화
function templateKey(code: string): string {
  // GLOD → GOLD (장금만 GLOD, 흥아는 GOLD)
  if (code === 'GLOD') return 'GOLD'
  // TRIT+TRAM → TRIT, FLOR+DFIC → FLOR, GESE+CROS → GESE 등
  return code.split('+')[0]
}

// ─────────────────────────────────────────────────────────────
// 사무소 / 반납지역
// ─────────────────────────────────────────────────────────────
const OFFICES = ['본사', '부산', '인천', '평택', '광양', '울산']
const REGIONS = [
  { label: '부산', value: 'BUSAN' },
  { label: '인천', value: 'INCHON' },
  { label: '평택', value: 'PYEONGTAEK' },
  { label: '광양', value: 'GWANGYANG' },
  { label: '울산', value: 'ULSAN' },
]

const CARRIER_CODES: Record<string, { code: string; alt: string }> = {
  장금상선: { code: 'SKR', alt: 'SKR' },
  흥아라인: { code: 'HAS', alt: 'HAL' },
}

// ─────────────────────────────────────────────────────────────
// 메일 템플릿
// ─────────────────────────────────────────────────────────────
type Template = {
  name: string
  language: string
  to: string
  cc: string
  subject: string
  body: string
}
type Templates = Record<string, Template>

function renderTemplate(
  tpl: Template,
  ctx: {
    carrier_name: string
    carrier_code: string
    carrier_alt: string
    office: string
    region: string
    region_en: string
    date: string
    containers: { container_no: string; container_type: string }[]
  }
): { subject: string; body: string } {
  const containerBlock = ctx.containers
    .filter((c) => c.container_no.trim())
    .map(
      (c) =>
        `${ctx.carrier_code}\n${c.container_no.trim()}\n${
          c.container_type.trim() || '45GP'
        }`
    )
    .join('\n\n')

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

// ─────────────────────────────────────────────────────────────
// 컨테이너 입력 파싱: "번호 사이즈" (한 줄에 하나)
// ─────────────────────────────────────────────────────────────
function parseContainerLines(
  text: string,
  defaultType: string
): { container_no: string; container_type: string }[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(/\s+/)
      return {
        container_no: parts[0]?.toUpperCase() ?? '',
        container_type: (parts[1] ?? defaultType).toUpperCase(),
      }
    })
}

// ─────────────────────────────────────────────────────────────
// localStorage 헬퍼 (사무소 마지막 값 저장)
// ─────────────────────────────────────────────────────────────
const LS_KEY = 'redelivery_ui_state_v1'

function loadUIState(): { company?: string; office?: string; region?: string } {
  if (typeof window === 'undefined') return {}
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) ?? '{}')
  } catch {
    return {}
  }
}

function saveUIState(state: Record<string, string>) {
  if (typeof window === 'undefined') return
  try {
    const prev = loadUIState()
    localStorage.setItem(LS_KEY, JSON.stringify({ ...prev, ...state }))
  } catch {}
}

// ─────────────────────────────────────────────────────────────
// 메인 컴포넌트
// ─────────────────────────────────────────────────────────────
export default function SearchForm() {
  const companies = Object.keys(LESSOR_CATALOG)

  const [company, setCompany] = useState(companies[0])
  const carrierLessors = LESSOR_CATALOG[company] ?? []
  const [lessor, setLessor] = useState(carrierLessors[0]?.code ?? '')
  const [office, setOffice] = useState('인천')
  const [region, setRegion] = useState('INCHON')
  const [containerText, setContainerText] = useState('')

  const [results, setResults] = useState<QueryResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [templates, setTemplates] = useState<Templates>({})

  // 초기 마운트: localStorage 복원 + 템플릿 로드
  useEffect(() => {
    const saved = loadUIState()
    if (saved.company && LESSOR_CATALOG[saved.company]) setCompany(saved.company)
    if (saved.office && OFFICES.includes(saved.office)) setOffice(saved.office)
    if (saved.region && REGIONS.find((r) => r.value === saved.region))
      setRegion(saved.region)

    fetch('/api/email-templates')
      .then((r) => r.json())
      .then((d) => setTemplates(d.templates ?? {}))
      .catch(() => {})
  }, [])

  // 선사 변경 시 임대사 목록 갱신
  useEffect(() => {
    const list = LESSOR_CATALOG[company] ?? []
    if (!list.find((l) => l.code === lessor)) {
      setLessor(list[0]?.code ?? '')
    }
    saveUIState({ company })
  }, [company, lessor])

  // 사무소 변경 시 반납지역 자동 동기화 (본사 제외)
  useEffect(() => {
    if (office === '본사') {
      saveUIState({ office })
      return
    }
    // 사무소명 → REGION value 매칭
    const matched = REGIONS.find((r) => r.label === office)
    if (matched) {
      setRegion(matched.value)
    }
    saveUIState({ office })
  }, [office])

  // 반납지역 변경 별도 저장
  useEffect(() => {
    saveUIState({ region })
  }, [region])

  const currentLessor = carrierLessors.find((l) => l.code === lessor)
  const isWip = currentLessor?.status === 'wip'
  const isEmailLessor = currentLessor?.mode === 'email'
  const isQueryLessor = currentLessor?.mode === 'query'

  const carrierInfo = CARRIER_CODES[company]
  const regionInfo = REGIONS.find((r) => r.value === region) ?? REGIONS[1]

  // 컨테이너 파싱
  const containers = useMemo(
    () => parseContainerLines(containerText, '45GP'),
    [containerText]
  )

  // 메일 mailto: 링크 생성
  const today = new Date()
  const dateStr = `${today.getMonth() + 1}/${String(today.getDate()).padStart(2, '0')}`

  const tplKey = lessor ? templateKey(lessor) : ''
  const tpl = templates[tplKey]

  const mailto = useMemo(() => {
    if (!tpl || containers.length === 0) return ''
    const { subject, body } = renderTemplate(tpl, {
      carrier_name: company,
      carrier_code: carrierInfo.code,
      carrier_alt: carrierInfo.alt,
      office,
      region: regionInfo.label,
      region_en: regionInfo.value,
      date: dateStr,
      containers,
    })
    const to = tpl.to.split(';').map((s) => s.trim()).filter(Boolean).join(',')
    const cc = tpl.cc.split(';').map((s) => s.trim()).filter(Boolean).join(',')
    // mailto: 는 RFC 6068 에 따라 application/x-www-form-urlencoded 가 아닌
    // 표준 percent-encoding 을 사용해야 한다. URLSearchParams 는 공백을 '+' 로
    // 인코딩하여 Outlook 등에서 '+' 가 그대로 표시되는 문제가 있으므로
    // encodeURIComponent 로 직접 인코딩.
    const parts: string[] = []
    if (cc) parts.push(`cc=${encodeURIComponent(cc)}`)
    parts.push(`subject=${encodeURIComponent(subject)}`)
    parts.push(`body=${encodeURIComponent(body)}`)
    return `mailto:${to}?${parts.join('&')}`
  }, [tpl, containers, company, carrierInfo, office, regionInfo, dateStr])

  // 조회 처리
  async function handleQuery() {
    if (containers.length === 0) {
      setError('컨테이너 번호를 입력하세요.')
      return
    }
    setLoading(true)
    setError('')
    setResults(null)
    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company,
          lessor,
          region,
          containers: containers.map((c) => c.container_no),
        }),
      })
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      setResults(data.results)
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : '조회 중 오류가 발생했습니다.'
      )
    } finally {
      setLoading(false)
    }
  }

  function handleMail(e: React.MouseEvent<HTMLAnchorElement>) {
    if (containers.length === 0) {
      e.preventDefault()
      setError('컨테이너 번호를 입력하세요.')
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 space-y-4">
        <div className="grid grid-cols-4 gap-4">
          {/* 선사 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              선사
            </label>
            <select
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
            >
              {companies.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          {/* 임대사 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              임대사
            </label>
            <select
              value={lessor}
              onChange={(e) => setLessor(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
            >
              {carrierLessors.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.code}
                  {l.mode === 'email' ? ' (메일)' : ''}
                  {l.status === 'wip' ? ' [준비중]' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* 사무소 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              사무소
            </label>
            <select
              value={office}
              onChange={(e) => setOffice(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
            >
              {OFFICES.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>

          {/* 반납지역 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              반납지역
            </label>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
            >
              {REGIONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 컨테이너 입력 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            컨테이너{' '}
            <span className="text-gray-400 font-normal">
              (한 줄에 「번호 사이즈」, 사이즈 생략 시 45GP)
            </span>
          </label>
          <textarea
            value={containerText}
            onChange={(e) => setContainerText(e.target.value)}
            placeholder={'ABCD1234567 45GP\nEFGH8901234 22GP\nIJKL5678901'}
            rows={6}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-500 resize-y"
          />
        </div>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        {isWip && (
          <p className="text-amber-600 text-sm bg-amber-50 border border-amber-200 rounded px-3 py-2">
            ⚠️ 이 임대사 웹 조회는 아직 준비중입니다. 메일로 보내기는 가능합니다.
          </p>
        )}

        {/* 버튼 영역 */}
        <div className="flex justify-end gap-2">
          {/* 조회 버튼: query 모드 임대사 */}
          {isQueryLessor && (
            <button
              type="button"
              onClick={handleQuery}
              disabled={loading || isWip}
              className="bg-slate-800 text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-slate-700 disabled:opacity-50 transition-colors"
            >
              {loading ? '조회 중...' : '🔍 조회하기'}
            </button>
          )}

          {/* 메일 보내기 버튼: 모든 임대사 (query 임대사도 백업용) */}
          <a
            href={mailto || '#'}
            onClick={handleMail}
            className={`px-6 py-2 rounded-md text-sm font-medium transition-colors ${
              containers.length === 0
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : isEmailLessor
                ? 'bg-slate-800 text-white hover:bg-slate-700'
                : 'bg-white text-slate-800 border border-slate-300 hover:bg-slate-50'
            }`}
          >
            {isEmailLessor ? '📧 메일 보내기' : '📧 메일로 신청'}
          </a>
        </div>
      </div>

      {/* 조회 결과 */}
      {isQueryLessor && results && <ResultTable results={results} />}
    </div>
  )
}
