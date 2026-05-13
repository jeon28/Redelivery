'use client'
import { useEffect, useMemo, useState } from 'react'

type Template = {
  name: string
  language: string
  to: string
  cc: string
  subject: string
  body: string
}
type Templates = Record<string, Template>

type ContainerRow = { container_no: string; container_type: string }

const CARRIERS = [
  { value: '장금상선', code: 'SKR', alt: 'SKR' },
  { value: '흥아라인', code: 'HAS', alt: 'HAL' },
]

const REGIONS = [
  { value: '인천', en: 'INCHON' },
  { value: '부산', en: 'BUSAN' },
  { value: '광양', en: 'GWANGYANG' },
]

function renderTemplate(
  tpl: Template,
  ctx: {
    carrier_name: string
    carrier_code: string
    carrier_alt: string
    region: string
    region_en: string
    date: string
    containers: ContainerRow[]
  }
): { subject: string; body: string } {
  // 컨테이너 블록 (carrier_code + 번호 + 타입 반복)
  const containerBlock = ctx.containers
    .filter((c) => c.container_no.trim())
    .map(
      (c) =>
        `${ctx.carrier_code}\n${c.container_no.trim()}\n${c.container_type.trim()}`
    )
    .join('\n\n')

  const first = ctx.containers[0] ?? { container_no: '', container_type: '' }

  const vars: Record<string, string> = {
    carrier_name: ctx.carrier_name,
    carrier_code: ctx.carrier_code,
    carrier_alt: ctx.carrier_alt,
    region: ctx.region,
    region_en: ctx.region_en,
    date: ctx.date,
    first_container: first.container_no,
    first_type: first.container_type,
    containers: containerBlock,
  }

  const replace = (s: string) =>
    s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? `{${k}}`)

  return { subject: replace(tpl.subject), body: replace(tpl.body) }
}

export default function EmailRequestForm() {
  const [templates, setTemplates] = useState<Templates>({})
  const [loading, setLoading] = useState(true)

  const [lessor, setLessor] = useState<string>('CAIC')
  const [carrier, setCarrier] = useState<string>('장금상선')
  const [region, setRegion] = useState<string>('인천')
  const [rows, setRows] = useState<ContainerRow[]>([
    { container_no: '', container_type: '' },
  ])

  useEffect(() => {
    fetch('/api/email-templates')
      .then((r) => r.json())
      .then((d) => {
        setTemplates(d.templates ?? {})
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const tpl = templates[lessor]
  const carrierInfo = CARRIERS.find((c) => c.value === carrier)!
  const regionInfo = REGIONS.find((r) => r.value === region)!

  const today = new Date()
  const dateStr = `${today.getMonth() + 1}/${String(today.getDate()).padStart(2, '0')}`

  const preview = useMemo(() => {
    if (!tpl) return { subject: '', body: '' }
    return renderTemplate(tpl, {
      carrier_name: carrier,
      carrier_code: carrierInfo.code,
      carrier_alt: carrierInfo.alt,
      region,
      region_en: regionInfo.en,
      date: dateStr,
      containers: rows,
    })
  }, [tpl, carrier, carrierInfo, region, regionInfo, dateStr, rows])

  const validContainers = rows.filter((r) => r.container_no.trim())

  const mailtoLink = useMemo(() => {
    if (!tpl) return '#'
    const to = tpl.to.split(';').map((s) => s.trim()).filter(Boolean).join(',')
    const cc = tpl.cc.split(';').map((s) => s.trim()).filter(Boolean).join(',')
    const params = new URLSearchParams()
    if (cc) params.set('cc', cc)
    params.set('subject', preview.subject)
    params.set('body', preview.body)
    return `mailto:${to}?${params.toString()}`
  }, [tpl, preview])

  const addRow = () =>
    setRows((p) => [...p, { container_no: '', container_type: '' }])
  const removeRow = (i: number) =>
    setRows((p) => (p.length > 1 ? p.filter((_, idx) => idx !== i) : p))
  const updateRow = (i: number, field: keyof ContainerRow, val: string) =>
    setRows((p) => p.map((r, idx) => (idx === i ? { ...r, [field]: val } : r)))

  const copyBody = async () => {
    await navigator.clipboard.writeText(
      `To: ${tpl?.to ?? ''}\nCc: ${tpl?.cc ?? ''}\nSubject: ${preview.subject}\n\n${preview.body}`
    )
    alert('메일 전체 내용이 클립보드에 복사되었습니다.')
  }

  if (loading) return <div className="text-gray-500 text-sm">로딩 중...</div>

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* ── 입력 영역 ─────────────────────────────────── */}
      <div className="space-y-4">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">선사</span>
              <select
                value={carrier}
                onChange={(e) => setCarrier(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
              >
                {CARRIERS.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.value}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">임대사</span>
              <select
                value={lessor}
                onChange={(e) => setLessor(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
              >
                {Object.entries(templates).map(([key, t]) => (
                  <option key={key} value={key}>
                    {key} — {t.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">반납지역</span>
              <select
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
              >
                {REGIONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.value}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-600">컨테이너</span>
              <button
                type="button"
                onClick={addRow}
                className="text-xs text-blue-600 hover:underline"
              >
                + 행 추가
              </button>
            </div>
            <div className="space-y-2">
              {rows.map((r, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    type="text"
                    placeholder="컨테이너 번호"
                    value={r.container_no}
                    onChange={(e) =>
                      updateRow(i, 'container_no', e.target.value.toUpperCase())
                    }
                    className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm font-mono"
                  />
                  <input
                    type="text"
                    placeholder="타입 (예: 45GP)"
                    value={r.container_type}
                    onChange={(e) =>
                      updateRow(i, 'container_type', e.target.value.toUpperCase())
                    }
                    className="w-32 px-2 py-1.5 border border-gray-300 rounded text-sm font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => removeRow(i)}
                    disabled={rows.length === 1}
                    className="px-2 py-1 text-red-500 hover:bg-red-50 rounded text-sm disabled:opacity-30"
                    title="삭제"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 text-xs text-gray-500 space-y-1">
          <div>
            <span className="font-medium text-gray-700">To:</span>{' '}
            {tpl?.to ?? '-'}
          </div>
          <div>
            <span className="font-medium text-gray-700">Cc:</span>{' '}
            {tpl?.cc ?? '-'}
          </div>
        </div>

        <div className="flex gap-2">
          <a
            href={mailtoLink}
            className={`flex-1 text-center px-4 py-2 rounded-md font-medium ${
              validContainers.length === 0
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-slate-800 text-white hover:bg-slate-900'
            }`}
            onClick={(e) =>
              validContainers.length === 0 ? e.preventDefault() : null
            }
          >
            📧 Outlook에서 열기
          </a>
          <button
            type="button"
            onClick={copyBody}
            className="px-4 py-2 border border-gray-300 rounded-md text-sm hover:bg-gray-50"
          >
            📋 전체 복사
          </button>
        </div>
      </div>

      {/* ── 미리보기 ──────────────────────────────────── */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 bg-slate-50 border-b border-gray-200 text-sm font-semibold text-gray-700">
          미리보기
        </div>
        <div className="p-4 space-y-3">
          <div>
            <div className="text-xs text-gray-500 mb-1">제목</div>
            <div className="bg-gray-50 px-3 py-2 rounded text-sm font-medium">
              {preview.subject || '(컨테이너를 입력하세요)'}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">본문</div>
            <pre className="bg-gray-50 px-3 py-2 rounded text-sm whitespace-pre-wrap font-sans min-h-[200px]">
              {preview.body || '(컨테이너를 입력하세요)'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}
