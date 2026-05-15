'use server'
import {
  createSession,
  deleteSession,
  createCredentialsUnlock,
  clearCredentialsUnlock,
  verifySession,
} from '@/lib/session'
import { authenticate, pinForOffice } from '@/lib/users'
import { redirect } from 'next/navigation'

export async function login(
  _state: { error: string } | undefined,
  formData: FormData
) {
  const username = formData.get('username') as string
  const password = formData.get('password') as string

  const office = authenticate(username, password)
  if (office) {
    await createSession(username, office)
    redirect('/dashboard')
  }

  return { error: '아이디 또는 비밀번호가 올바르지 않습니다.' }
}

export async function logout() {
  await deleteSession()
  redirect('/login')
}

export async function unlockCredentials(
  _state: { error: string } | undefined,
  formData: FormData
) {
  const pin = formData.get('pin') as string
  const { office } = await verifySession()
  const expected = pinForOffice(office)

  if (!expected) {
    return { error: '관리자 PIN이 설정되지 않았습니다.' }
  }
  if (pin === expected) {
    await createCredentialsUnlock()
    redirect('/dashboard/credentials')
  }
  return { error: 'PIN이 올바르지 않습니다.' }
}

export async function lockCredentials() {
  await clearCredentialsUnlock()
  redirect('/dashboard')
}
