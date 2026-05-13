import Link from 'next/link'
import { redirect } from 'next/navigation'
import { verifySession, verifyCredentialsUnlock } from '@/lib/session'
import { logout } from '@/app/actions/auth'
import UnlockForm from '@/components/UnlockForm'

export default async function CredentialsUnlockPage() {
  await verifySession()

  // 이미 잠금 해제된 상태라면 바로 관리 페이지로
  if (await verifyCredentialsUnlock()) {
    redirect('/dashboard/credentials')
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
              href="/dashboard/email-request"
              className="text-slate-300 hover:text-white transition-colors"
            >
              메일 반납
            </Link>
            <Link
              href="/dashboard/credentials/unlock"
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
      <main className="max-w-5xl mx-auto px-6 py-16">
        <UnlockForm />
      </main>
    </div>
  )
}
