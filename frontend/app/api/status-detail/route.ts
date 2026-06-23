import { NextRequest, NextResponse } from 'next/server'
import { decrypt } from '@/lib/session'

// Status 단독 조회도 Playwright 기반이라 수십 초 소요. Vercel 함수 제한 상향.
// 60s = Hobby/Pro 공통 안전 상한.
export const maxDuration = 60

export async function POST(req: NextRequest) {
  const cookie = req.cookies.get('session')?.value
  const session = await decrypt(cookie)
  if (!session?.userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }

  const body = await req.json()
  const railwayUrl = process.env.RAILWAY_API_URL

  if (railwayUrl) {
    try {
      const res = await fetch(`${railwayUrl}/status-detail`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      return NextResponse.json(await res.json(), { status: res.status })
    } catch {
      return NextResponse.json(
        { error: 'Railway 서버 연결 실패' },
        { status: 500 }
      )
    }
  }

  return NextResponse.json(
    { error: 'RAILWAY_API_URL 미설정' },
    { status: 500 }
  )
}
