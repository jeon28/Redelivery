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

const PLACEHOLDERS = [
  '{carrier_name}',
  '{carrier_code}',
  '{carrier_alt}',
  '{office}',
  '{region}',
  '{region_en}',
  '{date}',
  '{first_container}',
  '{first_type}',
  '{containers}',
]

export default function EmailTemplateTab({ office }: { office: string }) {
  const [templates, setTemplates] = useState<Templates>({})
  const [selected, setSelected] = useState<string>('')
  const [draft, setDraft] = useState<Template | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)

  useEffect(() => {
    fetch(`/api/email-templates?office=${encodeURIComponent(office)}`)
      .then((r) => r.json())
      .then((d) => {
        const t: Templates = d.templates ?? {}
        setTemplates(t)
        const first = Object.keys(t)[0] ?? ''
        setSelected(first)
        setDraft(first ? t[first] : null)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [office])

  const switchLessor = (code: string) => {
    setSelected(code)
    setDraft(templates[code])
    setMessage(null)
  }

  const updateField = (field: keyof Template, value: string) => {
    if (!draft) return
    setDraft({ ...draft, [field]: value })
  }

  const save = async () => {
    if (!selected || !draft) return
    setSaving(true)
    setMessage(null)
    try {
      const res = await fetch(
        `/api/email-templates/${encodeURIComponent(selected)}?office=${encodeURIComponent(office)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            subject: draft.subject,
            body: draft.body,
          }),
        }
      )
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? '저장 실패')
      setTemplates((p) => ({ ...p, [selected]: draft }))
      setMessage({ type: 'success', text: `${office} 사무소 양식이 저장되었습니다.` })
    } catch (e: unknown) {
      setMessage({
        type: 'error',
        text: e instanceof Error ? e.message : '저장 실패',
      })
    } finally {
      setSaving(false)
    }
  }

  const restore = async () => {
    if (!selected) return
    if (
      !confirm(
        `${selected} 템플릿의 ${office} 사무소 수정사항을 비우시겠습니까? 공용 기본값으로 회귀합니다.`
      )
    )
      return
    setSaving(true)
    setMessage(null)
    try {
      const res = await fetch(
        `/api/email-templates/${encodeURIComponent(selected)}/reset?office=${encodeURIComponent(office)}`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' } }
      )
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.error ?? '복원 실패')
      }
      // 재로드
      const fresh = await fetch(
        `/api/email-templates?office=${encodeURIComponent(office)}`
      ).then((r) => r.json())
      const newTpls: Templates = fresh.templates ?? {}
      setTemplates(newTpls)
      setDraft(newTpls[selected])
      setMessage({ type: 'success', text: '기본값으로 복원되었습니다.' })
    } catch (e: unknown) {
      setMessage({
        type: 'error',
        text: e instanceof Error ? e.message : '복원 실패',
      })
    } finally {
      setSaving(false)
    }
  }

  if (loading)
    return <div className="text-gray-500 text-sm">로딩 중...</div>

  if (!draft) return <div className="text-gray-500 text-sm">템플릿 없음</div>

  return (
    <div className="space-y-4">
      {/* 임대사 탭 */}
      <div className="flex flex-wrap gap-2">
        {Object.keys(templates).map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => switchLessor(code)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
              code === selected
                ? 'bg-slate-800 text-white border-slate-800'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            }`}
          >
            {code}
          </button>
        ))}
      </div>

      {/* 편집 영역 */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_240px] gap-4">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-800">
              {draft.name || selected}
            </h3>
            <span className="text-xs text-gray-500">
              언어: {draft.language === 'ko' ? '한글' : '영문'}
            </span>
          </div>

          <label className="block text-sm">
            <span className="text-gray-600 mb-1 block">Subject Line</span>
            <input
              type="text"
              value={draft.subject}
              onChange={(e) => updateField('subject', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
            />
          </label>

          <label className="block text-sm">
            <span className="text-gray-600 mb-1 block">Email Body</span>
            <textarea
              value={draft.body}
              onChange={(e) => updateField('body', e.target.value)}
              rows={14}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
            />
          </label>

          {message && (
            <div
              className={
                message.type === 'success'
                  ? 'text-green-600 text-sm'
                  : 'text-red-600 text-sm'
              }
            >
              {message.text}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={restore}
              disabled={saving}
              className="px-4 py-2 border border-gray-300 rounded text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              ↺ Restore
            </button>
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="px-5 py-2 bg-slate-800 text-white rounded text-sm font-medium hover:bg-slate-900 disabled:opacity-50"
            >
              {saving ? '저장 중...' : '💾 Save Changes'}
            </button>
          </div>
        </div>

        {/* 변수 가이드 */}
        <div className="bg-blue-50 rounded-lg border border-blue-200 p-4 text-xs space-y-2 h-fit">
          <h4 className="font-semibold text-blue-900 mb-1">
            Available placeholders
          </h4>
          <p className="text-blue-700 mb-2">
            제목/본문 안에 아래 변수를 넣으면 발송 시 자동 치환됩니다.
          </p>
          {PLACEHOLDERS.map((p) => (
            <div key={p}>
              <code className="px-1.5 py-0.5 bg-white rounded font-mono text-blue-700">
                {p}
              </code>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
