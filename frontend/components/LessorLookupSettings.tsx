'use client'
import { useEffect, useMemo, useState } from 'react'

// ─────────────────────────────────────────────────────────────
// 임대사 판별 설정: 반납 대장 업로드 + 접두어 표 편집
// ─────────────────────────────────────────────────────────────

type Summary = {
  uploaded_at: string | null
  filename: string | null
  sheets: { name: string; rows: number }[]
  count: number
  by_lessor: Record<string, number>
}

type Row = { prefix: string; lessor: string }

function toRows(mapping: Record<string, string>): Row[] {
  return Object.entries(mapping)
    .map(([prefix, lessor]) => ({ prefix, lessor }))
    .sort((a, b) => a.lessor.localeCompare(b.lessor) || a.prefix.localeCompare(b.prefix))
}

async function readJson(res: Response) {
  const data = await res.json()
  if (!res.ok || data.error || data.detail) {
    throw new Error(data.detail || data.error || `HTTP ${res.status}`)
  }
  return data
}

export default function LessorLookupSettings() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState('')

  const [rows, setRows] = useState<Row[]>([])
  const [defaults, setDefaults] = useState<Record<string, string>>({})
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [mapMsg, setMapMsg] = useState('')
  const [filter, setFilter] = useState('')

  useEffect(() => {
    fetch('/api/lease-inventory')
      .then(readJson)
      .then(setSummary)
      .catch((e) => setUploadMsg(`⚠️ 대장 정보 로드 실패: ${e.message}`))
    fetch('/api/prefix-map')
      .then(readJson)
      .then((d) => {
        setRows(toRows(d.mapping))
        setDefaults(d.defaults)
      })
      .catch((e) => setMapMsg(`⚠️ 접두어 표 로드 실패: ${e.message}`))
  }, [])

  async function handleUpload(file: File) {
    setUploading(true)
    setUploadMsg('')
    try {
      const res = await fetch('/api/lease-inventory', {
        method: 'POST',
        headers: { 'X-Filename': encodeURIComponent(file.name) },
        body: file,
      })
      const data = await readJson(res)
      setSummary(data)
      setUploadMsg(`✔ 업로드 완료 — 컨테이너 ${data.count.toLocaleString()}개`)
    } catch (e: unknown) {
      setUploadMsg(`⚠️ 업로드 실패: ${e instanceof Error ? e.message : e}`)
    } finally {
      setUploading(false)
    }
  }

  function updateRow(i: number, patch: Partial<Row>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
    setDirty(true)
  }

  async function saveMap(mapping: Record<string, string>) {
    setSaving(true)
    setMapMsg('')
    try {
      const res = await fetch('/api/prefix-map', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mapping }),
      })
      const data = await readJson(res)
      setRows(toRows(data.mapping))
      setDirty(false)
      setMapMsg('✔ 저장되었습니다.')
    } catch (e: unknown) {
      setMapMsg(`⚠️ 저장 실패: ${e instanceof Error ? e.message : e}`)
    } finally {
      setSaving(false)
    }
  }

  const visible = useMemo(() => {
    const f = filter.trim().toUpperCase()
    return rows
      .map((r, i) => ({ ...r, i }))
      .filter((r) => !f || r.prefix.includes(f) || r.lessor.includes(f))
  }, [rows, filter])

  const inputCls =
    'border border-gray-300 rounded px-2 py-1 text-sm font-mono uppercase w-24 focus:outline-none focus:ring-2 focus:ring-slate-500'

  return (
    <div className="space-y-6">
      {/* 반납 대장 */}
      <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-800">① 반납 대장 (우선 판별)</h3>
          <label
            className={`px-4 py-2 rounded-md text-sm font-medium cursor-pointer ${
              uploading ? 'bg-gray-200 text-gray-600' : 'bg-slate-800 text-white hover:bg-slate-700'
            }`}
          >
            {uploading ? '업로드 중...' : '📤 엑셀 업로드'}
            <input
              type="file"
              accept=".xlsx"
              className="hidden"
              disabled={uploading}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleUpload(f)
                e.target.value = ''
              }}
            />
          </label>
        </div>
        <p className="text-sm text-gray-700">
          월별 반납 대장 엑셀을 그대로 올리세요. <code>Container No</code>·<code>Lessor</code> 머리행이
          있는 시트를 모두 읽고, 올릴 때마다 전체가 교체됩니다.
        </p>
        {summary && summary.count > 0 ? (
          <div className="text-sm text-gray-800 space-y-2">
            <p>
              <b>{summary.filename ?? '(파일명 없음)'}</b> · 컨테이너{' '}
              <b>{summary.count.toLocaleString()}</b>개 · 시트 {summary.sheets.length}개 ·{' '}
              {summary.uploaded_at && new Date(summary.uploaded_at).toLocaleString('ko-KR')}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(summary.by_lessor).map(([l, n]) => (
                <span key={l} className="text-xs bg-gray-100 border border-gray-200 rounded px-2 py-0.5">
                  {l} {n}
                </span>
              ))}
            </div>
          </div>
        ) : (
          summary && <p className="text-sm text-amber-700">아직 업로드된 대장이 없습니다. 접두어 표로만 판별합니다.</p>
        )}
        {uploadMsg && <p className="text-sm">{uploadMsg}</p>}
      </section>

      {/* 접두어 표 */}
      <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-semibold text-gray-800">② 접두어 표 (대장에 없는 번호)</h3>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="검색 (예: TEMU, FLOR)"
            className="border border-gray-300 rounded px-2 py-1 text-sm w-48"
          />
        </div>
        <p className="text-sm text-gray-700">
          임대사 칸은 시스템 코드로 입력합니다 (TEXA, TRIT, FLOR, GESE, GOLD, BCON, CARL, CAIC, BLUE,
          GVCC, MWSC …). 등록되지 않은 임대사도 적어 두면 통합 조회에서 &quot;미지원&quot;으로 안내됩니다.
        </p>
        <div className="max-h-[480px] overflow-y-auto border border-gray-200 rounded">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0">
              <tr className="text-left text-gray-700">
                <th className="px-3 py-2">접두어</th>
                <th className="px-3 py-2">임대사</th>
                <th className="px-3 py-2 w-16"></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.i} className="border-t border-gray-100">
                  <td className="px-3 py-1.5">
                    <input
                      value={r.prefix}
                      maxLength={4}
                      onChange={(e) => updateRow(r.i, { prefix: e.target.value.toUpperCase() })}
                      className={inputCls}
                    />
                  </td>
                  <td className="px-3 py-1.5">
                    <input
                      value={r.lessor}
                      maxLength={4}
                      onChange={(e) => updateRow(r.i, { lessor: e.target.value.toUpperCase() })}
                      className={inputCls}
                    />
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        setRows((prev) => prev.filter((_, idx) => idx !== r.i))
                        setDirty(true)
                      }}
                      className="text-gray-500 hover:text-red-600"
                      title="삭제"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              setFilter('')
              setRows((prev) => [{ prefix: '', lessor: '' }, ...prev])
              setDirty(true)
            }}
            className="text-sm text-slate-800 border border-slate-300 rounded px-3 py-1.5 hover:bg-slate-50"
          >
            ＋ 행 추가
          </button>
          <div className="flex items-center gap-2">
            {mapMsg && <span className="text-sm">{mapMsg}</span>}
            <button
              type="button"
              disabled={saving}
              onClick={() => {
                if (confirm('접두어 표를 기본값으로 되돌릴까요? 직접 수정한 내용은 사라집니다.'))
                  saveMap(defaults)
              }}
              className="text-sm text-slate-800 border border-slate-300 rounded px-3 py-1.5 hover:bg-slate-50 disabled:opacity-50"
            >
              ↺ 기본값 복원
            </button>
            <button
              type="button"
              disabled={saving || !dirty}
              onClick={() =>
                saveMap(Object.fromEntries(rows.filter((r) => r.prefix && r.lessor).map((r) => [r.prefix, r.lessor])))
              }
              className="text-sm bg-slate-800 text-white rounded px-4 py-1.5 hover:bg-slate-700 disabled:opacity-50"
            >
              {saving ? '저장 중...' : '💾 저장'}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
