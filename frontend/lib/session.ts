import 'server-only'
import { SignJWT, jwtVerify } from 'jose'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'

const secretKey = process.env.SESSION_SECRET!
const encodedKey = new TextEncoder().encode(secretKey)

export async function encrypt(payload: { userId: string; expiresAt: Date }) {
  return new SignJWT(payload)
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('7d')
    .sign(encodedKey)
}

export async function decrypt(session: string | undefined = '') {
  try {
    const { payload } = await jwtVerify(session, encodedKey, {
      algorithms: ['HS256'],
    })
    return payload
  } catch {
    return null
  }
}

export async function createSession(userId: string) {
  const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
  const session = await encrypt({ userId, expiresAt })
  const cookieStore = await cookies()
  cookieStore.set('session', session, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    expires: expiresAt,
    sameSite: 'lax',
    path: '/',
  })
}

export async function deleteSession() {
  const cookieStore = await cookies()
  cookieStore.delete('session')
}

export async function verifySession() {
  const cookieStore = await cookies()
  const cookie = cookieStore.get('session')?.value
  const session = await decrypt(cookie)
  if (!session?.userId) redirect('/login')
  return { userId: session.userId as string }
}

// ────────────────────────────────────────────────────────────────────
// Credentials page unlock (별도 PIN 인증, 짧은 만료 시간)
// ────────────────────────────────────────────────────────────────────

const UNLOCK_COOKIE = 'credentials_unlock'
const UNLOCK_TTL_MS = 10 * 60 * 1000  // 10분

export async function createCredentialsUnlock() {
  const expiresAt = new Date(Date.now() + UNLOCK_TTL_MS)
  const token = await new SignJWT({ unlocked: true, expiresAt })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime(expiresAt)
    .sign(encodedKey)

  const cookieStore = await cookies()
  cookieStore.set(UNLOCK_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    expires: expiresAt,
    sameSite: 'lax',
    path: '/',
  })
}

export async function verifyCredentialsUnlock(): Promise<boolean> {
  const cookieStore = await cookies()
  const token = cookieStore.get(UNLOCK_COOKIE)?.value
  if (!token) return false
  const payload = await decrypt(token)
  return !!payload?.unlocked
}

export async function clearCredentialsUnlock() {
  const cookieStore = await cookies()
  cookieStore.delete(UNLOCK_COOKIE)
}
