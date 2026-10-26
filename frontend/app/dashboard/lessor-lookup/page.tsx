import { verifySession } from '@/lib/session'
import LessorLookupSettings from '@/components/LessorLookupSettings'
import DashboardHeader from '@/components/DashboardHeader'

export default async function LessorLookupPage() {
  const { office } = await verifySession()

  return (
    <div className="min-h-screen bg-gray-50">
      <DashboardHeader office={office} active="lookup" />
      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="mb-4">
          <h2 className="text-xl font-semibold text-gray-800">임대사 판별</h2>
          <p className="text-sm text-gray-700 mt-1">
            통합 조회에서 컨테이너 번호로 임대사를 찾을 때 쓰는 데이터입니다.
            반납 대장에 있는 번호가 우선이고, 없으면 접두어 표로 판별합니다.
          </p>
        </div>
        <LessorLookupSettings />
      </main>
    </div>
  )
}
