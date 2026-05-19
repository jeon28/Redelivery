'use client'
import { useEffect, useState } from 'react'

type Cred = { id: string; pw: string }
type Creds = Record<string, Record<string, Cred>>
type Companies = Record<string, { prefix: string; lessors: string[] }>

export default function CredentialsManager() {
  const [companies, setCompanies] = useState<Companies>({})
  const [creds, setCreds] = useState<Creds>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)

  useEffect(() => {
    fetch('/api/credentials')
      .then((r) => r.json())
      .then((data) => {
        setCompanies(data.companies ?? {})
        setCreds(data.credentials ?? {})
        setLoading(false)
      })
      .catch(() => {
        setMessage({ type: 'error', text: '자격증명을 불러오지 못했습니다.' })
        setLoading(false)
      })
  }, [])

  const update = (
    company: string,
    lessor: string,
    field: 'id' | 'pw',
    value: string
  ) => {
    setCreds((prev) => ({
      ...prev,
      [company]: {
        ...(prev[company] ?? {}),
        [lessor]: {
          ...(prev[company]?.[lessor] ?? { id: '', pw: '' }),
          [field]: value,
        },
      },
    }))
  }

  const save = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const res = await fetch('/api/credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: creds }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? '저장 실패')
      setMessage({ type: 'success', text: '저장되었습니다.' })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '저장 실패'
      setMessage({ type: 'error', text: msg })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="text-gray-500 text-sm">로딩 중...</div>
  }

  return (
    <div className="space-y-6">
      {Object.entries(companies).map(([company, cfg]) => (
        <div
          key={company}
          className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
        >
          <div className="px-6 py-3 bg-slate-50 border-b border-gray-200">
            <h2 className="font-semibold text-gray-800">{company}</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600 w-32">
                    임대사
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">
                    아이디
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">
                    비밀번호
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {cfg.lessors.map((lessor) => {
                  const c = creds[company]?.[lessor] ?? { id: '', pw: '' }
                  return (
                    <tr key={lessor}>
                      <td className="px-4 py-2 font-mono text-blue-700 font-semibold">
                        {lessor}
                      </td>
                      <td className="px-4 py-2">
                        <input
                          type="text"
                          value={c.id}
                          onChange={(e) =>
                            update(company, lessor, 'id', e.target.value)
                          }
                          className="w-full px-2 py-1 border border-gray-300 rounded text-sm font-mono"
                        />
                      </td>
                      <td className="px-4 py-2">
                        <input
                          type="text"
                          value={c.pw}
                          onChange={(e) =>
                            update(company, lessor, 'pw', e.target.value)
                          }
                          className="w-full px-2 py-1 border border-gray-300 rounded text-sm font-mono"
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="px-6 py-2 bg-slate-800 text-white rounded-md font-medium hover:bg-slate-900 disabled:opacity-50"
        >
          {saving ? '저장 중...' : '저장'}
        </button>
        <a
          href="/api/credentials/export"
          download
          className="text-sm text-slate-600 hover:text-slate-900 underline"
        >
          📥 CSV 다운로드
        </a>
        {message && (
          <span
            className={
              message.type === 'success'
                ? 'text-green-600 text-sm'
                : 'text-red-600 text-sm'
            }
          >
            {message.text}
          </span>
        )}
      </div>
    </div>
  )
}
