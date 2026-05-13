'use client'
import { useActionState } from 'react'
import { unlockCredentials } from '@/app/actions/auth'

export default function UnlockForm() {
  const [state, action, pending] = useActionState(unlockCredentials, undefined)

  return (
    <div className="max-w-sm mx-auto bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="text-center mb-4">
        <div className="w-12 h-12 mx-auto bg-amber-100 rounded-full flex items-center justify-center mb-3">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="w-6 h-6 text-amber-600"
          >
            <path
              fillRule="evenodd"
              d="M12 1.5a5.25 5.25 0 0 0-5.25 5.25v3a3 3 0 0 0-3 3v6.75a3 3 0 0 0 3 3h10.5a3 3 0 0 0 3-3v-6.75a3 3 0 0 0-3-3v-3c0-2.9-2.35-5.25-5.25-5.25Zm3.75 8.25v-3a3.75 3.75 0 1 0-7.5 0v3h7.5Z"
              clipRule="evenodd"
            />
          </svg>
        </div>
        <h3 className="font-semibold text-gray-800">관리자 PIN 입력</h3>
        <p className="text-sm text-gray-500 mt-1">
          비밀번호 관리 페이지는 별도의 PIN이 필요합니다.
        </p>
      </div>

      <form action={action} className="space-y-3">
        <input
          type="password"
          name="pin"
          autoFocus
          required
          placeholder="PIN"
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-center tracking-widest font-mono"
        />
        {state?.error && (
          <p className="text-red-600 text-sm text-center">{state.error}</p>
        )}
        <button
          type="submit"
          disabled={pending}
          className="w-full py-2 bg-slate-800 text-white rounded-md font-medium hover:bg-slate-900 disabled:opacity-50"
        >
          {pending ? '확인 중...' : '잠금 해제'}
        </button>
      </form>

      <p className="text-xs text-gray-400 text-center mt-4">
        잠금 해제 후 10분 동안 유효합니다.
      </p>
    </div>
  )
}
