'use client'
import { useEffect, useState } from 'react'

const OFFICES = ['본사', '부산', '인천', '평택', '광양', '울산']

const LS_KEY = 'redelivery_ui_state_v1'

function loadOffice(): string {
  if (typeof window === 'undefined') return '인천'
  try {
    const s = JSON.parse(localStorage.getItem(LS_KEY) ?? '{}')
    return OFFICES.includes(s.office) ? s.office : '인천'
  } catch {
    return '인천'
  }
}

function saveOffice(office: string) {
  if (typeof window === 'undefined') return
  try {
    const prev = JSON.parse(localStorage.getItem(LS_KEY) ?? '{}')
    localStorage.setItem(LS_KEY, JSON.stringify({ ...prev, office }))
  } catch {}
}

// 사무소 선택 헤더용 드롭다운.
// SearchForm 등 다른 컴포넌트와는 localStorage + `office-change` 커스텀 이벤트로 동기화.
// 추후 멀티유저 도입 시 사용자 프로필에서 자동 지정 가능하도록 분리.
export default function HeaderOfficeSelector() {
  const [office, setOffice] = useState('인천')

  useEffect(() => {
    setOffice(loadOffice())
  }, [])

  const change = (v: string) => {
    setOffice(v)
    saveOffice(v)
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('office-change', { detail: v }))
    }
  }

  return (
    <label className="flex items-center gap-2 text-sm text-slate-300">
      <span>사무소</span>
      <select
        value={office}
        onChange={(e) => change(e.target.value)}
        className="bg-slate-700 text-white border border-slate-600 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
      >
        {OFFICES.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  )
}
