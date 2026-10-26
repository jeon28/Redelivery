import 'server-only'
import { NextRequest, NextResponse } from 'next/server'
import { decrypt } from '@/lib/session'

// 스크래퍼(FastAPI) 프록시 공용 헬퍼 — 세션 확인 후 X-API-Key 를 붙여 전달.
export async function authed(req: NextRequest) {
  const cookie = req.cookies.get('session')?.value
  const session = await decrypt(cookie)
  return !!session?.userId
}

export async function proxyToScraper(
  req: NextRequest,
  path: string,
  init: { method?: string; headers?: Record<string, string>; body?: BodyInit } = {}
) {
  if (!(await authed(req)))
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })

  const url = process.env.RAILWAY_API_URL
  if (!url)
    return NextResponse.json({ error: 'RAILWAY_API_URL 미설정' }, { status: 500 })

  try {
    const res = await fetch(`${url}${path}`, {
      method: init.method ?? 'GET',
      headers: { 'X-API-Key': process.env.SCRAPER_API_KEY ?? '', ...init.headers },
      body: init.body,
      cache: 'no-store',
    })
    return NextResponse.json(await res.json(), { status: res.status })
  } catch {
    return NextResponse.json({ error: '스크래퍼 서버 연결 실패' }, { status: 502 })
  }
}
