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
type RuleEdit = {
  lessor: string
  type: 'to' | 'cc'
  value: string
}

export default function RecipientRulesTab() {
  const [templates, setTemplates] = useState<Templates>({})
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<RuleEdit | null>(null)
  const [editValue, setEditValue] = useState('')
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

  const startEdit = (lessor: string, type: 'to' | 'cc') => {
    setEditing({ lessor, type, value: templates[lessor]?.[type] ?? '' })
    setEditValue(templates[lessor]?.[type] ?? '')
    setMessage(null)
  }

  const cancelEdit = () => {
    setEditing(null)
    setEditValue('')
  }

  const saveEdit = async () => {
    if (!editing) return
    const key = `${editing.lessor}-${editing.type}`
    setSavingKey(key)
    try {
      const res = await fetch(
        `/api/email-templates/${encodeURIComponent(editing.lessor)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ [editing.type]: editValue }),
        }
      )
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? '저장 실패')
      setTemplates((p) => ({
        ...p,
        [editing.lessor]: {
          ...(p[editing.lessor] ?? {}),
          [editing.type]: editValue,
        } as Template,
      }))
      setEditing(null)
      setMessage({ type: 'success', text: '저장되었습니다.' })
    } catch (e: unknown) {
      setMessage({
        type: 'error',
        text: e instanceof Error ? e.message : '저장 실패',
      })
    } finally {
      setSavingKey(null)
    }
  }

  if (loading)
    return <div className="text-gray-500 text-sm">로딩 중...</div>

  const lessors = Object.keys(templates)

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-500">
        Define who receives emails per lessor. 임대사별로 To/Cc 수신자를 설정합니다.
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
              <th className="text-left px-4 py-2 font-medium text-gray-600 w-28">
                Lessor
              </th>
              <th className="text-left px-4 py-2 font-medium text-gray-600 w-20">
                Type
              </th>
              <th className="text-left px-4 py-2 font-medium text-gray-600">
                Email Address
              </th>
              <th className="text-right px-4 py-2 font-medium text-gray-600 w-24">
                Action
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {lessors.flatMap((lessor) => {
              const t = templates[lessor]
              return (['to', 'cc'] as const).map((type) => {
                const isEditing =
                  editing?.lessor === lessor && editing?.type === type
                const isSaving = savingKey === `${lessor}-${type}`
                const value = t[type] ?? ''
                return (
                  <tr key={`${lessor}-${type}`}>
                    <td className="px-4 py-2 font-mono font-semibold text-gray-800">
                      {lessor}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${
                          type === 'to'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-amber-100 text-amber-700'
                        }`}
                      >
                        {type.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      {isEditing ? (
                        <textarea
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          rows={2}
                          autoFocus
                          className="w-full border border-gray-300 rounded px-2 py-1 text-xs font-mono"
                        />
                      ) : (
                        <div className="text-xs text-gray-600 font-mono break-all">
                          {value || (
                            <span className="text-gray-400 italic">(비어있음)</span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {isEditing ? (
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            onClick={saveEdit}
                            disabled={isSaving}
                            className="px-2 py-1 bg-slate-800 text-white text-xs rounded hover:bg-slate-700 disabled:opacity-50"
                          >
                            {isSaving ? '저장중' : '저장'}
                          </button>
                          <button
                            type="button"
                            onClick={cancelEdit}
                            className="px-2 py-1 border border-gray-300 text-xs rounded hover:bg-gray-50"
                          >
                            취소
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => startEdit(lessor, type)}
                          className="text-blue-600 hover:underline text-xs"
                        >
                          ✏️ 편집
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
