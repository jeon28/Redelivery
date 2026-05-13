'use server'
import { createSession, deleteSession } from '@/lib/session'
import { redirect } from 'next/navigation'

export async function login(
  _state: { error: string } | undefined,
  formData: FormData
) {
  const username = formData.get('username') as string
  const password = formData.get('password') as string

  if (
    username === process.env.APP_USER_ID &&
    password === process.env.APP_USER_PW
  ) {
    await createSession('admin')
    redirect('/dashboard')
  }

  return { error: '아이디 또는 비밀번호가 올바르지 않습니다.' }
}

export async function logout() {
  await deleteSession()
  redirect('/login')
}
