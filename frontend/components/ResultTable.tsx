export interface QueryResult {
  container_no: string
  available: boolean
  depot: string | null
  booking_ref: string | null
  over_caps: number | null
  close_date: string | null
  reason: string | null
}

export default function ResultTable({ results }: { results: QueryResult[] }) {
  const available = results.filter((r) => r.available).length
  const unavailable = results.length - available

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 flex items-center gap-3">
        <h2 className="font-semibold text-gray-800">조회 결과</h2>
        <span className="text-sm text-gray-500">
          총 {results.length}개 ·{' '}
          <span className="text-green-600">가능 {available}개</span> ·{' '}
          <span className="text-red-500">불가 {unavailable}개</span>
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">컨테이너 번호</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">가능여부</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">반납지(데포)</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">반납번호</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">Over Caps</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">유효기간</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600 whitespace-nowrap">불가 사유</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {results.map((r) => (
              <tr
                key={r.container_no}
                className={r.available ? 'bg-green-50' : 'bg-red-50'}
              >
                <td className="px-4 py-3 font-mono font-medium text-gray-900">
                  {r.container_no}
                </td>
                <td className="px-4 py-3">
                  {r.available ? (
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
                <td className="px-4 py-3 text-red-600 text-xs">{r.reason ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
