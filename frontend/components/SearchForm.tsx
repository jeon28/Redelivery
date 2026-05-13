'use client'
import { useState } from 'react'
import ResultTable, { type QueryResult } from './ResultTable'

const COMPANIES = ['장금상선', '흥아라인']
const LESSORS = ['TEXA']
const REGIONS = [{ label: '인천', value: 'INCHON' }]

export default function SearchForm() {
  const [company, setCompany] = useState(COMPANIES[0])
  const [lessor, setLessor] = useState(LESSORS[0])
  const [region, setRegion] = useState(REGIONS[0].value)
  const [containerText, setContainerText] = useState('')
  const [results, setResults] = useState<QueryResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const containers = containerText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
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
        body: JSON.stringify({ company, lessor, region, containers }),
      })
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      setResults(data.results)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '조회 중 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                선사
              </label>
              <select
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
              >
                {COMPANIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                임대사
              </label>
              <select
                value={lessor}
                onChange={(e) => setLessor(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
              >
                {LESSORS.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                반납 지역
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
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              컨테이너 번호{' '}
              <span className="text-gray-400 font-normal">
                (줄바꿈으로 여러 개 입력, 최대 100개)
              </span>
            </label>
            <textarea
              value={containerText}
              onChange={(e) => setContainerText(e.target.value)}
              placeholder={'ABCD1234567\nEFGH8901234'}
              rows={5}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-500 resize-y"
            />
          </div>
          {error && <p className="text-red-500 text-sm">{error}</p>}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={loading}
              className="bg-slate-800 text-white px-6 py-2 rounded-md text-sm font-medium hover:bg-slate-700 disabled:opacity-50 transition-colors"
            >
              {loading ? '조회 중...' : '조회하기'}
            </button>
          </div>
        </form>
      </div>
      {results && <ResultTable results={results} />}
    </div>
  )
}
