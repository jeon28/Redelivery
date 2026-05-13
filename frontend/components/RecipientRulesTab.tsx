'use client'
import { useEffect, useState } from 'react'

type Template = {
  name: string
  language: string
  to: string
  cc: string
  subject: string
  body: string
}
type Templates = Record<string, Template>

export default function RecipientRulesTab() {
  const [templates, setTemplates] = useState<Templates>({})
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<string | null>(null)  // 편집중 임대사
  const [editTo, setEditTo] = useState('')
  const [editCc, setEditCc] = useState('')
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [message, setMessage] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)

  useEffect(() => {
    fetch('/api/email-templates')
      .then((r) => r.json())
      .then((d) => {
        setTemplates(d.templates ?? {})
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const startEdit = (lessor: string) => {
    const t = templates[lessor]
    setEditing(lessor)
    setEditTo(t?.to ?? '')
    setEditCc(t?.cc ?? '')
    setMessage(null)
  }

  const cancelEdit = () => {
    setEditing(null)
    setEditTo('')
    setEditCc('')
  }

  const saveEdit = async () => {
    if (!editing) return
    setSavingKey(editing)
    try {
      const res = await fetch(
        `/api/email-templates/${encodeURIComponent(editing)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ to: editTo, cc: editCc }),
        }
      )
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? '저장 실패')
      setTemplates((p) => ({
        ...p,
        [editing]: {
          ...(p[editing] ?? {}),
          to: editTo,
          cc: editCc,
        } as Template,
      }))
      setEditing(null)
      setMessage({ type: 'success', text: `${editing} 저장되었습니다.` })
    } catch (e: unknown) {
      setMessage({
        type: 'error',
        text: e instanceof Error ? e.message : '저장 실패',
      })
    } finally {
      setSavingKey(null)
    }
  }

  if (loading) return <div className="text-gray-500 text-sm">로딩 중...</div>

  const lessors = Object.keys(templates)

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-500">
        Define who receives emails per lessor. 임대사별 To/Cc 수신자를 설정합니다.
      </p>

      {message && (
        <div
          className={`text-sm px-3 py-2 rounded ${
            message.type === 'success'
              ? 'bg-green-50 text-green-700 border border-green-200'
              : 'bg-red-50 text-red-700 border border-red-200'
          }`}
        >
          {message.text}
        </div>
      )}

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-28">
                Lessor
              </th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">
                Recipients
              </th>
              <th className="text-right px-4 py-3 font-medium text-gray-600 w-32">
                Action
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {lessors.map((lessor) => {
              const t = templates[lessor]
              const isEditing = editing === lessor
              const isSaving = savingKey === lessor

              return (
                <tr key={lessor} className={isEditing ? 'bg-blue-50' : ''}>
                  <td className="px-4 py-3 align-top font-mono font-semibold text-gray-800">
                    {lessor}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <div className="space-y-2">
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-700">
                              TO
                            </span>
                            <span className="text-xs text-gray-400">
                              세미콜론(;)으로 구분
                            </span>
                          </div>
                          <textarea
                            value={editTo}
                            onChange={(e) => setEditTo(e.target.value)}
                            rows={2}
                            autoFocus
                            className="w-full border border-gray-300 rounded px-2 py-1 text-xs font-mono"
                          />
                        </div>
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-700">
                              CC
                            </span>
                          </div>
                          <textarea
                            value={editCc}
                            onChange={(e) => setEditCc(e.target.value)}
                            rows={2}
                            className="w-full border border-gray-300 rounded px-2 py-1 text-xs font-mono"
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        <div className="flex items-start gap-2">
                          <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-700 shrink-0 mt-0.5">
                            TO
                          </span>
                          <div className="text-xs text-gray-600 font-mono break-all">
                            {t.to || (
                              <span className="text-gray-400 italic">(비어있음)</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-start gap-2">
                          <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-700 shrink-0 mt-0.5">
                            CC
                          </span>
                          <div className="text-xs text-gray-600 font-mono break-all">
                            {t.cc || (
                              <span className="text-gray-400 italic">(비어있음)</span>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 align-top text-right">
                    {isEditing ? (
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          onClick={saveEdit}
                          disabled={isSaving}
                          className="px-3 py-1 bg-slate-800 text-white text-xs rounded hover:bg-slate-700 disabled:opacity-50"
                        >
                          {isSaving ? '저장중...' : '저장'}
                        </button>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          disabled={isSaving}
                          className="px-3 py-1 border border-gray-300 text-xs rounded hover:bg-gray-50 disabled:opacity-50"
                        >
                          취소
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => startEdit(lessor)}
                        className="text-blue-600 hover:underline text-xs"
                      >
                        ✏️ 편집
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
