import Link from 'next/link'
import type { ReactNode } from 'react'
import { logout } from '@/app/actions/auth'
import HeaderOfficeSelector from '@/components/HeaderOfficeSelector'

const MENU = [
  { key: 'single', href: '/dashboard', label: '통합 조회' },
  { key: 'multi', href: '/dashboard/multi', label: '다중 조회' },
  { key: 'lookup', href: '/dashboard/lessor-lookup', label: '임대사 판별' },
  { key: 'email', href: '/dashboard/email-setting', label: 'Email Setting' },
  { key: 'credentials', href: '/dashboard/credentials', label: '비밀번호 관리' },
] as const

export type MenuKey = (typeof MENU)[number]['key']

export default function DashboardHeader({
  office,
  active,
  actions,
}: {
  office: string
  active: MenuKey
  // 로그아웃 앞에 붙는 페이지 전용 버튼 (예: 비밀번호 관리의 🔒 잠금)
  actions?: ReactNode
}) {
  return (
    <header className="bg-slate-800 text-white px-6 py-4 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <h1 className="text-lg font-semibold">반납컨테이너 조회 시스템</h1>
        <nav className="flex items-center gap-4 text-sm">
          {MENU.map((m) => (
            <Link
              key={m.key}
              href={m.href}
              className={
                m.key === active
                  ? 'text-white font-medium border-b-2 border-white pb-0.5'
                  : 'text-slate-100 hover:text-white transition-colors'
              }
            >
              {m.label}
            </Link>
          ))}
        </nav>
      </div>
      <div className="flex items-center gap-6">
        <HeaderOfficeSelector office={office} />
        {actions}
        <form action={logout}>
          <button
            type="submit"
            className="text-sm text-slate-100 hover:text-white transition-colors"
          >
            로그아웃
          </button>
        </form>
      </div>
    </header>
  )
}
