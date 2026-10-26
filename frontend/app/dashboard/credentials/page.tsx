import { redirect } from 'next/navigation'
import { verifySession, verifyCredentialsUnlock } from '@/lib/session'
import { lockCredentials } from '@/app/actions/auth'
import CredentialsManager from '@/components/CredentialsManager'
import DashboardHeader from '@/components/DashboardHeader'

export default async function CredentialsPage() {
  const { office } = await verifySession()

  // 잠금 해제 안 된 상태라면 PIN 입력 페이지로 이동
  if (!(await verifyCredentialsUnlock())) {
    redirect('/dashboard/credentials/unlock')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <DashboardHeader
        office={office}
        active="credentials"
        actions={
          <form action={lockCredentials}>
            <button
              type="submit"
              className="text-sm text-slate-100 hover:text-white transition-colors"
            >
              🔒 잠금
            </button>
          </form>
        }
      />
      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="mb-4">
          <h2 className="text-xl font-semibold text-gray-800">비밀번호 관리</h2>
          <p className="text-sm text-gray-700 mt-1">
            임대사 계정의 아이디/비밀번호를 변경하면 즉시 시스템 전체에
            반영됩니다.
          </p>
        </div>
        <CredentialsManager />
      </main>
    </div>
  )
}
