import Link from 'next/link'
import { verifySession } from '@/lib/session'
import { logout } from '@/app/actions/auth'
import EmailRequestForm from '@/components/EmailRequestForm'

export default async function EmailRequestPage() {
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
              href="/dashboard/email-request"
              className="text-white font-medium border-b-2 border-white pb-0.5"
            >
              메일 반납
            </Link>
            <Link
              href="/dashboard/credentials"
              className="text-slate-300 hover:text-white transition-colors"
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
      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-4">
          <h2 className="text-xl font-semibold text-gray-800">메일 반납 요청</h2>
          <p className="text-sm text-gray-500 mt-1">
            컨테이너 번호와 반납지를 입력하면 임대사별 양식에 맞춰 메일이
            생성됩니다. <span className="font-medium">Outlook에서 열기</span>를
            클릭하면 자동으로 양식이 입력된 상태로 Outlook이 열립니다.
          </p>
        </div>
        <EmailRequestForm />
      </main>
    </div>
  )
}
