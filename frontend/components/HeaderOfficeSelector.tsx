// 로그인한 사무소를 헤더에 표시 전용으로 노출.
// 사무소 변경은 로그아웃 후 다른 계정으로 재로그인해야 가능.
export default function HeaderOfficeSelector({ office }: { office: string }) {
  return (
    <span className="flex items-center gap-2 text-sm text-slate-300">
      <span>사무소</span>
      <span className="bg-slate-700 text-white border border-slate-600 rounded px-2 py-1 text-sm font-medium">
        {office}
      </span>
    </span>
  )
}
