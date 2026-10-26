'use client'
import { useEffect, useMemo, useState } from 'react'
import ResultTable, { type QueryResult } from './ResultTable'
import DepotPickerModal from './DepotPickerModal'
import {
  LESSOR_CATALOG,
  COMPANY_LINE,
  REGIONS,
  CARRIER_CODES,
  type Templates,
  templateKey,
  catalogEntryFor,
  homepageFor,
  regionForOffice,
  buildMailto,
  todayMMDD,
  detectMobile,
  loadUIState,
  saveUIState,
  loadDepotHistory,
  saveDepotHistory,
  depotHistoryKey,
} from '@/lib/lessors'

// ─────────────────────────────────────────────────────────────
// 통합 조회 (단건): 선사 + 컨테이너 번호 1개 → 임대사/반납지역/타입 자동
// 판별은 백엔드 /lookup (반납 대장 우선 → 접두어 표)
// ─────────────────────────────────────────────────────────────

type LookupResult = {
  container_no: string
  valid_format: boolean
  check_digit_ok: boolean
  lessor: string | null
  source: 'inventory' | 'prefix' | null
  line: 'SK' | 'HA' | null
  type: string | null
  contract: string | null
  candidates: string[]
}

const CONTAINER_RE = /^[A-Z]{4}\d{7}$/
const TYPE_OPTIONS = ['22GP', '42GP', '45GP', '22R1', '45R1']

const SOURCE_LABEL: Record<string, { text: string; cls: string }> = {
  inventory: { text: '반납 대장 일치', cls: 'bg-green-50 text-green-700 border-green-200' },
  prefix: { text: '접두어 판별', cls: 'bg-blue-50 text-blue-700 border-blue-200' },
}

const LINE_TO_COMPANY: Record<string, string> = Object.fromEntries(
  Object.entries(COMPANY_LINE).map(([c, l]) => [l, c])
)

