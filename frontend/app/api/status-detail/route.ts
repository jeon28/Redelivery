import { NextRequest, NextResponse } from 'next/server'
import { decrypt } from '@/lib/session'

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
