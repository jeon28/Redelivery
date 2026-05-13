import { NextRequest, NextResponse } from 'next/server'
import { decrypt } from '@/lib/session'

async function authed(req: NextRequest) {
  const cookie = req.cookies.get('session')?.value
  const session = await decrypt(cookie)
  if (!session?.userId) return false

  // 비밀번호 관리 API는 unlock 쿠키도 필수
  const unlock = req.cookies.get('credentials_unlock')?.value
  const unlockPayload = await decrypt(unlock)
  return !!unlockPayload?.unlocked
}

function scraperUrl() {
  const url = process.env.RAILWAY_API_URL
  if (!url) throw new Error('RAILWAY_API_URL 미설정')
  return url
}

function apiKey() {
  return process.env.SCRAPER_API_KEY ?? ''
}

export async function GET(req: NextRequest) {
  if (!(await authed(req)))
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })

  try {
    const res = await fetch(`${scraperUrl()}/credentials`, {
      headers: { 'X-API-Key': apiKey() },
      cache: 'no-store',
    })
    return NextResponse.json(await res.json(), { status: res.status })
  } catch (e) {
    return NextResponse.json(
      { error: '스크래퍼 서버 연결 실패' },
      { status: 502 }
    )
  }
}

export async function POST(req: NextRequest) {
  if (!(await authed(req)))
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })

  const body = await req.json()
  try {
    const res = await fetch(`${scraperUrl()}/credentials`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey(),
      },
      body: JSON.stringify(body),
    })
    return NextResponse.json(await res.json(), { status: res.status })
  } catch (e) {
    return NextResponse.json(
      { error: '스크래퍼 서버 연결 실패' },
      { status: 502 }
    )
  }
}
