'use client'
import { useEffect, useState } from 'react'

export type Depot = {
  code: string
  name: string
  label: string
}

type Props = {
  open: boolean
  company: string
  region: string
  regionLabel: string  // 한글 region (예: '부산')
  value: string  // 현재 선택된 depot label
  onSelect: (label: string) => void
  onClose: () => void
}

export default function DepotPickerModal({
  open,
  company,
  region,
  regionLabel,
  value,
  onSelect,
  onClose,
}: Props) {
  const [depots, setDepots] = useState<Depot[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [picked, setPicked] = useState(value)

  useEffect(() => {
    if (!open) return
    setPicked(value)
    setError('')
    setLoading(true)
    const qs = new URLSearchParams({ company, region }).toString()
    fetch(`/api/flor/depots?${qs}`)
      .then((r) => r.json())
      .then((d) => {
        setDepots(d.depots ?? [])
        setLoading(false)
      })
      .catch(() => {
        setError('depot 목록을 불러오지 못했습니다.')
        setLoading(false)
      })
  }, [open, company, region, value])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
        <div className="px-5 py-4 border-b border-gray-200">
          <h3 className="font-semibold text-gray-800">
            {regionLabel} 반납CY를 선택하세요
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            FLOR은 Depot마다 수용 가능한 컨테이너 타입이 달라 직접 선택이 필요합니다.
          </p>
        </div>

        <div className="px-5 py-4 max-h-80 overflow-y-auto">
          {loading && (
            <div className="text-sm text-gray-500">로딩 중...</div>
          )}
          {error && (
            <div className="text-sm text-red-600">{error}</div>
          )}
          {!loading && !error && depots.length === 0 && (
            <div className="text-sm text-gray-500">
              이 지역의 등록된 Depot이 없습니다. 운영자에게 문의하세요.
            </div>
          )}
          {!loading && !error && depots.length > 0 && (
            <ul className="space-y-2">
              {depots.map((d) => (
                <li key={d.code || d.label}>
                  <label className="flex items-start gap-2 cursor-pointer p-2 rounded hover:bg-gray-50">
                    <input
                      type="radio"
                      name="depot"
                      value={d.label}
                      checked={picked === d.label}
                      onChange={() => setPicked(d.label)}
                      className="mt-1"
                    />
                    <span className="text-sm">
                      <span className="font-mono text-gray-700">({d.code})</span>{' '}
                      <span className="text-gray-800">{d.name}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="px-5 py-3 border-t border-gray-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 border border-gray-300 rounded text-sm text-gray-700 hover:bg-gray-50"
          >
            취소
          </button>
          <button
            type="button"
            disabled={!picked}
            onClick={() => {
              onSelect(picked)
              onClose()
            }}
            className="px-5 py-2 bg-slate-800 text-white rounded text-sm font-medium hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            확인
          </button>
        </div>
      </div>
    </div>
  )
}
