import { verifySession } from '@/lib/session'
import EmailSettingTabs from '@/components/EmailSettingTabs'
import DashboardHeader from '@/components/DashboardHeader'

export default async function EmailSettingPage() {
  const { office } = await verifySession()

  return (
    <div className="min-h-screen bg-gray-50">
      <DashboardHeader office={office} active="email" />
      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-4">
          <h2 className="text-xl font-semibold text-gray-800">Email Setting</h2>
          <p className="text-sm text-gray-700 mt-1">
            현재 편집 중: <span className="font-semibold">{office} 사무소</span>
            {' · '}수정 사항은 이 사무소 계정에만 적용됩니다.
          </p>
        </div>

        <EmailSettingTabs office={office} />
      </main>
    </div>
  )
}
