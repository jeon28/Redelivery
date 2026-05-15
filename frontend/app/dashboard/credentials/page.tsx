import Link from 'next/link'
import { redirect } from 'next/navigation'
import { verifySession, verifyCredentialsUnlock } from '@/lib/session'
import { logout, lockCredentials } from '@/app/actions/auth'
import CredentialsManager from '@/components/CredentialsManager'
import HeaderOfficeSelector from '@/components/HeaderOfficeSelector'

export default async function CredentialsPage() {
  const { office } = await verifySession()

  // 잠금 해제 안 된 상태라면 PIN 입력 페이지로 이동
  if (!(await verifyCredentialsUnlock())) {
    redirect('/dashboard/credentials/unlock')
  }

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
              className="text-slate-300 hover:text-white transition-colors"
            >
              Email Setting
            </Link>
            <Link
              href="/dashboard/credentials"
              className="text-white font-medium border-b-2 border-white pb-0.5"
            >
              비밀번호 관리
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-6">
          <HeaderOfficeSelector office={office} />
          <form action={lockCredentials}>
            <button
              type="submit"
              className="text-sm text-slate-300 hover:text-white transition-colors"
            >
              🔒 잠금
            </button>
          </form>
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
      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="mb-4">
          <h2 className="text-xl font-semibold text-gray-800">비밀번호 관리</h2>
          <p className="text-sm text-gray-500 mt-1">
            임대사 계정의 아이디/비밀번호를 변경하면 즉시 시스템 전체에
            반영됩니다.
          </p>
        </div>
        <CredentialsManager />
      </main>
    </div>
  )
}
