'use client'
import { useEffect, useMemo, useState } from 'react'
import ResultTable, { type QueryResult } from './ResultTable'
import DepotPickerModal from './DepotPickerModal'
import {
  LESSOR_CATALOG,
  REGIONS,
  CARRIER_CODES,
  type Templates,
  templateKey,
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
// 메인 컴포넌트
// ─────────────────────────────────────────────────────────────
export default function SearchForm({ office }: { office: string }) {
  const companies = Object.keys(LESSOR_CATALOG)

  const [company, setCompany] = useState(companies[0])
  const carrierLessors = LESSOR_CATALOG[company] ?? []
  const [lessor, setLessor] = useState(carrierLessors[0]?.code ?? '')
  // 반납지역 초기값: 로그인 사무소가 REGIONS에 있으면 그걸로, 없으면 INCHON
  const [region, setRegion] = useState(regionForOffice(office))
  const [containerText, setContainerText] = useState('')

  const [results, setResults] = useState<QueryResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [templates, setTemplates] = useState<Templates>({})

  // FLOR 전용: 반납CY(Depot) 선택 (Element UI 옵션 label 그대로 저장)
  const [depotLabel, setDepotLabel] = useState('')
  const [depotModalOpen, setDepotModalOpen] = useState(false)

  // 초기 마운트: localStorage 복원 + 사무소 머지된 템플릿 로드
  useEffect(() => {
    const saved = loadUIState()
    if (saved.company && LESSOR_CATALOG[saved.company]) setCompany(saved.company)
    if (saved.region && REGIONS.find((r) => r.value === saved.region))
      setRegion(saved.region)

    fetch(`/api/email-templates?office=${encodeURIComponent(office)}`)
      .then((r) => r.json())
      .then((d) => setTemplates(d.templates ?? {}))
      .catch(() => {})
  }, [office])

  // 선사 변경 시 임대사 목록 갱신
  useEffect(() => {
    const list = LESSOR_CATALOG[company] ?? []
    if (!list.find((l) => l.code === lessor)) {
      setLessor(list[0]?.code ?? '')
    }
    saveUIState({ company })
  }, [company, lessor])

  // 반납지역 변경 별도 저장
  useEffect(() => {
    saveUIState({ region })
  }, [region])

  const currentLessor = carrierLessors.find((l) => l.code === lessor)
  const isWip = currentLessor?.status === 'wip'
  const isEmailLessor = currentLessor?.mode === 'email'
  const isQueryLessor = currentLessor?.mode === 'query'
  const isMailFallback = !!currentLessor?.mailFallback
  // 메일 버튼을 정식 경로로 강조하는 케이스: email 모드 또는 query+mailFallback
  const emphasizeMailButton = isEmailLessor || isMailFallback

  const carrierInfo = CARRIER_CODES[company]
  const regionInfo = REGIONS.find((r) => r.value === region) ?? REGIONS[1]

  // FLOR/FLOR+DFIC 임대사일 때만 Depot 선택 활성
  const isFlor = lessor ? templateKey(lessor) === 'FLOR' : false
  // company / region / lessor 가 바뀌면 해당 조합의 마지막 선택을 history 에서 복원.
  // history 에 없으면 ''로 떨어져 기존 "미선택" UI 유지.
  useEffect(() => {
    if (!isFlor) {
      setDepotLabel('')
      return
    }
    const history = loadDepotHistory()
    setDepotLabel(history[depotHistoryKey(company, lessor, region)] ?? '')
  }, [company, lessor, region, isFlor])

  // 컨테이너 파싱
  const containers = useMemo(
    () => parseContainerLines(containerText, '45GP'),
    [containerText]
  )

  // 메일 mailto: 링크 생성
  const dateStr = todayMMDD()

  const tplKey = lessor ? templateKey(lessor) : ''
  const tpl = templates[tplKey]

  const [isMobile, setIsMobile] = useState(false)
  useEffect(() => {
    setIsMobile(detectMobile())
  }, [])

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
          containers,
        },
        isMobile
      ),
    [tpl, containers, company, carrierInfo, office, regionInfo, dateStr, isMobile]
  )

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
          depot: isFlor ? depotLabel : undefined,
        }),
      })
      const data = await res.json()
      // 백엔드(FastAPI) 표준 에러는 data.detail, 자체 라우트는 data.error.
      // status 코드도 같이 확인해 500/422 등 비정상 응답을 사용자에게 노출.
      if (!res.ok || data.error || data.detail) {
        throw new Error(
          data.detail || data.error || `조회 실패 (HTTP ${res.status})`
        )
      }
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
        <div className="grid grid-cols-3 gap-4">
          {/* 선사 */}
          <div>
            <label className="block text-sm font-medium text-gray-800 mb-1">
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
            <label className="flex items-center justify-between text-sm font-medium text-gray-800 mb-1">
              <span>임대사</span>
              {homepageFor(lessor) && (
                <a
                  href={homepageFor(lessor) as string}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-gray-500 hover:underline font-bold"
                  title={`${lessor} 홈페이지로 이동`}
                >
                  🌐 홈페이지
                </a>
              )}
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
                  {l.mailFallback ? ' (메일가능)' : ''}
                  {l.status === 'wip' ? ' [준비중]' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* 반납지역 (사무소는 헤더에서 선택 → 자동 동기화) */}
          <div>
            <label className="block text-sm font-medium text-gray-800 mb-1">
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

        {/* FLOR 전용 반납CY 선택 (모달) */}
        {isFlor && (
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-gray-800">
              반납CY
            </label>
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

        {/* 컨테이너 입력 */}
        <div>
          <label className="block text-sm font-medium text-gray-800 mb-1">
            컨테이너{' '}
            <span className="text-gray-500 font-normal">
              (수량 동시 조회 가능)
            </span>
          </label>
          <textarea
            value={containerText}
            onChange={(e) => setContainerText(e.target.value)}
            placeholder={'SKLU1234567 45GP\n메일 발송시 형식 입니다.'}
            rows={6}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-slate-500 resize-y"
          />
        </div>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        {isFlor && containers.length > 5 && (
          <p className="text-amber-600 text-sm bg-amber-50 border border-amber-200 rounded px-3 py-2">
            ⚠️ FLOR 6개 이상 입력 — 이미 반납번호가 발급된 컨테이너가 있을 경우 1건당
            ~6초 추가 소요됩니다.
          </p>
        )}

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
              disabled={loading || isWip || (isFlor && !depotLabel)}
              className="bg-slate-800 text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title={isFlor && !depotLabel ? '반납CY를 먼저 선택하세요' : undefined}
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
                ? 'bg-gray-200 text-gray-600 cursor-not-allowed'
                : emphasizeMailButton
                ? 'bg-slate-800 text-white hover:bg-slate-700'
                : 'bg-white text-slate-800 border border-slate-300 hover:bg-slate-50'
            }`}
          >
            {emphasizeMailButton ? '📧 메일 보내기' : '📧 메일로 신청'}
          </a>
        </div>
      </div>

      {/* 조회 결과 */}
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
          setDepotLabel(label)
          saveDepotHistory(depotHistoryKey(company, lessor, region), label)
        }}
        onClose={() => setDepotModalOpen(false)}
      />
    </div>
  )
}
