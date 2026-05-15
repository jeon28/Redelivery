import Link from 'next/link'
import { verifySession } from '@/lib/session'
import { logout } from '@/app/actions/auth'
import EmailSettingTabs from '@/components/EmailSettingTabs'
import HeaderOfficeSelector from '@/components/HeaderOfficeSelector'

export default async function EmailSettingPage() {
  const { office } = await verifySession()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-slate-800 text-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <h1 className="text-lg font-semibold">반납컨테이너 조회 시스템</h1>
          <nav className="flex items-center gap-4 text-sm">
            <Link
              href="/dashboard"
              className="text-slate-300 hover:text-white transition-colors"
            >
              조회
            </Link>
            <Link
              href="/dashboard/email-setting"
              className="text-white font-medium border-b-2 border-white pb-0.5"
            >
              Email Setting
            </Link>
            <Link
              href="/dashboard/credentials"
              className="text-slate-300 hover:text-white transition-colors"
            >
              비밀번호 관리
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-6">
          <HeaderOfficeSelector office={office} />
          <form action={logout}>
            <button
              type="submit"
              className="text-sm text-slate-300 hover:text-white transition-colors"
            >
              로그아웃
            </button>
          </form>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-4">
          <h2 className="text-xl font-semibold text-gray-800">Email Setting</h2>
          <p className="text-sm text-gray-500 mt-1">
            현재 편집 중: <span className="font-semibold">{office} 사무소</span>
            {' · '}수정 사항은 이 사무소 계정에만 적용됩니다.
          </p>
        </div>

        <EmailSettingTabs office={office} />
      </main>
    </div>
  )
}
