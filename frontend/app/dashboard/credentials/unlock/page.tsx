import { redirect } from 'next/navigation'
import { verifySession, verifyCredentialsUnlock } from '@/lib/session'
import UnlockForm from '@/components/UnlockForm'
import DashboardHeader from '@/components/DashboardHeader'

export default async function CredentialsUnlockPage() {
  const { office } = await verifySession()

  // 이미 잠금 해제된 상태라면 바로 관리 페이지로
  if (await verifyCredentialsUnlock()) {
    redirect('/dashboard/credentials')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <DashboardHeader office={office} active="credentials" />
      <main className="max-w-5xl mx-auto px-6 py-16">
        <UnlockForm />
      </main>
    </div>
  )
}
