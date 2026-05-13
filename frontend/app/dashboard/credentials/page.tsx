import Link from 'next/link'
import { verifySession } from '@/lib/session'
import { logout } from '@/app/actions/auth'
import CredentialsManager from '@/components/CredentialsManager'

export default async function CredentialsPage() {
  await verifySession()

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
              href="/dashboard/credentials"
              className="text-white font-medium border-b-2 border-white pb-0.5"
            >
              비밀번호 관리
            </Link>
          </nav>
        </div>
        <form action={logout}>
          <button
            type="submit"
            className="text-sm text-slate-300 hover:text-white transition-colors"
          >
            로그아웃
          </button>
        </form>
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
