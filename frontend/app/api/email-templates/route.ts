import { NextRequest, NextResponse } from 'next/server'
import { decrypt } from '@/lib/session'

async function authed(req: NextRequest) {
  const cookie = req.cookies.get('session')?.value
  const session = await decrypt(cookie)
  return !!session?.userId
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

  const office = req.nextUrl.searchParams.get('office') ?? ''
  const qs = office ? `?office=${encodeURIComponent(office)}` : ''

  try {
    const res = await fetch(`${scraperUrl()}/email-templates${qs}`, {
      headers: { 'X-API-Key': apiKey() },
      cache: 'no-store',
    })
    return NextResponse.json(await res.json(), { status: res.status })
  } catch {
    return NextResponse.json(
      { error: '스크래퍼 서버 연결 실패' },
      { status: 502 }
    )
  }
}
