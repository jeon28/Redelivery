import { verifySession } from '@/lib/session'
import SearchForm from '@/components/SearchForm'
import DashboardHeader from '@/components/DashboardHeader'

export default async function MultiQueryPage() {
  const { office } = await verifySession()

  return (
    <div className="min-h-screen bg-gray-50">
      <DashboardHeader office={office} active="multi" />
      <main className="max-w-5xl mx-auto px-6 py-8">
        <SearchForm office={office} />
      </main>
    </div>
  )
}
