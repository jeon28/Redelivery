import { verifySession } from '@/lib/session'
import SingleLookupForm from '@/components/SingleLookupForm'
import DashboardHeader from '@/components/DashboardHeader'

export default async function DashboardPage() {
  const { office } = await verifySession()

  return (
    <div className="min-h-screen bg-gray-50">
      <DashboardHeader office={office} active="single" />
      <main className="max-w-5xl mx-auto px-6 py-8">
        <SingleLookupForm office={office} />
      </main>
    </div>
  )
}
