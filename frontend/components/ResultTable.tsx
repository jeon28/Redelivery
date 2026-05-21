'use client'
import { useMemo, useState } from 'react'

export interface QueryResult {
  container_no: string
  available: boolean
  depot: string | null
  booking_ref: string | null
  over_caps: number | null
  close_date: string | null
  reason: string | null
  status?: string | null
  completed_date?: string | null
}

interface CancelApiResult {
  container_no: string
  booking_ref: string
  cancelled: boolean
  reason: string | null
}

interface Props {
  results: QueryResult[]
  company?: string
  lessor?: string
  region?: string
  onResultsChange?: (results: QueryResult[]) => void
}

export default function ResultTable({
  results,
  company,
  lessor,
  region,
  onResultsChange,
}: Props) {
  const available = results.filter((r) => r.available).length
  const unavailable = results.length - available

  // precleared 판정 — reason 에 'precleared' 포함된 가능 행.
  // 이 행은 booking_ref 가 비어있지만 사이트에 PPR 이 이미 존재. UI 에서 "완료" 표시.
  function isPrecleared(r: QueryResult): boolean {
    return (
      r.available &&
      !!r.reason &&
      r.reason.toLowerCase().includes('precleared')
    )
  }

  // 취소 가능 행 = available && booking_ref 있음 (precleared 는 booking_ref 없어서 제외)
  const cancellableKeys = useMemo(
    () =>
      new Set(
        results
          .filter((r) => r.available && r.booking_ref)
          .map((r) => r.container_no)
      ),
    [results]
  )

  // 체크박스 활성 행 = available 인 모든 행 (precleared 포함, Status 조회·취소 공용 선택).
  const selectableKeys = useMemo(
    () =>
      new Set(
        results.filter((r) => r.available).map((r) => r.container_no)
      ),
    [results]
  )

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [confirming, setConfirming] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState('')
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusError, setStatusError] = useState('')

  const canCancel = Boolean(
    company && lessor && region && onResultsChange
  )
  const canStatusLookup = Boolean(company && lessor && onResultsChange)

  // results 가 새로 들어오면 선택 초기화 (key가 더 이상 유효하지 않은 경우)
  const validSelected = useMemo(() => {
    const s = new Set<string>()
    for (const k of selected) {
      if (selectableKeys.has(k)) s.add(k)
    }
    return s
  }, [selected, selectableKeys])

  // 취소 대상 = 선택된 행 중 cancellableKeys 에 속한 것
  const cancellableSelected = useMemo(() => {
    const s = new Set<string>()
    for (const k of validSelected) {
      if (cancellableKeys.has(k)) s.add(k)
    }
    return s
  }, [validSelected, cancellableKeys])

  const allChecked =
    selectableKeys.size > 0 && validSelected.size === selectableKeys.size
  const someChecked =
    validSelected.size > 0 && validSelected.size < selectableKeys.size

  function toggleOne(container_no: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(container_no)) next.delete(container_no)
      else next.add(container_no)
      return next
    })
  }

  function toggleAll() {
    if (allChecked) {
      setSelected(new Set())
    } else {
      setSelected(new Set(selectableKeys))
    }
  }

  function openConfirm() {
    if (cancellableSelected.size === 0) return
    setCancelError('')
    setConfirming(true)
  }

  function closeConfirm() {
    if (cancelling) return
    setConfirming(false)
  }

  // 모달 문구 생성
  const confirmMessage = useMemo(() => {
    const items = results
      .filter((r) => cancellableSelected.has(r.container_no) && r.booking_ref)
      .map((r) => ({ container_no: r.container_no, booking_ref: r.booking_ref! }))
    const refs = Array.from(new Set(items.map((i) => i.booking_ref)))
    if (items.length === 0) return ''
    if (items.length === 1) {
      return `승인번호 ${refs[0]} 을 취소합니다. 진행할까요?`
    }
    if (refs.length === 1) {
      return `승인번호 ${refs[0]} 의 컨테이너 ${items.length}개를 취소합니다. 진행할까요?`
    }
    return `승인번호 ${refs[0]} 외 ${refs.length - 1}건의 컨테이너 ${items.length}개를 취소합니다. 진행할까요?`
  }, [results, cancellableSelected])

  async function confirmCancel() {
    if (!canCancel) return
    const items = results
      .filter((r) => cancellableSelected.has(r.container_no) && r.booking_ref)
      .map((r) => ({ container_no: r.container_no, booking_ref: r.booking_ref! }))
    if (items.length === 0) return

    setCancelling(true)
    setCancelError('')
    try {
      const res = await fetch('/api/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company, lessor, region, items }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || data.error || '취소 요청 실패')
      }
      const cancelResults = (data.results ?? []) as CancelApiResult[]
      applyCancelResults(cancelResults)
      setSelected(new Set())
      setConfirming(false)
    } catch (err: unknown) {
      setCancelError(
        err instanceof Error ? err.message : '취소 중 오류가 발생했습니다.'
      )
      setConfirming(false)
    } finally {
      setCancelling(false)
    }
  }

  function applyCancelResults(cancelResults: CancelApiResult[]) {
    if (!onResultsChange) return
    const byContainer = new Map<string, CancelApiResult>()
    for (const c of cancelResults) byContainer.set(c.container_no, c)

    const next = results.map((r) => {
      const c = byContainer.get(r.container_no)
      if (!c) return r
      if (c.cancelled) {
        return {
          ...r,
          available: false,
          booking_ref: null,
          depot: null,
          over_caps: null,
          close_date: null,
          reason: '취소 완료',
        }
      }
      return { ...r, reason: c.reason ?? '취소 실패' }
    })
    onResultsChange(next)
  }

  // 선택된 행만 Status 탭으로 단독 조회 (Stage 1 S2 안정화 적용 후 정상 동작).
  // precleared 행의 Expiry Date / Depot Name 등 enrichment 용도.
  async function runStatusLookup() {
    if (!canStatusLookup || validSelected.size === 0) return
    const containers = Array.from(validSelected)
    setStatusLoading(true)
    setStatusError('')
    try {
      const res = await fetch('/api/status-detail', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company, lessor, containers }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || data.error || 'Status 조회 실패')
      }
      const sd = (data.results ?? []) as QueryResult[]
      if (onResultsChange) {
        const byContainer = new Map<string, QueryResult>()
        for (const r of sd) byContainer.set(r.container_no, r)
        const next = results.map((r) => {
          const updated = byContainer.get(r.container_no)
          if (!updated) return r
          // booking_ref / depot / close_date / reason 갱신. 빈 값은 기존 유지.
          return {
            ...r,
            booking_ref: updated.booking_ref ?? r.booking_ref,
            depot: updated.depot ?? r.depot,
            over_caps: updated.over_caps ?? r.over_caps,
            close_date: updated.close_date ?? r.close_date,
            reason: updated.reason ?? r.reason,
            available: updated.available,
          }
        })
        onResultsChange(next)
      }
    } catch (err: unknown) {
      setStatusError(
        err instanceof Error ? err.message : 'Status 조회 중 오류가 발생했습니다.'
      )
    } finally {
      setStatusLoading(false)
    }
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold text-gray-800">조회 결과</h2>
          <span className="text-sm text-gray-500">
            총 {results.length}개 ·{' '}
            <span className="text-green-600">가능 {available}개</span> ·{' '}
            <span className="text-red-500">불가 {unavailable}개</span>
            {canCancel && validSelected.size > 0 && (
              <>
                {' · '}
                <span className="text-slate-700 font-medium">
                  {validSelected.size}개 선택됨
                </span>
              </>
            )}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {canStatusLookup && selectableKeys.size > 0 && (
            <button
              type="button"
              onClick={runStatusLookup}
              disabled={validSelected.size === 0 || statusLoading}
              className="bg-slate-700 text-white px-4 py-1.5 rounded-md text-sm font-medium hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              title="선택된 행만 Status 탭으로 별도 조회"
            >
              {statusLoading ? '조회 중...' : '선택 항목 Status 조회'}
            </button>
          )}
          {canCancel && cancellableKeys.size > 0 && (
            <button
              type="button"
              onClick={openConfirm}
              disabled={cancellableSelected.size === 0 || cancelling}
              className="bg-red-600 text-white px-4 py-1.5 rounded-md text-sm font-medium hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              title={cancellableSelected.size === 0 ? '취소 가능한 행을 선택하세요 (반납번호 있는 행)' : undefined}
            >
              선택 항목 취소
            </button>
          )}
        </div>
      </div>

      {(cancelError || statusError) && (
        <div className="px-6 py-2 text-sm text-red-600 bg-red-50 border-b border-red-100">
          {cancelError || statusError}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {canCancel && (
                <th className="px-3 py-3 w-10">
                  <input
                    type="checkbox"
                    aria-label="전체 선택"
                    checked={allChecked}
                    ref={(el) => {
                      if (el) el.indeterminate = someChecked
                    }}
                    onChange={toggleAll}
                    disabled={selectableKeys.size === 0}
                  />
                </th>
              )}
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">컨테이너 번호</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">가능여부</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">반납지(데포)</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">반납번호</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Over Caps</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">유효기간</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">조회 결과</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {results.map((r) => {
              const checkable = selectableKeys.has(r.container_no)
              const checked = validSelected.has(r.container_no)
              const precleared = isPrecleared(r)
              const completed = r.status === 'completed'
              const numberError = r.status === 'number_error'
              const rowBg = completed
                ? 'bg-gray-100'
                : numberError
                ? 'bg-amber-50'
                : precleared
                ? 'bg-blue-50'
                : r.available
                ? 'bg-green-50'
                : 'bg-red-50'
              return (
                <tr key={r.container_no} className={rowBg}>
                  {canCancel && (
                    <td className="px-3 py-3 w-10">
                      <input
                        type="checkbox"
                        aria-label={`${r.container_no} 선택`}
                        checked={checked}
                        disabled={!checkable}
                        onChange={() => toggleOne(r.container_no)}
                        title={
                          checkable
                            ? '선택 (Status 조회 또는 취소)'
                            : '선택할 수 없는 행입니다'
                        }
                      />
                    </td>
                  )}
                  <td className="px-4 py-3 font-mono font-medium text-gray-900">
                    {r.container_no}
                  </td>
                  <td className="px-4 py-3">
                    {completed ? (
                      <span className="text-gray-700 font-medium">🏁 반납완료</span>
                    ) : numberError ? (
                      <span className="text-amber-700 font-medium">🔢 넘버오류</span>
                    ) : precleared ? (
                      <span className="text-blue-700 font-medium">🟢 완료</span>
                    ) : r.available ? (
                      <span className="text-green-700 font-medium">✅ 가능</span>
                    ) : (
                      <span className="text-red-600 font-medium">❌ 불가</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-700">{r.depot ?? '-'}</td>
                  <td className="px-4 py-3 font-mono text-blue-700 font-medium">
                    {r.booking_ref ?? '-'}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{r.over_caps ?? '-'}</td>
                  <td className="px-4 py-3 text-gray-600">{r.close_date ?? '-'}</td>
                  <td className={`px-4 py-3 text-xs ${
                    r.available || completed
                      ? 'text-gray-600'
                      : numberError
                      ? 'text-amber-700'
                      : 'text-red-600'
                  }`}>
                    {r.reason ?? '-'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {confirming && (
        <div
          className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center px-4"
          onClick={closeConfirm}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="bg-white rounded-lg shadow-xl max-w-md w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-semibold text-gray-900 mb-3">
              반납 취소 확인
            </h3>
            <p className="text-sm text-gray-700 whitespace-pre-line">
              {confirmMessage}
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={closeConfirm}
                disabled={cancelling}
                className="px-4 py-1.5 rounded-md text-sm border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                취소
              </button>
              <button
                type="button"
                onClick={confirmCancel}
                disabled={cancelling}
                className="px-4 py-1.5 rounded-md text-sm bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
              >
                {cancelling ? '처리 중...' : '확인'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
