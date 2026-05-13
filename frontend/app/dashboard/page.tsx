import { verifySession } from '@/lib/session'
import { logout } from '@/app/actions/auth'
import SearchForm from '@/components/SearchForm'

export default async function DashboardPage() {
  await verifySession()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-slate-800 text-white px-6 py-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">반납컨테이너 조회 시스템</h1>
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
        <SearchForm />
      </main>
    </div>
  )
}