export default function SingleLookupForm({ office }: { office: string }) {
  const companies = Object.keys(LESSOR_CATALOG)

  const [company, setCompany] = useState(companies[0])
  const [containerInput, setContainerInput] = useState('')
  const [lookup, setLookup] = useState<LookupResult | null>(null)
  const [lookupLoading, setLookupLoading] = useState(false)
  // 사용자가 직접 고른 카탈로그 코드 (자동 판별 덮어쓰기)
  const [override, setOverride] = useState<string | null>(null)
  // 반납지역: 로그인 사무소 기준 (합의 2026-10-26). 화면에서 변경 가능, 저장 X.
  const [region, setRegion] = useState(regionForOffice(office))
  const [containerType, setContainerType] = useState('45GP')

  const [templates, setTemplates] = useState<Templates>({})
  // 이번 화면에서 고른 반납CY (키: 선사|임대사|지역). 없으면 저장된 마지막 선택.
  const [depotPicked, setDepotPicked] = useState<Record<string, string>>({})
  const [depotModalOpen, setDepotModalOpen] = useState(false)

  const [results, setResults] = useState<QueryResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [isMobile, setIsMobile] = useState(false)

  // 초기 마운트: 마지막 선사 복원 + 사무소 머지된 템플릿 로드
  useEffect(() => {
    const saved = loadUIState()
    if (saved.company && LESSOR_CATALOG[saved.company]) setCompany(saved.company)
    setIsMobile(detectMobile())
    fetch(`/api/email-templates?office=${encodeURIComponent(office)}`)
      .then((r) => r.json())
      .then((d) => setTemplates(d.templates ?? {}))
      .catch(() => {})
  }, [office])

  useEffect(() => {
    saveUIState({ company })
  }, [company])

  const containerNo = containerInput.replace(/[\s-]/g, '').toUpperCase()
  const formatOk = CONTAINER_RE.test(containerNo)

  // 번호가 11자리 형식이 되면 판별 (입력 중 연속 호출 방지용 짧은 지연)
  useEffect(() => {
    if (!formatOk) return
    let cancelled = false
    const t = setTimeout(async () => {
      setLookupLoading(true)
      try {
        const res = await fetch(`/api/lookup?container=${encodeURIComponent(containerNo)}`)
        const data = await res.json()
        if (cancelled) return
        if (!res.ok || data.error || data.detail) {
          throw new Error(data.detail || data.error || `판별 실패 (HTTP ${res.status})`)
        }
        setLookup(data)
        setContainerType(data.type || '45GP')
      } catch (err: unknown) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : '임대사 판별 중 오류가 발생했습니다.')
      } finally {
        if (!cancelled) setLookupLoading(false)
      }
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [containerNo, formatOk])

  // ── 판별 결과 → 이 선사의 카탈로그 항목 ──────────────────────
  const carrierLessors = LESSOR_CATALOG[company] ?? []
  const detected = lookup?.lessor ?? null
  const entry = override
    ? carrierLessors.find((l) => l.code === override)
    : detected
      ? catalogEntryFor(company, detected)
      : undefined
  const lessor = entry?.code ?? ''

  // 판별은 됐는데 이 선사 카탈로그에 없음 → 다른 선사 전용 or 시스템 미지원
  const otherCompanyFor = (base: string) =>
    companies.find((c) => c !== company && catalogEntryFor(c, base))
  const unsupportedMsg =
    !override && detected && !entry
      ? otherCompanyFor(detected)
        ? `${detected} 은(는) ${otherCompanyFor(detected)} 전용 임대사입니다. 선사를 확인하세요.`
        : `${detected} 은(는) 시스템에 등록되지 않은 임대사입니다. 수동으로 처리해 주세요.`
      : ''

  // 반납 대장상 선사와 선택 선사가 다르면 경고 (라인변경 건이 있어 잠그지는 않음)
  const ledgerCompany = lookup?.line ? LINE_TO_COMPANY[lookup.line] : undefined
  const lineMismatch = !!ledgerCompany && ledgerCompany !== company

  const isQueryLessor = entry?.mode === 'query'
  const isWip = entry?.status === 'wip'
  const showMail = !!entry
  const emphasizeMail = entry?.mode === 'email' || !!entry?.mailFallback
  const showType = emphasizeMail

  const carrierInfo = CARRIER_CODES[company]
  const regionInfo = REGIONS.find((r) => r.value === region) ?? REGIONS[1]

  // FLOR 반납CY: 다중 조회와 같은 history 키를 공유 → 마지막 선택이 기본값
  const isFlor = lessor ? templateKey(lessor) === 'FLOR' : false
  // (판별 이후에만 렌더되므로 localStorage 를 렌더 중에 읽어도 hydration 문제 없음)
  const depotKey = depotHistoryKey(company, lessor, region)
  const depotLabel = isFlor
    ? depotPicked[depotKey] ?? loadDepotHistory()[depotKey] ?? ''
    : ''

  const dateStr = todayMMDD()
  const tpl = lessor ? templates[templateKey(lessor)] : undefined
  const mailto = useMemo(
    () =>
      buildMailto(
        tpl,
        {
          carrier_name: company,
          carrier_code: carrierInfo.code,
          carrier_alt: carrierInfo.alt,
          office,
          region: regionInfo.label,
          region_en: regionInfo.value,
          date: dateStr,
          containers: formatOk
            ? [{ container_no: containerNo, container_type: containerType }]
            : [],
        },
        isMobile
      ),
    [tpl, company, carrierInfo, office, regionInfo, dateStr, formatOk, containerNo, containerType, isMobile]
  )

  async function handleQuery() {
    if (!formatOk || !lessor) return
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
          containers: [containerNo],
          depot: isFlor ? depotLabel : undefined,
        }),
      })
      const data = await res.json()
      if (!res.ok || data.error || data.detail) {
        throw new Error(data.detail || data.error || `조회 실패 (HTTP ${res.status})`)
      }
      setResults(data.results)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '조회 중 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const selectCls =
    'w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500'

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 space-y-5">
        {/* 1) 선사 + 컨테이너 */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-800 mb-1">선사</label>
            <div className="flex gap-2">
              {companies.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => {
                    setCompany(c)
                    setOverride(null)
                    setResults(null)
                  }}
                  className={`flex-1 px-3 py-2 rounded-md text-sm border transition-colors ${
                    c === company
                      ? 'bg-slate-800 text-white border-slate-800'
                      : 'bg-white text-gray-800 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-gray-800 mb-1">
              컨테이너 번호 <span className="text-gray-500 font-normal">(1개)</span>
            </label>
            <input
              value={containerInput}
              onChange={(e) => {
                // 번호가 바뀌면 이전 판별/결과/직접 선택 초기화
                setContainerInput(e.target.value)
                setLookup(null)
                setOverride(null)
                setResults(null)
                setError('')
              }}
              placeholder="예: DFSU7487867"
              maxLength={20}
              autoFocus
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono uppercase placeholder:normal-case placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-slate-500"
            />
            <p className="text-xs mt-1 h-4">
              {containerNo && !formatOk && (
                <span className="text-gray-500">영문 4자리 + 숫자 7자리를 입력하세요.</span>
              )}
              {lookup && !lookup.check_digit_ok && (
                <span className="text-red-600 font-medium">
                  ⚠️ 체크디짓이 맞지 않습니다 — 번호 오타를 확인하세요.
                </span>
              )}
              {lookup && lookup.check_digit_ok && (
                <span className="text-green-700">✔ 체크디짓 정상</span>
              )}
            </p>
          </div>
        </div>

        {/* 2) 판별 결과 */}
        {formatOk && (
          <div className="border-t border-gray-100 pt-4 space-y-3">
            {lookupLoading && <p className="text-sm text-gray-600">임대사 판별 중...</p>}

            {lookup && (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {/* 임대사 */}
                  <div>
                    <label className="flex items-center justify-between text-sm font-medium text-gray-800 mb-1">
                      <span className="flex items-center gap-2">
                        임대사
                        {!override && lookup.source && (
                          <span
                            className={`text-xs font-normal border rounded px-1.5 py-0.5 ${SOURCE_LABEL[lookup.source].cls}`}
                          >
                            {SOURCE_LABEL[lookup.source].text}
                          </span>
                        )}
                        {!override && !lookup.lessor && (
                          <span className="text-xs font-normal border rounded px-1.5 py-0.5 bg-red-50 text-red-700 border-red-200">
                            미판별
                          </span>
                        )}
                        {override && (
                          <span className="text-xs font-normal border rounded px-1.5 py-0.5 bg-amber-50 text-amber-700 border-amber-200">
                            직접 선택
                          </span>
                        )}
                      </span>
                      {lessor && homepageFor(lessor) && (
                        <a
                          href={homepageFor(lessor) as string}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-gray-500 hover:underline font-bold"
                        >
                          🌐 홈페이지
                        </a>
                      )}
                    </label>
                    <select
                      value={lessor}
                      onChange={(e) => setOverride(e.target.value || null)}
                      className={selectCls}
                    >
                      {!lessor && <option value="">— 임대사 선택 —</option>}
                      {carrierLessors.map((l) => (
                        <option key={l.code} value={l.code}>
                          {l.code}
                          {l.mode === 'email' ? ' (메일)' : ' (홈페이지 조회)'}
                          {l.status === 'wip' ? ' [준비중]' : ''}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* 반납지역 */}
                  <div>
                    <label className="block text-sm font-medium text-gray-800 mb-1">
                      반납지역 <span className="text-gray-500 font-normal">({office}사무소 기준)</span>
                    </label>
                    <select value={region} onChange={(e) => setRegion(e.target.value)} className={selectCls}>
                      {REGIONS.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* 타입 (메일 발송 시에만 사용) */}
                  {showType && (
                    <div>
                      <label className="block text-sm font-medium text-gray-800 mb-1">
                        타입{' '}
                        {lookup.type && (
                          <span className="text-gray-500 font-normal">(대장: {lookup.type})</span>
                        )}
                      </label>
                      <select
                        value={containerType}
                        onChange={(e) => setContainerType(e.target.value)}
                        className={selectCls}
                      >
                        {[...new Set([containerType, ...TYPE_OPTIONS])].map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                {/* 방식 / 계약 안내 */}
                {entry && (
                  <p className="text-sm text-gray-700">
                    방식:{' '}
                    <span className="font-semibold">
                      {entry.mode === 'query' ? '🔍 홈페이지 조회' : '📧 메일 발송'}
                    </span>
                    {entry.mailFallback && ' (메일 신청도 가능)'}
                    {lookup.contract && (
                      <span className="text-gray-500"> · 계약 {lookup.contract}</span>
                    )}
                  </p>
                )}

                {/* 같은 접두어로 대장에 나온 다른 임대사 */}
                {!override && lookup.candidates.length > 1 && lookup.source !== 'inventory' && (
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="text-gray-700">
                      {detected ? '이 접두어의 다른 후보:' : '반납 대장상 이 접두어 후보:'}
                    </span>
                    {lookup.candidates
                      .filter((c) => c !== detected)
                      .map((c) => {
                        const e = catalogEntryFor(company, c)
                        return (
                          <button
                            key={c}
                            type="button"
                            disabled={!e}
                            onClick={() => e && setOverride(e.code)}
                            className="px-2 py-0.5 border border-gray-300 rounded text-gray-800 hover:bg-gray-50 disabled:opacity-40"
                          >
                            {c}
                          </button>
                        )
                      })}
                  </div>
                )}

                {lineMismatch && (
                  <p className="text-amber-700 text-sm bg-amber-50 border border-amber-200 rounded px-3 py-2">
                    ⚠️ 반납 대장상 선사는 <b>{ledgerCompany}</b> 입니다.{' '}
                    <button
                      type="button"
                      onClick={() => ledgerCompany && setCompany(ledgerCompany)}
                      className="underline font-medium"
                    >
                      {ledgerCompany}(으)로 바꾸기
                    </button>
                  </p>
                )}

                {unsupportedMsg && (
                  <p className="text-red-700 text-sm bg-red-50 border border-red-200 rounded px-3 py-2">
                    ⛔ {unsupportedMsg}
                  </p>
                )}

                {isFlor && (
                  <div className="flex items-center gap-3">
                    <label className="text-sm font-medium text-gray-800">반납CY</label>
                    <button
                      type="button"
                      onClick={() => setDepotModalOpen(true)}
                      className={`flex-1 text-left px-3 py-2 border rounded-md text-sm transition-colors ${
                        depotLabel
                          ? 'border-gray-300 bg-white text-gray-800 hover:bg-gray-50'
                          : 'border-red-300 bg-red-50 text-red-600 hover:bg-red-100'
                      }`}
                    >
                      {depotLabel
                        ? `🏭 ${depotLabel}`
                        : `🏭 ${regionInfo.label} 반납CY 미선택 — 클릭하여 선택`}
                    </button>
                  </div>
                )}

                {isWip && (
                  <p className="text-amber-600 text-sm bg-amber-50 border border-amber-200 rounded px-3 py-2">
                    ⚠️ 이 임대사 웹 조회는 아직 준비중입니다. 메일로 보내기는 가능합니다.
                  </p>
                )}
              </>
            )}
          </div>
        )}

        {error && <p className="text-red-500 text-sm">{error}</p>}

        {/* 3) 버튼 */}
        {entry && (
          <div className="flex flex-col items-end gap-2">
            <div className="flex gap-2">
              {isQueryLessor && (
                <button
                  type="button"
                  onClick={handleQuery}
                  disabled={loading || isWip || (isFlor && !depotLabel)}
                  className="bg-slate-800 text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title={isFlor && !depotLabel ? '반납CY를 먼저 선택하세요' : undefined}
                >
                  {loading ? '조회 중...' : '🔍 조회하기'}
                </button>
              )}
              {showMail && (
                <a
                  href={mailto || '#'}
                  onClick={(e) => {
                    if (!mailto) {
                      e.preventDefault()
                      setError('메일 양식이 아직 로드되지 않았습니다. 잠시 후 다시 시도하세요.')
                    }
                  }}
                  className={`px-6 py-2 rounded-md text-sm font-medium transition-colors ${
                    emphasizeMail && !isQueryLessor
                      ? 'bg-slate-800 text-white hover:bg-slate-700'
                      : 'bg-white text-slate-800 border border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  {emphasizeMail && !isQueryLessor ? '📧 메일 보내기' : '📧 메일로 신청'}
                </a>
              )}
            </div>
            {isQueryLessor && (
              <p className="text-xs text-gray-600">
                ※ 조회 시 임대사 사이트에서 실제 반납 신청(반납번호 발급)이 진행됩니다.
              </p>
            )}
          </div>
        )}
      </div>

      {isQueryLessor && results && (
        <ResultTable
          results={results}
          company={company}
          lessor={lessor}
          region={region}
          onResultsChange={setResults}
        />
      )}

      <DepotPickerModal
        open={depotModalOpen}
        company={company}
        region={region}
        regionLabel={regionInfo.label}
        value={depotLabel}
        onSelect={(label) => {
          setDepotPicked((prev) => ({ ...prev, [depotKey]: label }))
          saveDepotHistory(depotKey, label)
        }}
        onClose={() => setDepotModalOpen(false)}
      />
    </div>
  )
}
