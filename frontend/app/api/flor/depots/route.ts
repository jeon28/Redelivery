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

  const company = req.nextUrl.searchParams.get('company') ?? ''
  const region = req.nextUrl.searchParams.get('region') ?? ''
  if (!company || !region) {
    return NextResponse.json(
      { error: 'company / region 쿼리 파라미터가 필요합니다' },
      { status: 400 }
    )
  }

  const qs = new URLSearchParams({ company, region }).toString()
  try {
    const res = await fetch(`${scraperUrl()}/flor/depots?${qs}`, {
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
