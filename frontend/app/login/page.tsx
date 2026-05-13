import LoginForm from '@/components/LoginForm'

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-sm">
        <h1 className="text-2xl font-bold text-center text-gray-800 mb-1">
          반납컨테이너 조회 시스템
        </h1>
        <p className="text-center text-gray-400 text-sm mb-8">장금상선 · 흥아라인</p>
        <LoginForm />
      </div>
    </div>
  )
}
